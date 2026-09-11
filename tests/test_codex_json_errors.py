from decimal import Decimal

from meridian.codex_provider import ProcessResult
from meridian.config import ResearchSettings
from meridian.research_agents.codex_json import CodexJsonClient, CodexJsonError


def test_auxiliary_agent_usage_limit_is_not_misclassified_as_auth() -> None:
    def runner(*args):
        return ProcessResult(
            returncode=1,
            stderr=(
                "warning: plugins were shortened; "
                "You've hit your usage limit. purchase more credits."
            ),
        )

    settings = ResearchSettings(
        provider="codex_cli",
        model="codex-default",
        timeout_seconds=30,
        max_retries=0,
        debate_rounds=0,
        max_parallel_tickers=1,
        minimum_research_coverage=Decimal("1"),
        live_enabled=True,
    )
    client = CodexJsonClient(executable="codex-test", runner=runner)
    try:
        client.run(
            prompt="plan only",
            input_payload={},
            output_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
            },
            settings=settings,
        )
    except CodexJsonError as error:
        assert str(error) == "CODEX_RATE_LIMITED"
    else:
        raise AssertionError("usage limit must fail closed")
