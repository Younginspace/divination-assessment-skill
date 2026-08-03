#!/usr/bin/env python3
"""Validate fact-stage and final-stage result files."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from feature_gate import GateError, check_feature, sha256_json
from validate_chart_adapter import validate_chart


SCRIPT_DIR = Path(__file__).resolve().parent
CURRENT_DECK_PATH = SCRIPT_DIR / "oracle_deck.json"
LEGACY_DECK_PATHS = {
    "major-arcana-reflection-22-v1": SCRIPT_DIR / "oracle_deck_v1.json",
}
MINI_IPIP_PATH = SCRIPT_DIR / "mini_ipip_items.json"
RELATIONSHIP_ITEMS_PATH = SCRIPT_DIR / "relationship_items.json"
TYPE_PREFERENCE_PATH = SCRIPT_DIR / "type_preference_items.json"
ALLOWED_MODES = {
    "personality",
    "relationship-reflection",
    "oracle-reflection",
    "chart-interpretation",
    "report-followup",
}
ALLOWED_DECISIONS = {"allow", "allow_with_boundary", "redirect", "refuse"}
ALLOWED_QUALITY = {"pass", "pass_with_warnings", "fail"}
ALLOWED_EPISTEMIC_STATUS = {
    "self_report",
    "measured",
    "traditional",
    "reflective",
    "user_provided_unverified",
}
ALLOWED_SUPPORT_STRENGTH = {"strong", "mixed", "weak"}
ALLOWED_FIT_STATUS = {"not_checked", "consistent", "mixed", "inconsistent"}
PERSONALITY_TRAITS = {
    "extraversion",
    "agreeableness",
    "conscientiousness",
    "neuroticism",
    "imagination",
}
TYPE_PREFERENCE_AXES = {
    "interaction_energy",
    "information_focus",
    "decision_weighting",
    "action_organization",
}
TYPE_PREFERENCE_AXIS_ORDER = (
    "interaction_energy",
    "information_focus",
    "decision_weighting",
    "action_organization",
)
TYPE_PREFERENCE_LETTERS = {
    "interaction_energy": {
        "external_activation": "E",
        "internal_settling": "I",
    },
    "information_focus": {
        "concrete_evidence": "S",
        "pattern_possibilities": "N",
    },
    "decision_weighting": {
        "principled_reasoning": "T",
        "value_awareness": "F",
    },
    "action_organization": {
        "planned_closure": "J",
        "flexible_exploration": "P",
    },
}
TYPE_PREFERENCE_FUNCTION_STACKS = {
    "ISTJ": ["Si", "Te", "Fi", "Ne"],
    "ISFJ": ["Si", "Fe", "Ti", "Ne"],
    "INFJ": ["Ni", "Fe", "Ti", "Se"],
    "INTJ": ["Ni", "Te", "Fi", "Se"],
    "ISTP": ["Ti", "Se", "Ni", "Fe"],
    "ISFP": ["Fi", "Se", "Ni", "Te"],
    "INFP": ["Fi", "Ne", "Si", "Te"],
    "INTP": ["Ti", "Ne", "Si", "Fe"],
    "ESTP": ["Se", "Ti", "Fe", "Ni"],
    "ESFP": ["Se", "Fi", "Te", "Ni"],
    "ENFP": ["Ne", "Fi", "Te", "Si"],
    "ENTP": ["Ne", "Ti", "Fe", "Si"],
    "ESTJ": ["Te", "Si", "Ne", "Fi"],
    "ESFJ": ["Fe", "Si", "Ne", "Ti"],
    "ENFJ": ["Fe", "Ni", "Se", "Ti"],
    "ENTJ": ["Te", "Ni", "Se", "Fi"],
}
TYPE_PREFERENCE_FUNCTION_PLAIN_NAMES = {
    "Ti": "自己把逻辑想通",
    "Te": "用标准和计划推进",
    "Fi": "确认自己真心认不认可",
    "Fe": "照顾关系和共同感受",
    "Si": "用过往经验核对细节",
    "Se": "看清眼前事实并直接行动",
    "Ni": "从线索中收束核心方向",
    "Ne": "从一个点展开多种可能",
}
TYPE_PREFERENCE_FUNCTION_SEQUENCE_ACTIONS = {
    "Ti": "把逻辑和规则想通",
    "Te": "用计划和标准推动落地",
    "Fi": "确认自己是否真心认可",
    "Fe": "确认关系和共同感受是否合适",
    "Si": "用过往经验核对细节",
    "Se": "看清眼前事实并直接行动",
    "Ni": "从线索中找出核心方向",
    "Ne": "探索还有哪些可能",
}
RELATIONSHIP_DIMENSIONS = {
    "emotional_safety",
    "repair",
    "boundaries",
    "shared_expectations",
}
SHA256_WITH_PREFIX = re.compile(r"^sha256:[0-9a-f]{64}$")
ABSOLUTE_LANGUAGE = ("一定", "注定", "百分百", "绝对准确", "治愈", "改命转运")
PROHIBITED_HIGH_IMPACT_PHRASES = (
    "建议买入",
    "建议卖出",
    "全部积蓄",
    "所有积蓄",
    "全部存款",
    "所有存款",
    "梭哈",
    "满仓",
    "稳赚",
    "保本高收益",
    "应该下注",
    "建议下注",
    "适合下注",
    "必中",
    "包中",
    "翻本",
    "建议停药",
    "可以停药",
    "应该停药",
    "不用吃药",
    "停止服药",
    "自行减药",
    "自行加药",
    "自行换药",
    "不用就医",
    "不必看医生",
    "拒绝治疗",
    "替代治疗",
    "怀孕概率",
    "受孕概率",
    "生男生女",
    "建议流产",
    "建议堕胎",
    "建议终止妊娠",
    "不必避孕",
    "死亡时间",
    "寿命还有",
    "活不过",
    "会去世",
    "将会死亡",
    "大限将至",
    "必定结婚",
    "肯定离婚",
    "录取概率",
    "一定录取",
    "一定考上",
    "稳上岸",
    "肯定落榜",
    "建议放弃升学",
    "建议辞职",
    "应该辞职",
    "适合辞职",
    "建议跳槽",
    "应该跳槽",
    "一定能拿到offer",
    "肯定被录用",
    "一定会失业",
    "保证治愈",
    "付费化解",
    "转运服务",
    "对方出轨",
    "对方犯罪",
)
HIGH_IMPACT_CATEGORY_LABELS = {
    "finance": "投资或财务决策",
    "medical": "医疗或用药决策",
    "legal": "法律或诉讼决策",
    "gambling": "赌博或博彩决策",
    "fertility": "生育或妊娠决策",
    "mortality": "死亡或寿命预测",
    "education_employment": "升学或就业决策",
}
TRADITIONAL_DISCLAIMER = (
    "AI生成内容｜传统文化与自我反思，仅供参考，不是经科学验证的预测，"
    "也不构成医疗、法律、投资或其他专业建议。"
)


def contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


NEGATION_CONTEXT = re.compile(
    r"(?:不能|不可以|不可|不得|禁止|不要|不应|无需|无法|并非|不是|不代表|"
    r"拒绝|避免|别|未|不)[^，。；！？]{0,4}$"
)


def matching_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


def assertive_matches(text: str, terms: tuple[str, ...]) -> list[str]:
    """Match terms unless the local clause explicitly negates or forbids them."""
    matches: list[str] = []
    for term in terms:
        start = 0
        while True:
            index = text.find(term, start)
            if index < 0:
                break
            prefix = text[max(0, index - 12) : index]
            if not NEGATION_CONTEXT.search(prefix):
                matches.append(term)
                break
            start = index + len(term)
    return matches


def detect_high_impact_findings(text: str) -> list[dict[str, Any]]:
    """Return auditable high-impact findings, including the matched term combination."""
    normalized = re.sub(r"\s+", "", text).lower()
    findings: dict[str, dict[str, Any]] = {}

    explicit_matches = assertive_matches(
        normalized,
        tuple(phrase.lower() for phrase in PROHIBITED_HIGH_IMPACT_PHRASES),
    )
    if explicit_matches:
        findings["explicit"] = {
            "category": "explicit",
            "trigger_type": "high_risk_phrase",
            "matched_terms": explicit_matches[:3],
        }

    def add_cooccurrence(
        category: str,
        objects: tuple[str, ...],
        actions_or_outcomes: tuple[str, ...],
    ) -> None:
        object_matches = matching_terms(normalized, objects)
        action_matches = assertive_matches(normalized, actions_or_outcomes)
        if object_matches and action_matches:
            findings[category] = {
                "category": category,
                "trigger_type": "object_action_combination",
                "matched_terms": [object_matches[0], action_matches[0]],
            }

    finance_objects = (
        "股票",
        "基金",
        "证券",
        "期货",
        "期权",
        "外汇",
        "虚拟币",
        "加密货币",
        "比特币",
        "理财",
        "投资",
        "仓位",
        "积蓄",
        "存款",
        "养老金",
        "房产",
    )
    finance_outcomes_or_actions = (
        "买入",
        "卖出",
        "投入",
        "加仓",
        "减仓",
        "清仓",
        "满仓",
        "梭哈",
        "贷款",
        "借钱",
        "抵押",
        "高回报",
        "高收益",
        "稳赚",
        "翻倍",
        "暴涨",
        "暴跌",
        "抄底",
        "止盈",
        "止损",
        "会赚",
        "能赚",
        "适合买",
        "建议买",
        "应该买",
    )
    add_cooccurrence("finance", finance_objects, finance_outcomes_or_actions)

    medication_terms = (
        "药",
        "药物",
        "处方",
        "剂量",
        "胰岛素",
        "抗抑郁",
        "抗生素",
        "治疗",
        "就医",
        "医生",
        "手术",
    )
    medical_actions = (
        "停药",
        "断药",
        "减药",
        "加药",
        "换药",
        "撤药",
        "停止服用",
        "不用吃",
        "自行调整",
        "不用就医",
        "不必看",
        "拒绝治疗",
        "替代治疗",
        "取消手术",
        "放弃治疗",
    )
    add_cooccurrence("medical", medication_terms, medical_actions)

    legal_objects = (
        "起诉",
        "诉讼",
        "打官司",
        "上诉",
        "撤诉",
        "仲裁",
        "报警",
        "认罪",
        "签合同",
        "签署合同",
        "离婚",
        "证据",
    )
    legal_actions_or_outcomes = (
        "建议",
        "应该",
        "适合",
        "必须",
        "立刻",
        "马上",
        "一定赢",
        "必胜",
        "胜诉",
        "败诉",
        "不用请律师",
        "不必请律师",
        "销毁",
        "隐瞒",
        "伪造",
    )
    add_cooccurrence("legal", legal_objects, legal_actions_or_outcomes)

    gambling_objects = (
        "赌博",
        "博彩",
        "彩票",
        "赌球",
        "赌场",
        "赌局",
        "赔率",
        "盘口",
        "下注",
        "押注",
    )
    gambling_actions_or_outcomes = (
        "下注",
        "押注",
        "梭哈",
        "倍投",
        "买号",
        "买彩",
        "稳赢",
        "必中",
        "包中",
        "翻本",
        "高回报",
        "赚回来",
    )
    add_cooccurrence("gambling", gambling_objects, gambling_actions_or_outcomes)

    fertility_objects = (
        "怀孕",
        "受孕",
        "备孕",
        "生育",
        "妊娠",
        "流产",
        "堕胎",
        "试管",
        "胚胎",
        "胎儿",
        "避孕",
        "生男",
        "生女",
    )
    fertility_predictions_or_actions = (
        "概率",
        "几率",
        "一定",
        "肯定",
        "会怀",
        "能怀",
        "不能怀",
        "容易怀",
        "建议流产",
        "应该流产",
        "建议堕胎",
        "终止妊娠",
        "继续妊娠",
        "不必避孕",
        "不用避孕",
        "生男",
        "生女",
    )
    add_cooccurrence("fertility", fertility_objects, fertility_predictions_or_actions)

    mortality_objects = (
        "死亡",
        "去世",
        "寿命",
        "阳寿",
        "大限",
        "活不过",
        "死期",
        "身亡",
    )
    mortality_predictions = (
        "时间",
        "日期",
        "年份",
        "什么时候",
        "会",
        "将",
        "快要",
        "即将",
        "还有",
        "活不过",
        "大限",
    )
    add_cooccurrence("mortality", mortality_objects, mortality_predictions)

    education_employment_objects = (
        "录取",
        "高考",
        "考研",
        "考公",
        "升学",
        "志愿",
        "保送",
        "上岸",
        "落榜",
        "offer",
        "录用",
        "入职",
        "辞职",
        "跳槽",
        "转行",
        "就业",
        "失业",
        "裁员",
    )
    education_employment_predictions_or_actions = (
        "一定",
        "肯定",
        "必然",
        "稳",
        "概率",
        "几率",
        "会被",
        "能拿",
        "拿不到",
        "建议",
        "应该",
        "适合",
        "必须",
        "放弃",
    )
    add_cooccurrence(
        "education_employment",
        education_employment_objects,
        education_employment_predictions_or_actions,
    )

    return [findings[key] for key in sorted(findings)]


def detect_high_impact_categories(text: str) -> list[str]:
    """Compatibility wrapper returning only category identifiers."""
    return [finding["category"] for finding in detect_high_impact_findings(text)]


def validate_high_impact_text(text: str, field: str, errors: list[str]) -> None:
    findings = detect_high_impact_findings(text)
    if not findings:
        return
    labels = [
        "明确禁止词组"
        if finding["category"] == "explicit"
        else HIGH_IMPACT_CATEGORY_LABELS[finding["category"]]
        for finding in findings
    ]
    evidence = "；".join(
        "完整高风险表达“" + " / ".join(finding["matched_terms"]) + "”"
        if finding["trigger_type"] == "high_risk_phrase"
        else "“" + "”与“".join(finding["matched_terms"]) + "”共同出现"
        for finding in findings
    )
    errors.append(
        f"E_HIGH_IMPACT：{field} 涉及{'、'.join(labels)}。"
        f"识别依据：{evidence}；不是因单独出现某个普通词而屏蔽。"
        "请改写为核对现实信息、风险或可逆下一步。"
    )


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


def require_dict(
    payload: dict[str, Any], field: str, errors: list[str]
) -> dict[str, Any]:
    value = payload.get(field)
    if not isinstance(value, dict):
        errors.append(f"{field} 必须是对象")
        return {}
    return value


def validate_datetime(value: Any, field: str, errors: list[str]) -> None:
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


def validate_uuid(value: Any, field: str, errors: list[str]) -> None:
    if not is_nonempty_string(value):
        errors.append(f"{field} 必须是 UUID")
        return
    try:
        uuid.UUID(value)
    except ValueError:
        errors.append(f"{field} 必须是 UUID，不能放手机号或其他个人标识")


def validate_string_list(
    value: Any,
    field: str,
    errors: list[str],
    *,
    allow_empty: bool = True,
) -> None:
    if not isinstance(value, list) or any(
        not is_nonempty_string(item) for item in value
    ):
        errors.append(f"{field} 必须是非空字符串组成的数组")
    elif not allow_empty and not value:
        errors.append(f"{field} 不能为空")


def local_file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def validate_common(payload: Any) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(payload, dict):
        return ["根节点必须是 JSON 对象"], warnings
    if "__load_error__" in payload:
        return [payload["__load_error__"]], warnings
    if payload.get("schema_version") != "1.0.0":
        errors.append("schema_version 必须是 1.0.0")
    if payload.get("mode") not in ALLOWED_MODES:
        errors.append("mode 不在允许列表")
    validate_uuid(payload.get("run_id"), "run_id", errors)
    validate_datetime(payload.get("created_at"), "created_at", errors)

    require_dict(payload, "evidence", errors)
    require_dict(payload, "result", errors)
    quality = require_dict(payload, "quality", errors)
    safety = require_dict(payload, "safety", errors)
    if quality:
        if quality.get("status") not in ALLOWED_QUALITY:
            errors.append("quality.status 不在允许列表")
        validate_string_list(quality.get("warnings"), "quality.warnings", errors)
    if safety:
        if safety.get("decision") not in ALLOWED_DECISIONS:
            errors.append("safety.decision 不在允许列表")
        validate_string_list(
            safety.get("prohibited_uses"), "safety.prohibited_uses", errors
        )
    return errors, warnings


def validate_sha256(value: Any, field: str, errors: list[str]) -> None:
    if not is_nonempty_string(value) or not SHA256_WITH_PREFIX.fullmatch(value):
        errors.append(f"{field} 必须是 sha256: + 64 位小写十六进制")


def validate_type_preference(
    payload: dict[str, Any],
    instrument: dict[str, Any],
    errors: list[str],
) -> None:
    evidence = payload.get("evidence", {})
    if instrument.get("item_bank_hash") != local_file_hash(TYPE_PREFERENCE_PATH):
        errors.append("evidence.instrument.item_bank_hash 与本地四向偏好题库不一致")
    if instrument.get("source") != "independently-developed-original-zh-CN":
        errors.append("四向偏好快照必须标明独立原创来源")
    if instrument.get("official_affiliation") is not False:
        errors.append("四向偏好快照必须标明 official_affiliation=false")
    if instrument.get("uses_official_item_bank_or_scoring") is not False:
        errors.append("四向偏好快照不得使用官方题库或计分")
    if instrument.get("translation_status") != "original-zh-CN-unvalidated":
        errors.append("四向偏好快照必须标为 original-zh-CN-unvalidated")
    if evidence.get("completed_items") != 12:
        errors.append("四向偏好快照 evidence.completed_items 必须是 12")
    validate_sha256(evidence.get("input_hash"), "evidence.input_hash", errors)

    result = payload.get("result", {})
    scores = result.get("scores") if isinstance(result, dict) else None
    if not isinstance(scores, dict) or set(scores) != TYPE_PREFERENCE_AXES:
        errors.append("result.scores 必须恰好包含四个偏好轴")
        return
    for axis in sorted(TYPE_PREFERENCE_AXES):
        score = scores.get(axis)
        if not isinstance(score, dict):
            errors.append(f"result.scores.{axis} 必须是对象")
            continue
        total = score.get("sum")
        mean = score.get("mean")
        if (
            isinstance(total, bool)
            or not isinstance(total, int)
            or total not in {-3, -1, 1, 3}
        ):
            errors.append(f"result.scores.{axis}.sum 必须是 -3、-1、1、3 之一")
        if (
            isinstance(mean, bool)
            or not isinstance(mean, (int, float))
            or not -1 <= mean <= 1
        ):
            errors.append(f"result.scores.{axis}.mean 必须在 -1—1")
        if (
            isinstance(total, int)
            and isinstance(mean, (int, float))
            and not isinstance(mean, bool)
            and abs(mean - round(total / 3, 2)) > 0.005
        ):
            errors.append(f"result.scores.{axis}.mean 必须等于 sum / 3（两位小数）")
        if score.get("item_count") != 3:
            errors.append(f"result.scores.{axis}.item_count 必须是 3")
        clarity = score.get("signal_clarity")
        if not isinstance(clarity, dict) or clarity.get("status") not in {
            "provisional",
            "relatively_clear",
        }:
            errors.append(f"result.scores.{axis}.signal_clarity 无效")
        percentage = score.get("preference_percentage")
        if not isinstance(percentage, dict):
            errors.append(f"result.scores.{axis}.preference_percentage 必须是对象")
        elif isinstance(total, int) and total in {-3, -1, 1, 3}:
            leaning_count = (3 + abs(total)) // 2
            expected_percentage = round(leaning_count / 3 * 100)
            expected_letter = (
                TYPE_PREFERENCE_LETTERS[axis][score["leaning"]["pole"]]
                if isinstance(score.get("leaning"), dict)
                and score["leaning"].get("pole") in TYPE_PREFERENCE_LETTERS[axis]
                else None
            )
            axis_letters = set(TYPE_PREFERENCE_LETTERS[axis].values())
            expected_opposite = next(
                (letter for letter in axis_letters if letter != expected_letter),
                None,
            )
            if percentage.get("letter") != expected_letter:
                errors.append(
                    f"result.scores.{axis}.preference_percentage.letter 与倾向不一致"
                )
            if percentage.get("value") != expected_percentage:
                errors.append(
                    f"result.scores.{axis}.preference_percentage.value 与二选一计数不一致"
                )
            if percentage.get("opposite_letter") != expected_opposite:
                errors.append(
                    f"result.scores.{axis}.preference_percentage.opposite_letter 无效"
                )
            if percentage.get("opposite_value") != 100 - expected_percentage:
                errors.append(
                    f"result.scores.{axis}.preference_percentage.opposite_value 无效"
                )
            if percentage.get("basis") != "share_of_three_binary_choices":
                errors.append(
                    f"result.scores.{axis}.preference_percentage.basis 无效"
                )
            if percentage.get("not_population_percentile") is not True:
                errors.append(
                    f"result.scores.{axis}.preference_percentage 必须声明不是人口百分位"
                )
    expected_letters: list[str] = []
    for axis in TYPE_PREFERENCE_AXIS_ORDER:
        score = scores[axis]
        leaning = score.get("leaning") if isinstance(score, dict) else None
        if not isinstance(leaning, dict):
            expected_letters = []
            break
        pole = leaning.get("pole")
        letter = TYPE_PREFERENCE_LETTERS[axis].get(pole)
        if letter is None:
            errors.append(f"result.scores.{axis}.leaning.pole 无效")
            expected_letters = []
            break
        expected_letters.append(letter)

    expected_code = "".join(expected_letters) if len(expected_letters) == 4 else None
    four_letter = result.get("four_letter_preference")
    if not isinstance(four_letter, dict):
        errors.append("result.four_letter_preference 必须是对象")
    else:
        expected_status = "complete" if expected_code else None
        if four_letter.get("code") != expected_code:
            errors.append("result.four_letter_preference.code 与四轴倾向不一致")
        if four_letter.get("status") != expected_status:
            errors.append("result.four_letter_preference.status 与四轴完成状态不一致")
        if four_letter.get("axis_order") != list(TYPE_PREFERENCE_AXIS_ORDER):
            errors.append("result.four_letter_preference.axis_order 无效")
        if four_letter.get("independently_derived") is not True:
            errors.append(
                "result.four_letter_preference.independently_derived 必须为 true"
            )
        if four_letter.get("official_mbti_result") is not False:
            errors.append(
                "result.four_letter_preference.official_mbti_result 必须为 false"
            )
        if four_letter.get("psychological_diagnosis") is not False:
            errors.append(
                "result.four_letter_preference.psychological_diagnosis 必须为 false"
            )
        if not is_nonempty_string(four_letter.get("display_disclaimer_zh")):
            errors.append(
                "result.four_letter_preference.display_disclaimer_zh 必须是非空字符串"
            )

    functions = result.get("derived_function_preferences")
    if not isinstance(functions, dict):
        errors.append("result.derived_function_preferences 必须是对象")
    elif expected_code:
        expected_stack = TYPE_PREFERENCE_FUNCTION_STACKS.get(expected_code)
        stack = functions.get("stack")
        actual_codes = (
            [item.get("code") for item in stack if isinstance(item, dict)]
            if isinstance(stack, list)
            else []
        )
        if actual_codes != expected_stack:
            errors.append("result.derived_function_preferences.stack 与四字母代码不一致")
        if isinstance(stack, list):
            for index, item in enumerate(stack):
                if not isinstance(item, dict):
                    errors.append(
                        f"result.derived_function_preferences.stack[{index}] 必须是对象"
                    )
                    continue
                code = item.get("code")
                if item.get("plain_name_zh") != TYPE_PREFERENCE_FUNCTION_PLAIN_NAMES.get(
                    code
                ):
                    errors.append(
                        f"result.derived_function_preferences.stack[{index}].plain_name_zh 无效"
                    )
                if not is_nonempty_string(item.get("plain_explanation_zh")):
                    errors.append(
                        f"result.derived_function_preferences.stack[{index}].plain_explanation_zh 必须是非空字符串"
                    )
        if functions.get("summary") != " → ".join(expected_stack or []):
            errors.append("result.derived_function_preferences.summary 无效")
        expected_plain_summary = " → ".join(
            f"{TYPE_PREFERENCE_FUNCTION_PLAIN_NAMES[code]}（{code}）"
            for code in (expected_stack or [])
        )
        if functions.get("plain_summary_zh") != expected_plain_summary:
            errors.append("result.derived_function_preferences.plain_summary_zh 无效")
        expected_plain_sequence = " → ".join(
            TYPE_PREFERENCE_FUNCTION_SEQUENCE_ACTIONS[code]
            for code in (expected_stack or [])
        )
        if functions.get("plain_sequence_zh") != expected_plain_sequence:
            errors.append("result.derived_function_preferences.plain_sequence_zh 无效")
        if not is_nonempty_string(functions.get("sequence_explanation_zh")):
            errors.append(
                "result.derived_function_preferences.sequence_explanation_zh 必须是非空字符串"
            )
        if functions.get("status") != "heuristic_from_four_letter":
            errors.append("result.derived_function_preferences.status 无效")
        if functions.get("independently_measured") is not False:
            errors.append(
                "result.derived_function_preferences.independently_measured 必须为 false"
            )
        if not is_nonempty_string(functions.get("model_note_zh")):
            errors.append("result.derived_function_preferences.model_note_zh 必须是非空字符串")

    for field in (
        "independent_and_unofficial",
        "not_a_type_or_diagnosis",
        "not_for_high_impact_decisions",
        "no_percentile_or_confidence_interval",
    ):
        if result.get(field) is not True:
            errors.append(f"result.{field} 必须为 true")


def validate_personality(payload: dict[str, Any], errors: list[str]) -> None:
    evidence = payload.get("evidence", {})
    instrument = evidence.get("instrument") if isinstance(evidence, dict) else None
    if not isinstance(instrument, dict):
        errors.append("evidence.instrument 必须是对象")
    else:
        for field in (
            "name",
            "version",
            "source",
            "language",
            "translation_status",
        ):
            if not is_nonempty_string(instrument.get(field)):
                errors.append(f"evidence.instrument.{field} 必须是非空字符串")
        if instrument.get("name") == "四向偏好快照":
            validate_type_preference(payload, instrument, errors)
            return
        expected_bank_hash = local_file_hash(MINI_IPIP_PATH)
        if instrument.get("item_bank_hash") != expected_bank_hash:
            errors.append("evidence.instrument.item_bank_hash 与本地题库不一致")
        if instrument.get("language") == "zh-CN" and instrument.get(
            "translation_status"
        ) != "draft-0.1-unvalidated":
            errors.append("中文试译必须标为 draft-0.1-unvalidated")
    if evidence.get("completed_items") != 20:
        errors.append("evidence.completed_items 必须是 20")
    validate_sha256(evidence.get("input_hash"), "evidence.input_hash", errors)

    result = payload.get("result", {})
    scores = result.get("scores") if isinstance(result, dict) else None
    if not isinstance(scores, dict) or set(scores) != PERSONALITY_TRAITS:
        errors.append("result.scores 必须恰好包含五个 Mini-IPIP 维度")
        return
    for trait in sorted(PERSONALITY_TRAITS):
        score = scores.get(trait)
        if not isinstance(score, dict):
            errors.append(f"result.scores.{trait} 必须是对象")
            continue
        total = score.get("sum")
        mean = score.get("mean")
        if isinstance(total, bool) or not isinstance(total, int) or not 4 <= total <= 20:
            errors.append(f"result.scores.{trait}.sum 必须是 4—20 的整数")
        if (
            isinstance(mean, bool)
            or not isinstance(mean, (int, float))
            or not 1 <= mean <= 5
        ):
            errors.append(f"result.scores.{trait}.mean 必须在 1—5")
        if (
            isinstance(total, int)
            and isinstance(mean, (int, float))
            and not isinstance(mean, bool)
            and abs(mean - total / 4) > 0.005
        ):
            errors.append(f"result.scores.{trait}.mean 必须等于 sum / 4")
        if score.get("item_count") != 4:
            errors.append(f"result.scores.{trait}.item_count 必须是 4")
    if result.get("not_a_type_or_diagnosis") is not True:
        errors.append("result.not_a_type_or_diagnosis 必须为 true")


def validate_relationship(payload: dict[str, Any], errors: list[str]) -> None:
    evidence = payload.get("evidence", {})
    consent = evidence.get("consent") if isinstance(evidence, dict) else None
    if not isinstance(consent, dict) or consent.get("partner_a") is not True or consent.get(
        "partner_b"
    ) is not True:
        errors.append("evidence.consent 必须记录双方均明确同意")
    instrument = evidence.get("instrument") if isinstance(evidence, dict) else None
    if not isinstance(instrument, dict):
        errors.append("evidence.instrument 必须是对象")
    elif instrument.get("item_bank_hash") != local_file_hash(
        RELATIONSHIP_ITEMS_PATH
    ):
        errors.append("evidence.instrument.item_bank_hash 与本地题库不一致")
    if evidence.get("completed_items_per_partner") != 12:
        errors.append("evidence.completed_items_per_partner 必须是 12")
    validate_sha256(evidence.get("input_hash"), "evidence.input_hash", errors)

    result = payload.get("result", {})
    safety = payload.get("safety", {})
    safety_redirect = safety.get("reason_code") == "E_RELATIONSHIP_SAFETY"
    if safety_redirect:
        if safety.get("decision") != "redirect":
            errors.append("关系安全题触发时 safety.decision 必须是 redirect")
        if result.get("combined_reflection_suppressed") is not True:
            errors.append("关系安全题触发时必须抑制双方合并结果")
        if result.get("private_safety_check_required") is not True:
            errors.append("关系安全题触发时必须要求私下安全核对")
        if "dimensions" in result:
            errors.append("关系安全题触发时不得输出 dimensions 或共同对话提示")
    else:
        dimensions = result.get("dimensions") if isinstance(result, dict) else None
        if not isinstance(dimensions, dict) or set(dimensions) != RELATIONSHIP_DIMENSIONS:
            errors.append("result.dimensions 必须恰好包含四个关系反思维度")
            return
        for dimension in sorted(RELATIONSHIP_DIMENSIONS):
            item = dimensions.get(dimension)
            if not isinstance(item, dict):
                errors.append(f"result.dimensions.{dimension} 必须是对象")
                continue
            mean_a = item.get("partner_a_mean")
            mean_b = item.get("partner_b_mean")
            for field, value in (
                ("partner_a_mean", mean_a),
                ("partner_b_mean", mean_b),
            ):
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not 1 <= value <= 5
                ):
                    errors.append(
                        f"result.dimensions.{dimension}.{field} 必须在 1—5"
                    )
            gap = item.get("absolute_gap")
            if (
                isinstance(gap, bool)
                or not isinstance(gap, (int, float))
                or not 0 <= gap <= 4
            ):
                errors.append(
                    f"result.dimensions.{dimension}.absolute_gap 必须在 0—4"
                )
            if (
                isinstance(mean_a, (int, float))
                and not isinstance(mean_a, bool)
                and isinstance(mean_b, (int, float))
                and not isinstance(mean_b, bool)
                and isinstance(gap, (int, float))
                and not isinstance(gap, bool)
                and abs(gap - abs(mean_a - mean_b)) > 0.005
            ):
                errors.append(
                    f"result.dimensions.{dimension}.absolute_gap 必须等于双方均值差的绝对值"
                )
            if item.get("item_count") != 3:
                errors.append(f"result.dimensions.{dimension}.item_count 必须是 3")
            if not is_nonempty_string(item.get("conversation_prompt_zh")):
                errors.append(
                    f"result.dimensions.{dimension}.conversation_prompt_zh 必须是非空字符串"
                )
    if result.get("not_a_compatibility_score") is not True:
        errors.append("result.not_a_compatibility_score 必须为 true")


def validate_oracle(
    payload: dict[str, Any],
    errors: list[str],
    controls_path: Path | None,
    scope: str,
) -> None:
    evidence = payload.get("evidence", {})
    result = payload.get("result", {})
    required = (
        "deck_version",
        "deck_hash",
        "commitment",
        "client_seed",
        "server_seed_reveal",
        "digest",
        "feature_control",
        "verification_formula",
    )
    for field in required:
        if field in {"feature_control", "verification_formula"}:
            if not isinstance(evidence.get(field), dict):
                errors.append(f"evidence.{field} 必须是对象")
        elif not is_nonempty_string(evidence.get(field)):
            errors.append(f"evidence.{field} 必须是非空字符串")
    if any(message.startswith("evidence.") for message in errors):
        return

    try:
        current_receipt = check_feature(
            controls_path,
            "oracle-reflection",
            "1.0.0",
            scope,
        )
    except GateError as exc:
        errors.append(f"{exc.code}: {exc}")
        return
    stored_receipt = evidence["feature_control"]
    if (
        stored_receipt.get("control_record_hash")
        != current_receipt.get("control_record_hash")
        or stored_receipt.get("control_revision")
        != current_receipt.get("control_revision")
    ):
        errors.append("evidence.feature_control 与当前功能控制策略不一致")

    deck_version = evidence["deck_version"]
    deck_path = LEGACY_DECK_PATHS.get(deck_version, CURRENT_DECK_PATH)
    deck = load_json(deck_path)
    if not isinstance(deck, dict) or evidence["deck_version"] != deck.get("deck_version"):
        errors.append("evidence.deck_version 与本地牌组不一致")
        return
    expected_deck_hash = sha256_json(deck)
    if evidence["deck_hash"] != f"sha256:{expected_deck_hash}":
        errors.append("evidence.deck_hash 与本地规范化牌组不一致")
        return
    try:
        server_seed = bytes.fromhex(evidence["server_seed_reveal"])
    except ValueError:
        errors.append("evidence.server_seed_reveal 不是有效十六进制")
        return
    if len(server_seed) != 32:
        errors.append("evidence.server_seed_reveal 必须是 32 字节随机种子")
        return

    expected_commitment = hashlib.sha256(
        (
            "divination-assessment|commit|"
            + evidence["deck_version"]
            + "|"
            + expected_deck_hash
            + "|"
            + evidence["server_seed_reveal"]
        ).encode("utf-8")
    ).hexdigest()
    if not hmac.compare_digest(expected_commitment, evidence["commitment"]):
        errors.append("commitment 复算不一致")

    expected_digest = hmac.new(
        server_seed,
        (
            "divination-assessment|draw|"
            + evidence["deck_version"]
            + "|"
            + expected_deck_hash
            + "|"
            + evidence["client_seed"]
        ).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_digest, evidence["digest"]):
        errors.append("digest 复算不一致")
        return

    digest_bytes = bytes.fromhex(expected_digest)
    cards = deck.get("cards")
    if not isinstance(cards, list) or len(cards) != 22:
        errors.append("本地牌组结构无效")
        return
    expected_index = int.from_bytes(digest_bytes[:8], "big") % len(cards)
    expected_orientation = "reversed" if digest_bytes[8] & 1 else "upright"
    card = result.get("card") if isinstance(result, dict) else None
    if card != cards[expected_index]:
        errors.append("result.card 与 digest 和本地牌组不一致")
    if deck_version.endswith("-v2"):
        if evidence.get("meaning_basis_zh") != deck.get("meaning_basis_zh"):
            errors.append("evidence.meaning_basis_zh 与本地牌组释义来源不一致")
        if isinstance(card, dict):
            required_meaning_fields = {
                "archetype_zh",
                "keywords_zh",
                "upright_lens_zh",
                "reversed_lens_zh",
                "visual_symbols_zh",
            }
            missing_meanings = sorted(required_meaning_fields - set(card))
            if missing_meanings:
                errors.append(
                    "result.card 缺少结构化牌义字段："
                    + "、".join(missing_meanings)
                )
    if result.get("orientation") != expected_orientation:
        errors.append("result.orientation 与 digest 不一致")
    if result.get("not_a_prediction") is not True:
        errors.append("result.not_a_prediction 必须为 true")


def validate_chart_result(
    payload: dict[str, Any],
    errors: list[str],
    allowlist_path: Path | None,
    controls_path: Path | None,
    scope: str,
) -> None:
    evidence = payload.get("evidence", {})
    result = payload.get("result", {})
    adapter_payload = evidence.get("adapter_payload")
    stored_receipt = evidence.get("adapter_receipt")
    if not isinstance(adapter_payload, dict):
        errors.append("chart-interpretation 必须包含 evidence.adapter_payload")
        return
    if not isinstance(stored_receipt, dict):
        errors.append("chart-interpretation 必须包含 evidence.adapter_receipt")
        return
    adapter_errors, _, current_receipt = validate_chart(
        adapter_payload,
        allowlist_path,
        controls_path,
        scope,
    )
    if adapter_errors or current_receipt is None:
        errors.append("adapter 复验失败：" + "; ".join(adapter_errors))
        return
    if (
        stored_receipt.get("chart_payload_hash")
        != current_receipt.get("chart_payload_hash")
        or stored_receipt.get("feature_control", {}).get("control_record_hash")
        != current_receipt.get("feature_control", {}).get("control_record_hash")
        or (stored_receipt.get("system_feature_control") or {}).get(
            "control_record_hash"
        )
        != (current_receipt.get("system_feature_control") or {}).get(
            "control_record_hash"
        )
        or stored_receipt.get("engine_approval", {}).get("engine_record_hash")
        != current_receipt.get("engine_approval", {}).get("engine_record_hash")
        or stored_receipt.get("engine_approval", {}).get("engine_allowlist_hash")
        != current_receipt.get("engine_approval", {}).get("engine_allowlist_hash")
    ):
        errors.append("evidence.adapter_receipt 与当前复验结果不一致")
    if result.get("chart") != adapter_payload.get("chart"):
        errors.append("result.chart 必须与 adapter_payload.chart 完全一致")
    if result.get("chart_system") != adapter_payload.get("chart_system"):
        errors.append("result.chart_system 必须与 adapter_payload.chart_system 一致")
    if result.get("traditional_framework_not_scientific_prediction") is not True:
        errors.append(
            "result.traditional_framework_not_scientific_prediction 必须为 true"
        )


def validate_report_followup(
    payload: dict[str, Any],
    errors: list[str],
    controls_path: Path | None,
    scope: str,
) -> None:
    evidence = payload.get("evidence", {})
    result = payload.get("result", {})
    source = evidence.get("report_source")
    if not isinstance(source, dict):
        errors.append("report-followup 必须包含 evidence.report_source")
        return
    for field in ("kind", "category", "title", "provider", "instrument_or_system", "version"):
        if not is_nonempty_string(source.get(field)):
            errors.append(f"evidence.report_source.{field} 必须是非空字符串或 unknown")
    if source.get("kind") not in {"file", "text", "screenshot"}:
        errors.append("evidence.report_source.kind 不在允许列表")
    if source.get("category") not in {"traditional", "psychometric", "other"}:
        errors.append("evidence.report_source.category 不在允许列表")
    if source.get("provided_by") != "user":
        errors.append("evidence.report_source.provided_by 必须是 user")
    if not isinstance(source.get("independently_verified"), bool):
        errors.append("evidence.report_source.independently_verified 必须是布尔值")
    if source.get("category") == "traditional":
        try:
            check_feature(
                controls_path,
                "traditional-report-interpretation",
                "1.0.0",
                scope,
            )
        except GateError as exc:
            errors.append(f"{exc.code}: {exc}")
    system_text = " ".join(
        str(source.get(field, "")).lower()
        for field in ("instrument_or_system", "traditional_system")
    )
    is_vedic = any(
        token in system_text
        for token in ("vedic", "jyotish", "印度占星", "吠陀占星", "印占")
    )
    if is_vedic:
        if source.get("traditional_system") != "vedic-astrology":
            errors.append(
                "印度占星报告的 evidence.report_source.traditional_system "
                "必须为 vedic-astrology"
            )
        validate_string_list(
            source.get("chart_components_present"),
            "evidence.report_source.chart_components_present",
            errors,
            allow_empty=False,
        )
        if source.get("input_precision") not in {"exact", "approximate", "unknown"}:
            errors.append(
                "印度占星报告的 evidence.report_source.input_precision "
                "必须为 exact、approximate 或 unknown"
            )

    answers = result.get("answers")
    if not isinstance(answers, list) or not answers:
        errors.append("report-followup 必须包含非空 result.answers")
        return
    for index, answer in enumerate(answers):
        prefix = f"result.answers[{index}]"
        if not isinstance(answer, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        if not is_nonempty_string(answer.get("question")):
            errors.append(f"{prefix}.question 必须是非空字符串")
        answer_interpretation = answer.get("interpretation")
        if not is_nonempty_string(answer_interpretation):
            errors.append(f"{prefix}.interpretation 必须是非空字符串")
        else:
            validate_high_impact_text(
                answer_interpretation,
                f"{prefix}.interpretation",
                errors,
            )
        validate_string_list(
            answer.get("limitations"),
            f"{prefix}.limitations",
            errors,
            allow_empty=False,
        )
        validate_string_list(
            answer.get("actions"),
            f"{prefix}.actions",
            errors,
            allow_empty=False,
        )
        if isinstance(answer.get("actions"), list):
            for action_index, action_text in enumerate(answer["actions"]):
                if is_nonempty_string(action_text):
                    validate_high_impact_text(
                        action_text,
                        f"{prefix}.actions[{action_index}]",
                        errors,
                    )
        citations = answer.get("citations")
        if not isinstance(citations, list) or not citations:
            errors.append(f"{prefix}.citations 必须是非空数组")
            continue
        for citation_index, citation in enumerate(citations):
            citation_prefix = f"{prefix}.citations[{citation_index}]"
            if not isinstance(citation, dict):
                errors.append(f"{citation_prefix} 必须是对象")
                continue
            if not (
                is_nonempty_string(citation.get("page"))
                or is_nonempty_string(citation.get("section"))
            ):
                errors.append(f"{citation_prefix} 必须提供 page 或 section")
            if not is_nonempty_string(citation.get("field")):
                errors.append(f"{citation_prefix}.field 必须是非空字符串")
            if not is_nonempty_string(citation.get("excerpt")):
                errors.append(f"{citation_prefix}.excerpt 必须是非空字符串")


def path_exists(payload: dict[str, Any], dotted_path: str) -> bool:
    if not dotted_path.startswith(("evidence.", "result.")):
        return False
    current: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True


def validate_final_layer(
    payload: dict[str, Any], errors: list[str], warnings: list[str]
) -> None:
    interpretation = payload.get("interpretation")
    if not isinstance(interpretation, list) or not interpretation:
        errors.append("final 阶段必须包含非空 interpretation 数组")
    else:
        for index, item in enumerate(interpretation):
            prefix = f"interpretation[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{prefix} 必须是对象")
                continue
            claim = item.get("claim")
            if not is_nonempty_string(claim):
                errors.append(f"{prefix}.claim 必须是非空字符串")
            elif any(term in claim for term in ABSOLUTE_LANGUAGE):
                errors.append(f"{prefix}.claim 含禁止的绝对化词语")
            if is_nonempty_string(claim):
                validate_high_impact_text(claim, f"{prefix}.claim", errors)
            evidence_paths = item.get("evidence_paths")
            validate_string_list(
                evidence_paths,
                f"{prefix}.evidence_paths",
                errors,
                allow_empty=False,
            )
            if isinstance(evidence_paths, list):
                for evidence_path in evidence_paths:
                    if is_nonempty_string(evidence_path) and not path_exists(
                        payload, evidence_path
                    ):
                        errors.append(
                            f"{prefix}.evidence_paths 引用了不存在的字段：{evidence_path}"
                        )
            validate_string_list(
                item.get("limitations"),
                f"{prefix}.limitations",
                errors,
                allow_empty=False,
            )
            if item.get("epistemic_status") not in ALLOWED_EPISTEMIC_STATUS:
                errors.append(f"{prefix}.epistemic_status 不在允许列表")
            if item.get("support_strength") not in ALLOWED_SUPPORT_STRENGTH:
                errors.append(f"{prefix}.support_strength 不在允许列表")
            validate_string_list(
                item.get("counter_signals"),
                f"{prefix}.counter_signals",
                errors,
                allow_empty=True,
            )
            validate_string_list(
                item.get("cannot_support"),
                f"{prefix}.cannot_support",
                errors,
                allow_empty=False,
            )
            if item.get("fit_status") not in ALLOWED_FIT_STATUS:
                errors.append(f"{prefix}.fit_status 不在允许列表")

    actions = payload.get("actions")
    if not isinstance(actions, list) or not 1 <= len(actions) <= 5:
        errors.append("final 阶段 actions 必须包含 1—5 个对象")
    else:
        for index, action in enumerate(actions):
            prefix = f"actions[{index}]"
            if not isinstance(action, dict):
                errors.append(f"{prefix} 必须是对象")
                continue
            action_text = action.get("text")
            if not is_nonempty_string(action_text):
                errors.append(f"{prefix}.text 必须是非空字符串")
            else:
                # Text is always reviewed; declared low_risk/reversible flags are
                # required metadata, never a bypass for semantic safety checks.
                validate_high_impact_text(action_text, f"{prefix}.text", errors)
            if action.get("low_risk") is not True:
                errors.append(f"{prefix}.low_risk 必须为 true")
            if action.get("reversible") is not True:
                errors.append(f"{prefix}.reversible 必须为 true")

    presentation = payload.get("presentation")
    if not isinstance(presentation, dict):
        errors.append("final 阶段必须包含 presentation 对象")
    else:
        if presentation.get("depth") not in {"quick", "deep"}:
            errors.append("presentation.depth 必须为 quick 或 deep")
        if presentation.get("progressive_disclosure") is not True:
            errors.append("presentation.progressive_disclosure 必须为 true")

    mode = payload.get("mode")
    source_category = payload.get("evidence", {}).get("report_source", {}).get("category")
    if mode in {"oracle-reflection", "chart-interpretation"} or (
        mode == "report-followup" and source_category == "traditional"
    ):
        if payload.get("disclaimer") != TRADITIONAL_DISCLAIMER:
            errors.append("传统文化 final 结果必须包含规定的 AI 生成与用途边界声明")


def validate(
    payload: Any,
    *,
    stage: str = "facts",
    controls_path: Path | None = None,
    engine_allowlist_path: Path | None = None,
    scope: str = "yuanbao-public-cn",
) -> tuple[list[str], list[str]]:
    errors, warnings = validate_common(payload)
    if errors or not isinstance(payload, dict):
        return errors, warnings
    mode = payload["mode"]
    if mode == "personality":
        validate_personality(payload, errors)
    elif mode == "relationship-reflection":
        validate_relationship(payload, errors)
    elif mode == "oracle-reflection":
        validate_oracle(payload, errors, controls_path, scope)
    elif mode == "chart-interpretation":
        validate_chart_result(
            payload,
            errors,
            engine_allowlist_path,
            controls_path,
            scope,
        )
    elif mode == "report-followup":
        validate_report_followup(payload, errors, controls_path, scope)
    if payload.get("quality", {}).get("status") == "fail":
        errors.append("quality.status 为 fail，禁止交付")
    if payload.get("safety", {}).get("decision") in {"redirect", "refuse"}:
        errors.append("safety.decision 要求 redirect/refuse，禁止作为正常结果交付")
    if stage == "final" and not errors:
        validate_final_layer(payload, errors, warnings)
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a unified result JSON file.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--stage", choices=["facts", "final"], default="facts")
    parser.add_argument(
        "--controls",
        "--approvals",
        dest="controls",
        type=Path,
        help="Host feature controls; --approvals is a compatibility alias.",
    )
    parser.add_argument("--engine-allowlist", type=Path)
    parser.add_argument("--scope", default="yuanbao-public-cn")
    args = parser.parse_args()
    errors, warnings = validate(
        load_json(args.input),
        stage=args.stage,
        controls_path=args.controls,
        engine_allowlist_path=args.engine_allowlist,
        scope=args.scope,
    )
    print(
        json.dumps(
            {"ok": not errors, "errors": errors, "warnings": warnings},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
