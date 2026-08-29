from pathlib import Path


def test_no_broker_execution_identifier_in_runtime_source() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (Path(__file__).parents[1] / "src").rglob("*.py")
    )
    forbidden = ("place_order", "submit_order", "execute_trade", "broker_login")
    assert not any(identifier in source for identifier in forbidden)
