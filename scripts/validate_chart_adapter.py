#!/usr/bin/env python3
"""Validate a gated, allowlisted external chart-engine result."""

from __future__ import annotations

import argparse
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from feature_gate import (
    GateError,
    check_feature,
    load_protected_json,
    parse_aware_datetime,
    sha256_json,
)


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ENGINE_ALLOWLIST = SCRIPT_DIR / "engine_allowlist.json"
ALLOWED_SYSTEMS = {"bazi", "western", "vedic", "ziwei"}
ALLOWED_PRECISION_KINDS = {"exact", "approximate", "range", "unknown"}
REQUIRED_ENGINE_FIELDS = {"name", "version", "artifact_hash", "license"}
HEX64 = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMON_BOUNDARY_CHECKS = {
    "timezone-resolved",
    "location-resolved",
    "time-precision-propagated",
}
SYSTEM_BOUNDARY_CHECKS = {
    "bazi": {"solar-term-boundary", "day-boundary-policy"},
    "western": {"ephemeris-engine-verified", "ephemeris-range"},
    "vedic": {
        "ephemeris-engine-verified",
        "ephemeris-range",
        "ayanamsa-model-declared",
        "sidereal-boundary-margin",
        "ascendant-latitude-range",
    },
    "ziwei": {"calendar-conversion", "school-configuration"},
}
BUNDLED_ENGINE_SYSTEMS = {
    "builtin-lunar-python-bazi": "bazi",
    "builtin-astronomy-engine-basic": "western",
    "builtin-astronomy-engine-vedic-lite": "vedic",
}


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return {"__load_error__": f"找不到文件：{path}"}
    except json.JSONDecodeError as exc:
        return {
            "__load_error__": f"JSON 解析失败：第 {exc.lineno} 行第 {exc.colno} 列"
        }


def is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_aware_datetime(value: Any, field: str, errors: list[str]) -> None:
    if not is_nonempty_string(value):
        errors.append(f"{field} 必须是非空 ISO 8601 字符串")
        return
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{field} 不是有效 ISO 8601 日期时间")
        return
    if parsed.tzinfo is None:
        errors.append(f"{field} 必须包含时区")


def validate_local_datetime(value: Any, field: str, errors: list[str]) -> None:
    if not is_nonempty_string(value):
        errors.append(f"{field} 必须是非空 ISO 8601 本地日期时间")
        return
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        errors.append(f"{field} 不是有效 ISO 8601 本地日期时间")
        return
    if parsed.tzinfo is not None:
        errors.append(f"{field} 不应含 UTC 偏移；时区必须单独放在 input.timezone")


