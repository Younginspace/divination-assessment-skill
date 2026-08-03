#!/usr/bin/env python3
"""Build a validated image-generation prompt for an oracle share card."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from render_share_card import build_spec
from validate_result import validate


SCRIPT_DIR = Path(__file__).resolve().parent
VISUAL_SYSTEM_PATH = SCRIPT_DIR.parent / "assets" / "immersive-card-visual-system.json"
ORIENTATION_LABELS = {"upright": "正位", "reversed": "逆位"}
ROMAN_NUMERALS = (
    "0",
    "I",
    "II",
    "III",
    "IV",
    "V",
    "VI",
    "VII",
    "VIII",
    "IX",
    "X",
    "XI",
    "XII",
    "XIII",
    "XIV",
    "XV",
    "XVI",
    "XVII",
    "XVIII",
    "XIX",
    "XX",
    "XXI",
)


class PromptError(ValueError):
    pass


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_json(payload: Any) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def require_oracle_card(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    if payload.get("mode") != "oracle-reflection":
        raise PromptError("E_UNSUPPORTED_MODE：沉浸式提示词 v1 只支持抽牌反思卡")
    result = payload.get("result")
    card = result.get("card") if isinstance(result, dict) else None
    orientation = result.get("orientation") if isinstance(result, dict) else None
    if not isinstance(card, dict) or orientation not in ORIENTATION_LABELS:
        raise PromptError("E_INVALID_ORACLE_RESULT：缺少牌面或正逆位")
    required = {
        "name_zh",
        "name_en",
        "keywords_zh",
        "archetype_zh",
        "upright_lens_zh",
        "reversed_lens_zh",
        "visual_symbols_zh",
    }
    if not required.issubset(card):
        raise PromptError("E_MEANING_UNAVAILABLE：当前牌组没有完整结构化牌义")
    if (
        not isinstance(card["visual_symbols_zh"], list)
        or not card["visual_symbols_zh"]
        or not all(isinstance(item, str) and item.strip() for item in card["visual_symbols_zh"])
    ):
        raise PromptError("E_MEANING_UNAVAILABLE：visual_symbols_zh 无效")
    if (
        not isinstance(card["keywords_zh"], list)
        or len(card["keywords_zh"]) < 2
        or not all(isinstance(item, str) and item.strip() for item in card["keywords_zh"])
    ):
        raise PromptError("E_MEANING_UNAVAILABLE：keywords_zh 无效")
    return card, orientation


def build_prompt(
    payload: dict[str, Any],
    visual_system: dict[str, Any],
    *,
    aspect: str,
    render_pass: str,
) -> dict[str, Any]:
    card, orientation = require_oracle_card(payload)
    spec = build_spec(payload, aspect=aspect, nickname=None)
    canvas = visual_system["canvas"]
    palette = visual_system["palette"]
    illustration = visual_system["illustration"]
    frame_system = visual_system["frame_system"]
    orientation_lens = card[f"{orientation}_lens_zh"]
    symbols = "、".join(card["visual_symbols_zh"])
    negative_items = list(visual_system["negative_prompt"])
    if render_pass == "framed-preview":
        if aspect != "portrait":
            raise PromptError("E_UNSUPPORTED_ASPECT：framed-preview 只支持 3:4 竖版")
        negative_items = [
            item for item in negative_items if not item.startswith("任何可读文字")
        ]
    negative_prompt = "；".join(negative_items)
    prompt_lines = [
            (
                "为一张中文抽牌反思卡生成带牌框和限定文字的完整牌面预览。"
                if render_pass == "framed-preview"
                else "为一张中文抽牌反思卡生成无字背景插画。只生成背景艺术，不渲染任何文字。"
            ),
            f"视觉系统：{visual_system['system_name']}。",
            f"画布：{spec['canvas']['width']}×{spec['canvas']['height']}，{canvas['aspect']}，满幅出血。",
            f"牌面主题：{card['name_zh']}（{card['name_en']}）·{ORIENTATION_LABELS[orientation]}。",
            f"核心母题：{card['archetype_zh']}",
            f"本次方向：{orientation_lens}",
            f"必须转译为原创场景的象征：{symbols}。不要复刻任何现有塔罗牌面。",
            f"媒介：{illustration['medium']}。",
            f"镜头：{illustration['camera']}。",
            f"光线：{illustration['lighting']}。",
            f"构图：{illustration['geometry']}。",
            f"材质：{illustration['texture']}。",
            f"人物规则：{illustration['character_policy']}。",
            (
                "配色："
                f"夜墨 {palette['night_ink']}、深靛 {palette['deep_indigo']}、"
                f"暮紫 {palette['twilight_violet']}、月白 {palette['moon_ivory']}、"
                f"仪式金 {palette['ritual_gold']}、静玉绿 {palette['quiet_jade']}；"
                f"{palette['rule']}。"
            ),
            f"顶部安全区：{canvas['zones']['header']}。",
            f"中部叙事区：{canvas['zones']['narrative']}。",
            f"底部安全区：{canvas['zones']['reflection']}。",
            "画面要安静、克制、具有进入夜间仪式的沉浸感；主视觉清楚，远看也能识别。",
    ]
    preview_exact_text: list[str] = []
    if render_pass == "framed-preview":
        card_index = card.get("index")
        if not isinstance(card_index, int) or not 0 <= card_index < len(ROMAN_NUMERALS):
            raise PromptError("E_INVALID_ORACLE_RESULT：牌号无效")
        preview_exact_text = [
            ROMAN_NUMERALS[card_index],
            card["name_zh"],
            card["name_en"].upper(),
            " · ".join(
                [ORIENTATION_LABELS[orientation], *card["keywords_zh"][:2]]
            ),
        ]
        prompt_lines.extend(
            [
                f"牌框：{frame_system['outer_border']}。",
                f"内框：{frame_system['inner_arch']}。",
                f"装饰：{frame_system['ornaments']}；{frame_system['density_rule']}。",
                f"标题层级：{frame_system['title_hierarchy']}。",
                f"字体：{frame_system['typography']}。",
                "只渲染以下四项 Exact text，逐字呈现，不增删、不翻译、不生成其他文字：",
                *[f"- {item}" for item in preview_exact_text],
                "严禁伪文字、额外说明、Logo、水印、证书、预测结论或新增信息。",
            ]
        )
    else:
        prompt_lines.append(
            "严禁出现任何可读文字、伪文字、Logo、水印、证书、预测结论或新增信息。"
        )
    prompt = "\n".join(prompt_lines)
    return {
        "schema_version": "1.0.0",
        "template_id": "oracle",
        "render_pass": render_pass,
        "canvas": spec["canvas"],
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "overlay_exact_text": spec["exact_text"],
        "preview_exact_text": preview_exact_text,
        "overlay_rule": (
            visual_system["frame_system"]["preview_rule"]
            if render_pass == "framed-preview"
            else visual_system["overlay"]["rendering_rule"]
        ),
        "privacy": spec["privacy"],
        "receipts": {
            "visual_system": sha256_json(visual_system),
            "public_content": spec["public_content_hash"],
            "deck": payload["evidence"]["deck_hash"],
        },
    }


def write_private(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise PromptError("E_OUTPUT_EXISTS：提示词输出已存在")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build an image-generation prompt for an oracle share card."
    )
    parser.add_argument("input", type=Path, help="Validated final.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--aspect", choices=("portrait", "square"), default="portrait")
    parser.add_argument(
        "--render-pass",
        choices=("text-free-background", "framed-preview"),
        default="text-free-background",
    )
    parser.add_argument("--controls", type=Path)
    parser.add_argument("--scope", default="yuanbao-public-cn")
    args = parser.parse_args()
    try:
        payload = load_json(args.input)
        errors, warnings = validate(
            payload,
            stage="final",
            controls_path=args.controls,
            scope=args.scope,
        )
        if errors:
            raise PromptError("E_INVALID_FINAL：" + "；".join(errors))
        visual_system = load_json(VISUAL_SYSTEM_PATH)
        prompt_spec = build_prompt(
            payload,
            visual_system,
            aspect=args.aspect,
            render_pass=args.render_pass,
        )
        write_private(args.output, prompt_spec)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, PromptError) as exc:
        print(
            json.dumps(
                {"ok": False, "error": {"code": "E_PROMPT_BUILD_FAILED", "message": str(exc)}},
                ensure_ascii=False,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(args.output.resolve()),
                "template_id": prompt_spec["template_id"],
                "render_pass": prompt_spec["render_pass"],
                "canvas": prompt_spec["canvas"],
                "receipts": prompt_spec["receipts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
