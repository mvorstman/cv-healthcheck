from __future__ import annotations

from typing import Any

from cvhealthcheck.api_client import ApiResult, CommvaultApiClient
from cvhealthcheck.auth import load_login_token

REPORTS_PLUS_BASE_PATH = "/commandcenter/api/cr/reportsplusengine"
REPORTS_PATH = f"{REPORTS_PLUS_BASE_PATH}/reports"
DATASETS_PATH = f"{REPORTS_PLUS_BASE_PATH}/datasets"


class ReportsPlusClient:
    def __init__(
        self,
        api_client: CommvaultApiClient | None = None,
        token: str | None = None,
        reports_path: str = REPORTS_PATH,
        datasets_path: str = DATASETS_PATH,
    ) -> None:
        self.api_client = api_client or CommvaultApiClient(token=token)
        self.token = token
        self.reports_path = reports_path
        self.datasets_path = datasets_path

    def _inventory_api_client(self) -> CommvaultApiClient:
        if self.token:
            return self.api_client
        login_token = load_login_token()
        if login_token:
            return CommvaultApiClient(settings=self.api_client.settings, token=login_token)
        return self.api_client

    def list_reports(self) -> ApiResult:
        return self._inventory_api_client().get(self.reports_path)

    def get_report(self, report_id_or_guid: str) -> ApiResult:
        return self._inventory_api_client().get(
            f"{self.reports_path}/{report_id_or_guid}"
        )

    def list_datasets(self) -> ApiResult:
        return self._inventory_api_client().get(self.datasets_path)

    def get_dataset_metadata(self, dataset_guid: str) -> ApiResult:
        return self._inventory_api_client().get(f"{self.datasets_path}/{dataset_guid}")

    def get_dataset_data(
        self,
        dataset_guid: str,
        fields: str | None = None,
        orderby: str | None = None,
        limit: int | None = None,
        parameters: dict[str, str] | None = None,
        format_: str = "object",
        include_other: bool = False,
    ) -> ApiResult:
        params: dict[str, Any] = {
            "format": format_,
            "includeOther": str(include_other).lower(),
        }
        if fields:
            params["fields"] = fields
        if orderby:
            params["orderby"] = orderby
        if limit is not None:
            params["limit"] = limit
        if parameters:
            params.update(parameters)

        return self._inventory_api_client().get(
            f"{self.datasets_path}/{dataset_guid}/data",
            params=params,
        )
