#!/usr/bin/env python3
"""Generate an allowlist-ready Bazi fact payload with vendored lunar-python."""

from __future__ import annotations

import argparse
import json
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

from lunar_python import Lunar, Solar  # noqa: E402


ENGINE_NAME = "builtin-lunar-python-bazi"
ENGINE_VERSION = "1.4.8+wrapper.1"
ENGINE_LICENSE = "MIT; vendored source and license included"


def artifact_hash() -> str:
    return sha256_artifact(
        [
            Path(__file__).resolve(),
            SCRIPT_DIR / "engine_common.py",
            VENDOR_DIR / "lunar_python",
            VENDOR_DIR / "LICENSE.lunar-python.txt",
        ],
        SCRIPT_DIR,
    )


def _lunar_from_input(payload: dict[str, Any]) -> tuple[Any, datetime, dict[str, Any]]:
    calendar = payload.get("calendar", "gregorian")
    if calendar == "gregorian":
        naive = parse_naive_datetime(payload.get("local_datetime"))
        solar = Solar.fromYmdHms(
            naive.year,
            naive.month,
            naive.day,
            naive.hour,
            naive.minute,
            naive.second,
        )
        return solar.getLunar(), naive, {}
    if calendar != "lunar":
        raise EngineError(
            "E_INVALID_INPUT",
            "calendar 必须是 gregorian 或 lunar。",
            ["calendar"],
        )
    lunar_value = payload.get("lunar_datetime")
    lunar_naive = parse_naive_datetime(lunar_value, "lunar_datetime")
    is_leap = payload.get("lunar_is_leap_month", False)
    if not isinstance(is_leap, bool):
        raise EngineError(
            "E_INVALID_INPUT",
            "lunar_is_leap_month 必须是布尔值。",
            ["lunar_is_leap_month"],
        )
    month = -lunar_naive.month if is_leap else lunar_naive.month
    try:
        lunar = Lunar.fromYmdHms(
            lunar_naive.year,
            month,
            lunar_naive.day,
            lunar_naive.hour,
            lunar_naive.minute,
            lunar_naive.second,
        )
        solar = lunar.getSolar()
    except Exception as exc:
        raise EngineError(
            "E_CALENDAR_CONVERSION",
            f"农历日期无法转换：{exc}",
            ["lunar_datetime", "lunar_is_leap_month"],
        ) from exc
    naive = datetime.fromisoformat(solar.toYmdHms().replace(" ", "T"))
    return lunar, naive, {
        "original_lunar_datetime": lunar_value,
        "lunar_is_leap_month": is_leap,
    }


def _jie_payload(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    return {"name": value.getName(), "local_datetime": value.getSolar().toYmdHms()}


def generate(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("solar_time_policy", "civil") != "civil":
        raise EngineError(
            "E_UNSUPPORTED_SOLAR_TIME",
            "内置引擎当前只支持 civil 标准时；不会把经度修正冒充真太阳时。",
            ["solar_time_policy"],
        )
    day_boundary = payload.get("day_boundary_policy", "civil-midnight")
    if day_boundary not in {"civil-midnight", "late-zi-next-day"}:
        raise EngineError(
            "E_INVALID_INPUT",
            "day_boundary_policy 必须是 civil-midnight 或 late-zi-next-day。",
            ["day_boundary_policy"],
        )

    lunar, solar_naive, original_calendar = _lunar_from_input(payload)
    aware, timezone_detail, timezone_resolution = resolve_local_datetime_with_metadata(
        solar_naive,
        payload.get("timezone"),
        payload.get("fold"),
        payload.get("historical_utc_offset"),
    )
    location = validate_location(payload.get("location"))
    time_precision = require_exact_single_chart_time(
        validate_time_precision(payload.get("time_precision"))
    )

    eight_char = lunar.getEightChar()
    eight_char.setSect(1 if day_boundary == "late-zi-next-day" else 2)
    pillars = {
        "year": eight_char.getYear(),
        "month": eight_char.getMonth(),
        "day": eight_char.getDay(),
        "hour": eight_char.getTime(),
    }
    details = {
        "heavenly_stems": {
            "year": eight_char.getYearGan(),
            "month": eight_char.getMonthGan(),
            "day": eight_char.getDayGan(),
            "hour": eight_char.getTimeGan(),
        },
        "earthly_branches": {
            "year": eight_char.getYearZhi(),
            "month": eight_char.getMonthZhi(),
            "day": eight_char.getDayZhi(),
            "hour": eight_char.getTimeZhi(),
        },
        "five_elements": {
            "year": eight_char.getYearWuXing(),
            "month": eight_char.getMonthWuXing(),
            "day": eight_char.getDayWuXing(),
            "hour": eight_char.getTimeWuXing(),
        },
        "nayin": {
            "year": eight_char.getYearNaYin(),
            "month": eight_char.getMonthNaYin(),
            "day": eight_char.getDayNaYin(),
            "hour": eight_char.getTimeNaYin(),
        },
        "previous_jie": _jie_payload(lunar.getPrevJie()),
        "next_jie": _jie_payload(lunar.getNextJie()),
        "day_boundary_policy": day_boundary,
        "solar_time_policy": "civil",
    }
    calendar = payload.get("calendar", "gregorian")
    normalized_input: dict[str, Any] = {
        "calendar": calendar,
        "local_datetime": solar_naive.isoformat(),
        "timezone": payload["timezone"],
        **timezone_resolution,
        "location": location,
        "time_precision": time_precision,
        "day_boundary_policy": day_boundary,
        "solar_time_policy": "civil",
        **original_calendar,
    }
    warnings = [
        "这是传统历法排盘事实，不是经科学验证的人生预测。",
        "地点仅用于记录来源；本版本按民用当地时排盘，不做真太阳时修正。",
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
        "chart_system": "bazi",
        "chart": {"pillars": pillars, "details": details},
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
                "name": "solar-term-boundary",
                "status": "pass",
                "detail": (
                    f"prev={details['previous_jie']}; next={details['next_jie']}; "
                    "月柱采用节令边界"
                ),
            },
            {
                "name": "day-boundary-policy",
                "status": "pass",
                "detail": day_boundary,
            },
        ],
        "provenance": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "timezone_db_version": timezone_db_version(),
            "calendar_engine": "lunar-python 1.4.8 (vendored)",
        },
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a bundled Bazi fact payload.")
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
