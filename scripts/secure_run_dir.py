#!/usr/bin/env python3
"""Create or safely clean a private one-run workspace under the system temp dir."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path


PREFIX = "divination-assessment-"
SENTINEL = ".divination-assessment-run"


class RunDirError(ValueError):
    pass


def create_run_dir() -> Path:
    path = Path(tempfile.mkdtemp(prefix=PREFIX))
    os.chmod(path, 0o700)
    sentinel_path = path / SENTINEL
    sentinel_path.write_text(str(uuid.uuid4()) + "\n", encoding="utf-8")
    os.chmod(sentinel_path, 0o600)
    return path


def validate_cleanup_target(path: Path) -> Path:
    temp_root = Path(tempfile.gettempdir()).resolve()
    if path.is_symlink():
        raise RunDirError("拒绝清理符号链接。")
    resolved = path.resolve()
    if resolved.parent != temp_root:
        raise RunDirError("只允许清理系统临时目录下的直接子目录。")
    if not resolved.name.startswith(PREFIX):
        raise RunDirError("目录名不是本 Skill 创建的临时目录。")
    sentinel = resolved / SENTINEL
    if not resolved.is_dir() or not sentinel.is_file() or sentinel.is_symlink():
        raise RunDirError("缺少有效 sentinel，拒绝清理。")
    return resolved


def cleanup_run_dir(path: Path) -> None:
    resolved = validate_cleanup_target(path)
    shutil.rmtree(resolved)


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage a private one-run workspace.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("create")
    cleanup_parser = subparsers.add_parser("cleanup")
    cleanup_parser.add_argument("--path", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "create":
            path = create_run_dir()
            payload = {
                "ok": True,
                "path": str(path),
                "directory_mode": "0700",
                "cleanup_command": f"python3 scripts/secure_run_dir.py cleanup --path {path}",
            }
        else:
            cleanup_run_dir(args.path)
            payload = {"ok": True, "removed": str(args.path)}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except RunDirError as exc:
        print(
            json.dumps(
                {"ok": False, "error": {"code": "E_RUN_DIR", "message": str(exc)}},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
