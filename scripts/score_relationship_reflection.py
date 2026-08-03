#!/usr/bin/env python3
"""Score a consent-based, non-diagnostic relationship reflection prototype."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ITEM_BANK_PATH = SCRIPT_DIR / "relationship_items.json"
SAFETY_CRITICAL_ITEMS = (3, 9)


class InputError(ValueError):
    def __init__(self, code: str, message: str, fields: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.fields = fields or []


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise InputError("E_FILE_NOT_FOUND", f"找不到文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise InputError(
            "E_INVALID_JSON",
            f"JSON 解析失败：第 {exc.lineno} 行第 {exc.colno} 列",
        ) from exc


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise InputError(
            "E_OUTPUT_EXISTS",
            "输出文件已存在；请为每次运行使用新的私有目录和唯一文件名。",
            ["output"],
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def load_bank() -> dict[str, Any]:
    bank = load_json(ITEM_BANK_PATH)
    if not isinstance(bank.get("items"), list) or len(bank["items"]) != 12:
        raise RuntimeError("Relationship item bank must contain exactly 12 items")
    return bank


def normalize_partner(raw: Any, partner_key: str) -> dict[int, int]:
    partner = raw.get(partner_key) if isinstance(raw, dict) else None
    if isinstance(partner, dict):
        extra_partner_fields = sorted(set(partner) - {"answers"})
        if extra_partner_fields:
            raise InputError(
                "E_INVALID_INPUT",
                f"{partner_key} 只允许 answers；不要附加姓名或身份信息。",
                [f"{partner_key}.{field}" for field in extra_partner_fields],
            )
    answers = partner.get("answers") if isinstance(partner, dict) else None
    if not isinstance(answers, dict):
        raise InputError(
            "E_INVALID_ANSWERS",
            f"{partner_key} 必须包含 answers 对象。",
            [f"{partner_key}.answers"],
        )

    expected = {str(index) for index in range(1, 13)}
    actual = set(answers)
    missing = sorted(expected - actual, key=int)
    extra = sorted(actual - expected)
    fields = [f"{partner_key}.answers.{item}" for item in missing + extra]
    if fields:
        raise InputError(
            "E_INVALID_ANSWERS",
            f"{partner_key} 的 answers 必须恰好包含题号 1—12。",
            fields,
        )

    normalized: dict[int, int] = {}
    invalid: list[str] = []
    for key, value in answers.items():
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
            invalid.append(f"{partner_key}.answers.{key}")
        else:
            normalized[int(key)] = value
    if invalid:
        raise InputError(
            "E_INVALID_ANSWERS",
            "每个答案都必须是 1—5 的整数。",
            sorted(invalid),
        )
    return normalized


def score_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise InputError("E_INVALID_INPUT", "根节点必须是 JSON 对象。")
    extra_root_fields = sorted(
        set(raw) - {"consent", "partner_a", "partner_b"}
    )
    if extra_root_fields:
        raise InputError(
            "E_INVALID_INPUT",
            "关系输入只允许 consent、partner_a 和 partner_b。",
            extra_root_fields,
        )
    consent = raw.get("consent")
    if not isinstance(consent, dict):
        raise InputError(
            "E_PARTNER_CONSENT",
            "必须提供双方分别确认的同意状态。",
            ["consent"],
        )
    extra_consent_fields = sorted(set(consent) - {"partner_a", "partner_b"})
    if extra_consent_fields:
        raise InputError(
            "E_INVALID_INPUT",
            "consent 只允许 partner_a 和 partner_b。",
            [f"consent.{field}" for field in extra_consent_fields],
        )
    missing_consent = [
        f"consent.{key}"
        for key in ("partner_a", "partner_b")
        if consent.get(key) is not True
    ]
    if missing_consent:
        raise InputError(
            "E_PARTNER_CONSENT",
            "双方都必须分别知情并明确同意；不得代填。",
            missing_consent,
        )

    bank = load_bank()
    answers_a = normalize_partner(raw, "partner_a")
    answers_b = normalize_partner(raw, "partner_b")
    input_hash = hashlib.sha256(
        json.dumps(
            raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    item_bank_hash = hashlib.sha256(ITEM_BANK_PATH.read_bytes()).hexdigest()

    safety_attention = any(
        answers[item_id] <= 2
        for answers in (answers_a, answers_b)
        for item_id in SAFETY_CRITICAL_ITEMS
    )
    if safety_attention:
        return {
            "schema_version": "1.0.0",
            "mode": "relationship-reflection",
            "run_id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "evidence": {
                "instrument": {
                    **bank["instrument"],
                    "item_bank_hash": f"sha256:{item_bank_hash}",
                },
                "consent": {"partner_a": True, "partner_b": True},
                "completed_items_per_partner": 12,
                "identifiers_collected": False,
                "input_hash": f"sha256:{input_hash}",
            },
            "result": {
                "combined_reflection_suppressed": True,
                "private_safety_check_required": True,
                "not_a_compatibility_score": True,
                "no_overall_score": True,
            },
            "quality": {
                "status": "pass_with_warnings",
                "warnings": [
                    "安全关键题触发私下核对；不要展示双方维度或共同沟通提示。"
                ],
                "response_patterns": {},
            },
            "safety": {
                "decision": "redirect",
                "reason_code": "E_RELATIONSHIP_SAFETY",
                "private_followup": True,
                "prohibited_uses": [
                    "诊断虐待或给关系去留结论",
                    "在恐惧、胁迫或暴力风险下安排双方共同练习",
                    "向任一方披露另一方具体触发了哪道题",
                ],
            },
        }

    by_dimension_a: dict[str, list[int]] = defaultdict(list)
    by_dimension_b: dict[str, list[int]] = defaultdict(list)
    for item in bank["items"]:
        dimension = item["dimension"]
        by_dimension_a[dimension].append(answers_a[item["id"]])
        by_dimension_b[dimension].append(answers_b[item["id"]])

    dimensions: dict[str, Any] = {}
    for dimension, metadata in bank["dimensions"].items():
        values_a = by_dimension_a[dimension]
        values_b = by_dimension_b[dimension]
        mean_a = round(sum(values_a) / len(values_a), 2)
        mean_b = round(sum(values_b) / len(values_b), 2)
        dimensions[dimension] = {
            "label_zh": metadata["label_zh"],
            "partner_a_mean": mean_a,
            "partner_b_mean": mean_b,
            "absolute_gap": round(abs(mean_a - mean_b), 2),
            "item_count": len(values_a),
            "conversation_prompt_zh": metadata["prompt_zh"],
        }

    warnings: list[str] = []
    patterns: dict[str, str] = {}
    for key, answers in (("partner_a", answers_a), ("partner_b", answers_b)):
        if len(set(answers.values())) == 1:
            patterns[key] = "straight_lining"
            warnings.append(f"{key} 的 12 题使用了同一个选项；请确认是否认真作答。")
        else:
            patterns[key] = "varied"

    return {
        "schema_version": "1.0.0",
        "mode": "relationship-reflection",
        "run_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "evidence": {
            "instrument": {
                **bank["instrument"],
                "item_bank_hash": f"sha256:{item_bank_hash}",
            },
            "consent": {"partner_a": True, "partner_b": True},
            "completed_items_per_partner": 12,
            "identifiers_collected": False,
            "input_hash": f"sha256:{input_hash}",
        },
        "result": {
            "dimensions": dimensions,
            "not_a_compatibility_score": True,
            "no_overall_score": True,
        },
        "quality": {
            "status": "pass_with_warnings" if warnings else "pass",
            "warnings": warnings,
            "response_patterns": patterns,
        },
        "safety": {
            "decision": "allow",
            "prohibited_uses": [
                "关系去留或婚姻决定",
                "暴力或胁迫场景中的共同沟通练习",
                "推断第三方忠诚、疾病或隐私",
                "生成匹配率或真爱指数",
            ],
        },
    }


def error_payload(error: InputError) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": error.code,
            "message": str(error),
            "fields": error.fields,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Score a non-diagnostic relationship reflection prototype."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.output and args.output.exists():
            raise InputError(
                "E_OUTPUT_EXISTS",
                "输出文件已存在；请为每次运行使用新的私有目录和唯一文件名。",
                ["output"],
            )
        payload = score_payload(load_json(args.input))
        if args.output:
            atomic_write_json(args.output, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except InputError as exc:
        print(json.dumps(error_payload(exc), ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    except Exception as exc:
        payload = {
            "ok": False,
            "error": {"code": "E_INTERNAL", "message": f"内部错误：{exc}", "fields": []},
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
