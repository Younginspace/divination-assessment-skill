#!/usr/bin/env python3
"""Render and score the original binary-choice 四向偏好快照."""

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
ITEM_BANK_PATH = SCRIPT_DIR / "type_preference_items.json"
AXIS_ORDER = (
    "interaction_energy",
    "information_focus",
    "decision_weighting",
    "action_organization",
)
EXPECTED_ITEM_IDS = set(range(1, 13))
ALLOWED_ANSWERS = {-1, 1}
EXPECTED_AXIS_LETTERS = {
    "interaction_energy": ("E", "I"),
    "information_focus": ("S", "N"),
    "decision_weighting": ("T", "F"),
    "action_organization": ("J", "P"),
}
CLARITY_LABELS_ZH = {
    "low": "低置信度",
    "provisional": "暂定倾向",
    "relatively_clear": "相对清晰",
}
FUNCTION_STACKS = {
    "ISTJ": ("Si", "Te", "Fi", "Ne"),
    "ISFJ": ("Si", "Fe", "Ti", "Ne"),
    "INFJ": ("Ni", "Fe", "Ti", "Se"),
    "INTJ": ("Ni", "Te", "Fi", "Se"),
    "ISTP": ("Ti", "Se", "Ni", "Fe"),
    "ISFP": ("Fi", "Se", "Ni", "Te"),
    "INFP": ("Fi", "Ne", "Si", "Te"),
    "INTP": ("Ti", "Ne", "Si", "Fe"),
    "ESTP": ("Se", "Ti", "Fe", "Ni"),
    "ESFP": ("Se", "Fi", "Te", "Ni"),
    "ENFP": ("Ne", "Fi", "Te", "Si"),
    "ENTP": ("Ne", "Ti", "Fe", "Si"),
    "ESTJ": ("Te", "Si", "Ne", "Fi"),
    "ESFJ": ("Fe", "Si", "Ne", "Ti"),
    "ENFJ": ("Fe", "Ni", "Se", "Ti"),
    "ENTJ": ("Te", "Ni", "Se", "Fi"),
}
FUNCTION_LABELS_ZH = {
    "Ti": "内向思维：在内部检验概念和逻辑是否自洽",
    "Te": "外向思维：用外部标准、结构和结果组织行动",
    "Fi": "内向情感：依据个人价值与真实感受作权衡",
    "Fe": "外向情感：关注关系氛围、共同期待与他人感受",
    "Si": "内向感觉：借既有经验和细节稳定理解当下",
    "Se": "外向感觉：直接回应眼前事实、体验与机会",
    "Ni": "内向直觉：收束线索，形成核心洞察或长期图景",
    "Ne": "外向直觉：扩展关联，探索多种可能与新组合",
}
FUNCTION_PLAIN_NAMES_ZH = {
    "Ti": "自己把逻辑想通",
    "Te": "用标准和计划推进",
    "Fi": "确认自己真心认不认可",
    "Fe": "照顾关系和共同感受",
    "Si": "用过往经验核对细节",
    "Se": "看清眼前事实并直接行动",
    "Ni": "从线索中收束核心方向",
    "Ne": "从一个点展开多种可能",
}
FUNCTION_PLAIN_EXPLANATIONS_ZH = {
    "Ti": (
        "遇到问题时，更容易先在脑中拆清概念、规则和因果，确认前后是否说得通。"
        "它不等于爱抬杠，而是习惯先建立一套自己能理解的逻辑。"
    ),
    "Te": (
        "事情需要落地时，更容易借助目标、优先级、步骤、截止时间和外部标准推进。"
        "它不等于强势，而是关注怎样把事情组织起来并完成。"
    ),
    "Fi": (
        "做决定时，更容易先问“这是不是我真正认可和在意的”，并留意选择是否违背自己的原则。"
        "它不等于情绪化，而是把个人价值和真实感受当作重要参照。"
    ),
    "Fe": (
        "做决定或沟通时，更容易先注意别人感受、关系氛围和大家能否形成共同期待。"
        "它不等于讨好，而是把人与人之间的影响当作重要信息。"
    ),
    "Si": (
        "需要稳定或核对时，更容易参考过去经验、熟悉做法和具体细节。"
        "它不等于保守，而是习惯用已经发生过的事实检查当下。"
    ),
    "Se": (
        "面对现场变化时，更容易先观察眼前真正发生了什么，并根据即时信息采取行动。"
        "它不等于冲动，而是对现实环境和当下机会比较敏感。"
    ),
    "Ni": (
        "面对许多零散线索时，更容易把它们收束成一个核心判断、长期方向或底层主题。"
        "它不等于预知未来，而是偏好寻找最能解释整体的主线。"
    ),
    "Ne": (
        "面对一个想法时，更容易继续联想到其他解释、连接和可选路线。"
        "它的优势是看见可能性，但有时也会因为选项太多而不容易马上收束。"
    ),
}
FUNCTION_SEQUENCE_ACTIONS_ZH = {
    "Ti": "把逻辑和规则想通",
    "Te": "用计划和标准推动落地",
    "Fi": "确认自己是否真心认可",
    "Fe": "确认关系和共同感受是否合适",
    "Si": "用过往经验核对细节",
    "Se": "看清眼前事实并直接行动",
    "Ni": "从线索中找出核心方向",
    "Ne": "探索还有哪些可能",
}
FUNCTION_ROLES_ZH = ("主要偏好", "辅助偏好", "第三偏好", "第四偏好")


