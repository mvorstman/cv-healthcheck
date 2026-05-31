"""
cvhealthcheck.extractors.conformance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ADR 0004 conformance check — schema validation of collected section data
against the catalog's declared section schema, at collection time.

The declared schema lives inside a section's ``extraction_instructions`` JSON
under a ``conformance`` block (the phase-1 steering decision — no migration,
matches the established flexible-catalog-payload pattern). All sub-checks are
optional; only declared aspects are checked:

    "conformance": {
        "required_fields": ["JobId", "ClientName", "Status", "StartTime"],
        "field_types":     {"JobId": "int", "ClientName": "string"},
        "enums":           {"Status": ["Completed", "Failed", "Running"]},
        "cardinality":     {"min": 1, "max": 1000}     # or {"exact": 13}
    }

When data fails conformance, ``check_conformance`` returns a structured
failure record in the exact shape fixed by ADR 0004 §"Conformance failures
and the AI-rebuild bridge" (consumed verbatim by a successor AI-rebuild ADR):

    {
        "reason": "missing_required_field",
        "expected": {"fields": [...]},
        "actual": {"fields": [...]},
        "delta": {"missing": [...], "unexpected": [...]},
        "hint": "..."
    }

When data conforms (or no conformance block is declared), it returns None.
The check is section-grained: a failed section is recorded; sibling sections
in the same subject continue to collect. ADR 0004 phase 1 only emits the
record — the renderer side (what to show for a failed section) is phase 2.
"""
from __future__ import annotations

from typing import Any

# Reason codes, in detection-priority order.
REASON_MISSING_REQUIRED_FIELD = "missing_required_field"
REASON_TYPE_MISMATCH = "type_mismatch"
REASON_UNKNOWN_ENUM_VALUE = "unknown_enum_value"
REASON_CARDINALITY_MISMATCH = "cardinality_mismatch"


# Declared type name -> Python types it accepts. None always passes (a null
# cell is not a type violation; required_fields covers presence separately).
_TYPE_CHECKS: dict[str, tuple[type, ...]] = {
    "int": (int,),
    "integer": (int,),
    "float": (float, int),
    "number": (float, int),
    "string": (str,),
    "str": (str,),
    "bool": (bool,),
    "boolean": (bool,),
}


def check_conformance(
    rows: list[dict[str, Any]],
    conformance: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Validate ``rows`` against a ``conformance`` schema block.

    Returns a structured failure record (ADR 0004 shape) on the first failing
    aspect, or None if the data conforms / no schema is declared.
    """
    if not conformance:
        return None

    required_fields: list[str] = list(conformance.get("required_fields") or [])
    field_types: dict[str, str] = dict(conformance.get("field_types") or {})
    enums: dict[str, list[Any]] = dict(conformance.get("enums") or {})
    cardinality: dict[str, Any] = dict(conformance.get("cardinality") or {})

    present_fields = _present_fields(rows)
    declared_fields = set(required_fields) | set(field_types) | set(enums)
    missing = [f for f in required_fields if f not in present_fields]
    unexpected = sorted(present_fields - declared_fields) if declared_fields else []

    expected = {"fields": required_fields}
    actual = {"fields": sorted(present_fields)}
    delta = {"missing": missing, "unexpected": unexpected}

    # 1. Required fields present.
    if missing:
        return {
            "reason": REASON_MISSING_REQUIRED_FIELD,
            "expected": expected,
            "actual": actual,
            "delta": delta,
            "hint": (
                "Schema appears to have drifted from the template's declaration. "
                f"Missing required field(s): {', '.join(missing)}."
            ),
        }

    # 2. Field types match (where declared). Null cells are not type errors.
    for field_name, declared_type in field_types.items():
        accepted = _TYPE_CHECKS.get(declared_type.lower())
        if accepted is None:
            continue
        for row in rows:
            value = row.get(field_name)
            if value is None:
                continue
            # bool is a subclass of int — guard so an int field doesn't accept True.
            if not isinstance(value, accepted) or (
                bool not in accepted and isinstance(value, bool)
            ):
                return {
                    "reason": REASON_TYPE_MISMATCH,
                    "expected": expected,
                    "actual": actual,
                    "delta": delta,
                    "hint": (
                        f"Field {field_name!r} expected type {declared_type!r} but "
                        f"a value of type {type(value).__name__!r} was collected."
                    ),
                }

    # 3. Enum values known (where declared).
    for field_name, allowed in enums.items():
        allowed_set = set(allowed)
        for row in rows:
            value = row.get(field_name)
            if value is None:
                continue
            if value not in allowed_set:
                return {
                    "reason": REASON_UNKNOWN_ENUM_VALUE,
                    "expected": expected,
                    "actual": actual,
                    "delta": delta,
                    "hint": (
                        f"Field {field_name!r} carried unknown value {value!r}; "
                        f"declared values are {sorted(map(str, allowed))}."
                    ),
                }

    # 4. Cardinality (row count) within declared bounds.
    count = len(rows)
    card_hint = _cardinality_violation(count, cardinality)
    if card_hint is not None:
        return {
            "reason": REASON_CARDINALITY_MISMATCH,
            "expected": expected,
            "actual": actual,
            "delta": delta,
            "hint": card_hint,
        }

    return None


def _present_fields(rows: list[dict[str, Any]]) -> set[str]:
    """The union of keys present across all rows."""
    present: set[str] = set()
    for row in rows:
        present.update(row.keys())
    return present


def _cardinality_violation(count: int, cardinality: dict[str, Any]) -> str | None:
    """Return a hint string if ``count`` violates the cardinality spec, else None."""
    if not cardinality:
        return None
    if "exact" in cardinality:
        exact = cardinality["exact"]
        if count != exact:
            return f"Expected exactly {exact} row(s) but collected {count}."
        return None
    minimum = cardinality.get("min")
    maximum = cardinality.get("max")
    if minimum is not None and count < minimum:
        return f"Expected at least {minimum} row(s) but collected {count}."
    if maximum is not None and count > maximum:
        return f"Expected at most {maximum} row(s) but collected {count}."
    return None
