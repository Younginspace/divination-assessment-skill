#!/usr/bin/env python3
"""Validate a privacy-minimized share-card spec and its deterministic SVG."""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
THEMES_PATH = SCRIPT_DIR.parent / "assets" / "share-card-themes.json"
ALLOWED_ASPECTS = {
    "portrait": (1080, 1440),
    "square": (1080, 1080),
}
PRIVATE_PATTERNS = {
    "phone": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "id_number": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    "email": re.compile(r"\b[^@\s]+@[^@\s]+\.[^@\s]+\b"),
    "url": re.compile(r"https?://|www\."),
    "uuid": re.compile(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        re.IGNORECASE,
    ),
    "date": re.compile(r"(?<!\d)(?:19|20)\d{2}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?"),
    "time": re.compile(r"(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d(?!\d)"),
    "coordinates": re.compile(r"(?<!\d)[+-]?\d{1,3}\.\d{4,}\s*[,，]\s*[+-]?\d{1,3}\.\d{4,}(?!\d)"),
}
PRIVATE_TERMS = (
    "手机号",
    "身份证",
    "精确住址",
    "经纬度",
    "出生日期",
    "出生时间",
    "出生城市",
    "run_id",
    "client_seed",
    "server_seed",
)
MISLEADING_TERMS = (
    "官方认证",
    "准确率",
    "科学诊断",
    "注定",
    "百分百",
    "改命",
    "转运",
    "必中",
)
TEMPLATE_REQUIREMENTS = {
    "type-preference": ("非官方简单测试", "12 道原创题"),
    "big-five": ("无本地常模", "不是心理诊断"),
    "relationship": ("不提供匹配率",),
    "oracle": ("不预测外部事件",),
    "bazi": ("AI生成", "传统文化与自我反思"),
    "western": ("AI生成", "传统文化与自我反思"),
    "vedic": ("AI生成", "传统文化与自我反思", "Vedic Lite Beta", "非 Swiss 专业兼容"),
    "report-followup": ("仅解释所提供报告",),
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize(value: Any) -> str:
    return " ".join(str(value).split())


def public_texts(spec: dict[str, Any]) -> list[str]:
    texts = [
        spec.get("eyebrow", ""),
        spec.get("title", ""),
        spec.get("hero", ""),
        spec.get("footer", ""),
        spec.get("companion_text", ""),
    ]
    for item in spec.get("stats", []):
        if isinstance(item, dict):
            texts.extend([item.get("label", ""), item.get("value", "")])
    texts.extend(spec.get("highlights", []))
    return [normalize(text) for text in texts if normalize(text)]


def scan_private(text: str) -> list[str]:
    findings = [name for name, pattern in PRIVATE_PATTERNS.items() if pattern.search(text)]
    findings.extend(term for term in PRIVATE_TERMS if term in text)
    return findings


def validate_spec(spec: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(spec, dict):
        return ["share-card spec 必须是对象"]
    if spec.get("schema_version") != "1.0.0":
        errors.append("schema_version 必须为 1.0.0")
    aspect = spec.get("aspect")
    if aspect not in ALLOWED_ASPECTS:
        errors.append("aspect 必须为 portrait 或 square")
    else:
        canvas = spec.get("canvas")
        expected = ALLOWED_ASPECTS[aspect]
        if not isinstance(canvas, dict) or (
            canvas.get("width"),
            canvas.get("height"),
        ) != expected:
            errors.append(f"canvas 必须为 {expected[0]}×{expected[1]}")

    themes = load_json(THEMES_PATH).get("templates", {})
    template_id = spec.get("template_id")
    if template_id not in themes:
        errors.append("template_id 不在内置主题列表")
    if spec.get("logo") is not None:
        errors.append("logo 必须为 null")
    if spec.get("product_name") is not None:
        errors.append("product_name 必须为 null")

    for field in ("title", "hero", "footer", "companion_text", "public_content_hash"):
        if not normalize(spec.get(field, "")):
            errors.append(f"{field} 必须是非空字符串")
    stats = spec.get("stats")
    if not isinstance(stats, list) or len(stats) > 5:
        errors.append("stats 必须是最多 5 项的数组")
    highlights = spec.get("highlights")
    if not isinstance(highlights, list) or len(highlights) > 3:
        errors.append("highlights 必须是最多 3 项的数组")

    joined = "\n".join(public_texts(spec))
    private_findings = scan_private(joined)
    if private_findings:
        errors.append("公开文字命中隐私模式: " + ", ".join(sorted(set(private_findings))))
    for term in MISLEADING_TERMS:
        if term in joined:
            errors.append(f"公开文字包含误导词: {term}")
    if "元宝" in joined or "Yuanbao" in joined:
        errors.append("分享卡不得露出元宝名称或 Logo")

    requirements = TEMPLATE_REQUIREMENTS.get(template_id, ())
    for required in requirements:
        if required not in joined:
            errors.append(f"{template_id} 缺少必显边界: {required}")

    exact_text = spec.get("exact_text")
    if not isinstance(exact_text, list) or not exact_text:
        errors.append("exact_text 必须是非空数组")
    else:
        normalized_exact = [normalize(item) for item in exact_text if normalize(item)]
        for required in (normalize(spec.get("title")), normalize(spec.get("hero")), normalize(spec.get("footer"))):
            if required and required not in normalized_exact:
                errors.append(f"exact_text 缺少: {required}")

    privacy = spec.get("privacy")
    required_privacy = {
        "birth_data_included": False,
        "raw_answers_included": False,
        "run_id_included": False,
        "third_party_identity_included": False,
        "logo_included": False,
    }
    if not isinstance(privacy, dict):
        errors.append("privacy 必须是对象")
    else:
        for key, expected in required_privacy.items():
            if privacy.get(key) is not expected:
                errors.append(f"privacy.{key} 必须为 false")
    return errors


def validate_svg(spec: dict[str, Any], svg_path: Path) -> list[str]:
    errors: list[str] = []
    try:
        raw = svg_path.read_text(encoding="utf-8")
        root = ET.fromstring(raw)
    except (OSError, ET.ParseError) as exc:
        return [f"SVG 无法读取: {exc}"]
    if root.tag.split("}")[-1] != "svg":
        errors.append("根节点必须是 svg")
        return errors
    canvas = spec.get("canvas", {})
    if root.get("width") != str(canvas.get("width")) or root.get("height") != str(
        canvas.get("height")
    ):
        errors.append("SVG 尺寸与 spec 不一致")
    lowered = raw.lower().replace('xmlns="http://www.w3.org/2000/svg"', "")
    for forbidden in ("<script", "<image", "<foreignobject", "http://", "https://"):
        if forbidden in lowered:
            errors.append(f"SVG 包含外部或可执行内容: {forbidden}")
    if "元宝" in raw or "yuanbao" in lowered:
        errors.append("SVG 不得露出元宝名称或 Logo")
    labels = {
        normalize(element.get("aria-label"))
        for element in root.iter()
        if element.get("aria-label")
    }
    for expected in spec.get("exact_text", []):
        if normalize(expected) not in labels:
            errors.append(f"SVG 缺少可核对文字: {normalize(expected)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate share-card spec and SVG.")
    parser.add_argument("spec", type=Path)
    parser.add_argument("--svg", type=Path)
    args = parser.parse_args()
    try:
        spec = load_json(args.spec)
    except (OSError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {"ok": False, "errors": [f"spec 无法读取: {exc}"]},
                ensure_ascii=False,
            )
        )
        return 2
    errors = validate_spec(spec)
    if not errors and args.svg:
        errors.extend(validate_svg(spec, args.svg))
    print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