class InputError(ValueError):
    """A user-correctable, structured input or output-path error."""

    def __init__(self, code: str, message: str, fields: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.fields = fields or []


class DuplicateKeyError(ValueError):
    """Raised when a JSON object contains an ambiguous duplicate key."""

    def __init__(self, key: str):
        super().__init__(key)
        self.key = key


class StructuredArgumentParser(argparse.ArgumentParser):
    """Convert command-line usage failures to the common JSON error contract."""

    def error(self, message: str) -> None:
        raise InputError("E_CLI_USAGE", f"命令行参数错误：{message}")


def unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(key)
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle, object_pairs_hook=unique_json_object)
    except FileNotFoundError as exc:
        raise InputError("E_FILE_NOT_FOUND", f"找不到文件：{path}", ["input"]) from exc
    except IsADirectoryError as exc:
        raise InputError(
            "E_INVALID_INPUT_PATH",
            f"输入路径必须是 JSON 文件，不能是目录：{path}",
            ["input"],
        ) from exc
    except PermissionError as exc:
        raise InputError(
            "E_FILE_UNREADABLE",
            f"没有权限读取输入文件：{path}",
            ["input"],
        ) from exc
    except UnicodeDecodeError as exc:
        raise InputError(
            "E_INVALID_ENCODING",
            "输入文件必须使用 UTF-8 编码。",
            ["input"],
        ) from exc
    except DuplicateKeyError as exc:
        raise InputError(
            "E_DUPLICATE_JSON_KEY",
            f"JSON 对象包含重复键：{exc.key}",
            [exc.key],
        ) from exc
    except json.JSONDecodeError as exc:
        raise InputError(
            "E_INVALID_JSON",
            f"JSON 解析失败：第 {exc.lineno} 行第 {exc.colno} 列",
            ["input"],
        ) from exc


