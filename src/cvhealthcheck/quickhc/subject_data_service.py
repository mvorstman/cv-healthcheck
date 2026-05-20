from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

from cvhealthcheck.license_summary.service import LicenseSummaryService
from cvhealthcheck.metrics import get_capacity_license_usage, get_client_growth_summary
from cvhealthcheck.reportsplus.backup_job_summary import load_backup_job_summary_artifact
from cvhealthcheck.reportsplus.catalog import read_json
from cvhealthcheck.reportsplus.security_assessment import security_assessment_quick_hc
from cvhealthcheck.quickhc.commcell import normalize_commserv

logger = logging.getLogger(__name__)

_MONTH_ABBR = {
    "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
    "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
    "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
}


def build_subject_initial_data() -> dict[str, Any]:
    """Build the full initial data structure for the Quick HC frontend."""
    cc = _load_commcell()
    sa = _load_security_assessment()
    ls = _load_license_summary()
    cg = _load_client_growth()
    cl = _load_capacity_license()
    bjs = _load_backup_job_summary()

    commcell_info = _build_commcell_header(cc)

    try:
        from flask import url_for
        report_url = url_for("main.quick_hc_report")
    except Exception:
        report_url = "/quick-hc/report"

    cats = [
        {
            "id": "identity", "name": "Identity", "icon": "🖥", "open": True,
            "subjects": [_build_environment_subject(cc)],
        },
        {
            "id": "security", "name": "Security", "icon": "🔒", "open": True,
            "subjects": [_build_security_assessment_subject(sa)],
        },
        {
            "id": "licensing", "name": "Licensing", "icon": "📋", "open": True,
            "subjects": [_build_license_summary_subject(ls)],
        },
        {
            "id": "performance", "name": "Performance & Growth", "icon": "📈", "open": True,
            "subjects": [
                _build_client_growth_subject(cg),
                _build_capacity_license_subject(cl),
            ],
        },
        {
            "id": "operations", "name": "Operations", "icon": "🔧", "open": True,
            "subjects": [_build_backup_job_summary_subject(bjs)],
        },
    ]

    return {
        "commcell": commcell_info,
        "cats": cats,
        "report_url": report_url,
    }


# ── DATA LOADERS ──

def _load_commcell() -> dict | None:
    try:
        payload = read_json("commserv.json", catalog_dir=Path("data/catalog/rest"))
        identity = payload.get("identity") if isinstance(payload, dict) else {}
        if not isinstance(identity, dict) or not identity:
            identity = normalize_commserv(payload if isinstance(payload, dict) else {}).to_dict()
        return identity
    except FileNotFoundError:
        return None
    except Exception:
        logger.exception("Error loading commcell data")
        return None


def _load_security_assessment() -> dict | None:
    try:
        return security_assessment_quick_hc()
    except Exception:
        logger.exception("Error loading security assessment")
        return None


def _load_license_summary() -> dict | None:
    try:
        return LicenseSummaryService().get_current()
    except FileNotFoundError:
        return None
    except Exception:
        logger.exception("Error loading license summary")
        return None


def _load_client_growth() -> dict | None:
    try:
        return get_client_growth_summary(live=False)
    except FileNotFoundError:
        return None
    except Exception:
        logger.exception("Error loading client growth")
        return None


def _load_capacity_license() -> dict | None:
    try:
        return get_capacity_license_usage(live=False)
    except FileNotFoundError:
        return None
    except Exception:
        logger.exception("Error loading capacity license")
        return None


def _load_backup_job_summary() -> dict | None:
    try:
        return load_backup_job_summary_artifact()
    except FileNotFoundError:
        return None
    except Exception:
        logger.exception("Error loading backup job summary")
        return None


# ── HEADER ──

def _build_commcell_header(cc: dict | None) -> dict:
    if not cc:
        return {"exists": False, "name": "", "version": "", "id": "", "timezone": ""}
    return {
        "exists": True,
        "name": cc.get("hostName") or "",
        "version": cc.get("csVersionInfo") or "",
        "id": cc.get("csGUID") or "",
        "timezone": cc.get("timeZone") or "",
    }


