# License Summary XML Report Definition Analysis

Research input:
- Local file: `research/commvault-report-definitions/Licensesummary.xml`
- Branch: `hardening/platform-foundation`
- Status: research only, no production code changes

## Scope

This note summarizes the Commvault License Summary report definition at a structural level only. It intentionally avoids copying environment-specific values such as registration codes, CommCell names, organization names, hostnames, tokens, or other sensitive identifiers.

## Report Identity

- Report title in the XML: `License summary`
- The definition is a multi-page custom report rather than a single flat export
- Sanitized structure counts observed in the XML:
  - `48` pages (`Page0` through `Page47`)
  - `66` unique dataset names
  - `226` total dataset declarations across pages

Interpretation:
- The XML confirms that License Summary is organized as a report shell with multiple page families
- The same dataset names are reused across different pages and drilldowns
- The report definition includes both page-level datasets and nested component references embedded in page body JSON

## Page Structure

### Page0

- `Page0` is the default page
- It acts as the summary/dashboard landing page
- It contains the high-level summary datasets currently relevant to the Quick HC collector:
  - `Get Last Collection Time`
  - `GetLicenseSummaryCapacityV3`
  - `GetLicenseSummaryVirtualizationV3`
  - `GetLicenseSummaryEndPointV3`
  - `GetLicenseSummaryOther`
  - `GetLicenseSummaryOIV3`
  - `GetLicenseSummaryActivate`
  - `GetLicenseSummaryMetallic`
  - `GetOrganizationName`

It also defines the `orgGUID` report input, populated from the organization dataset.

### Page16

- `Page16` is the detail/current-usage page
- The page header JavaScript on `Page0` links "More Info" to `Page16`
- The page contains the two current implementation detail datasets:
  - `usageBasedLicenses`
  - `agentFeatureLicenses`
- The page also carries:
  - `Get Last Collection Time`
  - an organization dropdown/input driven by `GetOrganizationName`
  - additional drilldown-specific inputs where relevant

Interpretation:
- `Page16` is the current-usage/detail page behind the visible CSV/HTML/current-usage tables
- This matches the existing artifact model fields for:
  - `other_licenses`
  - `agent_feature_licenses`

### Page40

- `Page0` header JavaScript links "Workload summary" to `Page40`
- This strongly indicates a separate workload/category-summary page family distinct from `Page16`

Interpretation:
- `Page40` is the obvious summary/workload landing page for the newer category sections such as:
  - Capacity Licenses
  - Operating Instance Licenses
  - Virtualization Licenses
  - User Licenses
  - Data Insights Licenses
  - Air Gap Protect Licenses
  - Other Licenses

### Other Page Families

The report includes many drilldown pages mapped from summary tiles or links. The XML’s embedded JavaScript defines a `drilldownPages` map that routes summary labels to specific pages such as:

- capacity-related drilldowns
- virtualization drilldowns
- endpoint/user drilldowns
- operating instance drilldowns
- activate/data-insights drilldowns
- metallic / air-gap-protect drilldowns
- unstructured data drilldowns

Interpretation:
- The report is not just a two-page summary/detail design
- It is a broader drilldown tree, with `Page0` as summary, `Page16` as current-usage detail, `Page40` as workload summary, and many more page-specific drilldowns behind those top-level views

## Dataset Families

### Summary Datasets

These are present on the summary/dashboard page and align with the workload/category summary model:

- `GetLicenseSummaryCapacityV3`
- `GetLicenseSummaryVirtualizationV3`
- `GetLicenseSummaryEndPointV3`
- `GetLicenseSummaryOther`
- `GetLicenseSummaryOIV3`
- `GetLicenseSummaryActivate`
- `GetLicenseSummaryMetallic`

Field shapes visible in the XML include summary-oriented columns such as:

- license/workload label fields
- purchased or entitlement-style values
- used/usage values
- percent or summary/status fields

This matches the current `workload_summary_sections[]` extension in the artifact model.

### Detail Datasets