def check_engine_allowlist(
    engine: dict[str, Any],
    chart_system: str,
    allowlist_path: Path | None,
) -> dict[str, Any]:
    resolved_allowlist_path = allowlist_path or DEFAULT_ENGINE_ALLOWLIST
    try:
        allowlist, allowlist_hash = load_protected_json(
            resolved_allowlist_path, "命理引擎 allowlist"
        )
    except GateError as exc:
        raise GateError("E_ENGINE_NOT_APPROVED", str(exc), exc.fields) from exc
    if allowlist.get("schema_version") != "1.0.0":
        raise GateError(
            "E_ENGINE_NOT_APPROVED",
            "引擎 allowlist schema_version 必须是 1.0.0。",
            ["engine_allowlist.schema_version"],
        )
    records = allowlist.get("engines")
    if not isinstance(records, list):
        raise GateError(
            "E_ENGINE_NOT_APPROVED",
            "引擎 allowlist 必须包含 engines 数组。",
            ["engine_allowlist.engines"],
        )

    matching = [
        record
        for record in records
        if isinstance(record, dict)
        and record.get("name") == engine.get("name")
        and record.get("version") == engine.get("version")
        and record.get("artifact_hash") == engine.get("artifact_hash")
    ]
    if len(matching) != 1:
        raise GateError(
            "E_ENGINE_NOT_APPROVED",
            "引擎名称、精确版本和 artifact hash 未命中唯一 allowlist 记录。",
            ["engine"],
        )
    record = matching[0]
    required = (
        "approval_id",
        "algorithm_review_id",
        "license_review_id",
        "deployment_review_id",
        "license",
        "expires_at",
    )
    missing = [
        f"engine_allowlist.{field}"
        for field in required
        if not is_nonempty_string(record.get(field))
    ]
    if missing:
        raise GateError(
            "E_ENGINE_NOT_APPROVED",
            "引擎 allowlist 记录不完整。",
            missing,
        )
    if record.get("status") != "approved":
        raise GateError(
            "E_ENGINE_NOT_APPROVED",
            "引擎状态不是 approved。",
            ["engine_allowlist.status"],
        )
    if record["license"] != engine.get("license"):
        raise GateError(
            "E_ENGINE_NOT_APPROVED",
            "引擎输出的许可证结论与 allowlist 不一致。",
            ["engine.license"],
        )
    systems = record.get("supported_systems")
    if not isinstance(systems, list) or chart_system not in systems:
        raise GateError(
            "E_ENGINE_NOT_APPROVED",
            f"引擎未获准生成 {chart_system}。",
            ["engine_allowlist.supported_systems"],
        )
    try:
        expires_at = parse_aware_datetime(
            record["expires_at"], "engine_allowlist.expires_at"
        )
    except GateError as exc:
        raise GateError("E_ENGINE_NOT_APPROVED", str(exc), exc.fields) from exc
    if expires_at <= datetime.now(timezone.utc):
        raise GateError(
            "E_ENGINE_NOT_APPROVED",
            "引擎 allowlist 记录已过期。",
            ["engine_allowlist.expires_at"],
        )
    return {
        "approval_id": record["approval_id"],
        "algorithm_review_id": record["algorithm_review_id"],
        "license_review_id": record["license_review_id"],
        "deployment_review_id": record["deployment_review_id"],
        "engine_record_hash": sha256_json(record),
        "engine_allowlist_hash": allowlist_hash,
        "expires_at": expires_at.isoformat(),
    }


def _difference_paths(actual: Any, expected: Any, path: str = "payload") -> list[str]:
    """Return bounded, human-readable paths whose deterministic values differ."""
    if type(actual) is not type(expected):
        # JSON numbers may round-trip as int or float without changing their value.
        if (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and isinstance(expected, (int, float))
            and not isinstance(expected, bool)
            and actual == expected
        ):
            return []
        return [path]
    if isinstance(actual, dict):
        differences: list[str] = []
        for key in sorted(set(actual) | set(expected)):
            child = f"{path}.{key}"
            if key not in actual or key not in expected:
                differences.append(child)
            else:
                differences.extend(_difference_paths(actual[key], expected[key], child))
            if len(differences) >= 12:
                break
        return differences[:12]
    if isinstance(actual, list):
        if len(actual) != len(expected):
            return [f"{path}.length"]
        differences = []
        for index, (actual_item, expected_item) in enumerate(zip(actual, expected)):
            differences.extend(
                _difference_paths(actual_item, expected_item, f"{path}[{index}]")
            )
            if len(differences) >= 12:
                break
        return differences[:12]
    return [] if actual == expected else [path]


