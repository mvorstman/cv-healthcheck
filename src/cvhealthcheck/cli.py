from __future__ import annotations

import argparse
import sys
from typing import Any

from .api_client import CommvaultApiClient
from .output.json_report import to_pretty_json
from .reportsplus.catalog import write_catalog
from .reportsplus.client import ReportsPlusClient
from .reportsplus.inventory import (
    DATASET_SUMMARY_FIELDS,
    LOGIN_TOKEN_REQUIRED_MESSAGE,
    REPORT_SUMMARY_FIELDS,
    extract_records,
    summarize_records,
)


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
        field: max(len(field), *(len(str(row.get(field, "") or "")) for row in rows))
        for field in fields
    }
    print("  ".join(field.ljust(widths[field]) for field in fields))
    print("  ".join("-" * widths[field] for field in fields))
    for row in rows:
        print(
            "  ".join(
                str(row.get(field, "") or "").ljust(widths[field])
                for field in fields
            )
        )


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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "api" and args.api_command == "ping":
        result = CommvaultApiClient().ping()
        return _print_result(result)

    if args.command == "reportsplus":
        client = ReportsPlusClient()
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


if __name__ == "__main__":
    sys.exit(main())
