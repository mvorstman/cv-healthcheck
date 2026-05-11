from __future__ import annotations

from cvhealthcheck.api_client import ApiResult

from .client import ReportsPlusClient


KNOWN_WORKING_DATASET_GUID = (
    "979eba7f-8c67-420c-a27e-85ed82066514:"
    "8ac30a77-3de2-4968-86c1-ade4b02c85a4"
)

KNOWN_WORKING_FIELDS = "[MonthStart],[Added],[Removed],[Total]"

KNOWN_WORKING_PARAMETERS = {
    "showDeconfigClients": "0",
    "includePsuedoClients": "0",
}


def fetch_metadata(dataset_guid: str) -> ApiResult:
    return ReportsPlusClient().get_dataset_metadata(dataset_guid)


def fetch_data(
    dataset_guid: str,
    fields: str | None = None,
    orderby: str | None = None,
    limit: int | None = None,
    parameters: dict[str, str] | None = None,
) -> ApiResult:
    return ReportsPlusClient().get_dataset_data(
        dataset_guid=dataset_guid,
        fields=fields,
        orderby=orderby,
        limit=limit,
        parameters=parameters,
    )

