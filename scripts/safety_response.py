#!/usr/bin/env python3
"""Build and validate the separate response used after a safety redirect.

Normal fact/final result validation deliberately rejects redirect/refuse records.
This script supports the one currently implemented redirect: a relationship
questionnaire safety signal. It emits fixed, non-diagnostic copy and never
exposes scores, answers, dimensions, or which partner triggered the signal.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0.0"
RESPONSE_KIND = "safety-redirect"
SUPPORTED_REASON = "E_RELATIONSHIP_SAFETY"
MESSAGE = (
    "这次不生成双方分析。请先暂停共同流程，并分别确认自己此刻是否感到安全。"
)
NEXT_STEPS = [
    "不要向任一方披露另一方的逐题答案或具体触发项。",
    "若存在即时危险，优先离开风险环境并联系当地紧急服务。",
    "需要求助资源时，由宿主按用户所在地区提供经过核验的本地信息。",
]


class SafetyResponseError(ValueError):
    def __init__(self, code: str, message: str, fields: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.fields = fields or []


def canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise SafetyResponseError("E_FILE_NOT_FOUND", f"找不到文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise SafetyResponseError(
            "E_INVALID_JSON",
            f"JSON 解析失败：第 {exc.lineno} 行第 {exc.colno} 列。",
        ) from exc


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise SafetyResponseError(
            "E_OUTPUT_EXISTS",
            "输出文件已存在；请使用新的私有单次运行目录和文件名。",
            ["output"],
        )
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise SafetyResponseError(
            "E_OUTPUT_PATH",
            "输出目录必须是已存在的普通目录。",
            ["output"],
        )
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _validate_source(source: Any) -> None:
    if not isinstance(source, dict):
        raise SafetyResponseError("E_SAFETY_SOURCE", "安全转向来源必须是对象。")
    if source.get("schema_version") != SCHEMA_VERSION:
        raise SafetyResponseError(
            "E_SAFETY_SOURCE",
            "安全转向来源 schema_version 必须是 1.0.0。",
            ["schema_version"],
        )
    if source.get("mode") != "relationship-reflection":
        raise SafetyResponseError(
            "E_SAFETY_SOURCE",
            "当前只支持关系反思的独立安全转向响应。",
            ["mode"],
        )
    safety = source.get("safety")
    if not isinstance(safety, dict) or safety.get("decision") != "redirect":
        raise SafetyResponseError(
            "E_SAFETY_SOURCE",
            "来源必须明确 safety.decision=redirect。",
            ["safety.decision"],
        )
    if safety.get("reason_code") != SUPPORTED_REASON:
        raise SafetyResponseError(
            "E_SAFETY_SOURCE",
            "来源缺少受支持的关系安全原因码。",
            ["safety.reason_code"],
        )
    result = source.get("result")
    if not isinstance(result, dict):
        raise SafetyResponseError(
            "E_SAFETY_SOURCE", "来源 result 必须是对象。", ["result"]
        )
    if (
        result.get("combined_reflection_suppressed") is not True
        or result.get("private_safety_check_required") is not True
        or "dimensions" in result
    ):
        raise SafetyResponseError(
            "E_SAFETY_SOURCE",
            "来源必须抑制合并结果、要求私下安全核对且不得包含 dimensions。",
            ["result"],
        )


def build(source: Any) -> dict[str, Any]:
    _validate_source(source)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": RESPONSE_KIND,
        "run_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "decision": "redirect",
        "reason_code": SUPPORTED_REASON,
        "source_hash": canonical_hash(source),
        "message": MESSAGE,
        "next_steps": NEXT_STEPS,
        "diagnosis_or_relationship_conclusion": False,
        "combined_result_disclosed": False,
        "local_resource_lookup_required": True,
    }


def validate(response: Any, source: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(response, dict):
        return ["根节点必须是 JSON 对象"]
    try:
        _validate_source(source)
    except SafetyResponseError as exc:
        errors.append(f"source 未通过安全来源契约：{exc}")
    expected_exact = {
        "schema_version": SCHEMA_VERSION,
        "kind": RESPONSE_KIND,
        "decision": "redirect",
        "reason_code": SUPPORTED_REASON,
        "message": MESSAGE,
        "next_steps": NEXT_STEPS,
        "diagnosis_or_relationship_conclusion": False,
        "combined_result_disclosed": False,
        "local_resource_lookup_required": True,
    }
    allowed = set(expected_exact) | {"run_id", "created_at", "source_hash"}
    extra = sorted(set(response) - allowed)
    if extra:
        errors.append("安全转向响应含未允许字段：" + ", ".join(extra))
    for field, expected in expected_exact.items():
        if response.get(field) != expected:
            errors.append(f"{field} 与固定安全响应契约不一致")
    try:
        uuid.UUID(response.get("run_id", ""))
    except (ValueError, TypeError):
        errors.append("run_id 必须是 UUID")
    try:
        created = datetime.fromisoformat(
            str(response.get("created_at", "")).replace("Z", "+00:00")
        )
        if created.tzinfo is None:
            raise ValueError
    except ValueError:
        errors.append("created_at 必须是带时区的 ISO 8601 日期时间")
    source_hash = response.get("source_hash")
    if (
        not isinstance(source_hash, str)
        or len(source_hash) != 71
        or not source_hash.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in source_hash[7:])
    ):
        errors.append("source_hash 必须是 sha256: + 64 位小写十六进制")
    elif source_hash != canonical_hash(source):
        errors.append("source_hash 与本次提供的安全转向来源不一致")
    return errors


def error_payload(exc: SafetyResponseError) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {"code": exc.code, "message": str(exc), "fields": exc.fields},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or validate a safety redirect.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("input", type=Path)
    build_parser.add_argument("--output", required=True, type=Path)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("input", type=Path)
    validate_parser.add_argument("--source", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "build":
            payload = build(load_json(args.input))
            atomic_write_json(args.output, payload)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        errors = validate(load_json(args.input), load_json(args.source))
        print(
            json.dumps(
                {"ok": not errors, "errors": errors},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if not errors else 1
    except SafetyResponseError as exc:
        print(json.dumps(error_payload(exc), ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
