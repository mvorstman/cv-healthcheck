from __future__ import annotations

import argparse
import sys
from typing import Any

from .api_client import CommvaultApiClient
from .labreadiness.evaluator import assess_lab_readiness
from .output.json_report import to_pretty_json
from .reportsplus.catalog import collected_at, read_json, write_catalog, write_json
from .reportsplus.client import ReportsPlusClient
from .reportsplus.inventory import (
    DATASET_SUMMARY_FIELDS,
    LOGIN_TOKEN_REQUIRED_MESSAGE,
    REPORT_SUMMARY_FIELDS,
    extract_records,
    health_candidates,
    summarize_datasets,
    summarize_reports,
    summarize_records,
)
from .reportsplus.priority import prioritize_candidates, priority_summary
from .reportsplus.validation import validate_candidates, validation_summary


def _parse_parameters(values: list[str] | None) -> dict[str, str]:
    parameters: dict[str, str] = {}
    for value in values or []:
        if "=" not in value:
            raise argparse.ArgumentTypeError(
                f"Parameter must be key=value, got {value!r}"
            )
        key, parameter_value = value.split("=", 1)
        parameters[key] = parameter_value
    return parameters


def _print_result(result: Any) -> int:
    if hasattr(result, "data") and result.data is not None:
        print(to_pretty_json(result.data))
    elif hasattr(result, "error") and result.error:
        print(result.error, file=sys.stderr)
    elif hasattr(result, "text"):
        print(result.text)
    else:
        print(to_pretty_json(result))
    return 0 if getattr(result, "ok", True) else 1


def _print_table(rows: list[dict[str, Any]], fields: list[str]) -> None:
    widths = {
        field: max(len(field), *(_display_width(row.get(field)) for row in rows))
        for field in fields
    }
    print("  ".join(field.ljust(widths[field]) for field in fields))
    print("  ".join("-" * widths[field] for field in fields))
    for row in rows:
        print(
            "  ".join(
                _display_value(row.get(field)).ljust(widths[field])
                for field in fields
            )
        )


def _display_value(value: Any) -> str:
    return "" if value is None else str(value)


def _display_width(value: Any) -> int:
    return len(_display_value(value))


def _print_inventory_result(
    result: Any,
    records: list[Any],
    summary: bool,
    summary_fields: list[str],
) -> int:
    if not getattr(result, "ok", False):
        if getattr(result, "status_code", None) == 401:
            print(LOGIN_TOKEN_REQUIRED_MESSAGE, file=sys.stderr)
        return _print_result(result)
    if summary:
        _print_table(summarize_records(records, summary_fields), summary_fields)
    else:
        print(to_pretty_json(result.data))
    return 0


def _summary_payload(source_catalog: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "collected_at": collected_at(),
        "source_catalog": source_catalog,
        "record_count": len(records),
        "records": records,
    }


def _write_reports_catalog(client: ReportsPlusClient) -> tuple[int, list[dict[str, Any]]]:
    result = client.list_reports()
    records = extract_records(result.data, preferred_keys=("reports", "data"))
    if not result.ok:
        if result.status_code == 401:
            print(LOGIN_TOKEN_REQUIRED_MESSAGE, file=sys.stderr)
        _print_result(result)
        return 1, []

    catalog_path = write_catalog("reports", client.reports_path, records)
    summaries = summarize_reports(records)
    summary_path = write_json(
        "reports_summary.json",
        _summary_payload(str(catalog_path), summaries),
    )
    print(f"{catalog_path}: {len(records)} records")
    print(f"{summary_path}: {len(summaries)} records")
    return 0, summaries


def _write_datasets_catalog(client: ReportsPlusClient) -> tuple[int, list[dict[str, Any]]]:
    result = client.list_datasets()
    records = extract_records(result.data, preferred_keys=("dataSet", "datasets", "data"))
    if not result.ok:
        if result.status_code == 401:
            print(LOGIN_TOKEN_REQUIRED_MESSAGE, file=sys.stderr)
        _print_result(result)
        return 1, []

    catalog_path = write_catalog("datasets", client.datasets_path, records)
    summaries = summarize_datasets(records)
    summary_path = write_json(
        "datasets_summary.json",
        _summary_payload(str(catalog_path), summaries),
    )
    print(f"{catalog_path}: {len(records)} records")
    print(f"{summary_path}: {len(summaries)} records")
    return 0, summaries


def _read_records(name: str) -> list[dict[str, Any]]:
    payload = read_json(name)
    records = payload.get("records", [])
    return records if isinstance(records, list) else []


