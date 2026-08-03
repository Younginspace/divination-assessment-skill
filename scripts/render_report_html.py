#!/usr/bin/env python3
"""Render a validated final result to a self-contained, privacy-minimized HTML file."""

from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
from typing import Any

from validate_result import validate


MODE_LABELS = {
    "personality": "人格偏好结果",
    "relationship-reflection": "关系反思结果",
    "oracle-reflection": "抽牌反思结果",
    "chart-interpretation": "传统文化盘面结果",
    "report-followup": "已有报告解释",
}


def escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def list_html(values: Any, empty_text: str = "无") -> str:
    if not isinstance(values, list) or not values:
        return f"<p class=\"muted\">{escape(empty_text)}</p>"
    items = "".join(f"<li>{escape(value)}</li>" for value in values)
    return f"<ul>{items}</ul>"


def render(payload: dict[str, Any], include_result: bool = False) -> str:
    mode = payload.get("mode", "unknown")
    title = MODE_LABELS.get(mode, "结果报告")
    presentation = payload.get("presentation", {})
    depth = presentation.get("depth", "quick")

    interpretation_cards = []
    for item in payload.get("interpretation", []):
        interpretation_cards.append(
            """
            <article class="card">
              <div class="badge">{strength}</div>
              <h3>{claim}</h3>
              <h4>限制与不能推出</h4>
              {limitations}
              {cannot_support}
              <h4>相反信号</h4>
              {counter_signals}
              <p class="meta">背景核对：{fit_status}</p>
            </article>
            """.format(
                strength=escape(item.get("support_strength", "unknown")),
                claim=escape(item.get("claim", "")),
                limitations=list_html(item.get("limitations")),
                cannot_support=list_html(item.get("cannot_support")),
                counter_signals=list_html(item.get("counter_signals"), "暂未记录"),
                fit_status=escape(item.get("fit_status", "not_checked")),
            )
        )

    action_cards = "".join(
        f"<li>{escape(item.get('text', ''))}</li>"
        for item in payload.get("actions", [])
        if isinstance(item, dict)
    )
    raw_result = ""
    if include_result:
        raw_result = (
            "<details><summary>展开结构化结果</summary><pre>"
            + escape(json.dumps(payload.get("result", {}), ensure_ascii=False, indent=2))
            + "</pre></details>"
        )
    disclaimer = payload.get("disclaimer")
    disclaimer_html = (
        f"<div class=\"notice\">{escape(disclaimer)}</div>" if disclaimer else ""
    )

    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>{title}</title>
  <style>
    :root {{ color-scheme: light; --ink:#26231f; --muted:#716b63; --paper:#f7f3eb;
      --card:#fffdfa; --line:#ded7cb; --accent:#6b4f37; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--paper); color:var(--ink);
      font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
      line-height:1.65; }}
    main {{ width:min(760px,calc(100% - 32px)); margin:32px auto 64px; }}
    header {{ padding:28px; border:1px solid var(--line); border-radius:18px;
      background:var(--card); }}
    h1 {{ margin:0 0 8px; font-size:clamp(26px,5vw,42px); }}
    h2 {{ margin-top:36px; }} h3 {{ margin:10px 0; }} h4 {{ margin:18px 0 6px; }}
    .eyebrow,.meta,.muted {{ color:var(--muted); }}
    .grid {{ display:grid; gap:16px; }}
    .card {{ padding:22px; border:1px solid var(--line); border-radius:16px;
      background:var(--card); }}
    .badge {{ display:inline-block; padding:3px 9px; border-radius:999px;
      background:#eee5d8; color:var(--accent); font-size:13px; }}
    .notice {{ margin-top:28px; padding:16px; border-left:4px solid var(--accent);
      background:var(--card); }}
    details {{ margin-top:28px; }} pre {{ overflow:auto; padding:16px; background:#211f1c;
      color:#f5efe5; border-radius:12px; }}
    footer {{ margin-top:32px; color:var(--muted); font-size:13px; }}
  </style>
</head>
<body>
<main>
  <header>
    <div class="eyebrow">本地生成 · {depth} · 默认隐藏原始输入</div>
    <h1>{title}</h1>
    <p>先看结论，再按需展开证据、反证和限制。</p>
  </header>
  <h2>如何理解</h2>
  <section class="grid">{interpretations}</section>
  <h2>可以试的一步</h2>
  <section class="card"><ol>{actions}</ol></section>
  {raw_result}
  {disclaimer}
  <footer>该文件无外部字体、脚本或网络请求。除非显式选择，否则不包含原始结果。</footer>
</main>
</body>
</html>
""".format(
        title=escape(title),
        depth=escape(depth),
        interpretations="".join(interpretation_cards),
        actions=action_cards,
        raw_result=raw_result,
        disclaimer=disclaimer_html,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-result", action="store_true")
    parser.add_argument("--controls", type=Path)
    parser.add_argument("--engine-allowlist", type=Path)
    parser.add_argument("--scope", default="yuanbao-public-cn")
    args = parser.parse_args()

    if args.output.exists():
        print(json.dumps({"ok": False, "error": {"code": "E_OUTPUT_EXISTS"}}))
        return 2
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
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

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        render(payload, include_result=args.include_result),
        encoding="utf-8",
    )
    os.chmod(args.output, 0o600)
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(args.output.resolve()),
                "privacy": "raw evidence omitted; result omitted unless --include-result",
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