def attest_bundled_engine(
    payload: dict[str, Any],
) -> tuple[list[str], dict[str, Any] | None]:
    """Recompute bundled-engine output locally and compare deterministic fields.

    An allowlist proves which binary/source snapshot was reviewed; it does not prove
    that a submitted chart came from that snapshot. Bundled engines can close that
    gap by replaying the normalized input. External engines are deliberately
    rejected until the host defines and verifies a separate attestation receipt.
    """
    engine = payload.get("engine")
    input_data = payload.get("input")
    if not isinstance(engine, dict) or not isinstance(input_data, dict):
        return ["E_ENGINE_ATTESTATION: engine 和 input 必须先通过结构校验。"], None

    engine_name = engine.get("name")
    chart_system = payload.get("chart_system")
    expected_system = BUNDLED_ENGINE_SYSTEMS.get(engine_name)
    if expected_system is None:
        return [
            "E_ENGINE_ATTESTATION_UNSUPPORTED: "
            "当前仅支持随包内置引擎的本地复算；外部引擎必须由宿主实现可验证的 "
            "attestation receipt，不能仅凭 allowlist 元数据放行。"
        ], None
    if chart_system != expected_system:
        return [
            "E_ENGINE_ATTESTATION: 内置引擎与 chart_system 不匹配。"
        ], None

    # Import lazily so a malformed/unapproved external payload never loads a
    # calculation engine merely to perform basic contract validation.
    if engine_name == "builtin-lunar-python-bazi":
        from bazi_engine import artifact_hash as local_artifact_hash
        from bazi_engine import generate as replay_generate
    elif engine_name == "builtin-astronomy-engine-basic":
        from western_engine import artifact_hash as local_artifact_hash
        from western_engine import generate as replay_generate
    else:
        from vedic_lite_engine import artifact_hash as local_artifact_hash
        from vedic_lite_engine import generate as replay_generate

    current_artifact_hash = local_artifact_hash()
    if engine.get("artifact_hash") != current_artifact_hash:
        return [
            "E_ENGINE_ARTIFACT_MISMATCH: payload.engine.artifact_hash "
            "与当前本地内置引擎源码/依赖的重算 hash 不一致。"
        ], None

    replay_input = deepcopy(input_data)
    if engine_name == "builtin-lunar-python-bazi" and replay_input.get(
        "calendar"
    ) == "lunar":
        # The Bazi adapter exposes the original lunar value under a provenance-
        # explicit name in normalized input. Restore only that alias; do not infer
        # calculation policies from attacker-controlled chart output.
        original_lunar = replay_input.get("original_lunar_datetime")
        if not is_nonempty_string(original_lunar):
            return [
                "E_ENGINE_REPLAY_INPUT: 农历盘缺少 input.original_lunar_datetime，"
                "无法从 payload.input 复算。"
            ], None
        replay_input["lunar_datetime"] = original_lunar

    try:
        expected = replay_generate(replay_input)
    except Exception as exc:
        return [
            "E_ENGINE_REPLAY_FAILED: 无法从 payload.input 复算内置盘面："
            f"{type(exc).__name__}: {exc}"
        ], None

    deterministic_fields = (
        "schema_version",
        "engine",
        "input",
        "chart_system",
        "chart",
        "boundary_checks",
        "warnings",
    )
    actual_deterministic = {
        field: payload.get(field) for field in deterministic_fields
    }
    expected_deterministic = {
        field: expected.get(field) for field in deterministic_fields
    }

    actual_provenance = payload.get("provenance")
    expected_provenance = expected.get("provenance")
    if isinstance(actual_provenance, dict):
        actual_provenance = {
            key: value
            for key, value in actual_provenance.items()
            if key != "generated_at"
        }
    if isinstance(expected_provenance, dict):
        expected_provenance = {
            key: value
            for key, value in expected_provenance.items()
            if key != "generated_at"
        }
    actual_deterministic["provenance"] = actual_provenance
    expected_deterministic["provenance"] = expected_provenance

    differences = _difference_paths(
        actual_deterministic, expected_deterministic
    )
    if differences:
        return [
            "E_ENGINE_REPLAY_MISMATCH: 本地复算结果与提交盘面不一致："
            + ", ".join(differences)
        ], None

    return [], {
        "kind": "bundled-local-recomputation-v1",
        "engine_name": engine_name,
        "local_artifact_hash": current_artifact_hash,
        "deterministic_payload_hash": (
            "sha256:" + sha256_json(expected_deterministic)
        ),
        "excluded_nondeterministic_fields": ["provenance.generated_at"],
    }


