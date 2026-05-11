from __future__ import annotations

from typing import Any

from cvhealthcheck.api_client import ApiResult, CommvaultApiClient


class ReportsPlusClient:
    def __init__(self, api_client: CommvaultApiClient | None = None) -> None:
        self.api_client = api_client or CommvaultApiClient()

    def get_dataset_metadata(self, dataset_guid: str) -> ApiResult:
        return self.api_client.get(
            f"/commandcenter/api/cr/reportsplusengine/datasets/{dataset_guid}"
        )

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

        return self.api_client.get(
            f"/commandcenter/api/cr/reportsplusengine/datasets/{dataset_guid}/data",
            params=params,
        )

