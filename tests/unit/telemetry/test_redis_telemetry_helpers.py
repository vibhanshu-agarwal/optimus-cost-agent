from __future__ import annotations

from decimal import Decimal

from tests.integration.telemetry.test_redis_telemetry_live import _retention_time_ms, _ts_info_mapping


def test_ts_info_mapping_accepts_flat_list():
    info = ["retentionTime", 2_592_000_000, "totalSamples", 1]

    mapping = _ts_info_mapping(info)

    assert mapping["retentionTime"] == 2_592_000_000
    assert _retention_time_ms(info) == 2_592_000_000


def test_ts_info_mapping_accepts_dict():
    info = {"retentionTime": 2_592_000_000, "totalSamples": 1}

    mapping = _ts_info_mapping(info)

    assert mapping["retentionTime"] == 2_592_000_000
    assert _retention_time_ms(info) == 2_592_000_000


def test_ts_range_sample_values_compare_via_decimal_str():
    sample_value = 0.003

    assert Decimal(str(sample_value)) == Decimal("0.003")
