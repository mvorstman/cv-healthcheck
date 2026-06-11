#!/usr/bin/env python
"""ADR-0014 curl-first gate — verify Reports Plus dataset addressing live.

All CommServe reads go through the ADR-0008 loopback endpoint
(``POST /internal/commserve`` with ``CV_INTERNAL_SECRET``); this script never
holds a CommServe token. Source ``~/.cv-healthcheck-env`` first, and make sure
the app is Connected (header pill) — an expired held token surfaces here as a
CommServe 401 errorCode 5 envelope.

What the gate must establish (ADR-0014 D5) before any implementation:
  1. whether the composite dataset address ``{reportGuid}:{componentGuid}``
     is a real, working path-segment form on this engine version;
  2. which GUID the component half actually is (the per-report component
     ``guid`` vs the underlying ``dataSetGuid``);
  3. the live ``parameter.*`` query conventions (incl. list-valued params).

Subcommands:
  check                       identity read; prints connection state
  report <id_or_guid>         fetch + parse a report definition; list its
                              components (name, dataSetGuid, component guid)
  data <address> [k=v ...]    GET datasets/<address>/data?limit=1&<params>
  gate [report_id]            scripted sequence (default report 206, License
                              summary): bare-GUID vs both composite forms

Every probe response is captured to ``data/catalog/adr0014_gate/<slug>.json``
(stable names — re-runs overwrite). Payloads come back already redacted by the
app (ADR-0008).

HARD CONSTRAINT: never fetch the ``PackageDetails`` dataset
(credential-exposure risk). The gate skips it; ``data`` has no name knowledge,
so the operator must not pass its GUID by hand.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CAPTURE_DIR = PROJECT_ROOT / "data" / "catalog" / "adr0014_gate"
DATASETS_BASE = "/commandcenter/api/cr/reportsplusengine/datasets"
REPORTS_BASE = "/commandcenter/api/cr/reportsplusengine/reports"
FORBIDDEN_DATASET_NAME = "packagedetails"

_INTERNAL_ENDPOINT_DEFAULT = "http://127.0.0.1:5001/internal/commserve"


def _loopback_get(path: str) -> dict:
    """Read-only GET via the app's loopback endpoint (ADR-0008)."""
    secret = os.environ.get("CV_INTERNAL_SECRET")
    if not secret:
        sys.exit("CV_INTERNAL_SECRET not set — source ~/.cv-healthcheck-env first")
    url = os.environ.get("CV_INTERNAL_ENDPOINT_URL", _INTERNAL_ENDPOINT_DEFAULT)
    resp = requests.post(
        url,
        headers={"X-Internal-Secret": secret},
        json={"path": path, "principal": "adr0014-gate", "capability": "read"},
        timeout=(5, 60),
    )
    if resp.status_code != 200:
        sys.exit(f"loopback endpoint returned HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def _capture(slug: str, path: str, envelope: dict) -> Path:
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    out = CAPTURE_DIR / f"{slug}.json"
    out.write_text(json.dumps({
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "path": path,
        "envelope": envelope,
    }, indent=2))
    return out


def _verdict(envelope: dict) -> str:
    if envelope.get("state") in ("disconnected", "expired"):
        return "NOT CONNECTED — reconnect via the app header pill"
    sc = envelope.get("status_code")
    if sc == 200:
        return "200 OK"
    return f"HTTP {sc} ({json.dumps(envelope.get('data'))[:120]})"


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60]


def cmd_check() -> int:
    env = _loopback_get("/commandcenter/api/CommServ")
    print(f"state={env.get('state')}  ->  {_verdict(env)}")
    return 0 if env.get("ok") else 1


