"""Exact source-value correspondence; never source authentication or calibration."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import Field

from meridian.schemas import StableModel


class NumericalCitation(StableModel):
    evidence_id: str = Field(min_length=1, max_length=160)
    pointer: str = Field(pattern=r"^/[^\s]{1,300}$")
    value: Decimal = Field(allow_inf_nan=False)
    unit: Literal["SOURCE_NATIVE"] = "SOURCE_NATIVE"


def resolve_pointer(payload: dict[str, Any], pointer: str) -> Any:
    current: Any = payload
    for raw in pointer.split("/")[1:]:
        key = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and key in current:
            current = current[key]
        elif isinstance(current, list) and key.isdigit() and int(key) < len(current):
            current = current[int(key)]
        else:
            raise ValueError("NUMERICAL_POINTER_UNRESOLVED")
    return current


def validate_numerical_claim(statement: str, citations: tuple[NumericalCitation, ...],
                             supporting_ids: tuple[str, ...], catalog: dict[str, dict[str, Any]]) -> None:
    numbers = re.findall(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?", statement.replace(",", ""))
    if numbers and not citations:
        raise ValueError("NUMERICAL_CITATION_REQUIRED")
    values: set[Decimal] = set()
    for cite in citations:
        if cite.evidence_id not in supporting_ids or cite.evidence_id not in catalog:
            raise ValueError("NUMERICAL_EVIDENCE_ID_UNSUPPORTED")
        source = resolve_pointer(catalog[cite.evidence_id], cite.pointer)
        if isinstance(source, (bool, dict, list)) or source is None:
            raise ValueError("NUMERICAL_SOURCE_NOT_SCALAR")
        try:
            observed = Decimal(str(source))
        except InvalidOperation as error:
            raise ValueError("NUMERICAL_SOURCE_NOT_NUMBER") from error
        if not observed.is_finite() or observed != cite.value:
            raise ValueError("NUMERICAL_VALUE_MISMATCH")
        values.add(observed)
    # Percent display is permitted only when '%' is explicit; exact pointer
    # still binds the underlying fraction. This does not prove prose semantics.
    allowed = values | {v * 100 for v in values} if "%" in statement else values
    if any(Decimal(n) not in allowed for n in numbers):
        raise ValueError("NUMERICAL_NARRATIVE_UNSUPPORTED")


def validate_numerical_narrative(payload: dict[str, Any]) -> None:
    """Numerical facts belong in pointer-bound claims, not unchecked role prose.

    Existing scalar confidence/probabilities remain subjective legacy fields;
    their explicit calibration status prevents interpreting them as forecasts.
    IDs and holding horizons are metadata, not quoted market measurements.
    """
    prose_fields = {"thesis", "key_drivers", "risks", "unknowns", "challenges", "missing_evidence",
        "description", "key_assumptions", "catalysts", "invalidators", "risk_factors",
        "primary_thesis", "key_risks", "what_changed", "required_followup"}

    def strings(value: Any):
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in prose_fields and any(re.search(r"\d", text) for text in strings(item)):
                    raise ValueError("NUMERICAL_FACT_OUTSIDE_GROUNDED_CLAIM")
                if key != "supporting_claims":
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(payload)
