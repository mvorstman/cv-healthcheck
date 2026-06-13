"""ADR-0016 parity harness for License Summary — reusable acceptance machinery.

Compares the CURRENT bespoke LS pipeline against a future generic-output
candidate over the real-export corpus under ``data/imports/license_summary/``.
This is the acceptance gate for the later LS de-bespoke conversion, so the parity
DEFINITIONS here are exactly ADR-0016's (Section 4):

  - semantic equivalence of the CanonicalArtifact — same sections, same
    items/rows, same field values — NOT raw-JSON byte equality (key ordering,
    whitespace, float formatting, source timestamps, artifact ids are not parity
    concerns and are never compared);
  - ``registration_code`` (and any sensitive field) is compared in its MASKED
    form, and the comparator asserts BOTH sides are masked — a raw value on
    either side is a FAIL, not a silent pass;
  - computed summaries are compared semantically (the count values);
  - THREE outcomes per field: pass / fail / PENDING-UNIT. Unit-bearing fields
    (the ``number_with_unit`` domain, ADR-0016 Open Item 1 — return shape
    UNRESOLVED) are quarantined as pending: never silently skipped, never
    auto-failed. The report counts them separately so the harness runs green on
    expressible fields while honestly flagging what it cannot yet compare.

This module is HARNESS ONLY — it imports the bespoke pipeline read-only and
writes nothing. No transform layer, no LS conversion, no bespoke deletion.

The candidate seam (:data:`bespoke_candidate`) is the bespoke pipeline today
(identity → bespoke-vs-bespoke proves the comparator + seam work); during the
conversion, swap in the generic recipe output.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from cvhealthcheck.adapters.license_summary import adapt as adapt_license_summary
from cvhealthcheck.artifacts.models import CanonicalArtifact
from cvhealthcheck.license_summary.import_csv import import_license_summary_csv
from cvhealthcheck.license_summary.import_html import import_license_summary_html
from cvhealthcheck.license_summary.service import persist_license_summary_artifact

LS_FIXTURE_DIR = Path("data/imports/license_summary")
_CSV_SUFFIXES = {".csv"}
_HTML_SUFFIXES = {".htm", ".html"}

# ADR-0017 D1: unit-bearing value fields are now ACTIVELY COMPARED via a
# value/unit equivalence (no longer quarantined PENDING-UNIT). The bespoke flat
# shape — a number plus a separate row `unit` field (other_licenses), or a
# "N unit" string (workload entitlement) — is treated as equal to the generic
# nested {value, unit} when their (value, unit) pairs match. The standalone `unit`
# field is SUBSUMED into these pairs (not compared on its own). number_with_unit is
# parse-and-keep, no normalization (Amendment A); the corpus is 38 (Amendment D).
UNIT_VALUE_FIELDS = frozenset({"available_total", "used", "entitlement_value"})

# Canonical field ids that MUST be masked on both sides (security). Not surfaced
# into the canonical by the bespoke adapter today (masking happens at parse), but
# the rule is encoded so it is live the moment a generic candidate surfaces one.
SENSITIVE_FIELD_IDS = frozenset({"registration_code", "masked_registration_code"})


class Outcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    PENDING_UNIT = "pending-unit"


@dataclass
class FieldResult:
    file: str
    section: str
    item: str
    field: str
    expected: Any
    actual: Any
    outcome: Outcome
    note: str = ""

    def as_row(self) -> str:
        """file | section | item | field | expected | actual | outcome."""
        return (
            f"{self.file} | {self.section} | {self.item} | {self.field} | "
            f"{self.expected!r} | {self.actual!r} | {self.outcome.value}"
            + (f"  ({self.note})" if self.note else "")
        )


@dataclass
class ParityReport:
    file: str
    results: list[FieldResult] = field(default_factory=list)

    @property
    def passed(self) -> list[FieldResult]:
        return [r for r in self.results if r.outcome is Outcome.PASS]

    @property
    def failed(self) -> list[FieldResult]:
        return [r for r in self.results if r.outcome is Outcome.FAIL]

    @property
    def pending(self) -> list[FieldResult]:
        return [r for r in self.results if r.outcome is Outcome.PENDING_UNIT]

    @property
    def ok(self) -> bool:
        """Parity holds when there are no FAILs. PENDING-UNIT is allowed —
        those fields are honestly quarantined, not silently passed."""
        return not self.failed


# ---------------------------------------------------------------------------
# Fixture discovery
# ---------------------------------------------------------------------------

def discover_ls_fixtures(base: Path = LS_FIXTURE_DIR) -> list[Path]:
    """Every real LS export under ``base`` (csv + html). xlsx (the REST API
    viewer recording) is a separate source path and is out of scope here."""
    return sorted(
        p
        for p in base.glob("*")
        if p.is_file() and p.suffix.lower() in (_CSV_SUFFIXES | _HTML_SUFFIXES)
    )


def fixture_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _CSV_SUFFIXES:
        return "csv"
    if suffix in _HTML_SUFFIXES:
        return "html"
    return "other"


# ---------------------------------------------------------------------------
# Pipelines — bespoke baseline + the future candidate seam
# ---------------------------------------------------------------------------

def bespoke_canonical(path: Path) -> CanonicalArtifact:
    """The CURRENT bespoke LS pipeline, faithful to the live upload path minus
    persistence side-effects: parse → persist(write_legacy=False) → adapt.
    Writes nothing (write_legacy=False returns the model dict; no registry, no
    files, no store)."""
    fmt = fixture_format(path)
    if fmt == "html":
        parsed = import_license_summary_html(path, write_artifact=False)
    elif fmt == "csv":
        parsed = import_license_summary_csv(path, write_artifact=False)
    else:
        raise ValueError(f"unsupported LS fixture: {path}")
    persisted = persist_license_summary_artifact(parsed, write_legacy=False)
    return adapt_license_summary(persisted)


# CandidateProducer is the seam the generic recipe output plugs into later.
CandidateProducer = Callable[[Path], CanonicalArtifact]


def bespoke_candidate(path: Path) -> CanonicalArtifact:
    """Placeholder candidate = the bespoke pipeline (identity). Proves the
    comparator + seam are real and reflexive today. Replace with the generic
    recipe producer during the conversion (ADR-0016 build order step 4)."""
    return bespoke_canonical(path)


@dataclass
class BaselineResult:
    file: str
    fmt: str
    produced: bool          # a CanonicalArtifact was produced without raising
    license_rows: int       # table-section items (other + agent + workload)
    sections: int
    error: str | None = None


def run_baseline(
    fixtures: list[Path], producer: CandidateProducer = bespoke_canonical
) -> list[BaselineResult]:
    """Run the bespoke path over every fixture; record produced/empty/error.
    Never raises — a parse failure is recorded as a corpus finding."""
    out: list[BaselineResult] = []
    for path in fixtures:
        fmt = fixture_format(path)
        try:
            art = producer(path)
        except Exception as exc:  # corpus finding — surfaced, not swallowed
            out.append(
                BaselineResult(path.name, fmt, produced=False, license_rows=0,
                               sections=0, error=f"{type(exc).__name__}: {exc}")
            )
            continue
        rows = sum(
            len(getattr(s, "items", []) or [])
            for s in art.sections
            if getattr(s, "type", None) == "table"
        )
        out.append(
            BaselineResult(path.name, fmt, produced=True, license_rows=rows,
                           sections=len(art.sections))
        )
    return out


# ---------------------------------------------------------------------------
# Semantic comparator (ADR-0016 parity rules + ADR-0017 decided equivalences)
# ---------------------------------------------------------------------------

_NUM_UNIT_RE = re.compile(r"^(-?[\d,]+(?:\.\d+)?)\s*(.*)$")


def _is_masked(value: Any) -> bool:
    """A sensitive value is safe iff it carries no raw content: absent (None)
    or masked (contains '*'). A present value with no '*' is RAW — a leak."""
    return value is None or "*" in str(value)


def _values_equal(expected: Any, actual: Any) -> bool:
    if expected is None and actual is None:
        return True
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return float(expected) == float(actual)
    return str(expected) == str(actual)


# ── ADR-0017 D1: value/unit equivalence ──────────────────────────────────────

def _num_norm(value: Any) -> Any:
    """Numbers (and numeric strings) → float for comparison; non-numeric → the
    stripped string; None → None."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return s


