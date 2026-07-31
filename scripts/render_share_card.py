#!/usr/bin/env python3
"""Build a validated, privacy-minimized share-card spec and deterministic SVG."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from validate_result import TRADITIONAL_DISCLAIMER, validate
from validate_share_card import MISLEADING_TERMS, scan_private, validate_spec


SCRIPT_DIR = Path(__file__).resolve().parent
THEMES_PATH = SCRIPT_DIR.parent / "assets" / "share-card-themes.json"
ASPECTS = {
    "portrait": (1080, 1440),
    "square": (1080, 1080),
}
ORIENTATION_LABELS = {"upright": "正位", "reversed": "逆位"}
PLANET_LABELS = {
    "sun": "太阳",
    "moon": "月亮",
    "mercury": "水星",
    "venus": "金星",
    "mars": "火星",
}


class CardError(ValueError):
    """Structured card creation failure."""


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize(value: Any) -> str:
    return " ".join(str(value).split())


def display_units(text: str) -> int:
    return sum(
        2 if unicodedata.east_asian_width(char) in {"W", "F", "A"} else 1
        for char in text
    )


def truncate_units(text: str, limit: int) -> str:
    text = normalize(text)
    if display_units(text) <= limit:
        return text
    kept: list[str] = []
    width = 0
    for char in text:
        char_width = 2 if unicodedata.east_asian_width(char) in {"W", "F", "A"} else 1
        if width + char_width > max(1, limit - 2):
            break
        kept.append(char)
        width += char_width
    return "".join(kept).rstrip("，。、；： ") + "…"


def safe_dynamic_text(value: Any, *, limit: int = 88) -> str | None:
    text = truncate_units(normalize(value), limit)
    if not text or scan_private(text):
        return None
    if any(term in text for term in MISLEADING_TERMS):
        return None
    if "元宝" in text or "Yuanbao" in text:
        return None
    return text


def public_observations(payload: dict[str, Any], limit: int = 2) -> list[str]:
    observations: list[str] = []
    for item in payload.get("interpretation", []):
        if not isinstance(item, dict):
            continue
        text = safe_dynamic_text(item.get("claim"), limit=76)
        if text and text not in observations:
            observations.append(text)
        if len(observations) >= limit:
            return observations
    for item in payload.get("actions", []):
        if not isinstance(item, dict):
            continue
        text = safe_dynamic_text(item.get("text"), limit=76)
        if text and text not in observations:
            observations.append(text)
        if len(observations) >= limit:
            break
    return observations


def public_actions(payload: dict[str, Any], limit: int = 1) -> list[str]:
    actions: list[str] = []
    for item in payload.get("actions", []):
        if not isinstance(item, dict):
            continue
        text = safe_dynamic_text(item.get("text"), limit=96)
        if text and text not in actions:
            actions.append(text)
        if len(actions) >= limit:
            break
    return actions


def type_preference_spec(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload["result"]
    preference = result["four_letter_preference"]
    code = preference["code"]
    stats: list[dict[str, str]] = []
    for axis in preference.get("axis_order", []):
        axis_data = preference.get("axis_map", {}).get(axis, {})
        stats.append(
            {
                "label": axis_data.get("letter", ""),
                "value": f"{axis_data.get('percentage', '')}%",
            }
        )
    sequence = result.get("derived_function_preferences", {}).get("plain_sequence_zh")
    highlights = []
    if safe_dynamic_text(sequence, limit=132):
        highlights.append(truncate_units(sequence, 132))
    highlights.extend(public_actions(payload, limit=1))
    return {
        "template_id": "type-preference",
        "eyebrow": "12 道原创 A/B 题",
        "title": "我的四字母偏好快照",
        "hero": code,
        "stats": stats[:4],
        "highlights": highlights[:2],
        "footer": "非官方简单测试｜12 道原创题｜仅供自我探索",
        "companion_text": "非官方简单测试；四轴百分比只表示本次选择占比，不代表人口常模或测量信度。",
    }


def big_five_spec(payload: dict[str, Any]) -> dict[str, Any]:
    scores = payload["result"]["scores"]
    stats = [
        {
            "label": score.get("label_zh", key),
            "value": f"{float(score.get('mean', 0)):.1f}/5",
        }
        for key, score in scores.items()
        if isinstance(score, dict)
    ]
    return {
        "template_id": "big-five",
        "eyebrow": "Mini-IPIP · 连续维度",
        "title": "我的五人格自我观察",
        "hero": "五个维度，没有好坏排名",
        "stats": stats[:5],
        "highlights": public_observations(payload, limit=2),
        "footer": "自我报告｜无本地常模｜不是心理诊断",
        "companion_text": "Mini-IPIP 结果是本次自我报告的连续维度；无本地常模，不是心理诊断。",
    }


def relationship_spec(payload: dict[str, Any]) -> dict[str, Any]:
    dimensions = payload["result"]["dimensions"]
    ranked = sorted(
        dimensions.values(),
        key=lambda item: float(item.get("absolute_gap", 0)),
        reverse=True,
    )
    stats = [
        {
            "label": item.get("label_zh", "对话维度"),
            "value": f"A {float(item.get('partner_a_mean', 0)):.1f} · B {float(item.get('partner_b_mean', 0)):.1f}",
        }
        for item in ranked[:4]
    ]
    prompt = safe_dynamic_text(ranked[0].get("conversation_prompt_zh"), limit=116) if ranked else None
    highlights = ([prompt] if prompt else []) + public_observations(payload, limit=2)
    return {
        "template_id": "relationship",
        "eyebrow": "双方分别知情提交",
        "title": "我们的关系反思卡",
        "hero": "先聊差异，再聊需要",
        "stats": stats,
        "highlights": highlights[:3],
        "footer": "只用于沟通反思｜不提供匹配率",
        "companion_text": "这是一份双方沟通反思，不是关系诊断，也不提供总体匹配率。",
    }


def oracle_spec(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload["result"]
    card = result["card"]
    orientation = ORIENTATION_LABELS.get(result.get("orientation"), "方向未标注")
    highlights = public_observations(payload, limit=2)
    if not highlights:
        highlights = ["把这张牌当作一个联想镜头：它让你想到什么？"]
    return {
        "template_id": "oracle",
        "eyebrow": "一次随机抽取",
        "title": "我抽到的反思卡",
        "hero": f"{card.get('name_zh', '')} · {orientation}",
        "stats": [],
        "highlights": highlights,
        "footer": "随机联想与自我反思｜不预测外部事件",
        "companion_text": TRADITIONAL_DISCLAIMER,
    }


def bazi_spec(payload: dict[str, Any], chart: dict[str, Any]) -> dict[str, Any]:
    pillars = chart["pillars"]
    ordered = [pillars[key] for key in ("year", "month", "day", "hour")]
    details = chart.get("details", {})
    elements = details.get("five_elements", {})
    stats = [
        {"label": "年柱", "value": pillars["year"]},
        {"label": "月柱", "value": pillars["month"]},
        {"label": "日柱", "value": pillars["day"]},
        {"label": "时柱", "value": pillars["hour"]},
    ]
    highlight = " · ".join(
        f"{label}{elements.get(key, '')}"
        for key, label in (("year", "年"), ("month", "月"), ("day", "日"), ("hour", "时"))
        if elements.get(key)
    )
    return {
        "template_id": "bazi",
        "eyebrow": "四柱事实摘录",
        "title": "我的八字盘面摘录",
        "hero": " · ".join(ordered),
        "stats": stats,
        "highlights": ([highlight] if highlight else []) + public_actions(payload, limit=1),
        "footer": "AI生成｜传统文化与自我反思，仅供参考",
        "companion_text": TRADITIONAL_DISCLAIMER,
    }


def western_spec(payload: dict[str, Any], chart: dict[str, Any]) -> dict[str, Any]:
    planets = chart.get("planets", {})
    stats = []
    for key in ("sun", "moon", "mercury", "venus"):
        item = planets.get(key)
        if isinstance(item, dict):
            stats.append(
                {
                    "label": PLANET_LABELS[key],
                    "value": f"{item.get('sign', '')} {float(item.get('degree_in_sign', 0)):.1f}°",
                }
            )
    sun = planets.get("sun", {}).get("sign", "—")
    moon = planets.get("moon", {}).get("sign", "—")
    return {
        "template_id": "western",
        "eyebrow": "热带黄道 · 基础星历",
        "title": "我的西洋星历摘录",
        "hero": f"太阳 {sun} · 月亮 {moon}",
        "stats": stats,
        "highlights": ["当前基础版不含宫位与上升点"] + public_actions(payload, limit=1),
        "footer": "AI生成｜传统文化与自我反思，仅供参考",
        "companion_text": TRADITIONAL_DISCLAIMER,
    }


def vedic_spec(payload: dict[str, Any], chart: dict[str, Any]) -> dict[str, Any]:
    ascendant = chart.get("ascendant", {})
    planets = chart.get("planets", {})
    moon = planets.get("moon", {})
    nakshatra = chart.get("moon_nakshatra", {})
    stats = [
        {"label": "Lagna", "value": ascendant.get("sign", "—")},
        {"label": "月亮", "value": moon.get("sign", "—")},
        {
            "label": "月宿",
            "value": f"{nakshatra.get('name', '—')} · Pada {nakshatra.get('pada', '—')}",
        },
    ]
    return {
        "template_id": "vedic",
        "eyebrow": "D1 · 整宫制 · 月宿",
        "title": "我的印度占星轻体验",
        "hero": f"Lagna {ascendant.get('sign', '—')}",
        "stats": stats,
        "highlights": ["线性近似 Lahiri 模型，不等同 Swiss 专业兼容结果"] + public_actions(payload, limit=1),
        "footer": "AI生成｜传统文化与自我反思，仅供参考｜Vedic Lite Beta｜非 Swiss 专业兼容",
        "companion_text": TRADITIONAL_DISCLAIMER,
    }


def report_spec(payload: dict[str, Any]) -> dict[str, Any]:
    answers = payload.get("result", {}).get("answers", [])
    first = answers[0] if answers and isinstance(answers[0], dict) else {}
    interpretation = safe_dynamic_text(first.get("interpretation"), limit=112)
    highlights = ([interpretation] if interpretation else []) + public_observations(payload, limit=2)
    source_category = payload.get("evidence", {}).get("report_source", {}).get("category")
    companion = (
        TRADITIONAL_DISCLAIMER
        if source_category == "traditional"
        else "仅解释用户提供的报告字段，不验证原报告准确性，也不构成专业诊断或建议。"
    )
    return {
        "template_id": "report-followup",
        "eyebrow": "来源绑定解释",
        "title": "我的报告反思摘录",
        "hero": "把断言改写成可核对的问题",
        "stats": [],
        "highlights": highlights[:3],
        "footer": "仅解释所提供报告｜不验证原报告准确性",
        "companion_text": companion,
    }


def build_public_content(payload: dict[str, Any]) -> dict[str, Any]:
    mode = payload.get("mode")
    result = payload.get("result", {})
    if mode == "personality":
        if isinstance(result.get("four_letter_preference"), dict):
            return type_preference_spec(payload)
        return big_five_spec(payload)
    if mode == "relationship-reflection":
        return relationship_spec(payload)
    if mode == "oracle-reflection":
        return oracle_spec(payload)
    if mode == "chart-interpretation":
        chart = result.get("chart", {})
        system = result.get("chart_system")
        if system == "bazi":
            return bazi_spec(payload, chart)
        if system == "western":
            return western_spec(payload, chart)
        if system == "vedic":
            return vedic_spec(payload, chart)
        raise CardError("E_UNSUPPORTED_CHART_SYSTEM")
    if mode == "report-followup":
        return report_spec(payload)
    raise CardError("E_UNSUPPORTED_MODE")


def build_spec(
    payload: dict[str, Any],
    *,
    aspect: str,
    nickname: str | None,
) -> dict[str, Any]:
    content = build_public_content(payload)
    safe_nickname = safe_dynamic_text(nickname, limit=24) if nickname else None
    if nickname and not safe_nickname:
        raise CardError("E_UNSAFE_NICKNAME")
    if safe_nickname:
        content["eyebrow"] = f"{safe_nickname} · {content['eyebrow']}"
    width, height = ASPECTS[aspect]
    exact_text = [
        content["eyebrow"],
        content["title"],
        content["hero"],
        *(
            f"{item['label']} {item['value']}"
            for item in content.get("stats", [])
        ),
        *content.get("highlights", []),
        content["footer"],
    ]
    public_payload = {
        "template_id": content["template_id"],
        "title": content["title"],
        "hero": content["hero"],
        "stats": content.get("stats", []),
        "highlights": content.get("highlights", []),
        "footer": content["footer"],
    }
    content.update(
        {
            "schema_version": "1.0.0",
            "aspect": aspect,
            "canvas": {"width": width, "height": height},
            "logo": None,
            "product_name": None,
            "exact_text": exact_text,
            "public_content_hash": "sha256:"
            + hashlib.sha256(
                json.dumps(
                    public_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
            "privacy": {
                "birth_data_included": False,
                "raw_answers_included": False,
                "run_id_included": False,
                "third_party_identity_included": False,
                "logo_included": False,
            },
        }
    )
    errors = validate_spec(content)
    if errors:
        raise CardError("E_INVALID_CARD_SPEC: " + "; ".join(errors))
    return content


def wrap_text(text: str, limit: int) -> list[str]:
    lines: list[str] = []
    current: list[str] = []
    current_width = 0
    for char in text:
        if char == "\n":
            lines.append("".join(current))
            current = []
            current_width = 0
            continue
        char_width = 2 if unicodedata.east_asian_width(char) in {"W", "F", "A"} else 1
        if current and current_width + char_width > limit:
            lines.append("".join(current))
            current = []
            current_width = 0
        current.append(char)
        current_width += char_width
    if current or not lines:
        lines.append("".join(current))
    return lines


def text_block(
    text: str,
    *,
    x: int,
    y: int,
    width_units: int,
    font_size: int,
    line_height: int,
    fill: str,
    weight: int = 400,
    anchor: str = "start",
) -> tuple[str, int]:
    lines = wrap_text(text, width_units)
    spans = "".join(
        f'<tspan x="{x}" dy="{0 if index == 0 else line_height}">{html.escape(line)}</tspan>'
        for index, line in enumerate(lines)
    )
    element = (
        f'<text x="{x}" y="{y}" fill="{fill}" font-size="{font_size}" '
        f'font-weight="{weight}" text-anchor="{anchor}" aria-label="{html.escape(text, quote=True)}">'
        f"{spans}</text>"
    )
    return element, line_height * len(lines)


def motif_svg(motif: str, width: int, height: int, accent: str) -> str:
    if motif in {"orbits", "mandala", "seal"}:
        return (
            f'<circle cx="{width - 80}" cy="80" r="230" fill="none" stroke="{accent}" stroke-opacity=".22" stroke-width="2"/>'
            f'<circle cx="{width - 80}" cy="80" r="150" fill="none" stroke="{accent}" stroke-opacity=".18" stroke-width="2"/>'
            f'<circle cx="{width - 80}" cy="80" r="8" fill="{accent}" fill-opacity=".7"/>'
        )
    if motif in {"stars", "constellation"}:
        points = [(110, 110), (220, 170), (880, 150), (940, 290), (770, 90), (160, 330)]
        stars = "".join(
            f'<circle cx="{x}" cy="{y}" r="{4 if index % 2 else 7}" fill="{accent}" fill-opacity=".72"/>'
            for index, (x, y) in enumerate(points)
        )
        lines = (
            f'<path d="M110 110 L220 170 L160 330 M770 90 L880 150 L940 290" '
            f'fill="none" stroke="{accent}" stroke-opacity=".25" stroke-width="2"/>'
        )
        return stars + lines
    if motif == "paired-arcs":
        return (
            f'<path d="M-80 280 C160 80 380 80 560 260" fill="none" stroke="{accent}" stroke-opacity=".2" stroke-width="46"/>'
            f'<path d="M540 160 C760 -20 1020 40 1160 250" fill="none" stroke="{accent}" stroke-opacity=".15" stroke-width="46"/>'
        )
    return (
        f'<path d="M0 180 H{width} M0 300 H{width} M160 0 V{height} M920 0 V{height}" '
        f'fill="none" stroke="{accent}" stroke-opacity=".08" stroke-width="2"/>'
    )


def render_svg(spec: dict[str, Any], themes: dict[str, Any]) -> str:
    width = spec["canvas"]["width"]
    height = spec["canvas"]["height"]
    theme = themes["templates"][spec["template_id"]]
    font_stack = themes["font_stack"]
    bg_start = theme["background_start"]
    bg_end = theme["background_end"]
    ink = theme["ink"]
    muted = theme["muted"]
    accent = theme["accent"]
    panel = theme["panel"]
    panel_height = height - 144
    content_width = width - 144
    chunks: list[str] = []
    chunks.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(spec["title"], quote=True)}">'
    )
    chunks.append(
        "<defs>"
        f'<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{bg_start}"/>'
        f'<stop offset="1" stop-color="{bg_end}"/>'
        "</linearGradient>"
        '<filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">'
        '<feDropShadow dx="0" dy="24" stdDeviation="28" flood-opacity=".12"/>'
        "</filter>"
        "</defs>"
    )
    chunks.append(f'<rect width="{width}" height="{height}" fill="url(#bg)"/>')
    chunks.append(motif_svg(theme["motif"], width, height, accent))
    chunks.append(
        f'<rect x="52" y="52" width="{width - 104}" height="{panel_height}" rx="48" '
        f'fill="{panel}" fill-opacity=".94" filter="url(#shadow)"/>'
    )
    chunks.append(
        f'<g font-family="{html.escape(font_stack, quote=True)}" letter-spacing=".2">'
    )
    y = 116
    block, used = text_block(
        spec["eyebrow"],
        x=88,
        y=y,
        width_units=48,
        font_size=24,
        line_height=34,
        fill=accent,
        weight=650,
    )
    chunks.append(block)
    y += used + 30
    block, used = text_block(
        spec["title"],
        x=88,
        y=y,
        width_units=28,
        font_size=44,
        line_height=58,
        fill=ink,
        weight=700,
    )
    chunks.append(block)
    y += used + 42
    hero_size = 94 if display_units(spec["hero"]) <= 16 else 58
    block, used = text_block(
        spec["hero"],
        x=88,
        y=y,
        width_units=32 if hero_size > 70 else 40,
        font_size=hero_size,
        line_height=hero_size + 18,
        fill=ink,
        weight=760,
    )
    chunks.append(block)
    y += used + 44

    stats = spec.get("stats", [])
    if stats:
        columns = min(len(stats), 4)
        gap = 14
        chip_width = int((content_width - gap * (columns - 1)) / columns)
        rows = (len(stats) + columns - 1) // columns
        chip_height = 112
        for index, item in enumerate(stats):
            row, column = divmod(index, columns)
            x = 88 + column * (chip_width + gap)
            chip_y = y + row * (chip_height + 14)
            label = normalize(item["label"])
            value = normalize(item["value"])
            combined = f"{label} {value}"
            chunks.append(
                f'<g aria-label="{html.escape(combined, quote=True)}">'
                f'<rect x="{x}" y="{chip_y}" width="{chip_width}" height="{chip_height}" rx="22" '
                f'fill="{theme["accent_soft"]}"/>'
                f'<text x="{x + 18}" y="{chip_y + 38}" fill="{muted}" font-size="20" font-weight="560">{html.escape(label)}</text>'
                f'<text x="{x + 18}" y="{chip_y + 80}" fill="{ink}" font-size="28" font-weight="720">{html.escape(value)}</text>'
                "</g>"
            )
        y += rows * (chip_height + 14) + 24

    highlights = spec.get("highlights", [])
    for index, highlight in enumerate(highlights):
        if y > height - 330:
            break
        chunks.append(
            f'<circle cx="102" cy="{y - 7}" r="8" fill="{accent}" fill-opacity="{0.9 - index * 0.15}"/>'
        )
        block, used = text_block(
            highlight,
            x=128,
            y=y,
            width_units=42 if height == 1440 else 46,
            font_size=28 if height == 1440 else 26,
            line_height=42,
            fill=ink,
            weight=520,
        )
        chunks.append(block)
        y += used + 20

    footer_y = height - 182
    chunks.append(
        f'<line x1="88" y1="{footer_y - 30}" x2="{width - 88}" y2="{footer_y - 30}" '
        f'stroke="{accent}" stroke-opacity=".22" stroke-width="2"/>'
    )
    block, _ = text_block(
        spec["footer"],
        x=88,
        y=footer_y,
        width_units=72,
        font_size=22,
        line_height=30,
        fill=muted,
        weight=520,
    )
    chunks.append(block)
    chunks.append("</g></svg>")
    return "".join(chunks)


def write_private(path: Path, content: str) -> None:
    if path.exists():
        raise CardError("E_OUTPUT_EXISTS")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    os.chmod(path, 0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a deterministic share card.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="SVG output path")
    parser.add_argument("--spec-output", type=Path, required=True)
    parser.add_argument("--aspect", choices=sorted(ASPECTS), default="portrait")
    parser.add_argument("--nickname")
    parser.add_argument("--controls", type=Path)
    parser.add_argument("--engine-allowlist", type=Path)
    parser.add_argument("--scope", default="yuanbao-public-cn")
    args = parser.parse_args()
    if args.output.exists() or args.spec_output.exists():
        print(json.dumps({"ok": False, "error": {"code": "E_OUTPUT_EXISTS"}}))
        return 2
    try:
        payload = load_json(args.input)
    except (OSError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {"ok": False, "error": {"code": "E_INVALID_INPUT", "message": str(exc)}},
                ensure_ascii=False,
            )
        )
        return 2
    errors, warnings = validate(
        payload,
        stage="final",
        controls_path=args.controls,
        engine_allowlist_path=args.engine_allowlist,
        scope=args.scope,
    )
    if errors:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "E_INVALID_FINAL",
                        "fields": errors,
                        "warnings": warnings,
                    },
                },
                ensure_ascii=False,
            )
        )
        return 1
    try:
        spec = build_spec(payload, aspect=args.aspect, nickname=args.nickname)
        themes = load_json(THEMES_PATH)
        svg = render_svg(spec, themes)
        write_private(
            args.spec_output,
            json.dumps(spec, ensure_ascii=False, indent=2) + "\n",
        )
        write_private(args.output, svg)
    except (CardError, KeyError, TypeError, ValueError) as exc:
        print(
            json.dumps(
                {"ok": False, "error": {"code": "E_CARD_BUILD_FAILED", "message": str(exc)}},
                ensure_ascii=False,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "svg": str(args.output.resolve()),
                "spec": str(args.spec_output.resolve()),
                "template_id": spec["template_id"],
                "aspect": spec["aspect"],
                "privacy": spec["privacy"],
                "companion_text": spec["companion_text"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
