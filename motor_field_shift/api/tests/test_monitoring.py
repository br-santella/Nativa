from datetime import date, timedelta
import requests
import pytest
from field_shift import monitoring as m

TODAY = date(2026, 11, 15)


def test_power_full_windows_zero_rain_and_missing_day(monkeypatch):
    days = [(TODAY-timedelta(days=n)).strftime('%Y%m%d') for n in range(1, 76)]
    payload = {'parameters': {'T2M': {'units': 'C'}, 'PRECTOTCORR': {'units': 'mm/day'}},
               'properties': {'parameter': {'T2M': dict.fromkeys(days, 20), 'PRECTOTCORR': dict.fromkeys(days, 0)}}}
    monkeypatch.setattr(m, '_get', lambda *a, **kw: payload)
    result = m.power(0, 0, TODAY)
    assert result['temperature']['value'] == 20
    assert result['temperature']['delta'] == 0
    assert result['precipitation']['value'] == 0
    assert result['precipitation']['delta'] is None  # never divide by zero
    payload['properties']['parameter']['PRECTOTCORR'][days[4]] = -999
    assert m.power(0, 0, TODAY)['precipitation']['value'] is None
    assert m.power(0, 0, TODAY)['temperature']['value'] == 20


def test_soil_units_and_percentage_points(monkeypatch):
    data = {'daily_units': {'soil_moisture_0_to_7cm_mean': 'm³/m³'}, 'daily': {'time': ['2026-11-01','2026-11-08'], 'soil_moisture_0_to_7cm_mean': [.3,.4]}}
    monkeypatch.setattr(m, '_get', lambda *a, **kw: data)
    result = m.soil(0, 0, TODAY)['moisture']
    assert result['value'] == 40
    assert result['delta'] == 10
    data['daily_units']['soil_moisture_0_to_7cm_mean'] = '%'
    with pytest.raises(ValueError):
        m.soil(0, 0, TODAY)


def _ndvi_rows(values):
    rows = []
    for day, (value, qa) in values.items():
        for band, raw in [('250m_16_days_NDVI', value), ('250m_16_days_pixel_reliability', qa)]:
            rows.append({'calendar_date': day, 'band': band, 'data': [raw]})
    return rows


@pytest.fixture
def ndvi_cache(tmp_path, monkeypatch):
    from field_shift.context import _base
    monkeypatch.setattr(_base, 'CACHE_DIR', tmp_path)
    return tmp_path


def test_ndvi_quality_mask_keeps_negative_values(monkeypatch, ndvi_cache):
    # 2026-11-01 is too recent (within 16 days) and must be ignored.
    rows = _ndvi_rows({'2026-09-14': (-1000, 0), '2026-09-30': (8000, 3), '2026-10-16': (5000, 1), '2026-11-01': (9000, 0)})
    calls = []
    monkeypatch.setattr(m, '_get', lambda url, **kw: calls.append((url, kw)) or {'subset': rows})
    result = m.vegetation(0, 0, TODAY)['vegetation']
    assert result['value'] == .5
    assert [p['value'] for p in result['series']] == [-.1, None, .5]
    assert result['delta'] is None  # no comparison across a cloudy composite
    assert len(calls) == 1 and calls[0][0].endswith('/subset')  # no separate /dates request
    assert calls[0][1]['startDate'] == 'A2026225' and calls[0][1]['endDate'] == 'A2026305'


def test_modis_composite_dates():
    assert m._modis_date(date(2026, 1, 1)) == 'A2026001'
    assert m._modis_date(date(2026, 1, 17)) == 'A2026017'
    assert m._modis_date(date(2026, 12, 31)) == 'A2026353'


def test_ndvi_fresh_cache_skips_provider(monkeypatch, ndvi_cache):
    rows = _ndvi_rows({'2026-10-16': (6000, 0)})
    calls = []
    monkeypatch.setattr(m, '_get', lambda url, **kw: calls.append(url) or {'subset': rows})
    first = m.vegetation(-24.95, -53.45, TODAY)
    second = m.vegetation(-24.95, -53.45, TODAY)
    assert first == second and first['vegetation']['value'] == .6
    assert len(calls) == 1


def test_ndvi_expired_cache_covers_outage(monkeypatch, ndvi_cache):
    monkeypatch.setattr(m, '_get', lambda url, **kw: {'subset': _ndvi_rows({'2026-10-16': (6000, 0)})})
    m.vegetation(-24.95, -53.45, TODAY)
    monkeypatch.setattr(m, 'NDVI_CACHE_TTL', 0)
    def timeout(*a, **kw): raise requests.ReadTimeout()
    monkeypatch.setattr(m, '_get', timeout)
    assert m.vegetation(-24.95, -53.45, TODAY)['vegetation']['value'] == .6
    # Only cloudy composites: keep the last valid reading instead of an empty card.
    monkeypatch.setattr(m, '_get', lambda url, **kw: {'subset': _ndvi_rows({'2026-10-16': (6000, 3)})})
    assert m.vegetation(-24.95, -53.45, TODAY)['vegetation']['value'] == .6
    # Without any cache the outage still propagates (monitor() isolates it).
    with pytest.raises(ValueError):
        m.vegetation(10, 10, TODAY)


def test_provider_outage_is_isolated(monkeypatch):
    def fail(*args): raise requests.Timeout()
    monkeypatch.setattr(m, 'power', fail)
    monkeypatch.setattr(m, 'soil', lambda *a: {'moisture': {'value': 42}})
    monkeypatch.setattr(m, 'vegetation', fail)
    result = m.monitor(-24.81,-53.55)
    assert result['indicators']['moisture']['value'] == 42
    assert result['indicators']['temperature']['value'] is None
    assert result['indicators']['vegetation']['series'] == []


def test_monitoring_endpoint_validates_point(client, monkeypatch):
    monkeypatch.setattr(m, 'monitor', lambda lat,lon: {'point': {'lat':lat,'lon':lon}, 'indicators': {}})
    assert client.get('/v1/monitoramento?lat=-24.81&lon=-53.55').json()['point']['lat'] == -24.81
    assert client.get('/v1/monitoramento?lat=91&lon=0').status_code == 422
    assert client.get('/v1/monitoramento?lat=nan&lon=0').status_code == 422
