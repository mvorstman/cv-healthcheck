"""
cvhealthcheck.reportsplus.report_definitions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Report Builder payloads for use with CommvaultSession.init_report().

AUDIT FINDINGS (2026-05-25):
  metrics/growth.py defines CLIENT_COUNT_SOURCE with
      dataset_guid = "f2bfe9ce-0101-4377-be9e-285981ac7fd8"
  and uses execute_dataset() for direct GET access — it does NOT define
  a reportBuilder.do payload anywhere.

  Report 318 is the Growth and Trends report (confirmed in metrics/).
  The payload here is the minimal definition needed for reportBuilder.do.
"""
from __future__ import annotations

_REPORT_318_ID = 318

# Minimal reportBuilder.do payload for the Growth and Trends report (318).
# The dataset_guid here matches CLIENT_COUNT_SOURCE in metrics/growth.py
# and the db extraction instructions for client_growth.monthly_table.
CLIENT_GROWTH_REPORT_DEFINITION: dict = {
    "reportId": _REPORT_318_ID,
    "datasets": [
        {"datasetGuid": "f2bfe9ce-0101-4377-be9e-285981ac7fd8"},
    ],
}

# Registry mapping subject_id → report definition for the collect route.
REPORT_DEFINITIONS: dict[str, dict] = {
    "client_growth": CLIENT_GROWTH_REPORT_DEFINITION,
}
