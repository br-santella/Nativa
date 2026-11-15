"""Validate YAML contracts without importing engine geospatial dependencies.

Run: python catalog/validate.py (requires PyYAML).
"""
from __future__ import annotations

import ast
from datetime import datetime
import math
from pathlib import Path
from string import Formatter
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parent


class UniqueLoader(yaml.SafeLoader):
    """Reject duplicate keys instead of silently discarding earlier values."""


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        require(key not in result, f'Duplicate YAML key: {key}')
        result[key] = loader.construct_object(value_node)
    return result


def require(condition, message):
    if not condition:
        raise ValueError(message)


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def check_source(source, path):
    require(isinstance(source, str), f'Invalid source: {path}')
    url = urlparse(source)
    require(url.scheme == 'https' and bool(url.netloc), f'Invalid source URL: {path}')


def check_ranges(value, path='catalog'):
    if isinstance(value, dict):
        if 'min' in value or 'max' in value:
            require({'min', 'max', 'unit', 'source'} <= value.keys(), f'Incomplete range: {path}')
            low, high = value['min'], value['max']
            require(all(type(v) in (int, float) and math.isfinite(v) for v in (low, high)),
                    f'Invalid numeric range: {path}')
            require(low <= high, f'Reversed range: {path}')
            require(isinstance(value['unit'], str) and bool(value['unit'].strip()), f'Missing unit: {path}')
        if 'source' in value:
            check_source(value['source'], path)
        if 'planting_window' in value:
            window = value['planting_window']
            # Some species profiles contain qualitative windows only.
            if 'start' in window or 'end' in window:
                require({'start', 'end', 'format', 'use', 'source', 'note'} <= window.keys(),
                        f'Incomplete planting window: {path}')
                require(window['format'] == 'DD/MM' and window['use'] == 'informational',
                        f'Planting window must be informational and use DD/MM: {path}')
                for date in (window['start'], window['end']):
                    require(isinstance(date, str) and len(date) == 5, f'Invalid date: {path}')
                    datetime.strptime(f'{date}/2000', '%d/%m/%Y')
        for key, item in value.items():
            check_ranges(item, f'{path}.{key}')
    elif isinstance(value, list):
        for index, item in enumerate(value):
            check_ranges(item, f'{path}[{index}]')


def engine_contract():
    path = ROOT.parent / 'motor_field_shift/src/field_shift/app/engine.py'
    definitions = {n.targets[0].id: n.value for n in ast.parse(path.read_text()).body
                   if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
    return {
        'criteria': set(ast.literal_eval(definitions['CRITERIOS'])),
        'verao': {ast.literal_eval(k) for k in definitions['VERAO'].keys},
        'segunda': {ast.literal_eval(k) for k in definitions['SEGUNDA'].keys},
    }


def check_templates(texts, criteria):
    require(texts['locale'] == 'en', 'Templates must use English')
    require(set(texts['criteria']) == criteria, 'Template criterion IDs differ from engine')
    allowed = set('margin difference source score risk period crop minimum maximum unit context '
                  'start_date end_date field municipality fields system pending_research'.split())
    count = 0
    for section in ('criteria', 'triggers', 'referrals'):
        require(bool(texts[section]), f'Empty template section: {section}')
        for key, template in texts[section].items():
            require(isinstance(template, str) and bool(template.strip()), f'Empty template: {key}')
            fields = set()
            for _, field, spec, conversion in Formatter().parse(template):
                if field is not None:
                    require(field in allowed and not spec and conversion is None,
                            f'Unsupported placeholder: {section}.{key}: {field}')
                    fields.add(field)
            if section == 'criteria' or (section == 'triggers' and key not in ('missing_data', 'curation_pending')):
                require('source' in fields, f'Missing evidence source: {section}.{key}')
            template.format_map({field: 'example' for field in fields})
            count += 1
    return count


def validate(data=None):
    if data is None:
        data = {p.stem: yaml.load(p.read_text(), Loader=UniqueLoader) for p in ROOT.glob('*.yaml')}
    crops, systems = data['crops']['crops'], data['sistemas']['systems']
    vocabulary, labels = data['vocabulario'], data['labels']
    contract = engine_contract()
    check_ranges(data)
    require(set(vocabulary['criteria']) == set(labels['criteria']) == contract['criteria'],
            'Vocabulary/display criterion IDs differ from engine')
    require(labels['locale'] == 'en', 'Labels must use English')
    require(set(vocabulary['engine_seasons']) == set(labels['engine_seasons']) == {'verao', 'segunda'},
            'Engine season vocabulary or labels differ')
    for values in vocabulary.values():
        require(isinstance(values, list) and len(values) == len(set(values)), 'Duplicate or invalid vocabulary')
    for crop_id, crop in crops.items():
        require(crop['purpose'] in vocabulary['purposes'], f'Unknown purpose: {crop_id}')
        textures = crop['soil_requirements']['suitable_textures']['values']
        require(set(textures) <= set(vocabulary['textures']), f'Unknown texture: {crop_id}')
        machines = crop['infrastructure']['machinery']['values']
        require(set(machines) <= set(vocabulary['machinery']), f'Unknown machinery: {crop_id}')
    require(set(systems) == contract['verao'] | contract['segunda'], 'System IDs differ from engine')
    for system_id, system in systems.items():
        require(set(system['components']) <= set(crops), f'Unknown crop component: {system_id}')
        require(system['purpose'] in vocabulary['purposes'], f'Unknown purpose: {system_id}')
        require(system['status'] in vocabulary['curation_statuses'], f'Unknown status: {system_id}')
        expected = {season for season in ('verao', 'segunda') if system_id in contract[season]}
        require(set(system['engine_seasons']) == expected, f'Wrong engine season: {system_id}')
        if system['status'] == 'curation_pending':
            require(bool(system.get('pending_research')), f'Missing research gaps: {system_id}')
        require(bool(system['components']) or system['status'] in ('curation_pending', 'not_applicable'),
                f'Empty components without explanation: {system_id}')
    # Grain oat must not silently become the cover-crop reference.
    require(not systems['aveia']['components'], 'Oat cover-crop species still requires curation')
    # A second-season rate must not leak into the species or first-season profile.
    require('topdressing_fertilizer_rate' not in crops['milho']['soil_requirements']['nitrogen'],
            'Season-specific maize fertilizer rate must not be in the species profile')
    count = check_templates(data['textos'], contract['criteria'])
    return f'OK: {len(data)} YAML files, {len(crops)} crops, {len(systems)} systems, {count} English templates.'


if __name__ == '__main__':
    print(validate())