#!/usr/bin/env python3
"""Resolve a host-controlled feature policy for the bounded entertainment modes.

The bundled policy makes the bounded low-risk modes usable out of the box. A host
can override it with an absolute file path or DIVINATION_FEATURE_CONTROLS_FILE.
Production hosts should supply a short-lived, signed server-side equivalent;
this local file gate is defense in depth, not an authorization boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONTROLS_PATH = SCRIPT_DIR / "feature_controls.default.json"
CONTROL_PROFILE_ENV = "DIVINATION_CONTROL_PROFILE"
CONTROL_HMAC_KEY_ENV = "DIVINATION_FEATURE_CONTROLS_HMAC_KEY"
CONTROL_MIN_REVISION_ENV = "DIVINATION_FEATURE_CONTROLS_MIN_REVISION"
PRODUCTION_MAX_TTL_SECONDS = 15 * 60
FEATURE_MODES = {
    "oracle-reflection": "REFLECTION_ONLY",
    "chart-generation": "FACTS_ONLY",
    "vedic-lite-generation": "VEDIC_LITE_FACTS_ONLY",
    "traditional-report-interpretation": "SOURCE_BOUND",
}


class GateError(ValueError):
    def __init__(self, code: str, message: str, fields: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.fields = fields or []


def sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def runtime_profile() -> str:
    profile = os.environ.get(CONTROL_PROFILE_ENV, "prototype").strip().lower()
    if profile not in {"prototype", "production"}:
        raise GateError(
            "E_FEATURE_DISABLED",
            f"{CONTROL_PROFILE_ENV} 只能是 prototype 或 production。",
            [CONTROL_PROFILE_ENV],
        )
    return profile


def parse_aware_datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise GateError(
            "E_FEATURE_DISABLED",
            f"{field} 必须是非空 ISO 8601 日期时间。",
            [field],
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GateError(
            "E_FEATURE_DISABLED",
            f"{field} 不是有效 ISO 8601 日期时间。",
            [field],
        ) from exc
    if parsed.tzinfo is None:
        raise GateError(
            "E_FEATURE_DISABLED",
            f"{field} 必须包含时区。",
            [field],
        )
    return parsed.astimezone(timezone.utc)


def load_protected_json(
    path: Path | None,
    label: str,
) -> tuple[dict[str, Any], str]:
    if path is None:
        raise GateError(
            "E_FEATURE_DISABLED",
            f"未配置{label}。",
            [label],
        )
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise GateError(
            "E_FEATURE_DISABLED",
            f"找不到{label}：{path}",
            [label],
        ) from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise GateError(
            "E_FEATURE_DISABLED",
            f"{label}必须是普通文件，不能是符号链接。",
            [label],
        )
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise GateError(
            "E_FEATURE_DISABLED",
            f"{label}不能允许同组或其他用户写入。",
            [label],
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GateError(
            "E_FEATURE_DISABLED",
            f"{label} JSON 解析失败：第 {exc.lineno} 行第 {exc.colno} 列。",
            [label],
        ) from exc
    if not isinstance(payload, dict):
        raise GateError(
            "E_FEATURE_DISABLED",
            f"{label}根节点必须是对象。",
            [label],
        )
    return payload, sha256_json(payload)


def resolve_controls_path(
    explicit: Path | None,
    profile: str,
) -> tuple[Path, str]:
    if explicit is not None:
        return explicit.expanduser().resolve(), "explicit"
    environment_path = os.environ.get("DIVINATION_FEATURE_CONTROLS_FILE")
    if environment_path:
        path = Path(environment_path)
        if not path.is_absolute():
            raise GateError(
                "E_FEATURE_DISABLED",
                "DIVINATION_FEATURE_CONTROLS_FILE 必须是绝对路径。",
                ["DIVINATION_FEATURE_CONTROLS_FILE"],
            )
        return path, "environment"
    if profile == "production":
        raise GateError(
            "E_FEATURE_DISABLED",
            "生产模式必须由宿主显式提供功能控制快照；禁止回落到随包默认文件。",
            ["DIVINATION_FEATURE_CONTROLS_FILE"],
        )
    return DEFAULT_CONTROLS_PATH, "bundled-default"


def verify_production_controls(
    controls: dict[str, Any],
    *,
    source: str,
    now: datetime,
) -> tuple[datetime, int]:
    """Verify a short-lived host snapshot for production use.

    The Yuanbao host is responsible for fetching the snapshot over its trusted
    control-plane channel. This verifier authenticates the mounted snapshot,
    applies a short TTL, and accepts a host-pinned minimum revision so a stale
    snapshot cannot silently reopen a feature.
    """

    if source == "bundled-default":
        raise GateError(
            "E_FEATURE_DISABLED",
            "生产模式禁止使用随包默认控制文件。",
            ["feature_controls"],
        )
    issued_at = parse_aware_datetime(
        controls.get("issued_at"), "feature_controls.issued_at"
    )
    expires_at = parse_aware_datetime(
        controls.get("expires_at"), "feature_controls.expires_at"
    )
    if issued_at > now:
        raise GateError(
            "E_FEATURE_DISABLED",
            "功能控制快照的 issued_at 晚于当前时间。",
            ["feature_controls.issued_at"],
        )
    lifetime = (expires_at - issued_at).total_seconds()
    if lifetime <= 0 or lifetime > PRODUCTION_MAX_TTL_SECONDS:
        raise GateError(
            "E_FEATURE_DISABLED",
            "生产功能控制快照的 TTL 必须大于 0 且不超过 15 分钟。",
            ["feature_controls.issued_at", "feature_controls.expires_at"],
        )

    revision_number = controls.get("revision_number")
    if (
        isinstance(revision_number, bool)
        or not isinstance(revision_number, int)
        or revision_number < 0
    ):
        raise GateError(
            "E_FEATURE_DISABLED",
            "生产功能控制快照必须包含非负整数 revision_number。",
            ["feature_controls.revision_number"],
        )
    minimum_text = os.environ.get(CONTROL_MIN_REVISION_ENV)
    if not isinstance(minimum_text, str) or not minimum_text.strip():
        raise GateError(
            "E_FEATURE_DISABLED",
            f"生产模式必须设置 {CONTROL_MIN_REVISION_ENV}，缺失时按关闭处理。",
            [CONTROL_MIN_REVISION_ENV],
        )
    try:
        minimum_revision = int(minimum_text)
    except ValueError as exc:
        raise GateError(
            "E_FEATURE_DISABLED",
            f"{CONTROL_MIN_REVISION_ENV} 必须是非负整数。",
            [CONTROL_MIN_REVISION_ENV],
        ) from exc
    if minimum_revision < 0 or revision_number < minimum_revision:
        raise GateError(
            "E_FEATURE_DISABLED",
            "功能控制快照 revision_number 低于宿主允许的最小版本。",
            ["feature_controls.revision_number", CONTROL_MIN_REVISION_ENV],
        )

    control_plane_id = controls.get("control_plane_id")
    if not isinstance(control_plane_id, str) or not control_plane_id.strip():
        raise GateError(
            "E_FEATURE_DISABLED",
            "生产功能控制快照缺少 control_plane_id。",
            ["feature_controls.control_plane_id"],
        )
    secret = os.environ.get(CONTROL_HMAC_KEY_ENV)
    if not isinstance(secret, str) or len(secret.encode("utf-8")) < 32:
        raise GateError(
            "E_FEATURE_DISABLED",
            f"生产模式必须通过 {CONTROL_HMAC_KEY_ENV} 注入至少 32 字节的服务端密钥。",
            [CONTROL_HMAC_KEY_ENV],
        )
    signature = controls.get("signature")
    if not isinstance(signature, str) or not re.fullmatch(
        r"hmac-sha256:[0-9a-f]{64}", signature
    ):
        raise GateError(
            "E_FEATURE_DISABLED",
            "生产功能控制快照缺少合法的 HMAC-SHA256 签名。",
            ["feature_controls.signature"],
        )
    unsigned = {key: value for key, value in controls.items() if key != "signature"}
    expected = "hmac-sha256:" + hmac.new(
        secret.encode("utf-8"),
        json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise GateError(
            "E_FEATURE_DISABLED",
            "生产功能控制快照签名校验失败。",
            ["feature_controls.signature"],
        )
    return issued_at, revision_number


def _check_v2(
    controls: dict[str, Any],
    controls_hash: str,
    source: str,
    feature: str,
    feature_version: str,
    scope: str,
    now: datetime,
    profile: str,
) -> dict[str, Any]:
    if controls.get("schema_version") != "2.0.0":
        raise GateError(
            "E_FEATURE_DISABLED",
            "功能控制文件 schema_version 必须是 2.0.0。",
            ["feature_controls.schema_version"],
        )
    revision = controls.get("revision")
    if not isinstance(revision, str) or not revision.strip():
        raise GateError(
            "E_FEATURE_DISABLED",
            "功能控制文件缺少 revision。",
            ["feature_controls.revision"],
        )
    issued_at = parse_aware_datetime(
        controls.get("issued_at"), "feature_controls.issued_at"
    )
    if issued_at > now:
        raise GateError(
            "E_FEATURE_DISABLED",
            "功能控制文件的 issued_at 晚于当前时间。",
            ["feature_controls.issued_at"],
        )
    expires_at = parse_aware_datetime(
        controls.get("expires_at"), "feature_controls.expires_at"
    )
    if expires_at <= now:
        raise GateError(
            "E_FEATURE_DISABLED",
            "功能控制文件已过期，按关闭处理。",
            ["feature_controls.expires_at"],
        )
    revision_number: int | None = None
    if profile == "production":
        _, revision_number = verify_production_controls(
            controls,
            source=source,
            now=now,
        )
    features = controls.get("features")
    if profile == "production" and (
        not isinstance(features, dict)
        or set(features) != set(FEATURE_MODES)
    ):
        raise GateError(
            "E_FEATURE_DISABLED",
            "生产功能控制快照必须恰好包含全部受控功能的完整记录。",
            ["feature_controls.features"],
        )
    record = features.get(feature) if isinstance(features, dict) else None
    if not isinstance(record, dict):
        raise GateError(
            "E_FEATURE_DISABLED",
            f"功能 {feature} 没有控制记录。",
            [f"feature_controls.features.{feature}"],
        )
    if record.get("enabled") is not True:
        raise GateError(
            "E_FEATURE_DISABLED",
            f"功能 {feature} 已由控制面关闭。",
            [f"feature_controls.features.{feature}.enabled"],
        )
    expected_mode = FEATURE_MODES[feature]
    if record.get("mode") != expected_mode:
        raise GateError(
            "E_FEATURE_DISABLED",
            f"功能 {feature} 只能以 {expected_mode} 受限模式运行。",
            [f"feature_controls.features.{feature}.mode"],
        )
    if record.get("feature_version") != feature_version:
        raise GateError(
            "E_FEATURE_DISABLED",
            f"功能 {feature} 的版本不匹配。",
            [f"feature_controls.features.{feature}.feature_version"],
        )
    scopes = record.get("scopes")
    if not isinstance(scopes, list) or scope not in scopes:
        raise GateError(
            "E_FEATURE_DISABLED",
            f"功能 {feature} 未向范围 {scope} 开放。",
            [f"feature_controls.features.{feature}.scopes"],
        )
    reason = record.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise GateError(
            "E_FEATURE_DISABLED",
            f"功能 {feature} 缺少控制原因。",
            [f"feature_controls.features.{feature}.reason"],
        )
    record_hash = sha256_json(record)
    return {
        "feature": feature,
        "feature_version": feature_version,
        "scope": scope,
        "enabled": True,
        "mode": expected_mode,
        "control_source": source,
        "control_profile": profile,
        "control_revision": revision,
        "control_revision_number": revision_number,
        "control_reason": reason,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "control_record_hash": record_hash,
        "controls_file_hash": controls_hash,
        # Compatibility keys for v1 result/state validators.
        "approval_id": f"CONTROL-{revision}",
        "approval_record_hash": record_hash,
    }


def _check_legacy_v1(
    controls: dict[str, Any],
    controls_hash: str,
    source: str,
    feature: str,
    feature_version: str,
    scope: str,
    now: datetime,
) -> dict[str, Any]:
    approvals = controls.get("approvals")
    record = approvals.get(feature) if isinstance(approvals, dict) else None
    if not isinstance(record, dict) or record.get("status") != "approved":
        raise GateError(
            "E_FEATURE_DISABLED",
            f"功能 {feature} 没有有效的兼容版控制记录。",
            [f"feature_approvals.approvals.{feature}"],
        )
    if record.get("feature_version") != feature_version:
        raise GateError(
            "E_FEATURE_DISABLED",
            f"功能 {feature} 的版本不匹配。",
            [f"feature_approvals.approvals.{feature}.feature_version"],
        )
    if scope not in record.get("scopes", []):
        raise GateError(
            "E_FEATURE_DISABLED",
            f"功能 {feature} 未向范围 {scope} 开放。",
            [f"feature_approvals.approvals.{feature}.scopes"],
        )
    expires_at = parse_aware_datetime(
        record.get("expires_at"),
        f"feature_approvals.approvals.{feature}.expires_at",
    )
    if expires_at <= now:
        raise GateError(
            "E_FEATURE_DISABLED",
            f"功能 {feature} 的兼容版控制记录已过期。",
            [f"feature_approvals.approvals.{feature}.expires_at"],
        )
    record_hash = sha256_json(record)
    return {
        "feature": feature,
        "feature_version": feature_version,
        "scope": scope,
        "enabled": True,
        "mode": FEATURE_MODES[feature],
        "control_source": source,
        "control_revision": record.get("approval_id", "legacy-v1"),
        "control_reason": "兼容版宿主控制记录",
        "expires_at": expires_at.isoformat(),
        "control_record_hash": record_hash,
        "controls_file_hash": controls_hash,
        "approval_id": record.get("approval_id", "legacy-v1"),
        "approval_record_hash": record_hash,
    }


def check_feature(
    controls_path: Path | None,
    feature: str,
    feature_version: str,
    scope: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    if feature not in FEATURE_MODES:
        raise GateError(
            "E_FEATURE_DISABLED",
            f"未知功能：{feature}",
            ["feature"],
        )
    profile = runtime_profile()
    path, source = resolve_controls_path(controls_path, profile)
    controls, controls_hash = load_protected_json(path, "功能控制文件")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if controls.get("schema_version") == "1.0.0":
        if profile == "production":
            raise GateError(
                "E_FEATURE_DISABLED",
                "生产模式不接受兼容版 v1 控制记录。",
                ["feature_controls.schema_version"],
            )
        return _check_legacy_v1(
            controls,
            controls_hash,
            source,
            feature,
            feature_version,
            scope,
            current,
        )
    return _check_v2(
        controls,
        controls_hash,
        source,
        feature,
        feature_version,
        scope,
        current,
        profile,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check a bounded divination feature control."
    )
    parser.add_argument("feature", choices=sorted(FEATURE_MODES))
    parser.add_argument("--feature-version", default="1.0.0")
    parser.add_argument("--scope", default="yuanbao-public-cn")
    parser.add_argument(
        "--controls",
        "--approvals",
        dest="controls",
        type=Path,
        help="Host control file; --approvals is retained as a compatibility alias.",
    )
    args = parser.parse_args()
    try:
        receipt = check_feature(
            args.controls,
            args.feature,
            args.feature_version,
            args.scope,
        )
        print(json.dumps({"ok": True, "receipt": receipt}, ensure_ascii=False, indent=2))
        return 0
    except GateError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": exc.code,
                        "message": str(exc),
                        "fields": exc.fields,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