# ── SUBJECT BUILDERS ──

def _nodata_subject(subject_id: str, name: str, full_url: str | None = None) -> dict:
    return {
        "id": subject_id,
        "name": name,
        "state": "nodata",
        "included": True,
        "subtitle": "Not collected",
        "fullUrl": full_url,
        "activeSource": None,
        "sources": [],
        "sections": [],
    }


def _build_environment_subject(cc: dict | None) -> dict:
    full_url = _try_url("main.quick_hc_commcell")
    if not cc:
        subj = _nodata_subject("environment", "CommCell Details", full_url)
        subj["activeSource"] = "rest_api"
        subj["sources"] = [{"id": "rest_api", "name": "Direct REST API", "desc": "Live call to CommServ API", "status": "n", "meta": []}]
        return subj

    name = cc.get("hostName") or "CommCell"
    version = cc.get("csVersionInfo") or ""
    subtitle = f"{name} · {version}" if version else name
    metadata_rows = [
        {"k": "COMMCELL NAME", "v": name},
        {"k": "COMMCELL ID", "v": str(cc.get("csGUID") or "—")},
        {"k": "VERSION", "v": version or "—"},
        {"k": "TIMEZONE", "v": str(cc.get("timeZone") or "—")},
    ]

    return {
        "id": "environment",
        "name": "CommCell Details",
        "state": "ok",
        "included": True,
        "subtitle": subtitle,
        "fullUrl": full_url,
        "activeSource": "rest_api",
        "sources": [
            {
                "id": "rest_api",
                "name": "Direct REST API",
                "desc": "Live call to GET /commandcenter/api/CommServ",
                "status": "v",
                "meta": [
                    {"k": "Host", "v": name},
                    {"k": "Version", "v": version or "Unknown"},
                ],
            },
        ],
        "sections": [
            {
                "id": "environment.metadata",
                "included": True,
                "title": "Environment metadata",
                "meta": "CommCell profile",
                "type": "meta",
                "rows": metadata_rows,
            }
        ],
    }