def is_plain_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def load_bank() -> dict[str, Any]:
    try:
        bank = load_json(ITEM_BANK_PATH)
    except InputError as exc:
        raise RuntimeError(f"题库不可用（{exc.code}）：{exc}") from exc

    if not isinstance(bank, dict) or bank.get("schema_version") != "1.0.0":
        raise RuntimeError("题库 schema_version 必须是 1.0.0")

    instrument = bank.get("instrument")
    if not isinstance(instrument, dict):
        raise RuntimeError("题库 instrument 必须是对象")
    for field in (
        "name",
        "version",
        "source",
        "content_status",
        "language",
        "translation_status",
    ):
        if not is_nonempty_string(instrument.get(field)):
            raise RuntimeError(f"题库 instrument.{field} 必须是非空字符串")
    if instrument.get("official_affiliation") is not False:
        raise RuntimeError("题库必须明确 official_affiliation=false")
    if instrument.get("uses_official_item_bank_or_scoring") is not False:
        raise RuntimeError("题库必须明确不使用官方题库或计分")
    if instrument.get("not_a_diagnostic_instrument") is not True:
        raise RuntimeError("题库必须明确不是诊断工具")

    scale = bank.get("response_scale")
    allowed_values = scale.get("allowed_values") if isinstance(scale, dict) else None
    if (
        not isinstance(allowed_values, list)
        or any(not is_plain_int(value) for value in allowed_values)
        or set(allowed_values) != ALLOWED_ANSWERS
    ):
        raise RuntimeError("题库二选一 response_scale 必须恰好为 -1、1")

    axes = bank.get("axes")
    if not isinstance(axes, dict) or set(axes) != set(AXIS_ORDER):
        raise RuntimeError("题库必须恰好包含四个预期轴")

    expected_axis_items: dict[str, set[int]] = {}
    for axis_key in AXIS_ORDER:
        axis = axes[axis_key]
        if not isinstance(axis, dict) or not is_nonempty_string(axis.get("label_zh")):
            raise RuntimeError(f"题库 axes.{axis_key} 结构无效")
        positive = axis.get("positive_pole")
        negative = axis.get("negative_pole")
        for pole_name, pole in (("positive_pole", positive), ("negative_pole", negative)):
            if (
                not isinstance(pole, dict)
                or not is_nonempty_string(pole.get("key"))
                or not is_nonempty_string(pole.get("label_zh"))
                or not is_nonempty_string(pole.get("letter"))
            ):
                raise RuntimeError(f"题库 axes.{axis_key}.{pole_name} 结构无效")
        actual_letters = (positive["letter"], negative["letter"])
        if actual_letters != EXPECTED_AXIS_LETTERS[axis_key]:
            raise RuntimeError(
                f"题库 axes.{axis_key} 的四字母映射必须是 "
                f"{EXPECTED_AXIS_LETTERS[axis_key]}"
            )
        item_ids = axis.get("item_ids")
        if (
            not isinstance(item_ids, list)
            or len(item_ids) != 3
            or any(not is_plain_int(item_id) for item_id in item_ids)
            or len(set(item_ids)) != 3
        ):
            raise RuntimeError(f"题库 axes.{axis_key}.item_ids 必须恰好包含三题")
        expected_axis_items[axis_key] = set(item_ids)

    items = bank.get("items")
    if not isinstance(items, list) or len(items) != 12:
        raise RuntimeError("题库必须恰好包含 12 道主问题")
    ids = [item.get("id") for item in items if isinstance(item, dict)]
    if (
        len(ids) != 12
        or any(not is_plain_int(item_id) for item_id in ids)
        or set(ids) != EXPECTED_ITEM_IDS
    ):
        raise RuntimeError("题库主问题 id 必须恰好为 1—12")

    actual_axis_items: dict[str, set[int]] = defaultdict(set)
    for item in items:
        axis_key = item.get("axis")
        if axis_key not in axes:
            raise RuntimeError(f"题目 {item.get('id')} 引用了未知轴")
        if not is_nonempty_string(item.get("prompt_zh")):
            raise RuntimeError(f"题目 {item.get('id')} 缺少 prompt_zh")
        choice_a = item.get("choice_a")
        choice_b = item.get("choice_b")
        if not isinstance(choice_a, dict) or not isinstance(choice_b, dict):
            raise RuntimeError(f"题目 {item.get('id')} 必须包含 choice_a/choice_b")
        if (
            choice_a.get("pole") != axes[axis_key]["positive_pole"]["key"]
            or choice_b.get("pole") != axes[axis_key]["negative_pole"]["key"]
            or not is_nonempty_string(choice_a.get("text_zh"))
            or not is_nonempty_string(choice_b.get("text_zh"))
        ):
            raise RuntimeError(f"题目 {item.get('id')} 的选项与轴两端不一致")
        actual_axis_items[axis_key].add(item["id"])

    if any(
        actual_axis_items[axis_key] != expected_axis_items[axis_key]
        for axis_key in AXIS_ORDER
    ):
        raise RuntimeError("题库 axes.item_ids 与 items 的实际映射不一致")
    if set().union(*expected_axis_items.values()) != EXPECTED_ITEM_IDS:
        raise RuntimeError("四轴题号必须完整且不重复地覆盖 1—12")

    administration = bank.get("administration")
    item_order = (
        administration.get("item_order")
        if isinstance(administration, dict)
        else None
    )
    if (
        not isinstance(item_order, list)
        or any(not is_plain_int(item_id) for item_id in item_order)
        or len(item_order) != 12
        or set(item_order) != EXPECTED_ITEM_IDS
    ):
        raise RuntimeError("题库 administration.item_order 必须完整覆盖 1—12")

    boundaries = bank.get("boundaries")
    if not isinstance(boundaries, dict):
        raise RuntimeError("题库 boundaries 必须是对象")
    for field in (
        "independent_and_unofficial",
        "not_a_type_or_diagnosis",
        "not_for_high_impact_decisions",
        "no_percentiles_or_statistical_confidence_intervals",
        "four_letter_result_is_unofficial",
        "not_an_official_mbti_result",
    ):
        if boundaries.get(field) is not True:
            raise RuntimeError(f"题库 boundaries.{field} 必须为 true")
    if not is_nonempty_string(boundaries.get("disclaimer_zh")):
        raise RuntimeError("题库必须包含非空 disclaimer_zh")
    return bank


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if os.path.lexists(path):
        raise InputError(
            "E_OUTPUT_EXISTS",
            "输出路径已存在；脚本拒绝覆盖，请使用新的私有目录和唯一文件名。",
            ["output"],
        )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise InputError(
            "E_OUTPUT_PATH",
            f"无法创建输出目录：{exc}",
            ["output"],
        ) from exc

    fd: int | None = None
    temp_name: str | None = None
    try:
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = None
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp_name, path)
        except FileExistsError as exc:
            raise InputError(
                "E_OUTPUT_EXISTS",
                "输出路径已存在；脚本拒绝覆盖，请使用新的私有目录和唯一文件名。",
                ["output"],
            ) from exc
        except OSError as exc:
            raise InputError(
                "E_OUTPUT_PATH",
                f"无法创建输出文件：{exc}",
                ["output"],
            ) from exc
    finally:
        if fd is not None:
            os.close(fd)
        if temp_name is not None and os.path.exists(temp_name):
            os.unlink(temp_name)