def validate_chart(
    payload: Any,
    allowlist_path: Path | None = None,
    controls_path: Path | None = None,
    scope: str = "yuanbao-public-cn",
) -> tuple[list[str], list[str], dict[str, Any] | None]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(payload, dict):
        return ["根节点必须是 JSON 对象"], warnings, None
    if "__load_error__" in payload:
        return [payload["__load_error__"]], warnings, None

    try:
        feature_receipt = check_feature(
            controls_path,
            "chart-generation",
            "1.0.0",
            scope,
        )
    except GateError as exc:
        errors.append(f"{exc.code}: {exc}")
        feature_receipt = None

    system_feature_receipt: dict[str, Any] | None = None

    if payload.get("schema_version") != "1.0.0":
        errors.append("schema_version 必须是 1.0.0")

    engine = payload.get("engine")
    if not isinstance(engine, dict):
        errors.append("engine 必须是对象")
        engine = {}
    else:
        for field in sorted(REQUIRED_ENGINE_FIELDS):
            if not is_nonempty_string(engine.get(field)):
                errors.append(f"engine.{field} 必须是非空字符串")
        artifact_hash = engine.get("artifact_hash")
        if is_nonempty_string(artifact_hash) and not HEX64.fullmatch(artifact_hash):
            errors.append("engine.artifact_hash 必须是完整的小写 sha256: + 64 位十六进制")

    chart_system = payload.get("chart_system")
    if chart_system not in ALLOWED_SYSTEMS:
        errors.append("chart_system 必须是 bazi、western、vedic 或 ziwei")
    elif chart_system == "vedic":
        try:
            system_feature_receipt = check_feature(
                controls_path,
                "vedic-lite-generation",
                "1.0.0",
                scope,
            )
        except GateError as exc:
            errors.append(f"{exc.code}: {exc}")

    engine_receipt: dict[str, Any] | None = None
    if isinstance(chart_system, str) and engine:
        try:
            engine_receipt = check_engine_allowlist(
                engine, chart_system, allowlist_path
            )
        except GateError as exc:
            errors.append(f"{exc.code}: {exc}")

    chart = payload.get("chart")
    if not isinstance(chart, dict) or not chart:
        errors.append("chart 必须是非空对象")
    elif chart_system == "bazi":
        pillars = chart.get("pillars")
        if not isinstance(pillars, dict):
            errors.append("bazi 的 chart.pillars 必须是对象")
        else:
            for pillar in ("year", "month", "day", "hour"):
                if not is_nonempty_string(pillars.get(pillar)):
                    errors.append(f"chart.pillars.{pillar} 必须是非空字符串")

    input_data = payload.get("input")
    if not isinstance(input_data, dict):
        errors.append("input 必须是对象")
    else:
        if input_data.get("calendar") not in {"gregorian", "lunar"}:
            errors.append("input.calendar 必须是 gregorian 或 lunar")
        validate_local_datetime(
            input_data.get("local_datetime"), "input.local_datetime", errors
        )
        timezone_name = input_data.get("timezone")
        if not is_nonempty_string(timezone_name):
            errors.append("input.timezone 必须是 IANA 时区名")
        else:
            try:
                ZoneInfo(timezone_name)
            except ZoneInfoNotFoundError:
                errors.append("input.timezone 不是当前 tzdata 可识别的 IANA 时区")

        location = input_data.get("location")
        if not isinstance(location, dict):
            errors.append("input.location 必须是对象")
        else:
            for field in ("label", "source", "precision"):
                if not is_nonempty_string(location.get(field)):
                    errors.append(f"input.location.{field} 必须是非空字符串")
            latitude = location.get("latitude")
            longitude = location.get("longitude")
            if (
                isinstance(latitude, bool)
                or not isinstance(latitude, (int, float))
                or not -90 <= latitude <= 90
            ):
                errors.append("input.location.latitude 必须在 -90 到 90")
            if (
                isinstance(longitude, bool)
                or not isinstance(longitude, (int, float))
                or not -180 <= longitude <= 180
            ):
                errors.append("input.location.longitude 必须在 -180 到 180")

        precision = input_data.get("time_precision")
        if not isinstance(precision, dict):
            errors.append("input.time_precision 必须是对象")
        else:
            if precision.get("kind") not in ALLOWED_PRECISION_KINDS:
                errors.append(
                    "input.time_precision.kind 必须是 exact、approximate、range 或 unknown"
                )
            minutes = precision.get("minutes")
            if (
                minutes is not None
                and (
                    isinstance(minutes, bool)
                    or not isinstance(minutes, (int, float))
                    or minutes < 0
                )
            ):
                errors.append("input.time_precision.minutes 必须是非负数或 null")

    checks = payload.get("boundary_checks")
    seen_names: set[str] = set()
    if not isinstance(checks, list) or not checks:
        errors.append("boundary_checks 必须是非空数组")
    else:
        for index, check in enumerate(checks):
            prefix = f"boundary_checks[{index}]"
            if not isinstance(check, dict):
                errors.append(f"{prefix} 必须是对象")
                continue
            name = check.get("name")
            if not is_nonempty_string(name):
                errors.append(f"{prefix}.name 必须是非空字符串")
            elif name in seen_names:
                errors.append(f"{prefix}.name 重复：{name}")
            else:
                seen_names.add(name)
            status = check.get("status")
            if status not in {"pass", "fail"}:
                errors.append(f"{prefix}.status 必须是 pass 或 fail")
            elif status == "fail":
                errors.append(f"{prefix} 未通过，禁止生成报告")
            if not is_nonempty_string(check.get("detail")):
                errors.append(f"{prefix}.detail 必须是非空字符串")
    if chart_system in ALLOWED_SYSTEMS:
        required_checks = COMMON_BOUNDARY_CHECKS | SYSTEM_BOUNDARY_CHECKS[chart_system]
        missing_checks = sorted(required_checks - seen_names)
        if missing_checks:
            errors.append(
                "缺少必备 boundary_checks：" + ", ".join(missing_checks)
            )

    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        errors.append("provenance 必须是对象")
    else:
        validate_aware_datetime(
            provenance.get("generated_at"), "provenance.generated_at", errors
        )
        if not is_nonempty_string(provenance.get("timezone_db_version")):
            errors.append("provenance.timezone_db_version 必须是非空字符串")
        if chart_system in {"western", "vedic"} and not is_nonempty_string(
            provenance.get("ephemeris_version")
        ):
            errors.append("western/vedic 必须提供 provenance.ephemeris_version")

    if not isinstance(payload.get("warnings"), list) or any(
        not isinstance(item, str) for item in payload.get("warnings", [])
    ):
        errors.append("warnings 必须是字符串数组")

    engine_attestation: dict[str, Any] | None = None
    if not errors:
        attestation_errors, engine_attestation = attest_bundled_engine(payload)
        errors.extend(attestation_errors)

    if (
        errors
        or feature_receipt is None
        or (chart_system == "vedic" and system_feature_receipt is None)
        or engine_receipt is None
        or engine_attestation is None
    ):
        return errors, warnings, None
    warnings.append("契约校验不能证明传统解释为科学事实；解释层仍须保留边界。")
    receipt = {
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "chart_payload_hash": f"sha256:{sha256_json(payload)}",
        "feature_control": feature_receipt,
        "system_feature_control": system_feature_receipt,
        "engine_approval": engine_receipt,
        "engine_attestation": engine_attestation,
    }
    return errors, warnings, receipt


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a gated, allowlisted chart-engine adapter result."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--allowlist", type=Path)
    parser.add_argument(
        "--controls",
        "--approvals",
        dest="controls",
        type=Path,
        help="Host feature controls; --approvals is a compatibility alias.",
    )
    parser.add_argument("--scope", default="yuanbao-public-cn")
    args = parser.parse_args()
    errors, warnings, receipt = validate_chart(
        load_json(args.input),
        args.allowlist,
        args.controls,
        args.scope,
    )
    payload = {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "receipt": receipt,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