def _build_security_assessment_subject(sa: dict | None) -> dict:
    full_url = _try_url("main.quick_hc_security_assessment")
    if not sa or not sa.get("exists"):
        subj = _nodata_subject("security_assessment", "Security Assessment", full_url)
        subj["activeSource"] = "rest_report"
        subj["sources"] = [
            {"id": "rest_report", "name": "REST Report", "desc": "Reports Plus report 336 — Security Assessment", "status": "n", "meta": []},
            {"id": "import", "name": "Import File", "desc": "Upload HTML or CSV export — format auto-detected", "status": "n", "meta": [], "hasUpload": True, "importUrl": "/quick-hc/security-assessment/import", "importField": "assessment_file"},
        ]
        return subj

    summary = sa.get("summary") or {}
    counters = summary.get("counters") or {}
    highlights = summary.get("highlights") or []
    sections = summary.get("sections") or []
    source_type = sa.get("source_type") or ""

    critical = int(counters.get("Critical") or 0)
    warning = int(counters.get("Warning") or 0)
    info_count = int(counters.get("Info") or 0)
    good_count = int(counters.get("Good") or 0)
    total = int(counters.get("Total checks") or 0)

    state = "issues" if (critical > 0 or warning > 0) else "ok"
    parts = []
    if critical: parts.append(f"{critical} critical")
    if warning: parts.append(f"{warning} warning")
    if info_count: parts.append(f"{info_count} info")
    if good_count: parts.append(f"{good_count} good")
    subtitle = " · ".join(parts) if parts else f"{total} checks"

    # Map findings
    highlight_findings = [
        {
            "sev": "crit" if f.get("status") == "Critical" else "warn",
            "title": str(f.get("parameter") or ""),
            "rem": _finding_rem(f),
        }
        for f in highlights[:12]
    ]

    info_good_findings = [
        {
            "sev": "info" if f.get("status") == "Info" else "good",
            "title": str(f.get("parameter") or ""),
            "rem": str(f.get("remarks") or ""),
        }
        for sec in sections
        for f in sec.get("checks") or []
        if f.get("status") in ("Info", "Good")
    ][:20]

    # Source metadata
    collected_at = sa.get("collected_at") or ""
    is_rest = source_type in ("rest",)
    is_import = source_type in ("csv", "html", "import")
    active_src = "rest_report" if is_rest else ("import" if is_import else "rest_report")

    return {
        "id": "security_assessment",
        "name": "Security Assessment",
        "state": state,
        "included": True,
        "subtitle": subtitle,
        "fullUrl": full_url,
        "activeSource": active_src,
        "sources": [
            {
                "id": "rest_report",
                "name": "REST Report",
                "desc": "Reports Plus report 336 — Security Assessment",
                "status": "v" if is_rest else "n",
                "meta": ([{"k": "Report ID", "v": "336"}, {"k": "Collected", "v": collected_at}, {"k": "Findings", "v": str(total)}] if is_rest and collected_at else [{"k": "Report ID", "v": "336"}] if is_rest else []),
            },
            {
                "id": "import",
                "name": "Import File",
                "desc": "Upload HTML or CSV export — format auto-detected",
                "status": "v" if is_import else "n",
                "meta": ([{"k": "Source Type", "v": source_type.upper()}, {"k": "Imported", "v": collected_at}] if is_import and collected_at else []),
                "hasUpload": True,
                "importUrl": "/quick-hc/security-assessment/import",
                "importField": "assessment_file",
            },
        ],
        "sections": [
            {
                "id": "security_assessment.summary",
                "title": "Summary counters",
                "meta": f"{total} checks",
                "included": True,
                "type": "counters",
                "counters": {
                    "Critical": critical,
                    "Warning": warning,
                    "Info": info_count,
                    "Good": good_count,
                },
            },
            {
                "id": "security_assessment.highlights",
                "title": "Critical / Warning highlights",
                "meta": "Priority findings",
                "included": True,
                "type": "findings_grid",
                "findings": highlight_findings,
            },
            {
                "id": "security_assessment.all_findings",
                "title": "Info / Good findings",
                "meta": "Informational checks",
                "included": False,
                "type": "findings_list",
                "findings": info_good_findings,
            },
        ],
    }


