#!/usr/bin/env python3
"""Convert a validated chart adapter payload into the unified result contract."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from validate_chart_adapter import load_json, validate_chart


class ConvertError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise ConvertError(
            "E_OUTPUT_EXISTS",
            "输出文件已存在；请使用新的私有单次运行目录和唯一文件名。",
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def convert(
    adapter_payload: Any,
    allowlist_path: Path | None,
    controls_path: Path | None,
    scope: str,
) -> dict[str, Any]:
    errors, warnings, receipt = validate_chart(
        adapter_payload,
        allowlist_path,
        controls_path,
        scope,
    )
    if errors or receipt is None:
        raise ConvertError(
            "E_ENGINE_EVIDENCE",
            "命理引擎结果未通过适配器验收：" + "; ".join(errors),
        )
    return {
        "schema_version": "1.0.0",
        "mode": "chart-interpretation",
        "run_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "evidence": {
            "adapter_payload": adapter_payload,
            "adapter_receipt": receipt,
        },
        "result": {
            "chart": adapter_payload["chart"],
            "chart_system": adapter_payload["chart_system"],
            "traditional_framework_not_scientific_prediction": True,
        },
        "quality": {
            "status": "pass_with_warnings" if warnings else "pass",
            "warnings": warnings,
        },
        "safety": {
            "decision": "allow_with_boundary",
            "prohibited_uses": [
                "医疗、法律、投资、赌博、生育、死亡或就业结果预测",
                "把传统解释写成科学事实",
                "输出高于输入时间精度的结论",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert an approved chart adapter payload to unified JSON."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--allowlist", type=Path)
    parser.add_argument(
        "--controls",
        "--approvals",
        dest="controls",
        type=Path,
        help="Host feature controls; --approvals is a compatibility alias.",
    )
    parser.add_argument("--scope", default="yuanbao-public-cn")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = convert(
            load_json(args.input),
            args.allowlist,
            args.controls,
            args.scope,
        )
        atomic_write_json(args.output, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except ConvertError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {"code": exc.code, "message": str(exc), "fields": []},
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "E_INTERNAL",
                        "message": f"内部错误：{exc}",
                        "fields": [],
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