def normalize_answers(raw: dict[str, Any]) -> dict[int, int]:
    answers = raw.get("answers")
    if not isinstance(answers, dict):
        raise InputError(
            "E_INVALID_ANSWERS",
            "输入必须包含 answers 对象。",
            ["answers"],
        )

    expected = {str(item_id) for item_id in EXPECTED_ITEM_IDS}
    actual = set(answers)
    missing = sorted(expected - actual, key=int)
    extra = sorted(actual - expected)
    fields = [f"answers.{key}" for key in missing + extra]
    if fields:
        raise InputError(
            "E_INVALID_ANSWERS",
            "answers 必须恰好包含题号 1—12。",
            fields,
        )

    normalized: dict[int, int] = {}
    invalid_fields: list[str] = []
    for key, value in answers.items():
        if not is_plain_int(value) or value not in ALLOWED_ANSWERS:
            invalid_fields.append(f"answers.{key}")
        else:
            normalized[int(key)] = value
    if invalid_fields:
        raise InputError(
            "E_INVALID_ANSWERS",
            "每题只允许选择 A 或 B；提交时请规范化为 A=1、B=-1。",
            sorted(invalid_fields),
        )
    return normalized


def render_questions(language: str) -> dict[str, Any]:
    if language != "zh-CN":
        raise InputError(
            "E_INVALID_LANGUAGE",
            "四向偏好快照目前只提供原创中文题，language 必须是 zh-CN。",
            ["language"],
        )
    bank = load_bank()
    items_by_id = {item["id"]: item for item in bank["items"]}
    questions = []
    for item_id in bank["administration"]["item_order"]:
        item = items_by_id[item_id]
        axis = bank["axes"][item["axis"]]
        questions.append(
            {
                "id": item["id"],
                "axis": {
                    "key": item["axis"],
                    "label_zh": axis["label_zh"],
                },
                "prompt_zh": item["prompt_zh"],
                "options": [
                    {
                        "id": "A",
                        "pole": item["choice_a"]["pole"],
                        "text_zh": item["choice_a"]["text_zh"],
                        "normalized_direction": 1,
                    },
                    {
                        "id": "B",
                        "pole": item["choice_b"]["pole"],
                        "text_zh": item["choice_b"]["text_zh"],
                        "normalized_direction": -1,
                    },
                ],
            }
        )

    return {
        "instrument": bank["instrument"],
        "language": language,
        "instructions_zh": bank["administration"]["instructions_zh"],
        "response_scale": bank["response_scale"],
        "questions": questions,
        "input_contract": {
            "language": "zh-CN",
            "answers": {
                "description": "必须恰好包含字符串题号 1—12；用户只选 A/B，提交时规范化为 A=1、B=-1。",
            },
        },
        "boundaries": bank["boundaries"],
    }


