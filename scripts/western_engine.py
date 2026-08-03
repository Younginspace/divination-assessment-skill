#!/usr/bin/env python3
"""Generate basic tropical planetary signs/aspects with Astronomy Engine.

This deliberately omits houses and the Ascendant. Those require a separately
reviewed house-system implementation or a commercially licensed ephemeris stack.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from datetime import timezone, datetime
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


ENGINE_NAME = "builtin-astronomy-engine-basic"
ENGINE_VERSION = "2.1.19+wrapper.1"
ENGINE_LICENSE = "MIT; vendored source and license included"
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
BODIES = (
    ("sun", astro.Body.Sun),
    ("moon", astro.Body.Moon),
    ("mercury", astro.Body.Mercury),
    ("venus", astro.Body.Venus),
    ("mars", astro.Body.Mars),
    ("jupiter", astro.Body.Jupiter),
    ("saturn", astro.Body.Saturn),
    ("uranus", astro.Body.Uranus),
    ("neptune", astro.Body.Neptune),
    ("pluto", astro.Body.Pluto),
)
ASPECTS = (
    ("conjunction", 0.0, 8.0),
    ("sextile", 60.0, 5.0),
    ("square", 90.0, 7.0),
    ("trine", 120.0, 7.0),
    ("opposition", 180.0, 8.0),
)


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


def _signed_separation(first: float, second: float) -> float:
    return (second - first + 180.0) % 360.0 - 180.0


def _aspects(planets: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for first, second in itertools.combinations(planets, 2):
        separation = abs(
            _signed_separation(
                planets[first]["longitude_deg"],
                planets[second]["longitude_deg"],
            )
        )
        matches = [
            (name, exact, orb, abs(separation - exact))
            for name, exact, orb in ASPECTS
            if abs(separation - exact) <= orb
        ]
        if matches:
            name, exact, allowed_orb, delta = min(matches, key=lambda item: item[3])
            result.append(
                {
                    "body_a": first,
                    "body_b": second,
                    "aspect": name,
                    "separation_deg": round(separation, 6),
                    "exact_angle_deg": exact,
                    "orb_deg": round(delta, 6),
                    "allowed_orb_deg": allowed_orb,
                }
            )
    return result


def generate(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("calendar", "gregorian") != "gregorian":
        raise EngineError(
            "E_INVALID_INPUT",
            "西洋基础星历输入只接受 gregorian。",
            ["calendar"],
        )
    naive = parse_naive_datetime(payload.get("local_datetime"))
    if not 1800 <= naive.year <= 2200:
        raise EngineError(
            "E_EPHEMERIS_RANGE",
            "内置西洋基础引擎的产品验收范围是 1800—2200 年。",
            ["local_datetime"],
        )
    aware, timezone_detail, timezone_resolution = resolve_local_datetime_with_metadata(
        naive,
        payload.get("timezone"),
        payload.get("fold"),
        payload.get("historical_utc_offset"),
    )
    location = validate_location(payload.get("location"))
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
    planets: dict[str, dict[str, Any]] = {}
    for name, body in BODIES:
        coordinates = astro.Ecliptic(astro.GeoVector(body, astro_time, True))
        longitude = coordinates.elon % 360.0
        sign_index = int(longitude // 30)
        planets[name] = {
            "longitude_deg": round(longitude, 6),
            "latitude_deg": round(coordinates.elat, 6),
            "sign": SIGNS_ZH[sign_index],
            "degree_in_sign": round(longitude % 30.0, 6),
            "frame": "geocentric true ecliptic of date (ECT), tropical",
        }
    normalized_input = {
        "calendar": "gregorian",
        "local_datetime": naive.isoformat(),
        "timezone": payload["timezone"],
        **timezone_resolution,
        "location": location,
        "time_precision": time_precision,
    }
    warnings = [
        "本版本只计算热带黄道行星位置、星座和主要相位，不计算上升点或宫位。",
        "占星解释属于传统文化框架，不是经科学验证的预测。",
    ]
    return {
        "schema_version": "1.0.0",
        "engine": {
            "name": ENGINE_NAME,
            "version": ENGINE_VERSION,
            "artifact_hash": artifact_hash(),
            "license": ENGINE_LICENSE,
        },
        "input": normalized_input,
        "chart_system": "western",
        "chart": {
            "coverage": "planets-signs-aspects-no-houses",
            "zodiac": "tropical",
            "planets": planets,
            "aspects": _aspects(planets),
            "houses": None,
            "ascendant": None,
        },
        "boundary_checks": [
            {"name": "timezone-resolved", "status": "pass", "detail": timezone_detail},
            {
                "name": "location-resolved",
                "status": "pass",
                "detail": (
                    f"{location['label']}; {location['latitude']},"
                    f"{location['longitude']}; source={location['source']}; "
                    "基础地心盘不使用地点计算宫位"
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
                "detail": "Vendored Astronomy Engine 2.1.19; artifact hash attached",
            },
            {
                "name": "ephemeris-range",
                "status": "pass",
                "detail": "Product-validated input gate: 1800-01-01 through 2200-12-31",
            },
        ],
        "provenance": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "timezone_db_version": timezone_db_version(),
            "ephemeris_version": "Astronomy Engine 2.1.19",
            "utc_datetime": utc_value.isoformat(),
        },
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a bundled basic western-ephemeris fact payload."
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