def _build_license_summary_subject(ls: dict | None) -> dict:
    full_url = _try_url("main.quick_hc_license_summary")
    if not ls:
        subj = _nodata_subject("license_summary", "License Summary", full_url)
        subj["activeSource"] = "rest_report"
        subj["sources"] = [
            {"id": "rest_report", "name": "REST Report", "desc": "Reports Plus report 206 — License Summary", "status": "n", "meta": []},
            {"id": "import", "name": "Import File", "desc": "Upload CSV or HTML export — format auto-detected", "status": "n", "meta": [], "hasUpload": True, "importUrl": "/quick-hc/license-summary/import", "importField": "license_summary_file"},
        ]
        return subj

    source_type = str(ls.get("source_type") or "")
    imported_at = str(ls.get("imported_at") or "")
    generated_on = str(ls.get("generated_on") or "")
    license_expiry = str(ls.get("license_expiry") or "")

    workload_sections = list(ls.get("workload_summary_sections") or [])
    other_licenses = list(ls.get("other_licenses") or [])
    agent_feature_licenses = list(ls.get("agent_feature_licenses") or [])

    wl_count = len(workload_sections)
    other_count = len(other_licenses)
    agent_count = len(agent_feature_licenses)

    subtitle_parts = []
    if wl_count: subtitle_parts.append(f"{wl_count} workload section{'s' if wl_count != 1 else ''}")
    if other_count: subtitle_parts.append(f"{other_count} other licenses")
    subtitle = " · ".join(subtitle_parts) if subtitle_parts else "Available"

    is_rest = source_type in ("rest", "reportsplus")
    is_import = source_type in ("csv", "html", "import")
    active_src = "rest_report" if is_rest else ("import" if is_import else "import")

    # Metadata rows
    meta_rows = [
        {"k": "SOURCE", "v": source_type.upper() if source_type else "Unknown"},
    ]
    if imported_at:
        meta_rows.append({"k": "IMPORTED", "v": imported_at[:19]})
    if generated_on:
        meta_rows.append({"k": "GENERATED ON", "v": generated_on})
    if license_expiry:
        meta_rows.append({"k": "LICENSE EXPIRY", "v": license_expiry, "cls": _expiry_class(license_expiry)})

    # Workload data
    workload_data = []
    for section in workload_sections:
        rows = list(section.get("rows") or [])
        workload_data.append({
            "name": str(section.get("section_name") or ""),
            "rows": [
                {
                    "license": str(row.get("license") or ""),
                    "ent": str(row.get("entitlement_value") or ""),
                    "used": str(row.get("used") or ""),
                    "pct": _safe_int_percent(row.get("usage_percent")),
                }
                for row in rows
            ],
        })

    # Other licenses table
    other_table_rows = [
        [
            str(r.get("license") or ""),
            str(r.get("available_total") if r.get("available_total") is not None else r.get("raw_available_total") or ""),
            str(r.get("used") if r.get("used") is not None else r.get("raw_used") or ""),
        ]
        for r in other_licenses[:30]
    ]

    # Agent/feature licenses table
    agent_table_rows = [
        [
            str(r.get("license") or ""),
            str(r.get("client") or ""),
            str(r.get("agent") or ""),
            " / ".join(str(v) for v in [r.get("permanent_used"), r.get("term_used")] if v is not None and v != ""),
        ]
        for r in agent_feature_licenses[:30]
    ]

    return {
        "id": "license_summary",
        "name": "License Summary",
        "state": "ok",
        "included": True,
        "subtitle": subtitle,
        "fullUrl": full_url,
        "activeSource": active_src,
        "sources": [
            {
                "id": "rest_report",
                "name": "REST Report",
                "desc": "Reports Plus report 206 — License Summary",
                "status": "v" if is_rest else "n",
                "meta": [{"k": "Report ID", "v": "206"}, {"k": "Status", "v": "Executable"}] if is_rest else [],
            },
            {
                "id": "import",
                "name": "Import File",
                "desc": "Upload CSV or HTML export — format auto-detected",
                "status": "v" if is_import else "n",
                "meta": ([{"k": "Source Type", "v": source_type.upper()}, {"k": "Imported", "v": imported_at[:19]}] if is_import and imported_at else []),
                "hasUpload": True,
                "importUrl": "/quick-hc/license-summary/import",
                "importField": "license_summary_file",
            },
        ],
        "sections": [
            {
                "id": "license_summary.metadata",
                "title": "Summary metadata",
                "meta": "Source and dates",
                "included": True,
                "type": "meta",
                "rows": meta_rows,
            },
            {
                "id": "license_summary.workload_sections",
                "title": "Workload Summary Sections",
                "meta": f"{wl_count} section{'s' if wl_count != 1 else ''}",
                "included": True,
                "type": "workload",
                "workload": workload_data,
            },
            {
                "id": "license_summary.other_licenses",
                "title": "Other Licenses table",
                "meta": f"{other_count} row{'s' if other_count != 1 else ''}",
                "included": True,
                "type": "table",
                "columns": ["License", "Available", "Used"],
                "rows": other_table_rows,
            },
            {
                "id": "license_summary.agent_feature_licenses",
                "title": "Agent / Feature Licenses table",
                "meta": f"{agent_count} row{'s' if agent_count != 1 else ''}",
                "included": True,
                "type": "table",
                "columns": ["License", "Client", "Agent", "Perm / Term Used"],
                "rows": agent_table_rows,
            },
        ],
    }


def _safe_int_percent(value: object) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return 0


