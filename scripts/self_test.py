#!/usr/bin/env python3
"""Run offline positive, negative, concurrency, and recovery tests."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PYTHON = sys.executable


class TestFailure(AssertionError):
    pass


def write_json(path: Path, payload: Any, mode: int = 0o600) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(path, mode)


def write_text(path: Path, text: str, mode: int = 0o600) -> None:
    path.write_text(text, encoding="utf-8")
    os.chmod(path, mode)


def run(
    arguments: list[str],
    expected_code: int = 0,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        [PYTHON, *arguments],
        cwd=SCRIPT_DIR,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, **(env or {})},
    )
    if process.returncode != expected_code:
        raise TestFailure(
            f"Expected exit {expected_code}, got {process.returncode}: "
            f"{' '.join(arguments)}\nstdout={process.stdout}\nstderr={process.stderr}"
        )
    return process


def assert_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise TestFailure(f"{label}: expected {expected!r}, got {actual!r}")


def create_approvals(temp_dir: Path) -> Path:
    common = {
        "status": "approved",
        "feature_version": "1.0.0",
        "approver": "offline-test-reviewer",
        "legal_review_id": "LEGAL-TEST-001",
        "platform_review_id": "PLATFORM-TEST-001",
        "policy_snapshot_date": "2026-07-30",
        "approved_at": "2026-07-01T00:00:00+00:00",
        "expires_at": "2099-01-01T00:00:00+00:00",
        "scopes": ["yuanbao-public-cn"],
    }
    payload = {
        "schema_version": "1.0.0",
        "profile": "offline-test-only",
        "approvals": {
            "oracle-reflection": {
                **common,
                "approval_id": "ORACLE-TEST-001",
            },
            "chart-generation": {
                **common,
                "approval_id": "CHART-TEST-001",
            },
            "vedic-lite-generation": {
                **common,
                "approval_id": "VEDIC-LITE-TEST-001",
            },
            "traditional-report-interpretation": {
                **common,
                "approval_id": "REPORT-TEST-001",
            },
        },
    }
    path = temp_dir / "feature-approvals.json"
    write_json(path, payload)
    return path


def create_disabled_controls(temp_dir: Path, feature: str) -> Path:
    modes = {
        "oracle-reflection": "REFLECTION_ONLY",
        "chart-generation": "FACTS_ONLY",
        "vedic-lite-generation": "VEDIC_LITE_FACTS_ONLY",
        "traditional-report-interpretation": "SOURCE_BOUND",
    }
    payload = {
        "schema_version": "2.0.0",
        "revision": f"offline-kill-{feature}",
        "issued_at": "2026-07-30T00:00:00+00:00",
        "expires_at": "2099-01-01T00:00:00+00:00",
        "features": {
            name: {
                "enabled": name != feature,
                "mode": mode,
                "feature_version": "1.0.0",
                "scopes": ["yuanbao-public-cn"],
                "reason": "离线熔断测试",
            }
            for name, mode in modes.items()
        },
    }
    path = temp_dir / f"feature-controls-disable-{feature}.json"
    write_json(path, payload)
    return path


def create_signed_production_controls(
    temp_dir: Path,
    *,
    secret: str,
    revision_number: int = 7,
) -> Path:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    modes = {
        "oracle-reflection": "REFLECTION_ONLY",
        "chart-generation": "FACTS_ONLY",
        "vedic-lite-generation": "VEDIC_LITE_FACTS_ONLY",
        "traditional-report-interpretation": "SOURCE_BOUND",
    }
    payload: dict[str, Any] = {
        "schema_version": "2.0.0",
        "revision": f"production-{revision_number}",
        "revision_number": revision_number,
        "control_plane_id": "offline-production-contract-test",
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=5)).isoformat(),
        "features": {
            feature: {
                "enabled": True,
                "mode": mode,
                "feature_version": "1.0.0",
                "scopes": ["yuanbao-public-cn"],
                "reason": "生产签名快照契约测试",
            }
            for feature, mode in modes.items()
        },
    }
    signature = hmac.new(
        secret.encode("utf-8"),
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    payload["signature"] = "hmac-sha256:" + signature
    path = temp_dir / "feature-controls-production.json"
    write_json(path, payload)
    return path


def create_allowlist(temp_dir: Path) -> Path:
    payload = {
        "schema_version": "1.0.0",
        "profile": "offline-test-only",
        "engines": [
            {
                "status": "approved",
                "name": "fixture-engine",
                "version": "1.2.3",
                "artifact_hash": "sha256:" + "a" * 64,
                "license": "internal-test-only",
                "supported_systems": ["bazi"],
                "approval_id": "ENGINE-TEST-001",
                "algorithm_review_id": "ALGO-TEST-001",
                "license_review_id": "LICENSE-TEST-001",
                "deployment_review_id": "DEPLOY-TEST-001",
                "expires_at": "2099-01-01T00:00:00+00:00",
            }
        ],
    }
    path = temp_dir / "engine-allowlist.json"
    write_json(path, payload)
    return path


def test_feature_gate(temp_dir: Path) -> None:
    enabled = run(["feature_gate.py", "oracle-reflection"])
    receipt = json.loads(enabled.stdout)["receipt"]
    assert_equal(receipt["mode"], "REFLECTION_ONLY", "bounded default mode")
    disabled_controls = create_disabled_controls(temp_dir, "oracle-reflection")
    disabled = run(
        [
            "feature_gate.py",
            "oracle-reflection",
            "--controls",
            str(disabled_controls),
        ],
        expected_code=2,
    )
    assert_equal(
        json.loads(disabled.stdout)["error"]["code"],
        "E_FEATURE_DISABLED",
        "remote kill switch",
    )
    approvals = create_approvals(temp_dir)
    legacy_enabled = run(
        [
            "feature_gate.py",
            "oracle-reflection",
            "--approvals",
            str(approvals),
        ]
    )
    assert_equal(json.loads(legacy_enabled.stdout)["ok"], True, "legacy control alias")

    missing_production = run(
        ["feature_gate.py", "oracle-reflection"],
        expected_code=2,
        env={
            "DIVINATION_CONTROL_PROFILE": "production",
            "DIVINATION_FEATURE_CONTROLS_FILE": "",
        },
    )
    assert_equal(
        json.loads(missing_production.stdout)["error"]["code"],
        "E_FEATURE_DISABLED",
        "production must not use bundled fallback",
    )
    secret = "offline-test-key-material-32-bytes-minimum"
    production_controls = create_signed_production_controls(
        temp_dir,
        secret=secret,
    )
    production = run(
        [
            "feature_gate.py",
            "oracle-reflection",
            "--controls",
            str(production_controls),
        ],
        env={
            "DIVINATION_CONTROL_PROFILE": "production",
            "DIVINATION_FEATURE_CONTROLS_HMAC_KEY": secret,
            "DIVINATION_FEATURE_CONTROLS_MIN_REVISION": "7",
        },
    )
    production_receipt = json.loads(production.stdout)["receipt"]
    assert_equal(
        production_receipt["control_profile"],
        "production",
        "signed production control profile",
    )
    missing_minimum_revision = run(
        [
            "feature_gate.py",
            "oracle-reflection",
            "--controls",
            str(production_controls),
        ],
        expected_code=2,
        env={
            "DIVINATION_CONTROL_PROFILE": "production",
            "DIVINATION_FEATURE_CONTROLS_HMAC_KEY": secret,
            "DIVINATION_FEATURE_CONTROLS_MIN_REVISION": "",
        },
    )
    assert_equal(
        json.loads(missing_minimum_revision.stdout)["error"]["code"],
        "E_FEATURE_DISABLED",
        "production minimum revision is mandatory",
    )
    invalid_signature = run(
        [
            "feature_gate.py",
            "oracle-reflection",
            "--controls",
            str(production_controls),
        ],
        expected_code=2,
        env={
            "DIVINATION_CONTROL_PROFILE": "production",
            "DIVINATION_FEATURE_CONTROLS_HMAC_KEY": "different-offline-key-material-32-bytes",
            "DIVINATION_FEATURE_CONTROLS_MIN_REVISION": "7",
        },
    )
    assert_equal(
        json.loads(invalid_signature.stdout)["error"]["code"],
        "E_FEATURE_DISABLED",
        "production signature mismatch must fail closed",
    )
    rollback = run(
        [
            "feature_gate.py",
            "oracle-reflection",
            "--controls",
            str(production_controls),
        ],
        expected_code=2,
        env={
            "DIVINATION_CONTROL_PROFILE": "production",
            "DIVINATION_FEATURE_CONTROLS_HMAC_KEY": secret,
            "DIVINATION_FEATURE_CONTROLS_MIN_REVISION": "8",
        },
    )
    assert_equal(
        json.loads(rollback.stdout)["error"]["code"],
        "E_FEATURE_DISABLED",
        "production revision rollback must fail closed",
    )


def test_questions(_: Path) -> None:
    process = run(["score_mini_ipip.py", "questions", "--language", "zh-CN"])
    payload = json.loads(process.stdout)
    assert_equal(len(payload["questions"]), 20, "Mini-IPIP question count")
    assert_equal(
        payload["translation_status"],
        "draft-0.1-unvalidated",
        "translation version",
    )


def add_final_layer(payload: dict[str, Any], evidence_path: str) -> None:
    payload["interpretation"] = [
        {
            "claim": "这是一条与事实字段绑定的谨慎解释。",
            "evidence_paths": [evidence_path],
            "limitations": ["不代表诊断、命运或固定身份。"],
            "epistemic_status": "self_report",
            "support_strength": "mixed",
            "counter_signals": [],
            "cannot_support": ["不能据此作诊断或高影响决定。"],
            "fit_status": "not_checked",
        }
    ]
    payload["actions"] = [
        {
            "text": "未来一周观察一个具体例子，再判断这条解释是否贴合。",
            "low_risk": True,
            "reversible": True,
        }
    ]
    payload["presentation"] = {
        "depth": "quick",
        "progressive_disclosure": True,
    }


def test_personality(temp_dir: Path) -> None:
    answers_path = temp_dir / "mini-answers.json"
    result_path = temp_dir / "mini-result.json"
    write_json(
        answers_path,
        {"language": "zh-CN", "answers": {str(i): 5 for i in range(1, 21)}},
    )
    run(
        [
            "score_mini_ipip.py",
            "score",
            str(answers_path),
            "--output",
            str(result_path),
        ]
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    expected_sums = {
        "extraversion": 12,
        "agreeableness": 12,
        "conscientiousness": 12,
        "neuroticism": 12,
        "imagination": 8,
    }
    actual_sums = {
        trait: score["sum"] for trait, score in result["result"]["scores"].items()
    }
    assert_equal(actual_sums, expected_sums, "Mini-IPIP keyed sums")
    assert_equal(result["quality"]["response_pattern"], "straight_lining", "pattern")
    run(["validate_result.py", str(result_path)])

    final_result = json.loads(result_path.read_text(encoding="utf-8"))
    add_final_layer(final_result, "result.scores.conscientiousness")
    final_path = temp_dir / "mini-final.json"
    write_json(final_path, final_result)
    run(["validate_result.py", str(final_path), "--stage", "final"])

    tampered = json.loads(result_path.read_text(encoding="utf-8"))
    tampered["result"]["scores"]["extraversion"]["mean"] = 1
    tampered_path = temp_dir / "mini-tampered.json"
    write_json(tampered_path, tampered)
    run(["validate_result.py", str(tampered_path)], expected_code=1)

    invalid_path = temp_dir / "mini-invalid.json"
    write_json(invalid_path, {"answers": {"1": 3}})
    process = run(
        ["score_mini_ipip.py", "score", str(invalid_path)], expected_code=2
    )
    assert_equal(
        json.loads(process.stderr)["error"]["code"],
        "E_INVALID_ANSWERS",
        "invalid answers",
    )
    stale = run(
        [
            "score_mini_ipip.py",
            "score",
            str(answers_path),
            "--output",
            str(result_path),
        ],
        expected_code=2,
    )
    assert_equal(
        json.loads(stale.stderr)["error"]["code"],
        "E_OUTPUT_EXISTS",
        "stale output refusal",
    )


def test_type_preference(temp_dir: Path) -> None:
    questions = json.loads(
        run(["score_type_preference.py", "questions"]).stdout
    )
    assert_equal(len(questions["questions"]), 12, "original preference question count")
    assert_equal(
        questions["instrument"]["official_affiliation"],
        False,
        "original preference affiliation",
    )

    answers_path = temp_dir / "preference-answers.json"
    result_path = temp_dir / "preference-result.json"
    write_json(
        answers_path,
        {
            "language": "zh-CN",
            "answers": {str(item): 1 for item in range(1, 13)},
        },
    )
    run(
        [
            "score_type_preference.py",
            "score",
            str(answers_path),
            "--output",
            str(result_path),
        ]
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert_equal(
        set(result["result"]["scores"]),
        {
            "interaction_energy",
            "information_focus",
            "decision_weighting",
            "action_organization",
        },
        "four original preference axes",
    )
    assert_equal(
        result["result"]["four_letter_preference"]["code"],
        "ESTJ",
        "all-positive four-letter preference",
    )
    assert_equal(
        result["result"]["four_letter_preference"]["official_mbti_result"],
        False,
        "four-letter result is explicitly unofficial",
    )
    assert_equal(
        result["result"]["scores"]["interaction_energy"]["preference_percentage"]["value"],
        100,
        "all-positive preference percentage",
    )
    assert_equal(
        result["result"]["derived_function_preferences"]["summary"],
        "Te → Si → Ne → Fi",
        "ESTJ derived function preference",
    )
    run(["validate_result.py", str(result_path)])

    negative_answers_path = temp_dir / "preference-negative-answers.json"
    negative_result_path = temp_dir / "preference-negative-result.json"
    write_json(
        negative_answers_path,
        {
            "language": "zh-CN",
            "answers": {str(item): -1 for item in range(1, 13)},
        },
    )
    run(
        [
            "score_type_preference.py",
            "score",
            str(negative_answers_path),
            "--output",
            str(negative_result_path),
        ]
    )
    negative = json.loads(negative_result_path.read_text(encoding="utf-8"))
    assert_equal(
        negative["result"]["four_letter_preference"]["code"],
        "INFP",
        "all-negative four-letter preference",
    )
    assert_equal(
        negative["result"]["derived_function_preferences"]["summary"],
        "Fi → Ne → Si → Te",
        "INFP derived function preference",
    )
    assert_equal(
        negative["result"]["derived_function_preferences"]["plain_summary_zh"],
        (
            "确认自己真心认不认可（Fi） → 从一个点展开多种可能（Ne） → "
            "用过往经验核对细节（Si） → 用标准和计划推进（Te）"
        ),
        "INFP plain-language function preference",
    )
    assert_equal(
        negative["result"]["derived_function_preferences"]["plain_sequence_zh"],
        (
            "确认自己是否真心认可 → 探索还有哪些可能 → "
            "用过往经验核对细节 → 用计划和标准推动落地"
        ),
        "INFP plain-language processing sequence",
    )
    assert_equal(
        all(
            item["plain_explanation_zh"]
            for item in negative["result"]["derived_function_preferences"]["stack"]
        ),
        True,
        "each derived function includes a plain-language explanation",
    )
    run(["validate_result.py", str(negative_result_path)])

    mixed_answers_path = temp_dir / "preference-mixed-answers.json"
    mixed_result_path = temp_dir / "preference-mixed-result.json"
    mixed_answers = {
        str(item): (-1 if item % 3 in {1, 2} else 1)
        for item in range(1, 13)
    }
    write_json(
        mixed_answers_path,
        {
            "language": "zh-CN",
            "answers": mixed_answers,
        },
    )
    run(
        [
            "score_type_preference.py",
            "score",
            str(mixed_answers_path),
            "--output",
            str(mixed_result_path),
        ]
    )
    mixed = json.loads(mixed_result_path.read_text(encoding="utf-8"))
    assert_equal(
        mixed["result"]["scores"]["interaction_energy"]["preference_percentage"]["value"],
        67,
        "two-of-three binary preference percentage",
    )
    assert_equal(
        mixed["result"]["four_letter_preference"]["code"],
        "INFP",
        "mixed binary four-letter preference",
    )
    run(["validate_result.py", str(mixed_result_path)])

    invalid_answers_path = temp_dir / "preference-invalid-answers.json"
    invalid_result_path = temp_dir / "preference-invalid-result.json"
    write_json(
        invalid_answers_path,
        {
            "language": "zh-CN",
            "answers": {str(item): 0 for item in range(1, 13)},
        },
    )
    invalid = run(
        [
            "score_type_preference.py",
            "score",
            str(invalid_answers_path),
            "--output",
            str(invalid_result_path),
        ],
        expected_code=2,
    )
    assert_equal(
        json.loads(invalid.stderr)["error"]["code"],
        "E_INVALID_ANSWERS",
        "binary-only answers",
    )


def relationship_payload(default: int = 3) -> dict[str, Any]:
    answers = {str(i): default for i in range(1, 13)}
    return {
        "consent": {"partner_a": True, "partner_b": True},
        "partner_a": {"answers": dict(answers)},
        "partner_b": {"answers": dict(answers)},
    }


def test_relationship(temp_dir: Path) -> None:
    answers_path = temp_dir / "relationship-answers.json"
    result_path = temp_dir / "relationship-result.json"
    write_json(answers_path, relationship_payload())
    run(
        [
            "score_relationship_reflection.py",
            str(answers_path),
            "--output",
            str(result_path),
        ]
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    for dimension in result["result"]["dimensions"].values():
        assert_equal(dimension["partner_a_mean"], 3.0, "partner A mean")
        assert_equal(dimension["partner_b_mean"], 3.0, "partner B mean")
        assert_equal(dimension["absolute_gap"], 0.0, "relationship gap")
    run(["validate_result.py", str(result_path)])

    tampered = json.loads(result_path.read_text(encoding="utf-8"))
    tampered["result"]["dimensions"]["repair"]["absolute_gap"] = 4
    tampered_path = temp_dir / "relationship-tampered.json"
    write_json(tampered_path, tampered)
    run(["validate_result.py", str(tampered_path)], expected_code=1)

    no_consent = relationship_payload()
    no_consent["consent"]["partner_b"] = False
    invalid_path = temp_dir / "relationship-no-consent.json"
    write_json(invalid_path, no_consent)
    process = run(
        ["score_relationship_reflection.py", str(invalid_path)], expected_code=2
    )
    assert_equal(
        json.loads(process.stderr)["error"]["code"],
        "E_PARTNER_CONSENT",
        "partner consent",
    )

    safety_input = relationship_payload(default=4)
    safety_input["partner_a"]["answers"]["3"] = 1
    safety_input["partner_b"]["answers"]["9"] = 1
    safety_input_path = temp_dir / "relationship-safety.json"
    safety_result_path = temp_dir / "relationship-safety-result.json"
    write_json(safety_input_path, safety_input)
    run(
        [
            "score_relationship_reflection.py",
            str(safety_input_path),
            "--output",
            str(safety_result_path),
        ]
    )
    safety_result = json.loads(safety_result_path.read_text(encoding="utf-8"))
    assert_equal(
        safety_result["safety"]["reason_code"],
        "E_RELATIONSHIP_SAFETY",
        "relationship safety redirect",
    )
    if "dimensions" in safety_result["result"]:
        raise TestFailure("safety result must suppress dimensions")
    run(["validate_result.py", str(safety_result_path)], expected_code=1)
    safety_response_path = temp_dir / "relationship-safety-response.json"
    run(
        [
            "safety_response.py",
            "build",
            str(safety_result_path),
            "--output",
            str(safety_response_path),
        ]
    )
    run(
        [
            "safety_response.py",
            "validate",
            str(safety_response_path),
            "--source",
            str(safety_result_path),
        ]
    )


def oracle_args(
    command: str,
    state_path: Path,
    approvals_path: Path,
    extra: list[str] | None = None,
) -> list[str]:
    return [
        "reflection_draw.py",
        command,
        "--state",
        str(state_path),
        "--approvals",
        str(approvals_path),
        *(extra or []),
    ]


def test_oracle(temp_dir: Path) -> None:
    approvals = create_approvals(temp_dir)
    os.chmod(temp_dir, 0o700)

    disabled_state = temp_dir / "disabled-state.json"
    disabled_controls = create_disabled_controls(temp_dir, "oracle-reflection")
    disabled = run(
        [
            "reflection_draw.py",
            "commit",
            "--state",
            str(disabled_state),
            "--controls",
            str(disabled_controls),
        ],
        expected_code=2,
    )
    assert_equal(
        json.loads(disabled.stderr)["error"]["code"],
        "E_FEATURE_DISABLED",
        "oracle remote kill switch",
    )

    state_path = temp_dir / "draw-state.json"
    result_path = temp_dir / "draw-result.json"
    seed_path = temp_dir / "client-seed.txt"
    other_seed_path = temp_dir / "other-seed.txt"
    write_text(seed_path, "用户自选种子-2026")
    write_text(other_seed_path, "另一个种子")
    commit_process = run(oracle_args("commit", state_path, approvals))
    commitment = json.loads(commit_process.stdout)["commitment"]
    if len(commitment) != 64:
        raise TestFailure("commitment must be a SHA-256 hex digest")
    run(
        oracle_args(
            "reveal",
            state_path,
            approvals,
            [
                "--client-seed-file",
                str(seed_path),
                "--output",
                str(result_path),
            ],
        )
    )
    run(
        [
            "validate_result.py",
            str(result_path),
            "--approvals",
            str(approvals),
        ]
    )
    idempotent = run(
        oracle_args(
            "reveal",
            state_path,
            approvals,
            ["--client-seed-file", str(seed_path)],
        )
    )
    assert_equal(
        json.loads(idempotent.stdout)["reused_existing_result"],
        True,
        "idempotent reveal",
    )
    different = run(
        oracle_args(
            "reveal",
            state_path,
            approvals,
            ["--client-seed-file", str(other_seed_path)],
        ),
        expected_code=2,
    )
    assert_equal(
        json.loads(different.stderr)["error"]["code"],
        "E_DRAW_STATE",
        "different second seed refused",
    )

    tampered = json.loads(result_path.read_text(encoding="utf-8"))
    tampered["result"]["orientation"] = (
        "upright"
        if tampered["result"]["orientation"] == "reversed"
        else "reversed"
    )
    tampered_path = temp_dir / "draw-tampered.json"
    write_json(tampered_path, tampered)
    run(
        [
            "validate_result.py",
            str(tampered_path),
            "--approvals",
            str(approvals),
        ],
        expected_code=1,
    )

    for round_index in range(20):
        concurrent_state = temp_dir / f"concurrent-state-{round_index}.json"
        run(oracle_args("commit", concurrent_state, approvals))
        processes = [
            subprocess.Popen(
                [
                    PYTHON,
                    "reflection_draw.py",
                    "reveal",
                    "--state",
                    str(concurrent_state),
                    "--approvals",
                    str(approvals),
                    "--client-seed-file",
                    str(seed),
                ],
                cwd=SCRIPT_DIR,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for seed in (seed_path, other_seed_path)
        ]
        results = [
            process.communicate(timeout=10) + (process.returncode,)
            for process in processes
        ]
        codes = sorted(result[2] for result in results)
        assert_equal(
            codes,
            [0, 2],
            f"concurrent reveal single winner round {round_index}",
        )

    recover_state = temp_dir / "recover-state.json"
    recover_result = temp_dir / "recover-result.json"
    run(oracle_args("commit", recover_state, approvals))
    failed_export = run(
        oracle_args(
            "reveal",
            recover_state,
            approvals,
            [
                "--client-seed-file",
                str(seed_path),
                "--output",
                str(temp_dir),
            ],
        ),
        expected_code=2,
    )
    assert_equal(
        json.loads(failed_export.stderr)["error"]["code"],
        "E_OUTPUT_EXISTS",
        "export failure remains recoverable",
    )
    run(
        oracle_args(
            "export",
            recover_state,
            approvals,
            ["--output", str(recover_result)],
        )
    )
    run(
        [
            "validate_result.py",
            str(recover_result),
            "--approvals",
            str(approvals),
        ]
    )


def valid_chart_payload() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "engine": {
            "name": "fixture-engine",
            "version": "1.2.3",
            "artifact_hash": "sha256:" + "a" * 64,
            "license": "internal-test-only",
        },
        "input": {
            "calendar": "gregorian",
            "local_datetime": "1990-09-15T14:30:00",
            "timezone": "Asia/Shanghai",
            "location": {
                "label": "江苏省苏州市",
                "latitude": 31.2989,
                "longitude": 120.5853,
                "source": "test-fixture",
                "precision": "city",
            },
            "time_precision": {"kind": "approximate", "minutes": 5},
        },
        "chart_system": "bazi",
        "chart": {
            "pillars": {
                "year": "fixture-year",
                "month": "fixture-month",
                "day": "fixture-day",
                "hour": "fixture-hour",
            }
        },
        "boundary_checks": [
            {"name": "timezone-resolved", "status": "pass", "detail": "fixture"},
            {"name": "location-resolved", "status": "pass", "detail": "fixture"},
            {
                "name": "time-precision-propagated",
                "status": "pass",
                "detail": "fixture",
            },
            {"name": "solar-term-boundary", "status": "pass", "detail": "fixture"},
            {"name": "day-boundary-policy", "status": "pass", "detail": "fixture"},
        ],
        "provenance": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "timezone_db_version": "fixture-2026a",
        },
        "warnings": ["测试夹具，不是真实排盘。"],
    }


def test_chart_adapter(temp_dir: Path) -> None:
    approvals = create_approvals(temp_dir)
    allowlist = create_allowlist(temp_dir)
    valid_path = temp_dir / "chart-valid.json"
    write_json(valid_path, valid_chart_payload())
    common_args = [
        "--allowlist",
        str(allowlist),
        "--approvals",
        str(approvals),
    ]
    external = run(
        ["validate_chart_adapter.py", str(valid_path), *common_args],
        expected_code=1,
    )
    if "E_ENGINE_ATTESTATION_UNSUPPORTED" not in external.stdout:
        raise TestFailure("external engine without host attestation must fail closed")

    fake = valid_chart_payload()
    fake["engine"]["version"] = "latest"
    fake["input"]["timezone"] = "Foo/Bar"
    fake_path = temp_dir / "chart-fake.json"
    write_json(fake_path, fake)
    run(
        ["validate_chart_adapter.py", str(fake_path), *common_args],
        expected_code=1,
    )


def test_builtin_engines(temp_dir: Path) -> None:
    input_path = temp_dir / "builtin-engine-input.json"
    bazi_path = temp_dir / "builtin-bazi.json"
    western_path = temp_dir / "builtin-western.json"
    vedic_path = temp_dir / "builtin-vedic-lite.json"
    payload = {
        "calendar": "gregorian",
        "local_datetime": "1990-09-15T14:30:00",
        "timezone": "Asia/Shanghai",
        "location": {
            "label": "江苏省苏州市",
            "latitude": 31.2989,
            "longitude": 120.5853,
            "source": "offline-golden-fixture",
            "precision": "city",
        },
        "time_precision": {"kind": "exact", "minutes": 0},
    }
    write_json(input_path, payload)
    run(["bazi_engine.py", str(input_path), "--output", str(bazi_path)])
    bazi = json.loads(bazi_path.read_text(encoding="utf-8"))
    assert_equal(
        bazi["chart"]["pillars"],
        {"year": "庚午", "month": "乙酉", "day": "癸未", "hour": "己未"},
        "Bazi white-dew regression fixture",
    )
    run(["validate_chart_adapter.py", str(bazi_path)])

    tampered_bazi = json.loads(bazi_path.read_text(encoding="utf-8"))
    tampered_bazi["chart"]["pillars"]["day"] = "甲子"
    tampered_bazi_path = temp_dir / "builtin-bazi-tampered.json"
    write_json(tampered_bazi_path, tampered_bazi)
    replay_rejection = run(
        ["validate_chart_adapter.py", str(tampered_bazi_path)],
        expected_code=1,
    )
    if "E_ENGINE_REPLAY_MISMATCH" not in replay_rejection.stdout:
        raise TestFailure("tampered Bazi chart must fail local recomputation")

    run(["western_engine.py", str(input_path), "--output", str(western_path)])
    western = json.loads(western_path.read_text(encoding="utf-8"))
    assert_equal(
        western["chart"]["coverage"],
        "planets-signs-aspects-no-houses",
        "western coverage boundary",
    )
    assert_equal(western["chart"]["houses"], None, "no invented houses")
    assert_equal(len(western["chart"]["planets"]), 10, "western planet count")
    run(["validate_chart_adapter.py", str(western_path)])

    run(["vedic_lite_engine.py", str(input_path), "--output", str(vedic_path)])
    vedic = json.loads(vedic_path.read_text(encoding="utf-8"))
    assert_equal(
        vedic["chart"]["coverage"],
        "d1-classical-planets-mean-nodes-lagna-whole-sign-nakshatra-beta",
        "Vedic Lite coverage boundary",
    )
    assert_equal(
        vedic["chart"]["ascendant"]["sign"],
        "射手",
        "Vedic Lite Lagna golden fixture",
    )
    assert_equal(
        vedic["chart"]["moon_nakshatra"],
        {
            "index": 8,
            "name": "Pushya",
            "pada": 3,
            "lord": "Saturn",
            "degree_within_nakshatra": 8.413159,
        },
        "Vedic Lite Moon nakshatra golden fixture",
    )
    assert_equal(len(vedic["chart"]["planets"]), 9, "Vedic Lite body count")
    assert_equal(
        vedic["chart"]["ayanamsa"]["swiss_ephemeris_compatible"],
        False,
        "Vedic Lite must not claim Swiss compatibility",
    )
    assert_equal(vedic["chart"]["divisional_charts"], None, "no invented D9")
    assert_equal(vedic["chart"]["dashas"], None, "no invented dasha")
    run(["validate_chart_adapter.py", str(vedic_path)])

    vedic_unified_path = temp_dir / "builtin-vedic-lite-unified.json"
    run(
        [
            "convert_chart_result.py",
            str(vedic_path),
            "--output",
            str(vedic_unified_path),
        ]
    )
    run(["validate_result.py", str(vedic_unified_path)])

    tampered_vedic = json.loads(vedic_path.read_text(encoding="utf-8"))
    tampered_vedic["chart"]["planets"]["moon"]["sidereal_longitude_deg"] += 1
    tampered_vedic_path = temp_dir / "builtin-vedic-lite-tampered.json"
    write_json(tampered_vedic_path, tampered_vedic)
    vedic_replay_rejection = run(
        ["validate_chart_adapter.py", str(tampered_vedic_path)],
        expected_code=1,
    )
    if "E_ENGINE_REPLAY_MISMATCH" not in vedic_replay_rejection.stdout:
        raise TestFailure("tampered Vedic Lite chart must fail local recomputation")

    vedic_disabled_controls = create_disabled_controls(
        temp_dir, "vedic-lite-generation"
    )
    vedic_disabled = run(
        [
            "validate_chart_adapter.py",
            str(vedic_path),
            "--controls",
            str(vedic_disabled_controls),
        ],
        expected_code=1,
    )
    if "E_FEATURE_DISABLED" not in vedic_disabled.stdout:
        raise TestFailure("Vedic Lite independent kill switch must fail closed")

    high_latitude_input = temp_dir / "vedic-high-latitude-input.json"
    high_latitude_output = temp_dir / "vedic-high-latitude-output.json"
    write_json(
        high_latitude_input,
        {
            **payload,
            "location": {
                **payload["location"],
                "label": "高纬度测试点",
                "latitude": 66.0,
            },
        },
    )
    high_latitude = run(
        [
            "vedic_lite_engine.py",
            str(high_latitude_input),
            "--output",
            str(high_latitude_output),
        ],
        expected_code=2,
    )
    assert_equal(
        json.loads(high_latitude.stderr)["error"]["code"],
        "E_ASCENDANT_LATITUDE_RANGE",
        "Vedic Lite polar latitude must fail closed",
    )

    boundary_input = temp_dir / "vedic-boundary-input.json"
    boundary_output = temp_dir / "vedic-boundary-output.json"
    write_json(
        boundary_input,
        {**payload, "local_datetime": "1990-01-03T01:00:00"},
    )
    boundary = run(
        [
            "vedic_lite_engine.py",
            str(boundary_input),
            "--output",
            str(boundary_output),
        ],
        expected_code=2,
    )
    assert_equal(
        json.loads(boundary.stderr)["error"]["code"],
        "E_SIDEREAL_BOUNDARY_UNCERTAINTY",
        "Vedic Lite near-boundary result must fail closed",
    )

    unsupported_path = temp_dir / "bazi-true-solar-input.json"
    unsupported_output = temp_dir / "bazi-true-solar-output.json"
    write_json(unsupported_path, {**payload, "solar_time_policy": "true-solar"})
    error = run(
        [
            "bazi_engine.py",
            str(unsupported_path),
            "--output",
            str(unsupported_output),
        ],
        expected_code=2,
    )
    assert_equal(
        json.loads(error.stderr)["error"]["code"],
        "E_UNSUPPORTED_SOLAR_TIME",
        "true-solar must not be silently approximated",
    )

    uncertain_input = temp_dir / "bazi-uncertain-input.json"
    uncertain_output = temp_dir / "bazi-uncertain-output.json"
    write_json(
        uncertain_input,
        {**payload, "time_precision": {"kind": "approximate", "minutes": 5}},
    )
    uncertain = run(
        [
            "bazi_engine.py",
            str(uncertain_input),
            "--output",
            str(uncertain_output),
        ],
        expected_code=2,
    )
    assert_equal(
        json.loads(uncertain.stderr)["error"]["code"],
        "E_TIME_UNCERTAINTY",
        "single chart must reject uncertain birth time",
    )

    historical_input = temp_dir / "bazi-historical-input.json"
    historical_output = temp_dir / "bazi-historical-output.json"
    write_json(
        historical_input,
        {**payload, "local_datetime": "1930-06-01T12:00:00"},
    )
    historical = run(
        [
            "bazi_engine.py",
            str(historical_input),
            "--output",
            str(historical_output),
        ],
        expected_code=2,
    )
    assert_equal(
        json.loads(historical.stderr)["error"]["code"],
        "E_HISTORICAL_TIMEZONE_OFFSET_REQUIRED",
        "pre-1949 chart must require an explicit audited offset",
    )
    historical_allowed_input = temp_dir / "bazi-historical-offset-input.json"
    historical_allowed_output = temp_dir / "bazi-historical-offset-output.json"
    write_json(
        historical_allowed_input,
        {
            **payload,
            "local_datetime": "1930-06-01T12:00:00",
            "historical_utc_offset": "+08:00",
        },
    )
    run(
        [
            "bazi_engine.py",
            str(historical_allowed_input),
            "--output",
            str(historical_allowed_output),
        ]
    )
    historical_chart = json.loads(
        historical_allowed_output.read_text(encoding="utf-8")
    )
    assert_equal(
        historical_chart["input"]["historical_utc_offset"],
        "+08:00",
        "audited historical offset preserved",
    )
    run(["validate_chart_adapter.py", str(historical_allowed_output)])

    late_zi_input = temp_dir / "bazi-late-zi-input.json"
    late_zi_output = temp_dir / "bazi-late-zi-output.json"
    write_json(
        late_zi_input,
        {
            **payload,
            "local_datetime": "1990-09-15T23:30:00",
            "day_boundary_policy": "late-zi-next-day",
        },
    )
    run(
        [
            "bazi_engine.py",
            str(late_zi_input),
            "--output",
            str(late_zi_output),
        ]
    )
    run(["validate_chart_adapter.py", str(late_zi_output)])

    unified_path = temp_dir / "builtin-bazi-unified.json"
    run(
        [
            "convert_chart_result.py",
            str(bazi_path),
            "--output",
            str(unified_path),
        ]
    )
    run(["validate_result.py", str(unified_path)])
    final = json.loads(unified_path.read_text(encoding="utf-8"))
    add_final_layer(final, "result.chart.pillars")
    final["interpretation"][0]["epistemic_status"] = "traditional"
    final["disclaimer"] = (
        "AI生成内容｜传统文化与自我反思，仅供参考，不是经科学验证的预测，"
        "也不构成医疗、法律、投资或其他专业建议。"
    )
    final_path = temp_dir / "builtin-bazi-final.json"
    write_json(final_path, final)
    run(["validate_result.py", str(final_path), "--stage", "final"])

    unsafe = json.loads(final_path.read_text(encoding="utf-8"))
    unsafe["interpretation"][0]["claim"] = "你一定会发财，建议买入。"
    unsafe_path = temp_dir / "builtin-bazi-unsafe-final.json"
    write_json(unsafe_path, unsafe)
    run(
        ["validate_result.py", str(unsafe_path), "--stage", "final"],
        expected_code=1,
    )

    savings_unsafe = json.loads(final_path.read_text(encoding="utf-8"))
    savings_unsafe["interpretation"][0]["claim"] = (
        "明天适合把全部积蓄投入这只股票，会获得高回报。"
    )
    savings_unsafe["actions"][0]["text"] = "把全部积蓄投入这只股票。"
    savings_unsafe_path = temp_dir / "builtin-bazi-savings-unsafe-final.json"
    write_json(savings_unsafe_path, savings_unsafe)
    run(
        ["validate_result.py", str(savings_unsafe_path), "--stage", "final"],
        expected_code=1,
    )

    refused = json.loads(final_path.read_text(encoding="utf-8"))
    refused["safety"]["decision"] = "refuse"
    refused_path = temp_dir / "builtin-bazi-refused-final.json"
    write_json(refused_path, refused)
    run(
        ["validate_result.py", str(refused_path), "--stage", "final"],
        expected_code=1,
    )

def report_payload(category: str = "psychometric") -> dict[str, Any]:
    payload = {
        "schema_version": "1.0.0",
        "mode": "report-followup",
        "run_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "evidence": {
            "report_source": {
                "kind": "file",
                "category": category,
                "title": "用户报告",
                "provider": "unknown",
                "instrument_or_system": "unknown",
                "version": "unknown",
                "provided_by": "user",
                "independently_verified": False,
            }
        },
        "result": {
            "answers": [
                {
                    "question": "这项分数说明什么？",
                    "citations": [
                        {
                            "page": "3",
                            "field": "尽责性均值",
                            "excerpt": "尽责性均值 4.25",
                        }
                    ],
                    "interpretation": "只说明报告中的一次自报结果。",
                    "limitations": ["缺少量表版本和常模。"],
                    "actions": ["结合一个真实行为例子核对。"],
                }
            ]
        },
        "quality": {"status": "pass_with_warnings", "warnings": ["来源未独立验证。"]},
        "safety": {
            "decision": "allow_with_boundary",
            "prohibited_uses": ["高影响决策"],
        },
    }
    add_final_layer(payload, "result.answers")
    payload["interpretation"][0]["epistemic_status"] = "user_provided_unverified"
    if category == "traditional":
        payload["disclaimer"] = (
            "AI生成内容｜传统文化与自我反思，仅供参考，不是经科学验证的预测，"
            "也不构成医疗、法律、投资或其他专业建议。"
        )
    return payload


def test_report_followup(temp_dir: Path) -> None:
    report_path = temp_dir / "report-followup.json"
    write_json(report_path, report_payload())
    run(["validate_result.py", str(report_path), "--stage", "final"])

    invalid = report_payload()
    invalid["evidence"]["report_source"] = {}
    invalid["result"]["answers"] = [1]
    invalid_path = temp_dir / "report-invalid.json"
    write_json(invalid_path, invalid)
    run(["validate_result.py", str(invalid_path)], expected_code=1)

    traditional = report_payload(category="traditional")
    traditional_path = temp_dir / "report-traditional.json"
    write_json(traditional_path, traditional)
    run(["validate_result.py", str(traditional_path), "--stage", "final"])
    disabled_controls = create_disabled_controls(
        temp_dir, "traditional-report-interpretation"
    )
    run(
        [
            "validate_result.py",
            str(traditional_path),
            "--stage",
            "final",
            "--controls",
            str(disabled_controls),
        ],
        expected_code=1,
    )

    vedic = report_payload(category="traditional")
    vedic_source = vedic["evidence"]["report_source"]
    vedic_source["instrument_or_system"] = "印度占星报告"
    vedic_source["traditional_system"] = "vedic-astrology"
    vedic_source["chart_components_present"] = ["D1", "D9", "vimshottari-dasha"]
    vedic_source["input_precision"] = "unknown"
    vedic_path = temp_dir / "report-vedic.json"
    write_json(vedic_path, vedic)
    run(["validate_result.py", str(vedic_path), "--stage", "final"])

    invalid_vedic = json.loads(vedic_path.read_text(encoding="utf-8"))
    del invalid_vedic["evidence"]["report_source"]["input_precision"]
    invalid_vedic_path = temp_dir / "report-vedic-invalid.json"
    write_json(invalid_vedic_path, invalid_vedic)
    run(
        ["validate_result.py", str(invalid_vedic_path), "--stage", "final"],
        expected_code=1,
    )

    invalid_ledger = report_payload()
    del invalid_ledger["interpretation"][0]["cannot_support"]
    invalid_ledger_path = temp_dir / "report-ledger-invalid.json"
    write_json(invalid_ledger_path, invalid_ledger)
    run(
        ["validate_result.py", str(invalid_ledger_path), "--stage", "final"],
        expected_code=1,
    )


def test_html_report(temp_dir: Path) -> None:
    final_path = temp_dir / "html-final.json"
    output_path = temp_dir / "share-report.html"
    write_json(final_path, report_payload())
    run(
        [
            "render_report_html.py",
            str(final_path),
            "--output",
            str(output_path),
        ]
    )
    rendered = output_path.read_text(encoding="utf-8")
    if "https://" in rendered or "http://" in rendered:
        raise TestFailure("HTML report must not contain external requests")
    if "尽责性均值 4.25" in rendered:
        raise TestFailure("HTML report must hide raw source/result content by default")
    if "不能据此作诊断或高影响决定" not in rendered:
        raise TestFailure("HTML report omitted interpretation ledger")
    if output_path.stat().st_mode & 0o077:
        raise TestFailure("HTML report must use mode 0600")
    run(
        [
            "render_report_html.py",
            str(final_path),
            "--output",
            str(output_path),
        ],
        expected_code=2,
    )


def test_share_card(temp_dir: Path) -> None:
    cases: list[tuple[str, Path, str | None]] = []

    type_final = json.loads(
        (temp_dir / "preference-negative-result.json").read_text(encoding="utf-8")
    )
    add_final_layer(type_final, "result.four_letter_preference")
    type_path = temp_dir / "share-type-final.json"
    write_json(type_path, type_final)
    cases.append(("type-preference", type_path, None))

    cases.append(("big-five", temp_dir / "mini-final.json", None))

    relationship_final = json.loads(
        (temp_dir / "relationship-result.json").read_text(encoding="utf-8")
    )
    add_final_layer(relationship_final, "result.dimensions")
    relationship_path = temp_dir / "share-relationship-final.json"
    write_json(relationship_path, relationship_final)
    cases.append(("relationship", relationship_path, None))

    oracle_final = json.loads((temp_dir / "draw-result.json").read_text(encoding="utf-8"))
    add_final_layer(oracle_final, "result.card")
    oracle_final["interpretation"][0]["epistemic_status"] = "reflective"
    oracle_final["disclaimer"] = (
        "AI生成内容｜传统文化与自我反思，仅供参考，不是经科学验证的预测，"
        "也不构成医疗、法律、投资或其他专业建议。"
    )
    oracle_path = temp_dir / "share-oracle-final.json"
    write_json(oracle_path, oracle_final)
    cases.append(("oracle", oracle_path, str(temp_dir / "feature-approvals.json")))

    cases.append(("bazi", temp_dir / "builtin-bazi-final.json", None))

    for system, chart_name, evidence_path in (
        ("western", "builtin-western.json", "result.chart.planets"),
        ("vedic", "builtin-vedic-lite.json", "result.chart.ascendant"),
    ):
        unified_path = temp_dir / f"share-{system}-facts.json"
        run(
            [
                "convert_chart_result.py",
                str(temp_dir / chart_name),
                "--output",
                str(unified_path),
            ]
        )
        final = json.loads(unified_path.read_text(encoding="utf-8"))
        add_final_layer(final, evidence_path)
        final["interpretation"][0]["epistemic_status"] = "traditional"
        final["disclaimer"] = (
            "AI生成内容｜传统文化与自我反思，仅供参考，不是经科学验证的预测，"
            "也不构成医疗、法律、投资或其他专业建议。"
        )
        final_path = temp_dir / f"share-{system}-final.json"
        write_json(final_path, final)
        cases.append((system, final_path, None))

    report_path = temp_dir / "share-report-final.json"
    write_json(report_path, report_payload())
    cases.append(("report-followup", report_path, None))

    for template_id, final_path, controls_path in cases:
        spec_path = temp_dir / f"card-{template_id}.json"
        svg_path = temp_dir / f"card-{template_id}.svg"
        arguments = [
            "render_share_card.py",
            str(final_path),
            "--output",
            str(svg_path),
            "--spec-output",
            str(spec_path),
        ]
        if controls_path:
            arguments.extend(["--controls", controls_path])
        run(arguments)
        run(["validate_share_card.py", str(spec_path), "--svg", str(svg_path)])
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        assert_equal(spec["template_id"], template_id, f"{template_id} routing")
        assert_equal(spec["logo"], None, f"{template_id} no logo")
        assert_equal(
            spec["privacy"]["birth_data_included"],
            False,
            f"{template_id} birth data omitted",
        )
        if svg_path.stat().st_mode & 0o077 or spec_path.stat().st_mode & 0o077:
            raise TestFailure(f"{template_id} share-card files must use mode 0600")
        svg = svg_path.read_text(encoding="utf-8")
        if type_final["run_id"] in svg or "元宝" in svg:
            raise TestFailure(f"{template_id} SVG leaked run id or product name")

    square_spec = temp_dir / "card-oracle-square.json"
    square_svg = temp_dir / "card-oracle-square.svg"
    run(
        [
            "render_share_card.py",
            str(oracle_path),
            "--output",
            str(square_svg),
            "--spec-output",
            str(square_spec),
            "--aspect",
            "square",
            "--controls",
            str(temp_dir / "feature-approvals.json"),
        ]
    )
    run(["validate_share_card.py", str(square_spec), "--svg", str(square_svg)])
    square = json.loads(square_spec.read_text(encoding="utf-8"))
    assert_equal(square["canvas"], {"width": 1080, "height": 1080}, "square card")

    unsafe_svg = temp_dir / "unsafe-nickname.svg"
    unsafe_spec = temp_dir / "unsafe-nickname.json"
    run(
        [
            "render_share_card.py",
            str(type_path),
            "--output",
            str(unsafe_svg),
            "--spec-output",
            str(unsafe_spec),
            "--nickname",
            "13800138000",
        ],
        expected_code=1,
    )
    if unsafe_svg.exists() or unsafe_spec.exists():
        raise TestFailure("unsafe nickname must not produce share-card files")

    valid_spec = temp_dir / "card-type-preference.json"
    valid_svg = temp_dir / "card-type-preference.svg"
    tampered_svg = temp_dir / "card-tampered.svg"
    write_text(
        tampered_svg,
        valid_svg.read_text(encoding="utf-8").replace("</svg>", "<script>1</script></svg>"),
    )
    run(
        ["validate_share_card.py", str(valid_spec), "--svg", str(tampered_svg)],
        expected_code=1,
    )


def test_secure_run_dir(_: Path) -> None:
    created = json.loads(run(["secure_run_dir.py", "create"]).stdout)
    path = Path(created["path"])
    if not path.is_dir() or (path.stat().st_mode & 0o077):
        raise TestFailure("secure run directory must exist with mode 0700")
    run(["secure_run_dir.py", "cleanup", "--path", str(path)])
    if path.exists():
        raise TestFailure("secure run directory cleanup failed")


def main() -> int:
    tests = [
        ("feature-gate", test_feature_gate),
        ("questions", test_questions),
        ("personality", test_personality),
        ("type-preference", test_type_preference),
        ("relationship", test_relationship),
        ("oracle", test_oracle),
        ("chart-adapter", test_chart_adapter),
        ("builtin-engines", test_builtin_engines),
        ("report-followup", test_report_followup),
        ("html-report", test_html_report),
        ("share-card", test_share_card),
        ("secure-run-dir", test_secure_run_dir),
    ]
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="divination-assessment-test-") as temp_name:
        temp_dir = Path(temp_name)
        os.chmod(temp_dir, 0o700)
        for name, test in tests:
            try:
                test(temp_dir)
                print(f"PASS {name}")
            except Exception as exc:
                failures.append(f"{name}: {exc}")
                print(f"FAIL {name}: {exc}")
    if failures:
        print("\nFailures:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"\nPASS all {len(tests)} test groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
