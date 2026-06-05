"""
cvhealthcheck.extractors.cc_endpoint
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ADR 0009 D2/D4 — policy for the Command Center API source's collect endpoint.

The endpoint a ``rest_command_center_api`` subject collects from is no longer
welded to ``GET /commandcenter/api/CommServ`` (ADR 0009 D1); it is declared by
the subject's source binding and, for MCP-authored subjects, *asserted by an AI
proposal*. That assertion is **untrusted input** (ADR 0008): before the app
persists it or collects against it, it is validated here as a **relative,
read-only Command Center path**.

"Read-only" is enforced jointly: (1) this allowlist anchors the path under the
Command Center API namespace, and (2) the collect path only ever issues a GET
(``CommandCenterExtractor`` / ``CommvaultApiClient.get``). A path string carries
no HTTP verb, so there is no per-verb check here — the GET-only contract is the
read-only guarantee, and this module bounds *where* that GET may point.

Leaf module: stdlib only, no project imports, so both the extractor (collect)
and ``create_subject_from_proposal`` (persist) can depend on it without cycles.
"""
from __future__ import annotations

from urllib.parse import urlsplit

# The source_type that routes a /collect to the CommandCenterExtractor and that
# carries a declared endpoint. Single source of truth (command_center.py and
# db/subjects.py both import it from here).
COMMAND_CENTER_SOURCE_TYPE = "rest_command_center_api"

# The historical single-object identity endpoint. A CC-API source that declares
# no endpoint defaults to this, so `environment` (recognition_hints = NULL) is
# byte-for-byte unchanged from ADR 0007.
DEFAULT_CC_ENDPOINT = "/commandcenter/api/CommServ"

# The read-only Command Center API surface an asserted endpoint must sit under.
_CC_API_PREFIX = "/commandcenter/api/"


class EndpointPolicyError(ValueError):
    """An asserted Command Center endpoint failed the relative/read-only policy."""


def validate_cc_endpoint(endpoint: str | None) -> str:
    """Resolve and validate a Command Center API collect endpoint.

    ``None`` or blank resolves to :data:`DEFAULT_CC_ENDPOINT`. Otherwise the
    value must be a **relative** path (no scheme, no host, not protocol-
    relative, no traversal, no whitespace/backslash) anchored under
    ``/commandcenter/api/``. Returns the validated path; raises
    :class:`EndpointPolicyError` on anything outside policy.
    """
    if endpoint is None:
        return DEFAULT_CC_ENDPOINT
    if not isinstance(endpoint, str):
        raise EndpointPolicyError(
            f"endpoint must be a string, got {type(endpoint).__name__}"
        )
    value = endpoint.strip()
    if not value:
        return DEFAULT_CC_ENDPOINT
    if any(ch.isspace() for ch in value) or "\\" in value:
        raise EndpointPolicyError(
            f"endpoint must not contain whitespace or backslashes: {endpoint!r}"
        )
    if value.startswith("//"):
        raise EndpointPolicyError(
            f"endpoint must not be protocol-relative: {endpoint!r}"
        )
    split = urlsplit(value)
    if split.scheme or split.netloc:
        raise EndpointPolicyError(
            f"endpoint must be relative (no scheme or host): {endpoint!r}"
        )
    if not value.startswith(_CC_API_PREFIX):
        raise EndpointPolicyError(
            f"endpoint must be a read-only Command Center path under "
            f"{_CC_API_PREFIX!r}: {endpoint!r}"
        )
    if ".." in value.split("/"):
        raise EndpointPolicyError(
            f"endpoint must not contain path traversal: {endpoint!r}"
        )
    return value
