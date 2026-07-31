#!/usr/bin/env python3
"""Generate a bounded Vedic/Jyotish D1 fact payload.

This is deliberately a prototype-grade compatibility layer, not a Swiss
Ephemeris replacement. It uses the vendored MIT Astronomy Engine for tropical
planet positions, an explicitly declared linear Lahiri approximation, an
independently implemented horizon formula for Lagna, whole-sign houses, and the
mean lunar node. It omits Vargas, dashas, transits, yogas, strengths and
predictive timing.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine_common import (
    EngineError,
    atomic_write_json,
    emit_error,
    load_json,
    parse_naive_datetime,
    require_exact_single_chart_time,
    resolve_local_datetime_with_metadata,
    sha256_artifact,
    timezone_db_version,
    validate_location,
    validate_time_precision,
)


SCRIPT_DIR = Path(__file__).resolve().parent
VENDOR_DIR = SCRIPT_DIR / "vendor"
sys.path.insert(0, str(VENDOR_DIR))

from astronomy import astronomy as astro  # noqa: E402


ENGINE_NAME = "builtin-astronomy-engine-vedic-lite"
ENGINE_VERSION = "2.1.19+vedic-lite-beta.1"
ENGINE_LICENSE = (
    "MIT Astronomy Engine; original wrapper/formulas; vendored source and license included"
)
PRODUCT_START_YEAR = 1950
PRODUCT_END_YEAR = 2100
MAX_ABS_LATITUDE_DEG = 65.0
BOUNDARY_MARGIN_DEG = 0.05

SIGNS_ZH = (
    "白羊",
    "金牛",
    "双子",
    "巨蟹",
    "狮子",
    "处女",
    "天秤",
    "天蝎",
    "射手",
    "摩羯",
    "水瓶",
    "双鱼",
)
SIGNS_IAST = (
    "Mesha",
    "Vrishabha",
    "Mithuna",
    "Karka",
    "Simha",
    "Kanya",
    "Tula",
    "Vrischika",
    "Dhanu",
    "Makara",
    "Kumbha",
    "Meena",
)
NAKSHATRAS = (
    "Ashwini",
    "Bharani",
    "Krittika",
    "Rohini",
    "Mrigashira",
    "Ardra",
    "Punarvasu",
    "Pushya",
    "Ashlesha",
    "Magha",
    "Purva Phalguni",
    "Uttara Phalguni",
    "Hasta",
    "Chitra",
    "Swati",
    "Vishakha",
    "Anuradha",
    "Jyeshtha",
    "Mula",
    "Purva Ashadha",
    "Uttara Ashadha",
    "Shravana",
    "Dhanishtha",
    "Shatabhisha",
    "Purva Bhadrapada",
    "Uttara Bhadrapada",
    "Revati",
)
NAKSHATRA_LORDS = (
    "Ketu",
    "Venus",
    "Sun",
    "Moon",
    "Mars",
    "Rahu",
    "Jupiter",
    "Saturn",
    "Mercury",
)
CLASSICAL_BODIES = (
    ("sun", astro.Body.Sun),
    ("moon", astro.Body.Moon),
    ("mercury", astro.Body.Mercury),
    ("venus", astro.Body.Venus),
    ("mars", astro.Body.Mars),
    ("jupiter", astro.Body.Jupiter),
    ("saturn", astro.Body.Saturn),
)
NAKSHATRA_SPAN_DEG = 360.0 / 27.0
PADA_SPAN_DEG = NAKSHATRA_SPAN_DEG / 4.0

# Official Swiss Ephemeris documentation publishes Lahiri values at these two
# epochs. The Beta model linearly interpolates/extrapolates their difference.
# It is intentionally named as an approximation and must not be represented as
# Swiss Ephemeris-compatible.
LAHIRI_1950_DEG = 23 + 9 / 60 + 31.2539 / 3600
LAHIRI_1990_DEG = 23 + 43 / 60 + 2.6259 / 3600
LAHIRI_LINEAR_RATE_DEG_PER_YEAR = (LAHIRI_1990_DEG - LAHIRI_1950_DEG) / 40.0
LAHIRI_1950_TT_DAYS_FROM_J2000 = -18262.5


def artifact_hash() -> str:
    return sha256_artifact(
        [
            Path(__file__).resolve(),
            SCRIPT_DIR / "engine_common.py",
            VENDOR_DIR / "astronomy",
            VENDOR_DIR / "LICENSE.astronomy-engine.txt",
        ],
        SCRIPT_DIR,
    )


def _normalize(longitude: float) -> float:
    return longitude % 360.0


def _distance_to_grid(longitude: float, span: float) -> float:
    remainder = _normalize(longitude) % span
    return min(remainder, span - remainder)


def _lahiri_linear_beta(astro_time: Any) -> float:
    julian_years = (
        astro_time.tt - LAHIRI_1950_TT_DAYS_FROM_J2000
    ) / 365.2425
    return LAHIRI_1950_DEG + julian_years * LAHIRI_LINEAR_RATE_DEG_PER_YEAR


def _mean_lunar_node_tropical(astro_time: Any) -> float:
    """Mean ascending lunar node, using the conventional polynomial in TT."""
    centuries = astro_time.tt / 36525.0
    longitude = (
        125.0445479
        - 1934.1362891 * centuries
        + 0.0020754 * centuries**2
        + centuries**3 / 467441.0
        - centuries**4 / 60616000.0
    )
    return _normalize(longitude)


def _tropical_ascendant(
    astro_time: Any,
    latitude_deg: float,
    longitude_deg: float,
) -> float:
    """Return the eastern ecliptic/horizon intersection in ECT longitude."""
    local_sidereal_deg = _normalize(
        astro.SiderealTime(astro_time) * 15.0 + longitude_deg
    )
    # Astronomy Engine exposes true obliquity of date on the pinned Time object.
    obliquity_deg = astro_time._etilt().tobl
    theta = math.radians(local_sidereal_deg)
    epsilon = math.radians(obliquity_deg)
    latitude = math.radians(latitude_deg)
    y_value = -math.cos(theta)
    x_value = math.sin(theta) * math.cos(epsilon) + math.tan(latitude) * math.sin(
        epsilon
    )
    western_intersection = _normalize(math.degrees(math.atan2(y_value, x_value)))
    return _normalize(western_intersection + 180.0)


def _placement(
    tropical_longitude: float,
    ayanamsa_deg: float,
    ascendant_sign_index: int,
    *,
    source: str,
) -> dict[str, Any]:
    sidereal_longitude = _normalize(tropical_longitude - ayanamsa_deg)
    sign_index = int(sidereal_longitude // 30.0)
    return {
        "tropical_longitude_deg": round(tropical_longitude, 6),
        "sidereal_longitude_deg": round(sidereal_longitude, 6),
        "sign": SIGNS_ZH[sign_index],
        "sign_iast": SIGNS_IAST[sign_index],
        "degree_in_sign": round(sidereal_longitude % 30.0, 6),
        "whole_sign_house": (sign_index - ascendant_sign_index) % 12 + 1,
        "source": source,
        "frame": "geocentric true ecliptic of date, sidereal Lahiri-linear Beta",
    }


def _moon_nakshatra(sidereal_longitude: float) -> dict[str, Any]:
    normalized = _normalize(sidereal_longitude)
    index = int(normalized // NAKSHATRA_SPAN_DEG)
    within = normalized - index * NAKSHATRA_SPAN_DEG
    pada = int(within // PADA_SPAN_DEG) + 1
    return {
        "index": index + 1,
        "name": NAKSHATRAS[index],
        "pada": pada,
        "lord": NAKSHATRA_LORDS[index % len(NAKSHATRA_LORDS)],
        "degree_within_nakshatra": round(within, 6),
    }


def _assert_boundary_margin(
    ascendant_sidereal: float,
    placements: dict[str, dict[str, Any]],
) -> float:
    sign_values = [ascendant_sidereal] + [
        item["sidereal_longitude_deg"] for item in placements.values()
    ]
    sign_margin = min(_distance_to_grid(value, 30.0) for value in sign_values)
    moon = placements["moon"]["sidereal_longitude_deg"]
    nakshatra_margin = _distance_to_grid(moon, NAKSHATRA_SPAN_DEG)
    pada_margin = _distance_to_grid(moon, PADA_SPAN_DEG)
    minimum = min(sign_margin, nakshatra_margin, pada_margin)
    if minimum < BOUNDARY_MARGIN_DEG:
        raise EngineError(
            "E_SIDEREAL_BOUNDARY_UNCERTAINTY",
            (
                "至少一个星座、月宿或 Pada 结果距离边界不足 "
                f"{BOUNDARY_MARGIN_DEG:.2f}°；Beta 岁差模型不应在此处硬判。"
            ),
            ["local_datetime", "location"],
        )
    return minimum


def generate(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("calendar", "gregorian") != "gregorian":
        raise EngineError(
            "E_INVALID_INPUT",
            "印度占星轻体验只接受 gregorian 输入。",
            ["calendar"],
        )
    naive = parse_naive_datetime(payload.get("local_datetime"))
    if not PRODUCT_START_YEAR <= naive.year <= PRODUCT_END_YEAR:
        raise EngineError(
            "E_EPHEMERIS_RANGE",
            (
                "印度占星轻体验 Beta 的产品验收范围是 "
                f"{PRODUCT_START_YEAR}—{PRODUCT_END_YEAR} 年。"
            ),
            ["local_datetime"],
        )
    aware, timezone_detail, timezone_resolution = resolve_local_datetime_with_metadata(
        naive,
        payload.get("timezone"),
        payload.get("fold"),
        payload.get("historical_utc_offset"),
    )
    location = validate_location(payload.get("location"))
    if abs(location["latitude"]) > MAX_ABS_LATITUDE_DEG:
        raise EngineError(
            "E_ASCENDANT_LATITUDE_RANGE",
            (
                "印度占星轻体验 Beta 暂不计算绝对纬度高于 "
                f"{MAX_ABS_LATITUDE_DEG:.1f}° 的上升点。"
            ),
            ["location.latitude"],
        )
    time_precision = require_exact_single_chart_time(
        validate_time_precision(payload.get("time_precision"))
    )
    utc_value = aware.astimezone(timezone.utc)
    astro_time = astro.Time.Make(
        utc_value.year,
        utc_value.month,
        utc_value.day,
        utc_value.hour,
        utc_value.minute,
        utc_value.second + utc_value.microsecond / 1_000_000,
    )
    ayanamsa_deg = _lahiri_linear_beta(astro_time)
    ascendant_tropical = _tropical_ascendant(
        astro_time,
        location["latitude"],
        location["longitude"],
    )
    ascendant_sidereal = _normalize(ascendant_tropical - ayanamsa_deg)
    ascendant_sign_index = int(ascendant_sidereal // 30.0)

    planets: dict[str, dict[str, Any]] = {}
    for name, body in CLASSICAL_BODIES:
        coordinates = astro.Ecliptic(astro.GeoVector(body, astro_time, True))
        planets[name] = _placement(
            coordinates.elon % 360.0,
            ayanamsa_deg,
            ascendant_sign_index,
            source="Astronomy Engine 2.1.19 geocentric ECT",
        )
        planets[name]["tropical_latitude_deg"] = round(coordinates.elat, 6)

    rahu_tropical = _mean_lunar_node_tropical(astro_time)
    planets["rahu"] = _placement(
        rahu_tropical,
        ayanamsa_deg,
        ascendant_sign_index,
        source="mean lunar ascending node polynomial (TT)",
    )
    planets["ketu"] = _placement(
        _normalize(rahu_tropical + 180.0),
        ayanamsa_deg,
        ascendant_sign_index,
        source="mean lunar descending node, opposite Rahu",
    )
    minimum_margin = _assert_boundary_margin(ascendant_sidereal, planets)

    normalized_input = {
        "calendar": "gregorian",
        "local_datetime": naive.isoformat(),
        "timezone": payload["timezone"],
        **timezone_resolution,
        "location": location,
        "time_precision": time_precision,
    }
    return {
        "schema_version": "1.0.0",
        "engine": {
            "name": ENGINE_NAME,
            "version": ENGINE_VERSION,
            "artifact_hash": artifact_hash(),
            "license": ENGINE_LICENSE,
        },
        "input": normalized_input,
        "chart_system": "vedic",
        "chart": {
            "coverage": "d1-classical-planets-mean-nodes-lagna-whole-sign-nakshatra-beta",
            "zodiac": "sidereal",
            "ayanamsa": {
                "model": "lahiri-linear-beta-1950-1990",
                "degrees": round(ayanamsa_deg, 8),
                "reference_values_deg": {
                    "1950-01-01-tt": round(LAHIRI_1950_DEG, 8),
                    "1990-01-01-tt": round(LAHIRI_1990_DEG, 8),
                },
                "rate_deg_per_julian_year": round(
                    LAHIRI_LINEAR_RATE_DEG_PER_YEAR, 10
                ),
                "swiss_ephemeris_compatible": False,
            },
            "house_system": "whole-sign",
            "ascendant": {
                "tropical_longitude_deg": round(ascendant_tropical, 6),
                "sidereal_longitude_deg": round(ascendant_sidereal, 6),
                "sign": SIGNS_ZH[ascendant_sign_index],
                "sign_iast": SIGNS_IAST[ascendant_sign_index],
                "degree_in_sign": round(ascendant_sidereal % 30.0, 6),
                "frame": "eastern ecliptic/horizon intersection of date",
            },
            "planets": planets,
            "moon_nakshatra": _moon_nakshatra(
                planets["moon"]["sidereal_longitude_deg"]
            ),
            "divisional_charts": None,
            "dashas": None,
            "transits": None,
        },
        "boundary_checks": [
            {"name": "timezone-resolved", "status": "pass", "detail": timezone_detail},
            {
                "name": "location-resolved",
                "status": "pass",
                "detail": (
                    f"{location['label']}; {location['latitude']},"
                    f"{location['longitude']}; source={location['source']}"
                ),
            },
            {
                "name": "time-precision-propagated",
                "status": "pass",
                "detail": json.dumps(time_precision, ensure_ascii=False),
            },
            {
                "name": "ephemeris-engine-verified",
                "status": "pass",
                "detail": "Vendored MIT Astronomy Engine 2.1.19; artifact hash attached",
            },
            {
                "name": "ephemeris-range",
                "status": "pass",
                "detail": (
                    f"Product-validated input gate: {PRODUCT_START_YEAR}-01-01 "
                    f"through {PRODUCT_END_YEAR}-12-31"
                ),
            },
            {
                "name": "ayanamsa-model-declared",
                "status": "pass",
                "detail": (
                    "lahiri-linear-beta-1950-1990; declared approximation; "
                    "not Swiss Ephemeris-compatible"
                ),
            },
            {
                "name": "sidereal-boundary-margin",
                "status": "pass",
                "detail": (
                    f"minimum relevant sign/nakshatra/pada margin="
                    f"{minimum_margin:.6f}°; required >= {BOUNDARY_MARGIN_DEG:.2f}°"
                ),
            },
            {
                "name": "ascendant-latitude-range",
                "status": "pass",
                "detail": (
                    f"abs(latitude)={abs(location['latitude']):.6f}°; "
                    f"required <= {MAX_ABS_LATITUDE_DEG:.1f}°"
                ),
            },
        ],
        "provenance": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "timezone_db_version": timezone_db_version(),
            "ephemeris_version": "Astronomy Engine 2.1.19",
            "ayanamsa_model_version": "lahiri-linear-beta-1950-1990/v1",
            "ascendant_formula_version": "eastern-horizon-atan2/v1",
            "utc_datetime": utc_value.isoformat(),
        },
        "warnings": [
            "这是印度占星轻体验 Beta：Lahiri 岁差为公开锚点的线性近似，不等同于 Swiss Ephemeris。",
            "只含 D1、古典七曜、平均交点 Rahu/Ketu、Lagna、整宫制和月宿；不含 D9、Dasha、行运、瑜伽、强弱或择时。",
            "占星解释属于传统文化框架，不是经科学验证的预测。",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a bounded Vedic Lite D1 fact payload."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = generate(load_json(args.input))
        atomic_write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps(emit_error(exc), ensure_ascii=False, indent=2), file=sys.stderr)
        return 2 if isinstance(exc, EngineError) else 3


if __name__ == "__main__":
    raise SystemExit(main())
