#!/usr/bin/env python3
"""Render and score the public-domain Mini-IPIP 20-item prototype."""

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
ITEM_BANK_PATH = SCRIPT_DIR / "mini_ipip_items.json"
TRAIT_LABELS_ZH = {
    "extraversion": "外向性",
    "agreeableness": "宜人性",
    "conscientiousness": "尽责性",
    "neuroticism": "情绪敏感性",
    "imagination": "想象与开放倾向",
}


class InputError(ValueError):
    """A user-correctable input error."""

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


def load_bank() -> dict[str, Any]:
    bank = load_json(ITEM_BANK_PATH)
    items = bank.get("items")
    if not isinstance(items, list) or len(items) != 20:
        raise RuntimeError("Mini-IPIP item bank must contain exactly 20 items")
    return bank


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


def normalize_answers(raw: Any) -> dict[int, int]:
    answers = raw.get("answers") if isinstance(raw, dict) else None
    if not isinstance(answers, dict):
        raise InputError(
            "E_INVALID_ANSWERS",
            "输入必须包含 answers 对象。",
            ["answers"],
        )

    expected = {str(index) for index in range(1, 21)}
    actual = set(answers)
    missing = sorted(expected - actual, key=int)
    extra = sorted(actual - expected)
    fields = [f"answers.{item}" for item in missing + extra]
    if fields:
        raise InputError(
            "E_INVALID_ANSWERS",
            "answers 必须恰好包含题号 1—20。",
            fields,
        )

    normalized: dict[int, int] = {}
    invalid_fields: list[str] = []
    for key, value in answers.items():
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
            invalid_fields.append(f"answers.{key}")
        else:
            normalized[int(key)] = value
    if invalid_fields:
        raise InputError(
            "E_INVALID_ANSWERS",
            "每个答案都必须是 1—5 的整数。",
            sorted(invalid_fields),
        )
    return normalized


def render_questions(language: str) -> dict[str, Any]:
    bank = load_bank()
    text_key = "zh_cn_draft" if language == "zh-CN" else "en"
    questions = [
        {"id": item["id"], "text": item[text_key]}
        for item in bank["items"]
    ]
    return {
        "instrument": bank["instrument"],
        "language": language,
        "translation_status": (
            bank["instrument"]["zh_cn_translation"]
            if language == "zh-CN"
            else "original"
        ),
        "instructions": (
            "按最近几个月通常的自己作答：1=非常不符合，5=非常符合。"
            if language == "zh-CN"
            else "Answer for your typical self in recent months: 1=very inaccurate, 5=very accurate."
        ),
        "response_scale": bank["response_scale"][language],
        "questions": questions,
    }


def score_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise InputError("E_INVALID_INPUT", "根节点必须是 JSON 对象。")
    extra_root_fields = sorted(set(raw) - {"language", "answers"})
    if extra_root_fields:
        raise InputError(
            "E_INVALID_INPUT",
            "人格输入只允许 language 和 answers；不要附加身份信息。",
            extra_root_fields,
        )
    language = raw.get("language", "zh-CN")
    if language not in {"zh-CN", "en"}:
        raise InputError(
            "E_INVALID_LANGUAGE",
            "language 只支持 zh-CN 或 en。",
            ["language"],
        )

    bank = load_bank()
    answers = normalize_answers(raw)
    input_hash = hashlib.sha256(
        json.dumps(
            raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    item_bank_hash = hashlib.sha256(ITEM_BANK_PATH.read_bytes()).hexdigest()
    trait_values: dict[str, list[int]] = defaultdict(list)
    for item in bank["items"]:
        answer = answers[item["id"]]
        keyed_value = 6 - answer if item["reverse"] else answer
        trait_values[item["trait"]].append(keyed_value)

    scores: dict[str, Any] = {}
    for trait in TRAIT_LABELS_ZH:
        values = trait_values[trait]
        if len(values) != 4:
            raise RuntimeError(f"Trait {trait} must have exactly four items")
        scores[trait] = {
            "label_zh": TRAIT_LABELS_ZH[trait],
            "sum": sum(values),
            "mean": round(sum(values) / len(values), 2),
            "item_count": len(values),
        }

    unique_response_count = len(set(answers.values()))
    warnings: list[str] = []
    response_pattern = "varied"
    if unique_response_count == 1:
        response_pattern = "straight_lining"
        warnings.append("20 题使用了同一个选项；请确认是否按真实情况作答。")

    return {
        "schema_version": "1.0.0",
        "mode": "personality",
        "run_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "evidence": {
            "instrument": {
                "name": bank["instrument"]["name"],
                "version": bank["instrument"]["version"],
                "source": bank["instrument"]["source"],
                "license_status": bank["instrument"]["license_status"],
                "language": language,
                "translation_status": (
                    bank["instrument"]["zh_cn_translation"]
                    if language == "zh-CN"
                    else "original"
                ),
                "item_bank_hash": f"sha256:{item_bank_hash}",
            },
            "response_scale": "1-5",
            "completed_items": 20,
            "input_hash": f"sha256:{input_hash}",
        },
        "result": {
            "scores": scores,
            "score_range": {"sum": [4, 20], "mean": [1, 5]},
            "not_a_type_or_diagnosis": True,
        },
        "quality": {
            "status": "pass_with_warnings" if warnings else "pass",
            "warnings": warnings,
            "response_pattern": response_pattern,
            "unique_response_count": unique_response_count,
        },
        "safety": {
            "decision": "allow",
            "prohibited_uses": [
                "心理或医疗诊断",
                "招聘、录取或职业淘汰",
                "未建立常模时输出百分位",
                "派生 MBTI 类型或固定人格标签",
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render or score the Mini-IPIP 20-item prototype."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    questions_parser = subparsers.add_parser("questions", help="Print the item set.")
    questions_parser.add_argument(
        "--language", choices=["zh-CN", "en"], default="zh-CN"
    )

    score_parser = subparsers.add_parser("score", help="Score a JSON answer file.")
    score_parser.add_argument("input", type=Path)
    score_parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "questions":
            payload = render_questions(args.language)
        else:
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
            "error": {
                "code": "E_INTERNAL",
                "message": f"内部错误：{exc}",
                "fields": [],
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