These are present on `Page16` and align with the current detail-table implementation:

- `usageBasedLicenses`
- `agentFeatureLicenses`

Observed field shapes:

- `usageBasedLicenses`
  - includes usage category/dial plus purchased/usage-oriented fields
  - appears to drive current-usage license-detail tables
- `agentFeatureLicenses`
  - includes license, permanent/evaluation totals, client, agent, and install date style fields
  - clearly maps to the existing Agent and Feature Licenses table

### Organization / Metadata Datasets

Relevant metadata datasets and fields visible in the XML include:

- `GetOrganizationName`
- `Get Organization Name`
- `Get Last Collection Time`

Observed metadata fields include:

- `OrgGUID`
- `Organization`
- `RowID`
- `Last Collection Time`
- `License Expiry`
- `CommCellID`
- `CommCell`
- `RegistrationCode`
- `Version`
- `TimeZone`
- `Last Generation Time`
- `Last Application Time`

Interpretation:
- The XML confirms that the report definition itself expects these metadata fields to exist
- The current collector’s behavior of leaving missing values unset is still correct, because presence in the definition does not guarantee rows are returned in every CommCell

## GUID Parameter Model

Many datasets in the XML require a `GUID` parameter.

Observed pattern:

- report input id: `orgGUID`
- input source dataset: `GetOrganizationName` or `Get Organization Name`
- input label/value model:
  - label field: `Organization`
  - value field: `OrgGUID`
  - sort field: `RowID`

Observed execution pattern:

- summary and detail datasets often define:
  - parameter name: `GUID`
  - value expression: `=input.orgGUID`

Interpretation:

1. The report first discovers available organizations/companies from the organization dataset.
2. The selected organization provides `OrgGUID`.
3. `OrgGUID` is then passed into the page-level datasets as `GUID`.

This validates the current dynamic-parameter approach:

- do not hardcode dataset GUID values
- do not hardcode organization/company identifiers
- discover organization context first
- pass the discovered org GUID into the target datasets

## Relationship To The Current Collector

The XML supports the current `collect_rest.py` design decisions.

### Validated Collector Assumptions

- Summary datasets and detail datasets are separate families
- `Page0` summary/workload data and `Page16` detail/current-usage data are not the same execution target
- The report definition relies on page context and page-local datasets
- `orgGUID` is the dynamic parameter backbone for many datasets

### Collector Implications

- Page-level datasets are the reliable execution target
- Nested `dataSetGuid` references embedded in component JSON should not be blindly executed
- Datasets should be classified by:
  - page context
  - field/header shape
  - intended report family (summary vs detail vs drilldown)

This matches the current live fixes:

- the collector should execute the page-level dataset definitions
- the collector should discover org GUIDs dynamically
- the collector should normalize by table shape rather than by one fixed exported layout

## Sensitive Fields

Sensitive or environment-specific fields clearly present in the XML include:

- `RegistrationCode`
- `CommCellID`
- `CommCell`
- organization/company identifiers
- report-specific GUID relationships

Handling guidance:

- Do not commit the raw XML without sanitization
- Do not copy actual registration codes, customer names, CommCell names, or org identifiers into committed docs
- Treat report-definition exports as potentially customer/environment specific, even when they look like product-level metadata

## Future Architecture

This XML is a useful input for a later generic report-definition layer, but that work should remain research-only for now.

Possible future layering:

1. report definition layer
   - parse pages, inputs, datasets, and component wiring
2. dataset discovery layer
   - identify page-level executable datasets
   - identify parameter sources and dependencies
3. collector layer
   - execute datasets with discovered parameters
   - classify results by page family and field shape
4. artifact pipeline
   - normalize into canonical report artifacts

Potential long-term value:

- generic Commvault report-definition parsing
- better dynamic dataset discovery
- less report-specific reverse engineering per collector

Current recommendation:

- keep XML analysis as research only
- do not widen production scope yet
- continue to treat page-level execution plus shape-based classification as the stable approach for License Summary