def _to_unit_pair(operand: Any) -> tuple[Any, Any]:
    """Normalize a unit-field operand to (value_norm, unit_or_None). Accepts a
    (value, unit) tuple (bespoke flat: number + the row's separate `unit`), a
    {value, unit} dict (generic nested), a "N unit" string (bespoke workload
    text), a bare number, or None."""
    if operand is None:
        return (None, None)
    if isinstance(operand, tuple):
        value, unit = operand
    elif isinstance(operand, dict) and "value" in operand:
        value, unit = operand.get("value"), operand.get("unit")
    elif isinstance(operand, str):
        match = _NUM_UNIT_RE.match(operand.strip())
        if match:
            value, unit = match.group(1), (match.group(2).strip() or None)
        else:
            value, unit = operand, None
    else:  # bare number
        value, unit = operand, None
    return (_num_norm(value), unit or None)


def unit_value_equal(left: Any, right: Any) -> bool:
    """ADR-0017 D1: two unit-bearing values are equal iff their (value, unit)
    pairs match — regardless of flat (number + separate unit, or "N unit" string)
    vs nested {value, unit} representation."""
    return _to_unit_pair(left) == _to_unit_pair(right)


def _unit_operand_from_row(row: dict[str, Any], field_id: str) -> Any:
    """Build a unit-field operand from a row: a dict / string / None passes
    through (parsed by _to_unit_pair); a bare number is paired with the row's
    separate `unit` field (the bespoke other_licenses flat shape)."""
    val = row.get(field_id)
    if isinstance(val, (dict, str)) or val is None:
        return val
    return (val, row.get("unit"))