def _build_client_growth_subject(cg: dict | None) -> dict:
    full_url = _try_url("main.metrics_client_growth")
    if not cg:
        subj = _nodata_subject("client_growth", "Client Growth", full_url)
        subj["activeSource"] = "rest_report"
        subj["sources"] = [{"id": "rest_report", "name": "REST Report", "desc": "Reports Plus report 318 — Client Growth", "status": "n", "meta": []}]
        return subj

    records = list(cg.get("records") or [])
    history_range = cg.get("history_range") or {}
    latest = records[-1] if records else {}
    total_clients = int(latest.get("total_clients") or 0)
    added = int(latest.get("added") or 0)
    latest_month = latest.get("month") or ""

    # YoY calculation
    yoy_pct = None
    if len(records) >= 13:
        prev_year = records[-13]
        prev_total = int(prev_year.get("total_clients") or 0)
        if prev_total > 0:
            pct = round((total_clients - prev_total) / prev_total * 100)
            yoy_pct = f"{'+' if pct >= 0 else ''}{pct}%"

    subtitle_parts = []
    if total_clients: subtitle_parts.append(f"{total_clients} clients")
    if yoy_pct: subtitle_parts.append(f"{yoy_pct} YoY")
    subtitle = " · ".join(subtitle_parts) if subtitle_parts else "Available"

    # Chart data (last 12 months)
    recent = records[-12:]
    chart = {
        "months": [_short_month(r.get("month") or "") for r in recent],
        "totals": [int(r.get("total_clients") or 0) for r in recent],
        "added": [int(r.get("added") or 0) for r in recent],
        "latest_total": total_clients,
        "yoy_pct": yoy_pct,
    }

    # Summary meta rows
    period_start = records[0].get("month") if records else ""
    meta_rows = [
        {"k": "LATEST TOTAL", "v": f"{total_clients} clients"},
        {"k": "LATEST MONTH", "v": latest_month},
        {"k": "ADDED (LATEST)", "v": f"+{added}"},
        {"k": "RECORDS", "v": str(len(records))},
    ]
    if yoy_pct:
        meta_rows.append({"k": "YoY GROWTH", "v": yoy_pct, "cls": "ok" if not yoy_pct.startswith("-") else "warn"})

    # Monthly table
    monthly_rows = [
        [
            str(r.get("month") or ""),
            str(r.get("total_clients") or ""),
            f"+{r.get('added') or 0}",
            f"-{r.get('removed') or 0}",
        ]
        for r in reversed(records[-24:])
    ]

    return {
        "id": "client_growth",
        "name": "Client Growth",
        "state": "ok",
        "included": True,
        "subtitle": subtitle,
        "fullUrl": full_url,
        "activeSource": "rest_report",
        "sources": [
            {
                "id": "rest_report",
                "name": "REST Report",
                "desc": "Reports Plus report 318 — Client Growth",
                "status": "v",
                "meta": [
                    {"k": "Report ID", "v": "318"},
                    {"k": "Records", "v": str(len(records))},
                ],
            },
        ],
        "sections": [
            {
                "id": "client_growth.summary",
                "title": "Summary metrics",
                "meta": f"{total_clients} total clients" if total_clients else "Overview",
                "included": True,
                "type": "meta",
                "rows": meta_rows,
            },
            {
                "id": "client_growth.chart",
                "title": "Client Growth chart",
                "meta": "12-month trend",
                "included": True,
                "type": "chart_growth",
                "chart": chart,
            },
            {
                "id": "client_growth.monthly_table",
                "title": "Monthly summary table",
                "meta": f"{len(records)} rows",
                "included": True,
                "type": "table",
                "columns": ["Month", "Total Clients", "Added", "Removed"],
                "rows": monthly_rows,
            },
        ],
    }


