from datetime import datetime, timezone
from pathlib import Path
import pytest
from custom_components.alectra_utilities.parser import parse_espi_xml, UsageData

FIXTURE_XML = (Path(__file__).parent / "fixtures" / "sample_espi.xml").read_text()

REAL_FIXTURE = Path(__file__).parent / "fixtures" / "real_espi.xml"


def test_parse_returns_usage_data():
    result = parse_espi_xml(FIXTURE_XML)
    assert isinstance(result, UsageData)


def test_parse_reading_count():
    result = parse_espi_xml(FIXTURE_XML)
    assert len(result.readings) == 3  # 2 hourly + 1 register


def test_parse_first_reading_kwh():
    result = parse_espi_xml(FIXTURE_XML)
    first = result.delivered_intervals[0]
    assert first.kwh == pytest.approx(0.5)


def test_parse_second_reading_kwh():
    result = parse_espi_xml(FIXTURE_XML)
    second = result.delivered_intervals[1]
    assert second.kwh == pytest.approx(0.75)


def test_parse_first_reading_timestamp():
    result = parse_espi_xml(FIXTURE_XML)
    first = result.delivered_intervals[0]
    assert first.start == datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def test_parse_readings_sorted_by_time():
    result = parse_espi_xml(FIXTURE_XML)
    starts = [r.start for r in result.readings]
    assert starts == sorted(starts)


def test_parse_cost_present():
    result = parse_espi_xml(FIXTURE_XML)
    intervals = result.delivered_intervals
    assert intervals[0].cost_cad == pytest.approx(0.075)
    assert intervals[1].cost_cad == pytest.approx(0.1125)


def test_parse_total_kwh():
    result = parse_espi_xml(FIXTURE_XML)
    assert result.total_kwh == pytest.approx(1.25)


def test_parse_latest_interval_kwh():
    result = parse_espi_xml(FIXTURE_XML)
    assert result.latest_interval_kwh == pytest.approx(0.75)


def test_parse_no_cost_when_absent():
    xml_no_cost = FIXTURE_XML.replace("<cost>7500</cost>", "").replace("<cost>11250</cost>", "")
    result = parse_espi_xml(xml_no_cost)
    assert all(r.cost_cad is None for r in result.delivered_intervals)


def test_parse_power_of_ten_multiplier():
    """Multiplier of 3 means values are in kWh already (kilo-Wh), so 500 kWh."""
    xml_kilo = FIXTURE_XML.replace(
        "<powerOfTenMultiplier>0</powerOfTenMultiplier>",
        "<powerOfTenMultiplier>3</powerOfTenMultiplier>",
    )
    result = parse_espi_xml(xml_kilo)
    assert result.delivered_intervals[0].kwh == pytest.approx(500.0)


def test_parse_latest_interval_kwh_empty():
    """latest_interval_kwh returns None when there are no delivered intervals."""
    data = UsageData(readings=[])
    assert data.latest_interval_kwh is None


def test_parse_empty_feed_returns_empty_readings():
    empty_xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <id>urn:uuid:empty</id>
</feed>"""
    result = parse_espi_xml(empty_xml)
    assert result.readings == []
    assert result.total_kwh == 0.0


def test_parse_missing_time_period_raises():
    xml = FIXTURE_XML.replace("<timePeriod>", "<xTimePeriod>").replace("</timePeriod>", "</xTimePeriod>")
    with pytest.raises(ValueError, match="timePeriod"):
        parse_espi_xml(xml)


def test_parse_missing_child_elements_raises():
    xml = FIXTURE_XML.replace("<start>1735689600</start>", "", 1)
    with pytest.raises(ValueError, match="required child elements"):
        parse_espi_xml(xml)


def test_parse_power_of_ten_out_of_range_raises():
    xml = FIXTURE_XML.replace(
        "<powerOfTenMultiplier>0</powerOfTenMultiplier>",
        "<powerOfTenMultiplier>99</powerOfTenMultiplier>",
    )
    with pytest.raises(ValueError, match="out of valid ESPI range"):
        parse_espi_xml(xml)


def test_parse_flow_direction_on_readings():
    result = parse_espi_xml(FIXTURE_XML)
    for r in result.delivered_intervals:
        assert r.flow_direction == 1
    for r in result.register_reads:
        assert r.flow_direction == 1


def test_parse_register_reads_separated():
    result = parse_espi_xml(FIXTURE_XML)
    assert len(result.delivered_intervals) == 2
    assert len(result.register_reads) == 1
    assert result.register_reads[0].duration_seconds == 0
    assert result.register_reads[0].kwh == pytest.approx(50.0)
    assert result.latest_register_kwh == pytest.approx(50.0)


@pytest.mark.skipif(
    not REAL_FIXTURE.exists(),
    reason="Real fixture absent — run sidecar to capture real_espi.xml first",
)
def test_parse_real_xml_separates_meter_types():
    data = parse_espi_xml(REAL_FIXTURE.read_text())
    # Delivered intervals should be hourly readings only (duration=3600)
    for r in data.delivered_intervals:
        assert r.duration_seconds == 3600
        assert r.flow_direction == 1
    # Register reads should have duration=0
    for r in data.register_reads:
        assert r.duration_seconds == 0
    # Should have 72 delivered intervals (3 days x 24 hours) and 3 register reads
    assert len(data.delivered_intervals) == 72
    assert len(data.register_reads) == 3
    # Latest register should be a large cumulative value
    assert data.latest_register_kwh > 100_000
    # Total delivered should be much smaller than register reads
    assert data.total_kwh < data.latest_register_kwh
    # Latest interval should be a small hourly value
    assert data.latest_interval_kwh < 10
