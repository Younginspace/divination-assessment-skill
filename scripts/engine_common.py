#!/usr/bin/env python3
"""Shared, standard-library-only helpers for the bundled calculation engines."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class EngineError(ValueError):
    def __init__(self, code: str, message: str, fields: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.fields = fields or []


def load_json(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise EngineError("E_INVALID_INPUT", "输入文件不能是符号链接。", ["input"])
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EngineError("E_FILE_NOT_FOUND", f"找不到输入文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise EngineError(
            "E_INVALID_JSON",
            f"JSON 解析失败：第 {exc.lineno} 行第 {exc.colno} 列。",
        ) from exc
    if not isinstance(payload, dict):
        raise EngineError("E_INVALID_INPUT", "输入根节点必须是 JSON 对象。")
    return payload


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise EngineError(
            "E_OUTPUT_EXISTS",
            "输出文件已存在；请使用新的私有单次运行目录和文件名。",
            ["output"],
        )
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise EngineError(
            "E_OUTPUT_PATH",
            "输出目录必须是已存在的普通目录。",
            ["output"],
        )
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def parse_naive_datetime(value: Any, field: str = "local_datetime") -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise EngineError(
            "E_INVALID_INPUT",
            f"{field} 必须是非空 ISO 8601 本地日期时间。",
            [field],
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise EngineError(
            "E_INVALID_INPUT",
            f"{field} 不是有效 ISO 8601 本地日期时间。",
            [field],
        ) from exc
    if parsed.tzinfo is not None:
        raise EngineError(
            "E_INVALID_INPUT",
            f"{field} 不应包含 UTC 偏移；请单独提供 IANA timezone。",
            [field],
        )
    return parsed


def resolve_local_datetime(
    naive: datetime,
    timezone_name: Any,
    fold: Any = None,
) -> tuple[datetime, str]:
    """Resolve a post-1948 local time while preserving the legacy return shape."""
    aware, detail, _ = resolve_local_datetime_with_metadata(
        naive,
        timezone_name,
        fold,
    )
    return aware, detail


def _format_utc_offset(value: timedelta | None) -> str:
    if value is None:
        raise EngineError(
            "E_INVALID_TIMEZONE",
            "无法解析该当地时间的 UTC 偏移。",
            ["timezone"],
        )
    total_seconds = int(value.total_seconds())
    sign = "+" if total_seconds >= 0 else "-"
    total_minutes = abs(total_seconds) // 60
    hours, minutes = divmod(total_minutes, 60)
    return f"{sign}{hours:02d}:{minutes:02d}"


def _parse_historical_utc_offset(value: Any) -> timezone:
    if not isinstance(value, str) or not re.fullmatch(r"[+-]\d{2}:\d{2}", value):
        raise EngineError(
            "E_INVALID_HISTORICAL_UTC_OFFSET",
            "historical_utc_offset 必须是 ±HH:MM，例如 +08:00。",
            ["historical_utc_offset"],
        )
    sign = 1 if value[0] == "+" else -1
    hours = int(value[1:3])
    minutes = int(value[4:6])
    if minutes >= 60 or hours > 14 or (hours == 14 and minutes != 0):
        raise EngineError(
            "E_INVALID_HISTORICAL_UTC_OFFSET",
            "historical_utc_offset 超出可接受范围（-14:00 至 +14:00）。",
            ["historical_utc_offset"],
        )
    return timezone(sign * timedelta(hours=hours, minutes=minutes))


def resolve_local_datetime_with_metadata(
    naive: datetime,
    timezone_name: Any,
    fold: Any = None,
    historical_utc_offset: Any = None,
) -> tuple[datetime, str, dict[str, Any]]:
    if not isinstance(timezone_name, str) or not timezone_name.strip():
        raise EngineError(
            "E_INVALID_TIMEZONE",
            "timezone 必须是 IANA 时区名。",
            ["timezone"],
        )
    if fold is not None and fold not in (0, 1):
        raise EngineError(
            "E_INVALID_INPUT",
            "fold 必须是 0、1 或省略。",
            ["fold"],
        )
    try:
        requested_zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise EngineError(
            "E_INVALID_TIMEZONE",
            f"当前环境无法识别 IANA 时区：{timezone_name}",
            ["timezone"],
        ) from exc

    tzdb_version = timezone_db_version()
    if naive.year < 1949:
        if historical_utc_offset is None:
            raise EngineError(
                "E_HISTORICAL_TIMEZONE_OFFSET_REQUIRED",
                (
                    "1949 年前的 IANA 历史时区结果不会自动采用；请根据可复核来源"
                    "显式提供 historical_utc_offset（例如 +08:00）。"
                ),
                ["local_datetime", "timezone", "historical_utc_offset"],
            )
        fixed_zone = _parse_historical_utc_offset(historical_utc_offset)
        if fold not in (None, 0):
            raise EngineError(
                "E_INVALID_INPUT",
                "固定 historical_utc_offset 不存在回拨歧义，fold 只能省略或为 0。",
                ["fold"],
            )
        aware = naive.replace(tzinfo=fixed_zone, fold=0)
        resolved_offset = _format_utc_offset(aware.utcoffset())
        detail = (
            f"{timezone_name}; UTC offset={resolved_offset}; fold=0; "
            "1949 年前按用户显式 historical_utc_offset 处理，未采用 IANA 历史偏移"
        )
        return aware, detail, {
            "resolved_utc_offset": resolved_offset,
            "fold": 0,
            "timezone_db_version": tzdb_version,
            "historical_utc_offset": historical_utc_offset,
            "timezone_provenance": {
                "method": "user-provided-historical-fixed-offset",
                "requested_iana_timezone": timezone_name,
                "historical_utc_offset": historical_utc_offset,
                "iana_historical_rules_used": False,
            },
        }
    if historical_utc_offset is not None:
        raise EngineError(
            "E_INVALID_HISTORICAL_UTC_OFFSET",
            "historical_utc_offset 只用于 1949 年前输入；本日期应使用 IANA timezone。",
            ["historical_utc_offset"],
        )

    zone = requested_zone

    valid: list[datetime] = []
    for candidate_fold in (0, 1):
        candidate = naive.replace(tzinfo=zone, fold=candidate_fold)
        round_trip = (
            candidate.astimezone(timezone.utc)
            .astimezone(zone)
            .replace(tzinfo=None)
        )
        if round_trip == naive and all(
            old.utcoffset() != candidate.utcoffset() for old in valid
        ):
            valid.append(candidate)
    if not valid:
        raise EngineError(
            "E_NONEXISTENT_LOCAL_TIME",
            "该当地时间落在时钟跳变造成的不存在区间。",
            ["local_datetime", "timezone"],
        )
    if len(valid) > 1:
        if fold not in (0, 1):
            raise EngineError(
                "E_AMBIGUOUS_LOCAL_TIME",
                "该当地时间出现两次；请显式提供 fold=0 或 fold=1。",
                ["fold"],
            )
        aware = naive.replace(tzinfo=zone, fold=fold)
    else:
        aware = valid[0]
    detail = (
        f"{timezone_name}; UTC offset={aware.utcoffset()}; fold={aware.fold}; "
        "已完成 UTC 往返校验"
    )
    return aware, detail, {
        "resolved_utc_offset": _format_utc_offset(aware.utcoffset()),
        "fold": aware.fold,
        "timezone_db_version": tzdb_version,
        "timezone_provenance": {
            "method": "iana-zoneinfo",
            "requested_iana_timezone": timezone_name,
            "iana_historical_rules_used": True,
        },
    }


def validate_location(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EngineError("E_INVALID_LOCATION", "location 必须是对象。", ["location"])
    normalized: dict[str, Any] = {}
    for field in ("label", "source", "precision"):
        item = value.get(field)
        if not isinstance(item, str) or not item.strip():
            raise EngineError(
                "E_INVALID_LOCATION",
                f"location.{field} 必须是非空字符串。",
                [f"location.{field}"],
            )
        normalized[field] = item.strip()
    latitude = value.get("latitude")
    longitude = value.get("longitude")
    if (
        isinstance(latitude, bool)
        or not isinstance(latitude, (int, float))
        or not -90 <= latitude <= 90
    ):
        raise EngineError(
            "E_INVALID_LOCATION",
            "location.latitude 必须在 -90 到 90。",
            ["location.latitude"],
        )
    if (
        isinstance(longitude, bool)
        or not isinstance(longitude, (int, float))
        or not -180 <= longitude <= 180
    ):
        raise EngineError(
            "E_INVALID_LOCATION",
            "location.longitude 必须在 -180 到 180。",
            ["location.longitude"],
        )
    normalized["latitude"] = float(latitude)
    normalized["longitude"] = float(longitude)
    return normalized


def validate_time_precision(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EngineError(
            "E_INVALID_INPUT",
            "time_precision 必须是对象。",
            ["time_precision"],
        )
    kind = value.get("kind")
    if kind not in {"exact", "approximate", "range", "unknown"}:
        raise EngineError(
            "E_INVALID_INPUT",
            "time_precision.kind 必须是 exact、approximate、range 或 unknown。",
            ["time_precision.kind"],
        )
    minutes = value.get("minutes")
    if (
        minutes is not None
        and (
            isinstance(minutes, bool)
            or not isinstance(minutes, (int, float))
            or minutes < 0
        )
    ):
        raise EngineError(
            "E_INVALID_INPUT",
            "time_precision.minutes 必须是非负数或 null。",
            ["time_precision.minutes"],
        )
    return {"kind": kind, "minutes": minutes}


def require_exact_single_chart_time(
    time_precision: dict[str, Any],
) -> dict[str, Any]:
    """Reject uncertain inputs when an engine can emit only one exact chart."""
    if (
        time_precision.get("kind") != "exact"
        or time_precision.get("minutes") != 0
    ):
        raise EngineError(
            "E_TIME_UNCERTAINTY",
            (
                "当前引擎只能输出单一盘面，因此要求 time_precision.kind=exact "
                "且 minutes=0；不精确、范围或未知时间需要先做范围盘/人工确认。"
            ),
            ["time_precision.kind", "time_precision.minutes"],
        )
    return time_precision


def sha256_artifact(paths: list[Path], base: Path) -> str:
    digest = hashlib.sha256()
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(
                item
                for item in path.rglob("*")
                if item.is_file()
                and "__pycache__" not in item.parts
                and not item.name.endswith((".pyc", ".pyo"))
            )
        elif path.is_file():
            files.append(path)
    for path in sorted(set(files), key=lambda item: item.relative_to(base).as_posix()):
        relative = path.relative_to(base).as_posix().encode("utf-8")
        data = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return "sha256:" + digest.hexdigest()


def timezone_db_version() -> str:
    try:
        from importlib.metadata import version

        return "tzdata-" + version("tzdata")
    except Exception:
        return "system-zoneinfo"


def emit_error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, EngineError):
        return {
            "ok": False,
            "error": {
                "code": exc.code,
                "message": str(exc),
                "fields": exc.fields,
            },
        }
    return {
        "ok": False,
        "error": {
            "code": "E_INTERNAL",
            "message": f"内部错误：{exc}",
            "fields": [],
        },
    }