def _build_capacity_license_subject(cl: dict | None) -> dict:
    full_url = _try_url("main.metrics_capacity_license")
    if not cl:
        subj = _nodata_subject("capacity_license", "Capacity Licenses", full_url)
        subj["activeSource"] = "rest_report"
        subj["sources"] = [{"id": "rest_report", "name": "REST Report", "desc": "Reports Plus report 318 — Capacity License", "status": "n", "meta": []}]
        return subj

    records = list(cl.get("records") or [])
    history_range = cl.get("history_range") or {}
    latest_month = history_range.get("end") or ""

    # Aggregate by month
    monthly: dict[str, dict[str, float]] = {}
    for r in records:
        m = str(r.get("month") or "")
        if not m:
            continue
        monthly.setdefault(m, {"used": 0.0, "purchased": 0.0})
        # treat negative sentinel values (-1) as 0
        monthly[m]["used"] += max(float(r.get("used_capacity") or 0), 0.0)
        monthly[m]["purchased"] += max(float(r.get("purchased_capacity") or 0), 0.0)

    sorted_months = sorted(monthly.keys())
    recent_months = sorted_months[-12:]

    # Latest period stats
    latest_used = monthly[latest_month]["used"] if latest_month in monthly else 0.0
    latest_purchased = monthly[latest_month]["purchased"] if latest_month in monthly else 0.0
    utilisation_pct = round(latest_used / latest_purchased * 100, 1) if latest_purchased > 0 else 0.0

    # Peak purchased (for chart scale)
    peak_purchased = max((monthly[m]["purchased"] for m in recent_months), default=1.0)

    subtitle_parts = []
    if latest_used: subtitle_parts.append(f"{latest_used:.1f} TB used")
    if utilisation_pct: subtitle_parts.append(f"{utilisation_pct:.0f}%")
    subtitle = " · ".join(subtitle_parts) if subtitle_parts else "Available"

    chart = {
        "months": [_short_month(m) for m in recent_months],
        "used": [round(monthly[m]["used"], 2) for m in recent_months],
        "purchased": round(peak_purchased, 2),
        "utilisation_pct": utilisation_pct,
    }

    meta_rows = [
        {"k": "USED CAPACITY", "v": f"{latest_used:.1f} TB"},
        {"k": "PURCHASED", "v": f"{latest_purchased:.1f} TB"},
        {"k": "UTILISATION", "v": f"{utilisation_pct:.0f}%"},
        {"k": "PERIOD", "v": latest_month},
    ]

    # Capacity entity table
    latest_records = [r for r in records if str(r.get("month") or "") == latest_month]
    entity_rows = [
        [
            str(r.get("entity_name") or ""),
            f"{float(r.get('used_capacity') or 0):.2f} TB",
            f"{float(r.get('purchased_capacity') or 0):.2f} TB",
            f"{round(float(r.get('used_capacity') or 0) / float(r.get('purchased_capacity') or 1) * 100):.0f}%",
        ]
        for r in latest_records[:30]
    ]

    return {
        "id": "capacity_license",
        "name": "Capacity Licenses",
        "state": "ok",
        "included": True,
        "subtitle": subtitle,
        "fullUrl": full_url,
        "activeSource": "rest_report",
        "sources": [
            {
                "id": "rest_report",
                "name": "REST Report",
                "desc": "Reports Plus report 318 — Capacity License",
                "status": "v",
                "meta": [
                    {"k": "Report ID", "v": "318"},
                    {"k": "Period", "v": latest_month},
                ],
            },
        ],
        "sections": [
            {
                "id": "capacity_license.summary",
                "title": "Summary",
                "meta": latest_month or "Latest period",
                "included": True,
                "type": "meta",
                "rows": meta_rows,
            },
            {
                "id": "capacity_license.table",
                "title": "Usage/details table",
                "meta": f"{len(latest_records)} entities",
                "included": True,
                "type": "table",
                "columns": ["Entity", "Used", "Purchased", "Utilisation"],
                "rows": entity_rows,
            },
        ],
    }


