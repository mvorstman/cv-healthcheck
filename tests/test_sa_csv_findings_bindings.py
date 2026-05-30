"""SA migration Phase 1a — generic CSV findings bindings reach parity with the
bespoke security_assessment/import_csv.py.

The generic CSVExtractor previously emitted only tables; SA's six findings
sections are bound via the existing `multi_section` format (the SA CSV
blank-line-separates sections into [label, header, data...] blocks). The one
extractor change is applying the existing `status_to_severity` instruction to
findings rows — exactly as HTMLExtractor already does — so severities (and thus
the overall verdict) match the bespoke path instead of defaulting to "info".

Both paths terminate at result_to_artifact / _build_canonical_from_import; this
test pins that they produce equivalent canonical findings.
"""
import re
import sqlite3
from pathlib import Path

from cvhealthcheck.artifacts.enums import ArtifactStatus, FindingSeverity
from cvhealthcheck.artifacts.models import FindingsSection
from cvhealthcheck.extractors.csv import CSVExtractor
from cvhealthcheck.extractors.result_to_artifact import result_to_artifact
from cvhealthcheck.security_assessment.import_csv import parse_security_assessment_csv
from cvhealthcheck.security_assessment.service import _build_canonical_from_import


# A synthetic SA CSV in the real export's shape: title + Generated-on, then
# blank-line-separated sections each [label, header, data...].
_SA_CSV = (
    "Security Assessment\n"
    " Generated on: May 17, 2026 07:00:14 PM\n"
    "\n"
    "Access Security\n"
    "Parameter,Status,Remarks,Action\n"
    "Two-factor authentication,Info,Disabled,How to enable\n"
    "Password complexity level,Good,Level 3,\n"
    "\n"
    "Platform Security\n"
    "Parameter,Status,Remarks,Action\n"
    "Threat Indicator alert,Critical,Disabled,How to enable an alert\n"
    "Ransomware protection,Good,All mount paths secured,\n"
)


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _generic(db_path: Path, csv_path: Path):
    conn = _conn(db_path)
    try:
        res = CSVExtractor(conn).extract(csv_path, "security_assessment", 1)
    finally:
        conn.close()
    assert not res.errors, res.errors
    return result_to_artifact(res, "security_assessment", "Security Assessment")


def _flat(artifact):
    out = {}
    for sec in artifact.sections:
        key = re.sub(r"[^a-z0-9]+", "_", sec.id.lower()).strip("_").replace("security_assessment_", "")
        for it in sec.items:
            out[(key, it.title)] = it
    return out


def test_generic_csv_findings_map_severities(migrated_db_path: Path, tmp_path: Path):
    csv_path = tmp_path / "sa.csv"
    csv_path.write_text(_SA_CSV, encoding="utf-8")
    art = _generic(migrated_db_path, csv_path)

    # Six namespaced findings sections exist; the two with data carry findings.
    sections = {s.id: s for s in art.sections if isinstance(s, FindingsSection)}
    assert "security_assessment.access_security" in sections
    assert "security_assessment.platform_security" in sections

    by = _flat(art)
    # Severities come from status_to_severity, NOT defaulted to info.
    assert by[("access_security", "Password complexity level")].severity == FindingSeverity.good
    assert by[("platform_security", "Threat Indicator alert")].severity == FindingSeverity.critical
    assert by[("access_security", "Two-factor authentication")].severity == FindingSeverity.info
    # A critical finding drives the overall verdict.
    assert art.summary.status == ArtifactStatus.critical


def test_generic_csv_matches_bespoke(migrated_db_path: Path, tmp_path: Path):
    csv_path = tmp_path / "sa.csv"
    csv_path.write_text(_SA_CSV, encoding="utf-8")

    generic = _generic(migrated_db_path, csv_path)
    bespoke = _build_canonical_from_import(
        parse_security_assessment_csv(_SA_CSV, source_file=str(csv_path))
    )

    g, b = _flat(generic), _flat(bespoke)
    assert set(g) == set(b), (sorted(set(g) - set(b)), sorted(set(b) - set(g)))
    for key in g:
        assert g[key].severity == b[key].severity, key
        assert (g[key].description or "") == (b[key].description or ""), key
        assert (g[key].recommendation or "") == (b[key].recommendation or ""), key
    assert generic.summary.status == bespoke.summary.status
