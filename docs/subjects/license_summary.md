# License Summary subject

License Summary has its own artifact pipeline, built on the same registry-backed persistence pattern as [Security Assessment](security_assessment.md). It is surfaced through the Quick HC License Summary page (see [../architecture/quickhc.md](../architecture/quickhc.md)).

## Sources

- CSV export import
- HTML export import
- XLSX API-viewer recording import
- REST dataset extraction through Reports Plus report 206

## Module layout

```text
src/cvhealthcheck/license_summary/
models.py      — canonical LicenseSummaryArtifact, OtherLicense, AgentFeatureLicense, and workload-summary models
import_csv.py  — multi-section CSV parsing
import_html.py — HTML table extraction by validated header shape
collect_rest.py— REST report 206 normalization plus XLSX recording import
validate.py    — canonical row validity filters
artifact.py    — artifact construction and compatibility writes
service.py     — upload orchestration and registry-backed read path
```

The canonical artifact covers acquisition, normalization, provenance, and persistence. There is no scoring, compliance rule, recommendation, or trend analytics in this subject. A canonical adapter, canonical side-writes for both live REST collection and file import, and Quick HC translation through `quickhc/canonical_view.py` connect the pipeline to the rest of the system.

Outputs:

```text
data/imports/license_summary/artifact_registry.sqlite3
data/catalog/license_summary/<artifact_id>.json
data/catalog/license_summary/latest.json
data/catalog/license_summary/latest_<source_type>.json
```

## Section model

The page renders workload/category summary sections separately from the detail tables.

Detail-table sections:

- Other Licenses — current usage details
- Agent and Feature Licenses — current usage details

Workload/category summary sections:

- Capacity Licenses
- Operating Instance Licenses
- Virtualization Licenses
- User Licenses
- Data Insights Licenses
- Air Gap Protect Licenses
- Other Licenses

Live REST collection discovers summary/category datasets dynamically from report 206 and renders only sections that return real rows. A summary dataset that is unavailable or fails in a given CommCell is omitted rather than fabricated.

## Missing-values policy

License Summary never fabricates absent sections and never guesses values: only sections that return real rows are rendered, and `license_expiry` stays `N/A` when report 206 returns no value. This is the project-wide License Summary missing-values convention — see [../PATTERNS.md](../PATTERNS.md) (Standing conventions).