def _classify_field(
    file: str, section: str, item: str, field_id: str, expected: Any, actual: Any,
) -> FieldResult:
    # ADR-0017 D6: a sensitive field is equal iff BOTH sides are masked and
    # NEITHER leaks raw — the mask FORMAT is not compared (generic segment-mask ≡
    # bespoke first-4/last-4).
    if field_id in SENSITIVE_FIELD_IDS:
        exp_safe, act_safe = _is_masked(expected), _is_masked(actual)
        if not (exp_safe and act_safe):
            return FieldResult(
                file, section, item, field_id, expected, actual, Outcome.FAIL,
                f"RAW sensitive value present (expected_masked={exp_safe}, actual_masked={act_safe})",
            )
        return FieldResult(file, section, item, field_id, expected, actual,
                           Outcome.PASS, "both masked, raw absent (D6 — mask-format-independent)")
    outcome = Outcome.PASS if _values_equal(expected, actual) else Outcome.FAIL
    return FieldResult(file, section, item, field_id, expected, actual, outcome)


def _classify_unit_value(
    file: str, section: str, item: str, field_id: str,
    brow: dict[str, Any], crow: dict[str, Any],
) -> FieldResult:
    equal = unit_value_equal(
        _unit_operand_from_row(brow, field_id), _unit_operand_from_row(crow, field_id)
    )
    return FieldResult(
        file, section, item, field_id, brow.get(field_id), crow.get(field_id),
        Outcome.PASS if equal else Outcome.FAIL, "D1 value/unit equivalence",
    )


def _metric_items(section: Any) -> dict[str, Any]:
    return {it.id: it.value for it in getattr(section, "items", []) or []}


def _table_rows(section: Any) -> list[dict[str, Any]]:
    return list(getattr(section, "items", []) or [])


def _row_key(row: dict[str, Any], index: int) -> str:
    name = row.get("license")
    return str(name) if name else f"#{index}"


def _section_is_empty(section: Any) -> bool:
    """ADR-0017 D4/F4: a section with no rows is 'no rows of that type' —
    semantically identical to the section being absent."""
    if section is None:
        return True
    return (
        len(getattr(section, "items", []) or []) == 0
        and len(getattr(section, "series", []) or []) == 0
    )


def _compare_summary(
    report: ParityReport, baseline: CanonicalArtifact, candidate: CanonicalArtifact
) -> None:
    exp = {m.id: m.value for m in baseline.summary.metrics}
    act = {m.id: m.value for m in candidate.summary.metrics}
    for mid in sorted(set(exp) | set(act)):
        report.results.append(
            _classify_field(report.file, "summary", mid, mid, exp.get(mid), act.get(mid))
        )


def _compare_section(
    report: ParityReport, sid: str, base_sec: Any, cand_sec: Any
) -> None:
    stype = getattr(base_sec, "type", None)
    if stype != getattr(cand_sec, "type", None):
        report.results.append(FieldResult(
            report.file, sid, "", "<type>", getattr(base_sec, "type", None),
            getattr(cand_sec, "type", None), Outcome.FAIL, "section type mismatch"))
        return

    if stype == "metric":
        exp, act = _metric_items(base_sec), _metric_items(cand_sec)
        for fid in sorted(set(exp) | set(act)):
            report.results.append(_classify_field(
                report.file, sid, fid, fid, exp.get(fid), act.get(fid)))
        return

    if stype == "table":
        base_rows, cand_rows = _table_rows(base_sec), _table_rows(cand_sec)
        # ADR-0017 D4/F3: match rows by 'license' key — this collapses duplicate
        # rows to the DISTINCT set, so row-multiplicity differences (bespoke drops
        # dupes, generic surfaces them) are tolerated; the distinct set must match.
        keyed = (
            all(r.get("license") for r in base_rows)
            and all(r.get("license") for r in cand_rows)
        )
        if keyed:
            base_map = {str(r["license"]): r for r in base_rows}
            cand_map = {str(r["license"]): r for r in cand_rows}
            keys = sorted(set(base_map) | set(cand_map))
            pairs = [(k, base_map.get(k), cand_map.get(k)) for k in keys]
        else:
            n = max(len(base_rows), len(cand_rows))
            pairs = [
                (_row_key(base_rows[i] if i < len(base_rows) else {}, i),
                 base_rows[i] if i < len(base_rows) else None,
                 cand_rows[i] if i < len(cand_rows) else None)
                for i in range(n)
            ]
        for item_key, brow, crow in pairs:
            if brow is None or crow is None:
                report.results.append(FieldResult(
                    report.file, sid, item_key, "<row>",
                    "present" if brow is not None else "absent",
                    "present" if crow is not None else "absent",
                    Outcome.FAIL, "row presence mismatch"))
                continue
            for fid in sorted(set(brow) | set(crow)):
                if fid == "unit":
                    continue  # D1: subsumed into the value/unit pairs
                if fid in UNIT_VALUE_FIELDS:
                    report.results.append(
                        _classify_unit_value(report.file, sid, item_key, fid, brow, crow))
                else:
                    report.results.append(_classify_field(
                        report.file, sid, item_key, fid, brow.get(fid), crow.get(fid)))
        return

    # Fallback for any other section type — compare serialized form whole.
    exp_dump = base_sec.model_dump(mode="json")
    act_dump = cand_sec.model_dump(mode="json")
    report.results.append(FieldResult(
        report.file, sid, "", "<section>", exp_dump, act_dump,
        Outcome.PASS if exp_dump == act_dump else Outcome.FAIL,
        f"whole-section compare (type={stype})"))


