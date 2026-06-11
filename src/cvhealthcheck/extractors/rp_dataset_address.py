"""
cvhealthcheck.extractors.rp_dataset_address
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ADR 0014 — policy for the Reports Plus dataset source's address and parameters.

A ``reportsplus_dataset`` subject collects from a directly-addressed Reports
Plus dataset. The address is declared by the subject's source binding and, for
MCP-authored subjects, *asserted by an AI proposal* — untrusted input
(ADR 0008). Before the app persists it or collects against it, it is validated
here as one of the two live-verified grammars (gate findings,
``docs/research/adr0014-gate-findings.md``):

- a bare dataset GUID (standalone/deployed datasets), or
- ``{reportGuid}:{entryGuid}`` (report-bound datasets; the second half is the
  report definition's per-report entry ``guid``, NOT the underlying
  ``dataSetGuid``).

Read-only is enforced jointly: the address is a pure GUID form (it cannot
escape the datasets path it is interpolated into), and the collect path only
ever issues GETs (``CommvaultSession``). Parameter names are validated to the
dataset-parameter identifier shape here; whether a name exists on the dataset
is checked at collect time against the dataset's declared parameters — the
engine silently ignores unknown names, so a typo would otherwise collect wrong
data successfully (gate finding 3).

Leaf module: stdlib only, no project imports, so the extractor (collect) and
``create_subject_from_proposal`` (persist) can depend on it without cycles.
"""
from __future__ import annotations

import re

# The source_type that routes a /collect to the ReportsPlusDatasetExtractor and
# carries a declared dataset address. Single source of truth (the extractor and
# db/subjects.py both import it from here).
REPORTSPLUS_DATASET_SOURCE_TYPE = "reportsplus_dataset"

_GUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_ADDRESS_RE = re.compile(rf"^({_GUID})(:({_GUID}))?$")

# Dataset parameter names as declared in GetOperation.parameters[].name —
# identifier-shaped (userlist, i_days, slaDays, TimeRange, ...).
_PARAM_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_SCALAR_TYPES = (str, int, float)


class AddressPolicyError(ValueError):
    """An asserted Reports Plus dataset address failed the GUID-grammar policy."""


class ParameterPolicyError(ValueError):
    """A declared dataset parameter failed the name/value shape policy."""


def validate_rp_dataset_address(address: object) -> str:
    """Validate a Reports Plus dataset address; returns it lowercase-normalized.

    Unlike the CC-API endpoint there is no default — a ``reportsplus_dataset``
    source without an address is a seeding error, surfaced loudly. Accepts a
    bare GUID or ``guid:guid`` (lowercased on return; GUIDs are
    case-insensitive). Raises :class:`AddressPolicyError` otherwise.
    """
    if address is None:
        raise AddressPolicyError(
            "reportsplus_dataset source requires a dataset_address "
            "(bare dataset GUID, or '{reportGuid}:{entryGuid}' for a "
            "report-bound dataset)"
        )
    if not isinstance(address, str):
        raise AddressPolicyError(
            f"dataset_address must be a string, got {type(address).__name__}"
        )
    value = address.strip()
    if not _ADDRESS_RE.match(value):
        raise AddressPolicyError(
            "dataset_address must be a GUID or '{reportGuid}:{entryGuid}' "
            f"(two GUIDs joined by ':'): {address!r}"
        )
    return value.lower()


def encode_dataset_parameters(parameters: dict | None) -> dict[str, object]:
    """Encode declared dataset parameters into their query-string form.

    Instruction keys are the dataset's declared parameter names (bare, no
    ``parameter.`` prefix — authors stay out of encoding details). A scalar
    value encodes as ``parameter.<name>``; a list value as the repeated
    ``parameter.<name>[]`` form (gate finding 3). Raises
    :class:`ParameterPolicyError` for non-identifier names or non-scalar
    values, before anything reaches the wire.
    """
    if not parameters:
        return {}
    if not isinstance(parameters, dict):
        raise ParameterPolicyError(
            f"parameters must be a dict, got {type(parameters).__name__}"
        )
    encoded: dict[str, object] = {}
    for name, value in parameters.items():
        if not isinstance(name, str) or not _PARAM_NAME_RE.match(name):
            raise ParameterPolicyError(
                f"parameter name must be the dataset's declared identifier "
                f"(no 'parameter.' prefix): {name!r}"
            )
        if isinstance(value, list):
            bad = [v for v in value if not isinstance(v, _SCALAR_TYPES)]
            if bad:
                raise ParameterPolicyError(
                    f"parameter {name!r} list values must be scalars: {bad!r}"
                )
            encoded[f"parameter.{name}[]"] = value
        elif isinstance(value, _SCALAR_TYPES):
            encoded[f"parameter.{name}"] = value
        else:
            raise ParameterPolicyError(
                f"parameter {name!r} value must be a scalar or list of "
                f"scalars, got {type(value).__name__}"
            )
    return encoded