def score_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise InputError("E_INVALID_INPUT", "根节点必须是 JSON 对象。")
    allowed_root_fields = {"language", "answers"}
    extra_root_fields = sorted(set(raw) - allowed_root_fields)
    if extra_root_fields:
        raise InputError(
            "E_INVALID_INPUT",
            "输入只允许 language 和 answers；不要附加身份信息。",
            extra_root_fields,
        )

    language = raw.get("language", "zh-CN")
    if language != "zh-CN":
        raise InputError(
            "E_INVALID_LANGUAGE",
            "四向偏好快照目前只支持 zh-CN。",
            ["language"],
        )

    bank = load_bank()
    answers = normalize_answers(raw)
    items_by_axis: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in bank["items"]:
        items_by_axis[item["axis"]].append(item)

    base_sums = {
        axis_key: sum(answers[item["id"]] for item in items_by_axis[axis_key])
        for axis_key in AXIS_ORDER
    }
    input_hash = hashlib.sha256(
        json.dumps(
            raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    item_bank_hash = hashlib.sha256(ITEM_BANK_PATH.read_bytes()).hexdigest()

    scores: dict[str, Any] = {}
    warnings: list[str] = []

    for axis_key in AXIS_ORDER:
        axis = bank["axes"][axis_key]
        values = [answers[item["id"]] for item in items_by_axis[axis_key]]
        raw_sum = base_sums[axis_key]
        positive_count = sum(value == 1 for value in values)
        negative_count = sum(value == -1 for value in values)
        positive_percentage = round(positive_count / 3 * 100)
        negative_percentage = 100 - positive_percentage
        direction = 1 if raw_sum > 0 else -1
        leaning_pole = (
            axis["positive_pole"] if direction > 0 else axis["negative_pole"]
        )
        opposite_pole = (
            axis["negative_pole"] if direction > 0 else axis["positive_pole"]
        )
        leaning_percentage = (
            positive_percentage if direction > 0 else negative_percentage
        )
        opposite_percentage = 100 - leaning_percentage
        clarity = "relatively_clear" if leaning_percentage == 100 else "provisional"

        scores[axis_key] = {
            "label_zh": axis["label_zh"],
            "positive_pole": axis["positive_pole"],
            "negative_pole": axis["negative_pole"],
            "sum": raw_sum,
            "mean": round(raw_sum / 3, 2),
            "item_count": 3,
            "score_range": {
                "sum": [-3, 3],
                "mean": [-1, 1],
            },
            "base_position": "positive" if direction > 0 else "negative",
            "leaning": {
                "pole": leaning_pole["key"],
                "label_zh": leaning_pole["label_zh"],
            },
            "direction_source": "binary_choice_majority",
            "preference_percentage": {
                "letter": leaning_pole["letter"],
                "value": leaning_percentage,
                "opposite_letter": opposite_pole["letter"],
                "opposite_value": opposite_percentage,
                "basis": "share_of_three_binary_choices",
                "not_population_percentile": True,
            },
            "signal_clarity": {
                "status": clarity,
                "label_zh": CLARITY_LABELS_ZH[clarity],
                "low_confidence": False,
                "reason_codes": [],
                "reasons_zh": [],
                "not_a_statistical_confidence_interval": True,
            },
            "response_pattern": {
                "positive_count": positive_count,
                "negative_count": negative_count,
                "directional_conflict": positive_count > 0 and negative_count > 0,
            },
        }

    letters: list[str] = []
    four_letter_axis_map: dict[str, Any] = {}
    for axis_key in AXIS_ORDER:
        score = scores[axis_key]
        letter = score["preference_percentage"]["letter"]
        letters.append(letter)
        four_letter_axis_map[axis_key] = {
            "letter": letter,
            "percentage": score["preference_percentage"]["value"],
            "opposite_letter": score["preference_percentage"]["opposite_letter"],
            "opposite_percentage": score["preference_percentage"]["opposite_value"],
            "direction_source": score["direction_source"],
            "signal_clarity": score["signal_clarity"]["status"],
        }
    four_letter_code = "".join(letters)

    four_letter_result = {
        "code": four_letter_code,
        "status": "complete",
        "label_zh": "四字母偏好结果",
        "axis_order": list(AXIS_ORDER),
        "axis_map": four_letter_axis_map,
        "independently_derived": True,
        "official_mbti_result": False,
        "psychological_diagnosis": False,
        "display_disclaimer_zh": (
            "非官方简单测试｜结果来自 12 道原创题，仅供自我探索。"
        ),
    }

    function_codes = FUNCTION_STACKS[four_letter_code]
    derived_function_preferences = {
        "status": "heuristic_from_four_letter",
        "stack": [
            {
                "code": code,
                "role": FUNCTION_ROLES_ZH[index],
                "description_zh": FUNCTION_LABELS_ZH[code],
                "plain_name_zh": FUNCTION_PLAIN_NAMES_ZH[code],
                "plain_explanation_zh": FUNCTION_PLAIN_EXPLANATIONS_ZH[code],
            }
            for index, code in enumerate(function_codes)
        ],
        "summary": " → ".join(function_codes),
        "plain_summary_zh": " → ".join(
            f"{FUNCTION_PLAIN_NAMES_ZH[code]}（{code}）"
            for code in function_codes
        ),
        "plain_sequence_zh": " → ".join(
            FUNCTION_SEQUENCE_ACTIONS_ZH[code] for code in function_codes
        ),
        "sequence_explanation_zh": (
            "把这条链理解为常见的处理顺序，而不是能力排名："
            "排在前面的通常更自然，排在后面的更多在特定情境下补位。"
        ),
        "independently_measured": False,
        "model_note_zh": "由四字母偏好代号按常见类型学模型推导，未单独测量。",
    }

    unique_response_count = len(set(answers.values()))
    response_pattern = "varied"
    if unique_response_count == 1:
        response_pattern = "straight_lining"
        warnings.append("12 题全部选择同一侧；请确认是否按真实情况作答。")

    return {
        "schema_version": "1.0.0",
        "mode": "personality",
        "run_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "evidence": {
            "instrument": {
                **bank["instrument"],
                "item_bank_hash": f"sha256:{item_bank_hash}",
            },
            "response_scale": {
                "values": [-1, 1],
                "user_choices": ["A", "B"],
                "choice_a_value": 1,
                "choice_b_value": -1,
                "positive_supports": "choice_a",
                "negative_supports": "choice_b",
            },
            "completed_items": 12,
            "identifiers_collected": False,
            "input_hash": f"sha256:{input_hash}",
        },
        "result": {
            "scores": scores,
            "axis_order": list(AXIS_ORDER),
            "unresolved_axes": [],
            "four_letter_preference": four_letter_result,
            "derived_function_preferences": derived_function_preferences,
            "independent_and_unofficial": True,
            "not_a_type_or_diagnosis": True,
            "not_for_high_impact_decisions": True,
            "no_percentile_or_confidence_interval": True,
        },
        "quality": {
            "status": "pass_with_warnings" if warnings else "pass",
            "warnings": warnings,
            "response_pattern": response_pattern,
            "unique_response_count": unique_response_count,
            "low_confidence_axes": [],
        },
        "safety": {
            "decision": "allow_with_boundary",
            "disclaimer_zh": bank["boundaries"]["disclaimer_zh"],
            "prohibited_uses": [
                "心理或医疗诊断",
                "招聘、录取、晋升、裁员、分班或职业淘汰",
                "信贷、保险、医疗、法律或其他高影响决策",
                "宣称官方授权、与官方人格工具等价或输出其官方类型",
                "仅凭本结果决定职业、关系或人生选择",
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
    parser = StructuredArgumentParser(
        description="Render or score the original 四向偏好快照."
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        parser_class=StructuredArgumentParser,
    )

    questions_parser = subparsers.add_parser(
        "questions",
        help="Print the 12 binary-choice questions.",
    )
    questions_parser.add_argument(
        "--language",
        default="zh-CN",
        help="Question language; currently only zh-CN.",
    )

    score_parser = subparsers.add_parser(
        "score",
        help="Score a JSON answer file.",
    )
    score_parser.add_argument("input", type=Path)
    score_parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        if args.command == "questions":
            payload = render_questions(args.language)
        else:
            if os.path.lexists(args.output):
                raise InputError(
                    "E_OUTPUT_EXISTS",
                    "输出路径已存在；脚本拒绝覆盖，请使用新的私有目录和唯一文件名。",
                    ["output"],
                )
            payload = score_payload(load_json(args.input))
            atomic_write_json(args.output, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except InputError as exc:
        print(
            json.dumps(error_payload(exc), ensure_ascii=False, indent=2),
            file=sys.stderr,
        )
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
