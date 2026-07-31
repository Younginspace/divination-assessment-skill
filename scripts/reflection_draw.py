#!/usr/bin/env python3
"""Run a gated, single-result commit–reveal reflection card draw."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import hmac
import json
import os
import secrets
import stat
import sys
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from feature_gate import GateError, check_feature, sha256_json


SCRIPT_DIR = Path(__file__).resolve().parent
DECK_PATH = SCRIPT_DIR / "oracle_deck.json"
COMMIT_PREFIX = "divination-assessment|commit"
DRAW_PREFIX = "divination-assessment|draw"
FEATURE = "oracle-reflection"
FEATURE_VERSION = "1.0.0"


class DrawError(ValueError):
    def __init__(self, code: str, message: str, fields: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.fields = fields or []


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise DrawError("E_FILE_NOT_FOUND", f"找不到文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise DrawError(
            "E_INVALID_JSON",
            f"JSON 解析失败：第 {exc.lineno} 行第 {exc.colno} 列",
        ) from exc


def validate_private_parent(path: Path) -> None:
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise DrawError(
            "E_RUN_DIR",
            "状态文件必须位于已存在的私有单次运行目录。",
            ["state"],
        )
    mode = stat.S_IMODE(parent.stat().st_mode)
    if mode & 0o077:
        raise DrawError(
            "E_RUN_DIR",
            "运行目录权限必须是 0700 或更严格。",
            ["state"],
        )


def atomic_write_json(
    path: Path,
    payload: dict[str, Any],
    *,
    private: bool = False,
    overwrite: bool = False,
) -> None:
    if path.exists() and not overwrite:
        raise DrawError(
            "E_OUTPUT_EXISTS",
            "目标文件已存在；请使用新的文件名，避免把旧结果误当成当前结果。",
            ["output"],
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        if private:
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        if private:
            os.chmod(path, 0o600)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


@contextmanager
def exclusive_state_lock(state_path: Path) -> Iterator[None]:
    lock_path = state_path.with_name(state_path.name + ".lock")
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def load_deck() -> dict[str, Any]:
    deck = load_json(DECK_PATH)
    cards = deck.get("cards") if isinstance(deck, dict) else None
    if not isinstance(cards, list) or len(cards) != 22:
        raise RuntimeError("Oracle deck must contain exactly 22 cards")
    if [card.get("index") for card in cards] != list(range(22)):
        raise RuntimeError("Oracle deck indices must be contiguous from 0 to 21")
    return deck


def deck_hash_for(deck: dict[str, Any]) -> str:
    return sha256_json(deck)


def commitment_for(
    deck_version: str, deck_hash: str, server_seed_hex: str
) -> str:
    message = (
        f"{COMMIT_PREFIX}|{deck_version}|{deck_hash}|{server_seed_hex}"
    ).encode("utf-8")
    return hashlib.sha256(message).hexdigest()


def digest_for(
    deck_version: str,
    deck_hash: str,
    server_seed_hex: str,
    client_seed: str,
) -> str:
    try:
        key = bytes.fromhex(server_seed_hex)
    except ValueError as exc:
        raise DrawError("E_DRAW_STATE", "状态文件中的 server_seed 无效。") from exc
    message = (
        f"{DRAW_PREFIX}|{deck_version}|{deck_hash}|{client_seed}"
    ).encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def load_client_seed(path: Path) -> str:
    if path.is_symlink():
        raise DrawError(
            "E_INVALID_CLIENT_SEED",
            "client seed 文件不能是符号链接。",
            ["client_seed_file"],
        )
    try:
        mode = path.stat().st_mode
    except FileNotFoundError as exc:
        raise DrawError(
            "E_INVALID_CLIENT_SEED",
            f"找不到 client seed 文件：{path}",
            ["client_seed_file"],
        ) from exc
    if not stat.S_ISREG(mode):
        raise DrawError(
            "E_INVALID_CLIENT_SEED",
            "client seed 必须来自普通文本文件。",
            ["client_seed_file"],
        )
    if path.stat().st_size > 1024:
        raise DrawError(
            "E_INVALID_CLIENT_SEED",
            "client seed 文件过大。",
            ["client_seed_file"],
        )
    client_seed = path.read_text(encoding="utf-8").rstrip("\r\n")
    if not client_seed or len(client_seed) > 256 or "\x00" in client_seed:
        raise DrawError(
            "E_INVALID_CLIENT_SEED",
            "client_seed 必须是 1—256 个字符的非空文本。",
            ["client_seed_file"],
        )
    return client_seed


def feature_receipt(controls_path: Path | None, scope: str) -> dict[str, Any]:
    try:
        return check_feature(
            controls_path,
            FEATURE,
            FEATURE_VERSION,
            scope,
        )
    except GateError as exc:
        raise DrawError(exc.code, str(exc), exc.fields) from exc


def validate_state(
    state: Any,
    deck: dict[str, Any],
    current_receipt: dict[str, Any],
) -> dict[str, Any]:
    required = {
        "schema_version",
        "deck_version",
        "deck_hash",
        "server_seed",
        "commitment",
        "created_at",
        "status",
        "feature_control_receipt",
    }
    if not isinstance(state, dict) or not required.issubset(state):
        raise DrawError("E_DRAW_STATE", "状态文件结构不完整。", ["state"])
    if state["schema_version"] != "1.2.0":
        raise DrawError("E_DRAW_STATE", "状态文件版本不受支持。", ["state"])
    current_deck_hash = deck_hash_for(deck)
    if (
        state["deck_version"] != deck["deck_version"]
        or state["deck_hash"] != current_deck_hash
    ):
        raise DrawError(
            "E_DRAW_STATE",
            "牌组版本或内容与 commit 时不一致。",
            ["deck_version", "deck_hash"],
        )
    stored_receipt = state.get("feature_control_receipt")
    if (
        not isinstance(stored_receipt, dict)
        or stored_receipt.get("control_record_hash")
        != current_receipt.get("control_record_hash")
    ):
        raise DrawError(
            "E_FEATURE_DISABLED",
            "当前功能控制策略与 commit 时不一致，禁止继续。",
            ["feature_control_receipt"],
        )
    return state


def commit(
    state_path: Path,
    controls_path: Path | None,
    scope: str,
) -> dict[str, Any]:
    validate_private_parent(state_path)
    receipt = feature_receipt(controls_path, scope)
    deck = load_deck()
    deck_hash = deck_hash_for(deck)
    with exclusive_state_lock(state_path):
        if state_path.exists():
            raise DrawError(
                "E_DRAW_STATE",
                "状态文件已存在；请使用新的私有单次运行目录。",
                ["state"],
            )
        server_seed_hex = secrets.token_hex(32)
        deck_version = deck["deck_version"]
        commitment = commitment_for(deck_version, deck_hash, server_seed_hex)
        state = {
            "schema_version": "1.2.0",
            "deck_version": deck_version,
            "deck_hash": deck_hash,
            "server_seed": server_seed_hex,
            "commitment": commitment,
            "created_at": utc_now(),
            "status": "committed",
            "feature_control_receipt": receipt,
        }
        atomic_write_json(state_path, state, private=True)
    return {
        "ok": True,
        "phase": "commit",
        "deck_version": deck_version,
        "deck_hash": f"sha256:{deck_hash}",
        "card_count": len(deck["cards"]),
        "commitment": commitment,
        "control_revision": receipt["control_revision"],
        "next": "请用户自行提供非敏感 client seed；把它安全写入私有文本文件后执行 reveal。",
    }


def build_result(
    state: dict[str, Any],
    deck: dict[str, Any],
    client_seed: str,
    receipt: dict[str, Any],
) -> dict[str, Any]:
    server_seed_hex = state["server_seed"]
    expected_commitment = commitment_for(
        state["deck_version"], state["deck_hash"], server_seed_hex
    )
    if not hmac.compare_digest(expected_commitment, state["commitment"]):
        raise DrawError(
            "E_DRAW_STATE",
            "承诺与状态中的随机种子不一致。",
            ["state"],
        )

    digest = digest_for(
        state["deck_version"],
        state["deck_hash"],
        server_seed_hex,
        client_seed,
    )
    digest_bytes = bytes.fromhex(digest)
    card_index = int.from_bytes(digest_bytes[:8], "big") % len(deck["cards"])
    orientation = "reversed" if digest_bytes[8] & 1 else "upright"
    card = deck["cards"][card_index]
    return {
        "schema_version": "1.0.0",
        "mode": "oracle-reflection",
        "run_id": str(uuid.uuid4()),
        "created_at": utc_now(),
        "evidence": {
            "deck_version": deck["deck_version"],
            "deck_hash": f"sha256:{state['deck_hash']}",
            "commitment": state["commitment"],
            "client_seed": client_seed,
            "server_seed_reveal": server_seed_hex,
            "digest": digest,
            "feature_control": receipt,
            "verification_formula": {
                "commitment": "SHA256('divination-assessment|commit|' + deck_version + '|' + deck_hash + '|' + server_seed_hex)",
                "digest": "HMAC-SHA256(key=bytes.fromhex(server_seed_hex), message='divination-assessment|draw|' + deck_version + '|' + deck_hash + '|' + client_seed)",
                "card_index": "unsigned_big_endian(digest[0:8]) mod 22",
                "orientation": "digest byte 8 least-significant bit: 0=upright, 1=reversed",
            },
        },
        "result": {
            "card": card,
            "orientation": orientation,
            "not_a_prediction": True,
        },
        "quality": {
            "status": "pass",
            "warnings": [
                "该流程可复核承诺与抽取，但服务器在 commit 前仍可选择种子；不要称为绝对公平。"
            ],
        },
        "safety": {
            "decision": "allow_with_boundary",
            "prohibited_uses": [
                "医疗、法律、投资、赌博、生育或死亡预测",
                "替代现实证据或专业建议",
                "因不满意结果而重复抽取",
            ],
        },
    }


def reveal(
    state_path: Path,
    client_seed: str,
    controls_path: Path | None,
    scope: str,
) -> tuple[dict[str, Any], bool]:
    receipt = feature_receipt(controls_path, scope)
    deck = load_deck()
    with exclusive_state_lock(state_path):
        state = validate_state(load_json(state_path), deck, receipt)
        if state["status"] == "revealed":
            existing = state.get("revealed_result")
            if not isinstance(existing, dict):
                raise DrawError(
                    "E_DRAW_STATE",
                    "状态已标记揭示，但缺少持久化结果。",
                    ["revealed_result"],
                )
            existing_seed = existing.get("evidence", {}).get("client_seed")
            if existing_seed != client_seed:
                raise DrawError(
                    "E_DRAW_STATE",
                    "该承诺已使用另一个 client seed 揭示；不能重新抽取。",
                    ["client_seed"],
                )
            return existing, True
        if state["status"] != "committed":
            raise DrawError("E_DRAW_STATE", "未知状态，禁止揭示。", ["status"])

        result = build_result(state, deck, client_seed, receipt)
        revealed_state = dict(state)
        revealed_state["status"] = "revealed"
        revealed_state["revealed_at"] = result["created_at"]
        revealed_state["revealed_result"] = result
        atomic_write_json(
            state_path,
            revealed_state,
            private=True,
            overwrite=True,
        )
        return result, False


def export_existing(
    state_path: Path,
    controls_path: Path | None,
    scope: str,
) -> dict[str, Any]:
    receipt = feature_receipt(controls_path, scope)
    deck = load_deck()
    with exclusive_state_lock(state_path):
        state = validate_state(load_json(state_path), deck, receipt)
        if state["status"] != "revealed" or not isinstance(
            state.get("revealed_result"), dict
        ):
            raise DrawError(
                "E_DRAW_STATE",
                "还没有可导出的已揭示结果。",
                ["status"],
            )
        return state["revealed_result"]


def error_payload(error: DrawError) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": error.code,
            "message": str(error),
            "fields": error.fields,
        },
    }


def add_gate_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--controls",
        "--approvals",
        dest="controls",
        type=Path,
        help="Host feature controls; --approvals is a compatibility alias.",
    )
    parser.add_argument("--scope", default="yuanbao-public-cn")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a gated, single-result reflection card draw."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    commit_parser = subparsers.add_parser("commit")
    commit_parser.add_argument("--state", required=True, type=Path)
    add_gate_arguments(commit_parser)

    reveal_parser = subparsers.add_parser("reveal")
    reveal_parser.add_argument("--state", required=True, type=Path)
    reveal_parser.add_argument("--client-seed-file", required=True, type=Path)
    reveal_parser.add_argument("--output", type=Path)
    add_gate_arguments(reveal_parser)

    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--state", required=True, type=Path)
    export_parser.add_argument("--output", required=True, type=Path)
    add_gate_arguments(export_parser)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "commit":
            payload = commit(args.state, args.controls, args.scope)
        elif args.command == "reveal":
            client_seed = load_client_seed(args.client_seed_file)
            payload, reused = reveal(
                args.state,
                client_seed,
                args.controls,
                args.scope,
            )
            if args.output:
                atomic_write_json(args.output, payload, private=True)
            if reused:
                print(
                    json.dumps(
                        {
                            "ok": True,
                            "phase": "reveal",
                            "reused_existing_result": True,
                            "result": payload,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                return 0
        else:
            payload = export_existing(args.state, args.controls, args.scope)
            atomic_write_json(args.output, payload, private=True)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except DrawError as exc:
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
