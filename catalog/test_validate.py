"""Regression checks for mistakes that can silently corrupt catalog data."""
import copy
from pathlib import Path
import unittest

import yaml

from validate import UniqueLoader, check_ranges, validate


class CatalogValidationTests(unittest.TestCase):
    def setUp(self):
        self.data = {p.stem: yaml.load(p.read_text(), Loader=UniqueLoader)
                     for p in Path(__file__).parent.glob('*.yaml')}

    def test_catalog_matches_engine(self):
        self.assertIn('13 systems', validate(self.data))

    def test_rejects_unknown_component_and_wrong_season(self):
        for field, value in [('components', ['unknown_crop']), ('engine_seasons', ['segunda'])]:
            with self.subTest(field=field):
                data = copy.deepcopy(self.data)
                data['sistemas']['systems']['milho_verao'][field] = value
                with self.assertRaises(ValueError):
                    validate(data)

    def test_rejects_duplicate_yaml_keys(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate YAML key'):
            yaml.load('min: 1\nmin: 2\n', Loader=UniqueLoader)

    def test_rejects_invalid_ranges_and_dates(self):
        for value in [
            {'min': 3, 'max': 1, 'unit': 'days', 'source': 'https://example.org'},
            {'min': 1, 'max': 2, 'unit': 'days'},
            {'min': float('nan'), 'max': 2, 'unit': 'days', 'source': 'https://example.org'},
            {'planting_window': {'start': '31/02', 'end': '31/03', 'format': 'DD/MM',
                                 'use': 'informational', 'source': 'https://example.org', 'note': 'Example'}},
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                check_ranges(value)

    def test_rejects_unknown_template_fields(self):
        self.data['textos']['criteria']['renda'] = '{source} {crop.name}'
        with self.assertRaisesRegex(ValueError, 'Unsupported placeholder'):
            validate(self.data)

    def test_rejects_grain_oat_as_cover_crop(self):
        self.data['sistemas']['systems']['aveia']['components'] = ['aveia_branca']
        with self.assertRaisesRegex(ValueError, 'Oat cover-crop'):
            validate(self.data)


if __name__ == '__main__':
    unittest.main()