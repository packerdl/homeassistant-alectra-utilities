from __future__ import annotations

import defusedxml.ElementTree as ET
import logging
from xml.etree.ElementTree import Element
from dataclasses import dataclass, field
from datetime import datetime, timezone

_LOGGER = logging.getLogger(__name__)

ESPI_NS = "http://naesb.org/espi"
ATOM_NS = "http://www.w3.org/2005/Atom"


@dataclass
class IntervalReading:
    start: datetime
    duration_seconds: int
    kwh: float
    cost_cad: float | None
    flow_direction: int = 1  # 1=delivered, 4=received, 19=net


@dataclass
class _ReadingTypeInfo:
    multiplier: int
    flow_direction: int
    accumulation_behaviour: int  # 1=cumulative, 4=delta


@dataclass
class UsageData:
    readings: list[IntervalReading] = field(default_factory=list)

    @property
    def delivered_intervals(self) -> list[IntervalReading]:
        """Hourly delta readings for energy delivered (flow_direction=1, duration > 0)."""
        return [r for r in self.readings
                if r.flow_direction == 1 and r.duration_seconds > 0]

    @property
    def register_reads(self) -> list[IntervalReading]:
        """Cumulative meter register snapshots (duration = 0)."""
        return [r for r in self.readings if r.duration_seconds == 0]

    @property
    def total_kwh(self) -> float:
        return sum(r.kwh for r in self.delivered_intervals)

    @property
    def latest_interval_kwh(self) -> float | None:
        intervals = self.delivered_intervals
        return intervals[-1].kwh if intervals else None

    @property
    def data_timestamp(self) -> datetime | None:
        intervals = self.delivered_intervals
        return intervals[-1].start if intervals else None

    @property
    def latest_register_kwh(self) -> float | None:
        reads = self.register_reads
        return reads[-1].kwh if reads else None


def parse_espi_xml(xml_text: str) -> UsageData:
    root = ET.fromstring(xml_text)
    reading_type_map = _build_reading_type_map(root)
    readings = _extract_readings(root, reading_type_map)
    readings.sort(key=lambda r: r.start)
    return UsageData(readings=readings)


def _build_reading_type_map(root: Element) -> dict[str, _ReadingTypeInfo]:
    """Build a map of ReadingType ID → metadata from all ReadingType entries."""
    rt_map: dict[str, _ReadingTypeInfo] = {}
    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        rt = entry.find(f".//{{{ESPI_NS}}}ReadingType")
        if rt is None:
            continue
        # Extract the ReadingType ID from <link rel="self" href="...ReadingType/{ID}">
        rt_id = None
        for link in entry.findall(f"{{{ATOM_NS}}}link"):
            if link.get("rel") == "self":
                href = link.get("href", "")
                if "/ReadingType/" in href:
                    rt_id = href.rsplit("/", 1)[-1]
                    break

        multiplier_elem = rt.find(f"{{{ESPI_NS}}}powerOfTenMultiplier")
        if multiplier_elem is not None:
            multiplier = int(multiplier_elem.text)
            if not (-9 <= multiplier <= 9):
                raise ValueError(
                    f"powerOfTenMultiplier {multiplier} out of valid ESPI range [-9, 9]"
                )
        else:
            _LOGGER.warning(
                "powerOfTenMultiplier not found in ReadingType; assuming 0 (Wh)"
            )
            multiplier = 0

        flow_elem = rt.find(f"{{{ESPI_NS}}}flowDirection")
        flow_direction = int(flow_elem.text) if flow_elem is not None else 1

        accum_elem = rt.find(f"{{{ESPI_NS}}}accumulationBehaviour")
        accumulation = int(accum_elem.text) if accum_elem is not None else 4

        info = _ReadingTypeInfo(
            multiplier=multiplier,
            flow_direction=flow_direction,
            accumulation_behaviour=accumulation,
        )
        if rt_id is not None:
            rt_map[rt_id] = info
        else:
            # No self link — store under a sentinel key so we still have the metadata
            rt_map["_default"] = info

    return rt_map


def _extract_readings(
    root: Element, reading_type_map: dict[str, _ReadingTypeInfo]
) -> list[IntervalReading]:
    readings: list[IntervalReading] = []

    # Fallback when no ReadingType metadata is present (simple XML)
    if not reading_type_map:
        _LOGGER.warning(
            "No ReadingType entries found in ESPI XML; assuming Wh (multiplier=0, flow=delivered)"
        )
        default_info = _ReadingTypeInfo(multiplier=0, flow_direction=1, accumulation_behaviour=4)
    else:
        default_info = next(iter(reading_type_map.values()))

    # Track current MeterReading context as we walk entries in order
    current_info: _ReadingTypeInfo = default_info

    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        # Check if this entry contains a MeterReading
        mr = entry.find(f".//{{{ESPI_NS}}}MeterReading")
        if mr is not None:
            # Extract ReadingType ID from <link rel="related" href="...ReadingType/{ID}">
            for link in entry.findall(f"{{{ATOM_NS}}}link"):
                if link.get("rel") == "related":
                    href = link.get("href", "")
                    if "/ReadingType/" in href:
                        rt_id = href.rsplit("/", 1)[-1]
                        if rt_id in reading_type_map:
                            current_info = reading_type_map[rt_id]
                        break
            continue

        # Check if this entry contains IntervalBlock(s)
        for block in entry.findall(f".//{{{ESPI_NS}}}IntervalBlock"):
            for idx, ir in enumerate(block.findall(f"{{{ESPI_NS}}}IntervalReading")):
                try:
                    readings.append(
                        _parse_interval_reading(ir, current_info.multiplier, current_info.flow_direction)
                    )
                except (ValueError, TypeError) as err:
                    raise ValueError(f"IntervalReading #{idx}: {err}") from err

    return readings


def _parse_interval_reading(
    ir: Element, multiplier: int, flow_direction: int = 1
) -> IntervalReading:
    tp = ir.find(f"{{{ESPI_NS}}}timePeriod")
    if tp is None:
        raise ValueError("IntervalReading missing required <timePeriod> element")
    start_elem = tp.find(f"{{{ESPI_NS}}}start")
    duration_elem = tp.find(f"{{{ESPI_NS}}}duration")
    value_elem = ir.find(f"{{{ESPI_NS}}}value")
    if start_elem is None or duration_elem is None or value_elem is None:
        raise ValueError("IntervalReading missing required child elements")
    start_ts = int(start_elem.text)
    duration = int(duration_elem.text)
    value_wh = int(value_elem.text) * (10**multiplier)
    kwh = value_wh / 1000.0

    cost_elem = ir.find(f"{{{ESPI_NS}}}cost")
    cost_cad = int(cost_elem.text) / 100_000.0 if cost_elem is not None else None

    return IntervalReading(
        start=datetime.fromtimestamp(start_ts, tz=timezone.utc),
        duration_seconds=duration,
        kwh=kwh,
        cost_cad=cost_cad,
        flow_direction=flow_direction,
    )
