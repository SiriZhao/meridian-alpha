from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "verify_live_gpt_external.ps1"
INSTRUCTIONS = ROOT / "EXTERNAL_LIVE_ACCEPTANCE.md"


def test_external_harness_contract_is_present_and_shadow_only() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "MERIDIAN EXTERNAL LIVE GPT ACCEPTANCE" in text
    assert "EXTERNAL_HOST_INVALID: RUN_FROM_NORMAL_POWERSHELL" in text
    assert "DIRECT_MODEL_SUCCESS" in text
    assert "P1_STAGE2_EXTERNAL_CODEX_BLOCKED" in text
    assert "shadow_only = $true" in text
    assert "orders_created = 0" in text
    assert "orders_executed = 0" in text
    assert "execution_authority = 'NONE'" in text
    assert "danger-full-access" not in text
    assert "OPENAI_API_KEY" not in text


def test_b_failure_precedes_role_and_chain_calls() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    b_stop = text.index("if ($directResult.status -ne 'DIRECT_MODEL_SUCCESS')")
    role_start = text.index("$roles = @(")
    chain_start = text.index("function Invoke-ShadowRecord")
    assert b_stop < role_start < chain_start
    assert "exit 1" in text[b_stop:role_start]


def test_external_instructions_require_normal_powershell_and_return_artifact() -> None:
    text = INSTRUCTIONS.read_text(encoding="utf-8")
    assert "normal Windows Terminal / PowerShell" in text
    assert "verify_live_gpt_external.ps1" in text
    assert "RESULT FILE:" in text
    assert "orders_created=0" in text