def _fetch_components(report_ref: str) -> tuple[dict, list[dict]]:
    """Fetch a report definition and return (report_payload, components).

    Components carry the per-report ``guid`` and the underlying
    ``dataSetGuid`` — the two candidates for the composite's second half.
    """
    from cvhealthcheck.reportsplus.inventory import parse_content_field

    path = f"{REPORTS_BASE}/{report_ref}"
    env = _loopback_get(path)
    _capture(f"report_{_slugify(report_ref)}", path, env)
    if not env.get("ok"):
        sys.exit(f"report fetch failed: {_verdict(env)}")
    payload = env["data"]
    definition = parse_content_field(payload)

    components: list[dict] = []
    seen: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            ds = node.get("dataSet")
            if isinstance(ds, dict) and (ds.get("dataSetGuid") or ds.get("guid")):
                key = f"{ds.get('guid')}/{ds.get('dataSetGuid')}"
                if key not in seen:
                    seen.add(key)
                    components.append({
                        "dataset_name": ds.get("dataSetName"),
                        "component_guid": ds.get("guid"),
                        "dataset_guid": ds.get("dataSetGuid"),
                    })
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(definition)
    return payload, components


def cmd_report(report_ref: str) -> int:
    payload, components = _fetch_components(report_ref)
    print(f"report: {payload.get('name') or payload.get('reportName')!r}"
          f"  guid={payload.get('guid')}")
    for c in components:
        name = c["dataset_name"] or "?"
        banned = FORBIDDEN_DATASET_NAME in name.lower()
        flag = "  [FORBIDDEN — never fetch]" if banned else ""
        print(f"  {name}: component_guid={c['component_guid']}"
              f"  dataSetGuid={c['dataset_guid']}{flag}")
    return 0


def cmd_data(address: str, params: list[str]) -> int:
    if FORBIDDEN_DATASET_NAME in address.lower():
        sys.exit("refusing: PackageDetails is never fetched (ADR-0014 D5)")
    query = "&".join(["limit=1", *params]) if params else "limit=1"
    path = f"{DATASETS_BASE}/{address}/data?{query}"
    env = _loopback_get(path)
    out = _capture(f"data_{_slugify(address + '_' + query)}", path, env)
    print(f"GET {path}\n  -> {_verdict(env)}\n  capture: {out.relative_to(PROJECT_ROOT)}")
    return 0 if env.get("ok") else 1


def cmd_gate(report_ref: str) -> int:
    """The scripted ADR-0014 D5 sequence against one report's components."""
    payload, components = _fetch_components(report_ref)
    report_guid = payload.get("guid")
    if not report_guid:
        sys.exit("report payload has no guid — cannot build composite addresses")
    usable = [c for c in components
              if c["dataset_guid"] and c["component_guid"]
              and FORBIDDEN_DATASET_NAME not in (c["dataset_name"] or "").lower()]
    if not usable:
        sys.exit("no usable (non-forbidden) components found")
    c = usable[0]
    print(f"report guid: {report_guid}")
    print(f"test component: {c['dataset_name']!r}"
          f" (component_guid={c['component_guid']}, dataSetGuid={c['dataset_guid']})\n")

    results = {}
    for label, address in (
        ("bare_dataset_guid", c["dataset_guid"]),
        ("composite_report_component", f"{report_guid}:{c['component_guid']}"),
        ("composite_report_dataset", f"{report_guid}:{c['dataset_guid']}"),
    ):
        path = f"{DATASETS_BASE}/{address}/data?limit=1"
        env = _loopback_get(path)
        _capture(f"gate_{label}", path, env)
        results[label] = _verdict(env)
        print(f"{label}:\n  GET {path}\n  -> {results[label]}\n")

    summary = _capture("gate_summary", f"{REPORTS_BASE}/{report_ref}", {
        "report_guid": report_guid,
        "component": c,
        "results": results,
    })
    print(f"summary capture: {summary.relative_to(PROJECT_ROOT)}")
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd, *rest = argv
    if cmd == "check":
        return cmd_check()
    if cmd == "report" and len(rest) == 1:
        return cmd_report(rest[0])
    if cmd == "data" and rest:
        return cmd_data(rest[0], rest[1:])
    if cmd == "gate":
        return cmd_gate(rest[0] if rest else "206")
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