def _build_backup_job_summary_subject(bjs: dict | None) -> dict:
    full_url = _try_url("main.quick_hc_backup_job_summary")
    if not bjs:
        subj = _nodata_subject("backup_job_summary", "Backup Job Summary", full_url)
        subj["activeSource"] = "rest_report"
        subj["sources"] = [{"id": "rest_report", "name": "REST Report", "desc": "Reports Plus Backup Job Summary dataset", "status": "n", "meta": []}]
        return subj

    total_jobs = int(bjs.get("total_jobs") or 0)
    failed_jobs = int(bjs.get("failed_jobs") or 0)
    completed_jobs = int(bjs.get("completed_jobs") or 0)
    running_jobs = int(bjs.get("running_jobs") or 0)
    recent_failures = list(bjs.get("recent_failures") or [])
    recent_jobs = list(bjs.get("recent_jobs") or [])
    status_breakdown = dict(bjs.get("status_breakdown") or {})

    state = "issues" if failed_jobs > 0 else "ok"
    subtitle_parts = [f"{total_jobs} jobs"]
    if failed_jobs: subtitle_parts.append(f"{failed_jobs} failed")
    subtitle = " · ".join(subtitle_parts)

    # Summary meta
    meta_rows = [
        {"k": "TOTAL JOBS", "v": str(total_jobs)},
        {"k": "COMPLETED", "v": str(completed_jobs)},
        {"k": "FAILED", "v": str(failed_jobs), "cls": "err" if failed_jobs > 0 else ""},
        {"k": "RUNNING", "v": str(running_jobs)},
    ]

    # Status breakdown as counters
    status_meta = [
        {"k": str(k), "v": str(v)}
        for k, v in sorted(status_breakdown.items(), key=lambda x: -x[1])
    ]

    # Recent failures as findings list
    failure_findings = [
        {
            "sev": "crit",
            "title": str(f.get("client") or f.get("job_id") or "Unknown Job"),
            "rem": str(f.get("failure_reason") or f.get("status") or ""),
        }
        for f in recent_failures[:10]
    ]

    # Recent jobs table
    job_rows = [
        [
            str(j.get("job_id") or ""),
            str(j.get("client") or ""),
            str(j.get("status") or ""),
            str(j.get("start_time") or ""),
            str(j.get("size") or ""),
        ]
        for j in recent_jobs[:15]
    ]

    return {
        "id": "backup_job_summary",
        "name": "Backup Job Summary",
        "state": state,
        "included": True,
        "subtitle": subtitle,
        "fullUrl": full_url,
        "activeSource": "rest_report",
        "sources": [
            {
                "id": "rest_report",
                "name": "REST Report",
                "desc": "Reports Plus Backup Job Summary dataset",
                "status": "v",
                "meta": [
                    {"k": "Total Jobs", "v": str(total_jobs)},
                    {"k": "Generated", "v": str(bjs.get("generated_at") or "")},
                ],
            },
        ],
        "sections": [
            {
                "id": "backup_job_summary.summary",
                "title": "Summary",
                "meta": f"{total_jobs} jobs",
                "included": True,
                "type": "meta",
                "rows": meta_rows,
            },
            {
                "id": "backup_job_summary.status_breakdown",
                "title": "Status breakdown",
                "meta": f"{len(status_breakdown)} statuses",
                "included": True,
                "type": "meta",
                "rows": status_meta,
            },
            {
                "id": "backup_job_summary.recent_failures",
                "title": "Recent failures",
                "meta": f"{len(recent_failures)} failures",
                "included": True,
                "type": "findings_list",
                "findings": failure_findings,
            },
            {
                "id": "backup_job_summary.recent_jobs",
                "title": "Recent jobs",
                "meta": f"{len(recent_jobs)} jobs",
                "included": True,
                "type": "table",
                "columns": ["Job ID", "Client", "Status", "Start Time", "Size"],
                "rows": job_rows,
            },
        ],
    }


# ── UTILITIES ──

def _try_url(endpoint: str) -> str | None:
    try:
        from flask import url_for
        return url_for(endpoint)
    except Exception:
        return None


def _short_month(month_str: str) -> str:
    """Convert '2026-04' to 'Apr'."""
    if not month_str or len(month_str) < 7:
        return month_str
    mm = month_str[5:7]
    return _MONTH_ABBR.get(mm, mm)


def _expiry_class(date_str: str) -> str:
    """Return CSS class for license expiry date: 'warn' if <90 days, 'err' if past."""
    try:
        expiry = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        delta = (expiry - date.today()).days
        if delta < 0:
            return "err"
        if delta < 90:
            return "warn"
    except Exception:
        pass
    return ""


def _finding_rem(f: dict) -> str:
    section = str(f.get("section") or "")
    remarks = str(f.get("remarks") or "")
    if section and remarks:
        return f"{section} · {remarks}"
    return remarks or section
