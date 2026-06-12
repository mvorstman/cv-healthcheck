from __future__ import annotations

from typing import Any

from cvhealthcheck.api_client import CommvaultApiClient
from cvhealthcheck.auth import load_login_token
from cvhealthcheck.reportsplus.catalog import collected_at

from .models import CommCellIdentity, QuickHcSource

COMMSERV_ENDPOINT = "/commandcenter/api/CommServ"
COMMSERV_SOURCE = QuickHcSource(
    mode="Quick HealthCheck",
    subject="CommCell Identity / Version",
    endpoint=COMMSERV_ENDPOINT,
    method="GET",
    auth="Login-issued Authtoken",
)


def get_commcell_identity(
    api_client: CommvaultApiClient | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Live GET CommServ identity. Returns the payload only — the global
    ``data/catalog/rest/commserv.json`` provenance write is retired (Fix 2
    (c)): it was an unscoped cross-customer file; the scoped environment
    artifact is the persisted identity record now."""
    client = api_client or CommvaultApiClient(token=token or load_login_token())
    result = client.get(COMMSERV_ENDPOINT)
    normalized = normalize_commserv(result.data)
    return {
        "collected_at": collected_at(),
        "source": COMMSERV_SOURCE.to_dict(),
        "http_status": result.status_code,
        "ok": result.ok,
        "identity": normalized.to_dict(),
        "raw": result.data,
        "error": result.error,
    }


def normalize_commserv(payload: Any) -> CommCellIdentity:
    source = payload if isinstance(payload, dict) else {}
    nested = _commserv_record(payload)
    version = _first_present(source, ("csVersionInfo", "versionInfo", "version"))
    return CommCellIdentity(
        hostName=_string(_first_present(source, ("hostName", "hostname", "commServeHostName"))),
        csGUID=_string(
            _first_present(source, ("csGUID", "csGuid", "commcellGUID", "commCellGuid"))
            or _first_present(nested, ("csGUID", "csGuid", "commcellGUID", "commCellGuid"))
        ),
        csVersionInfo=version,
        releaseId=_release_id(version, source),
        osType=_string(_first_present(source, ("osType", "OSType", "osName"))),
        timeZone=_string(_first_present(source, ("timeZone", "timezone", "timeZoneName"))),
    )


def _commserv_record(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    for key in ("commServ", "commserv", "commcell", "commCell", "CommServ"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return payload


def _first_present(source: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = source.get(key)
        if value not in (None, ""):
            return value
    lowered = {str(key).lower(): key for key in source}
    for key in keys:
        actual = lowered.get(key.lower())
        if actual is not None and source.get(actual) not in (None, ""):
            return source[actual]
    return None


def _release_id(version: Any, source: dict[str, Any]) -> Any:
    release = _first_present(source, ("releaseId", "releaseID"))
    if release is not None:
        return release
    if isinstance(version, dict):
        return _first_present(version, ("releaseId", "releaseID"))
    return None


def _string(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None
