"""Convert application schemas to the provider's strict structured-output dialect."""
from __future__ import annotations

from typing import Any

EVIDENCE_FIELDS = frozenset({'evidence_used', 'supporting_evidence_ids',
    'contradicting_evidence_ids', 'contradicting_evidence', 'evidence_ids'})


def evidence_bound_schema(value: Any, evidence_ids: set[str]) -> Any:
    """Constrain citation arrays to the exact input catalog, retaining local checks."""
    if isinstance(value, list):
        return [evidence_bound_schema(item, evidence_ids) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: evidence_bound_schema(item, evidence_ids) for key, item in value.items()}
    for name, definition in result.get('properties', {}).items():
        if name in EVIDENCE_FIELDS and definition.get('type') == 'array':
            definition['description'] = 'Exact IDs from the supplied evidence catalog; never prose or an invented ID.'
            if evidence_ids:
                definition['items'] = {'type': 'string', 'enum': sorted(evidence_ids)}
            else:
                definition['maxItems'] = 0
    return result


def strict_output_schema(value: Any) -> Any:
    """Keep validation constraints, require all keys, preserve explicit null unions.

    Pydantic defaults express local omission semantics. The provider requires every
    property in ``required``, including in definitions and nested objects. Optional
    model fields already contain a null branch; empty default arrays remain arrays.
    """
    if isinstance(value, list):
        return [strict_output_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: strict_output_schema(item) for key,item in value.items() if key != 'default'}
    if result.get('type') == 'object' or 'properties' in result:
        result['additionalProperties'] = False
        result['required'] = list(result.get('properties', {}))
    return result