def compare_artifacts(
    file: str, baseline: CanonicalArtifact, candidate: CanonicalArtifact
) -> ParityReport:
    """Semantic CanonicalArtifact parity (ADR-0016 + ADR-0017 equivalences)."""
    report = ParityReport(file=file)
    _compare_summary(report, baseline, candidate)

    base_secs = {s.id: s for s in baseline.sections}
    cand_secs = {s.id: s for s in candidate.sections}
    for sid in sorted(set(base_secs) | set(cand_secs)):
        if sid not in base_secs or sid not in cand_secs:
            # ADR-0017 D4/F4: an empty section ≡ an absent section.
            present = base_secs.get(sid) or cand_secs.get(sid)
            if _section_is_empty(present):
                report.results.append(FieldResult(
                    file, sid, "", "<section>", "absent/empty", "absent/empty",
                    Outcome.PASS, "empty section ≡ absent section (D4/F4)"))
            else:
                report.results.append(FieldResult(
                    file, sid, "", "<section>",
                    "present" if sid in base_secs else "absent",
                    "present" if sid in cand_secs else "absent",
                    Outcome.FAIL, "section presence mismatch (non-empty)"))
            continue
        _compare_section(report, sid, base_secs[sid], cand_secs[sid])
    return report


# ---------------------------------------------------------------------------
# Corpus-level report (deliverable 6 — also callable as a script)
# ---------------------------------------------------------------------------

def corpus_summary() -> dict[str, Any]:
    """Discover the corpus, run the bespoke baseline, run bespoke-vs-candidate
    parity, and return a structured summary (counts, formats, parse results,
    PENDING-UNIT field classes encountered)."""
    fixtures = discover_ls_fixtures()
    baseline = run_baseline(fixtures)
    pending_field_classes: dict[str, int] = {}
    total_pass = total_fail = total_pending = 0
    failures: list[FieldResult] = []
    for path in fixtures:
        try:
            base = bespoke_canonical(path)
            cand = bespoke_candidate(path)
        except Exception:
            continue
        rep = compare_artifacts(path.name, base, cand)
        total_pass += len(rep.passed)
        total_fail += len(rep.failed)
        total_pending += len(rep.pending)
        failures.extend(rep.failed)
        for r in rep.pending:
            pending_field_classes[r.field] = pending_field_classes.get(r.field, 0) + 1
    return {
        "fixture_count": len(fixtures),
        "formats": {
            "csv": sum(1 for b in baseline if b.fmt == "csv"),
            "html": sum(1 for b in baseline if b.fmt == "html"),
        },
        "produced": sum(1 for b in baseline if b.produced),
        "parse_errors": [b for b in baseline if not b.produced],
        "empty_no_license_rows": [b for b in baseline if b.produced and b.license_rows == 0],
        "comparator_totals": {"pass": total_pass, "fail": total_fail, "pending_unit": total_pending},
        "pending_unit_field_classes": pending_field_classes,
        "failures": failures,
    }


if __name__ == "__main__":  # pragma: no cover - manual report
    import json

    s = corpus_summary()
    printable = dict(s)
    printable["parse_errors"] = [vars(b) for b in s["parse_errors"]]
    printable["empty_no_license_rows"] = [b.file for b in s["empty_no_license_rows"]]
    printable["failures"] = [f.as_row() for f in s["failures"]]
    print(json.dumps(printable, indent=2))