def _write_priority_catalog() -> int:
    read_json("health_candidates.json")
    report_summaries = _read_records("reports_summary.json")
    dataset_summaries = _read_records("datasets_summary.json")
    candidates = prioritize_candidates(report_summaries, dataset_summaries)
    summary = priority_summary(candidates)
    path = write_json(
        "health_candidate_priority.json",
        {
            "collected_at": collected_at(),
            "source_catalogs": [
                "data/catalog/health_candidates.json",
                "data/catalog/reports_summary.json",
                "data/catalog/datasets_summary.json",
            ],
            "record_count": len(candidates),
            "summary": summary,
            "records": candidates,
        },
    )
    print(f"{path}: {len(candidates)} records")
    print(f"HIGH: {summary['HIGH']}  MEDIUM: {summary['MEDIUM']}  LOW: {summary['LOW']}")
    for candidate in candidates[:10]:
        print(
            f"{candidate['priority']:6} "
            f"{candidate['source_type']:7} "
            f"{candidate['name']} -> {candidate['mapped_health_area']}"
        )
    return 0


def _show_priority_catalog() -> int:
    try:
        payload = read_json("health_candidate_priority.json")
    except FileNotFoundError:
        print(
            "data/catalog/health_candidate_priority.json is missing. "
            "Run `cv-healthcheck reportsplus catalog prioritize` first.",
            file=sys.stderr,
        )
        return 1
    records = payload.get("records", [])
    if not isinstance(records, list):
        records = []
    for priority in ("HIGH", "MEDIUM", "LOW"):
        group = [record for record in records if record.get("priority") == priority]
        if not group:
            continue
        print(f"\n{priority}")
        _print_table(
            group,
            [
                "source_type",
                "name",
                "id",
                "guid",
                "mapped_health_area",
                "reason",
            ],
        )
    return 0


def _write_execution_validation(
    priority: str,
    limit: int,
    include_all: bool,
) -> int:
    priority_payload = read_json("health_candidate_priority.json")
    datasets_payload = read_json("datasets.json")
    candidates = priority_payload.get("records", [])
    datasets = datasets_payload.get("records", [])
    if not isinstance(candidates, list):
        candidates = []
    if not isinstance(datasets, list):
        datasets = []
    records = validate_candidates(
        candidates,
        datasets,
        priority=priority,
        limit=limit,
        include_all=include_all,
    )
    summary = validation_summary(records)
    path = write_json(
        "execution_validation.json",
        {
            "collected_at": collected_at(),
            "source_catalogs": [
                "data/catalog/health_candidate_priority.json",
                "data/catalog/datasets.json",
            ],
            "record_count": len(records),
            "summary": summary,
            "records": records,
        },
    )
    print(f"{path}: {len(records)} records")
    print(
        "EXECUTABLE: {EXECUTABLE}  NEEDS_PARAMS: {NEEDS_PARAMS}  "
        "FAILS: {FAILS}  SKIPPED: {SKIPPED}".format(**summary)
    )
    return 0


def _show_execution_validation() -> int:
    try:
        payload = read_json("execution_validation.json")
    except FileNotFoundError:
        print(
            "data/catalog/execution_validation.json is missing. "
            "Run `cv-healthcheck reportsplus catalog validate-candidates` first.",
            file=sys.stderr,
        )
        return 1
    records = payload.get("records", [])
    if not isinstance(records, list):
        records = []
    summary = validation_summary(records)
    print(
        "EXECUTABLE: {EXECUTABLE}  NEEDS_PARAMS: {NEEDS_PARAMS}  "
        "FAILS: {FAILS}  SKIPPED: {SKIPPED}".format(**summary)
    )
    rows = [
        {
            "candidate_name": record.get("candidate_name"),
            "mapped_health_area": record.get("mapped_health_area"),
            "status": record.get("status"),
            "record_count": record.get("record_count"),
            "field_count": len(record.get("returned_fields") or []),
        }
        for record in records
    ]
    if rows:
        _print_table(
            rows,
            [
                "candidate_name",
                "mapped_health_area",
                "status",
                "record_count",
                "field_count",
            ],
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cv-healthcheck")
    subparsers = parser.add_subparsers(dest="command", required=True)

    api_parser = subparsers.add_parser("api")
    api_subparsers = api_parser.add_subparsers(dest="api_command", required=True)
    api_subparsers.add_parser("ping")

    reports_parser = subparsers.add_parser("reportsplus")
    reports_subparsers = reports_parser.add_subparsers(
        dest="reportsplus_command",
        required=True,
    )

    reports_inventory_parser = reports_subparsers.add_parser("reports")
    reports_inventory_parser.add_argument("--summary", action="store_true")

    datasets_inventory_parser = reports_subparsers.add_parser("datasets")
    datasets_inventory_parser.add_argument("--summary", action="store_true")

    catalog_parser = reports_subparsers.add_parser("catalog")
    catalog_subparsers = catalog_parser.add_subparsers(
        dest="catalog_command",
        required=True,
    )
    catalog_subparsers.add_parser("reports")
    catalog_subparsers.add_parser("datasets")
    catalog_subparsers.add_parser("all")
    catalog_subparsers.add_parser("prioritize")
    catalog_subparsers.add_parser("show-priority")
    validate_parser = catalog_subparsers.add_parser("validate-candidates")
    validate_parser.add_argument("--priority", default="HIGH")
    validate_parser.add_argument("--limit", type=int, default=5)
    validate_parser.add_argument("--all", action="store_true")
    catalog_subparsers.add_parser("show-validation")

    metadata_parser = reports_subparsers.add_parser("metadata")
    metadata_parser.add_argument("--dataset-guid", required=True)

    data_parser = reports_subparsers.add_parser("data")
    data_parser.add_argument("--dataset-guid", required=True)
    data_parser.add_argument("--fields")
    data_parser.add_argument("--orderby")
    data_parser.add_argument("--limit", type=int)
    data_parser.add_argument(
        "--parameter",
        action="append",
        default=[],
        help="Dataset parameter as key=value. Can be repeated.",
    )

    lab_parser = subparsers.add_parser("lab")
    lab_subparsers = lab_parser.add_subparsers(dest="lab_command", required=True)
    readiness_parser = lab_subparsers.add_parser("readiness")
    readiness_parser.add_argument("--json", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "api" and args.api_command == "ping":
        result = CommvaultApiClient().ping()
        return _print_result(result)

    if args.command == "lab" and args.lab_command == "readiness":
        result = assess_lab_readiness(write=True)
        if args.json:
            print(to_pretty_json(result))
        else:
            _print_lab_readiness(result)
        return 0

    if args.command == "reportsplus":
        client = ReportsPlusClient()
        if args.reportsplus_command == "catalog":
            if args.catalog_command == "reports":
                status, _ = _write_reports_catalog(client)
                return status
            if args.catalog_command == "datasets":
                status, _ = _write_datasets_catalog(client)
                return status
            if args.catalog_command == "all":
                reports_status, report_summaries = _write_reports_catalog(client)
                datasets_status, dataset_summaries = _write_datasets_catalog(client)
                candidates = health_candidates(report_summaries, dataset_summaries)
                candidates_path = write_json(
                    "health_candidates.json",
                    {
                        "collected_at": collected_at(),
                        "record_count": len(candidates["reports"])
                        + len(candidates["datasets"]),
                        "records": candidates,
                    },
                )
                print(
                    f"{candidates_path}: "
                    f"{len(candidates['reports'])} reports, "
                    f"{len(candidates['datasets'])} datasets"
                )
                return 0 if reports_status == 0 and datasets_status == 0 else 1
            if args.catalog_command == "prioritize":
                return _write_priority_catalog()
            if args.catalog_command == "show-priority":
                return _show_priority_catalog()
            if args.catalog_command == "validate-candidates":
                return _write_execution_validation(
                    priority=args.priority,
                    limit=args.limit,
                    include_all=args.all,
                )
            if args.catalog_command == "show-validation":
                return _show_execution_validation()
        if args.reportsplus_command == "reports":
            result = client.list_reports()
            records = extract_records(result.data, preferred_keys=("reports", "data"))
            if result.ok:
                write_catalog("reports", client.reports_path, records)
            return _print_inventory_result(
                result,
                records,
                args.summary,
                REPORT_SUMMARY_FIELDS,
            )
        if args.reportsplus_command == "datasets":
            result = client.list_datasets()
            records = extract_records(result.data, preferred_keys=("datasets", "data"))
            if result.ok:
                write_catalog("datasets", client.datasets_path, records)
            return _print_inventory_result(
                result,
                records,
                args.summary,
                DATASET_SUMMARY_FIELDS,
            )
        if args.reportsplus_command == "metadata":
            return _print_result(client.get_dataset_metadata(args.dataset_guid))
        if args.reportsplus_command == "data":
            return _print_result(
                client.get_dataset_data(
                    dataset_guid=args.dataset_guid,
                    fields=args.fields,
                    orderby=args.orderby,
                    limit=args.limit,
                    parameters=_parse_parameters(args.parameter),
                )
            )

    parser.error("Unsupported command")
    return 2


def _print_lab_readiness(result: dict[str, Any]) -> None:
    print(f"Readiness state: {result['readiness_state']}")
    print(result["summary"])
    print("\nMajor indicators:")
    indicators = result.get("indicators", {})
    rows = [
        {
            "indicator": name,
            "value": indicator.get("value"),
            "status": indicator.get("status"),
        }
        for name, indicator in indicators.items()
    ]
    _print_table(rows, ["indicator", "value", "status"])
    print("\nRecommendations:")
    for recommendation in result.get("recommendations", []):
        print(f"- {recommendation}")


if __name__ == "__main__":
    sys.exit(main())
