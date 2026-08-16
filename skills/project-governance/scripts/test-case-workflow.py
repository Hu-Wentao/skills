#!/usr/bin/env python3
"""Inspect governed CSV test cases for implementation and verification use."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


SCHEMA = "project-governance.test-case-development.v1"
CONFIG_SCHEMA = "project-governance.test-case-workflow.v1"
CONFIG_RELATIVE = Path(
    ".agents/skills-config/project-governance/test-case-workflow.json"
)
RESULTS = {"PASS", "FAIL", "BLOCKED", "NOT_RUN"}
REQUIRED_COLUMN_ROLES = {
    "id",
    "requirement",
    "title",
    "steps",
    "expected",
    "result",
}
OPTIONAL_COLUMN_ROLES = {
    "priority",
    "preconditions",
    "actual",
    "execution_count",
    "test_date",
    "tester",
    "evidence",
}
CATALOG_KEYS = {
    "path",
    "format",
    "encoding",
    "governance_document",
    "eligible_document_statuses",
    "requirement_authority",
    "columns",
}
CATALOG_BLOCKING_CODES = {
    "duplicate_headers",
    "missing_headers",
    "missing_case_id",
    "duplicate_case_id",
}


class WorkflowError(ValueError):
    """Raised when workflow configuration or input is unsafe or invalid."""


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def failure(operation: str, message: str, *, code: str = "operational_error") -> int:
    emit(
        {
            "schema": SCHEMA,
            "operation": operation,
            "state": "operational_error",
            "error": {"code": code, "message": message},
        }
    )
    return 2


def exact_keys(value: dict[str, Any], allowed: set[str], field: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise WorkflowError(f"{field} contains unsupported keys: {', '.join(unknown)}")


def nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowError(f"{field} must be a non-empty string")
    return value.strip()


def contained_file(root: Path, value: str, field: str) -> Path:
    path = (root / value).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise WorkflowError(f"{field} must stay inside the project root") from exc
    if not path.is_file():
        raise WorkflowError(f"{field} not found: {path}")
    return path


def load_configuration(root: Path) -> tuple[Path, dict[str, Any]] | None:
    path = root / CONFIG_RELATIVE
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"{CONFIG_RELATIVE} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise WorkflowError(f"{CONFIG_RELATIVE} must contain an object")
    exact_keys(value, {"schema", "profile", "catalogs"}, "configuration")
    if value.get("schema") != CONFIG_SCHEMA:
        raise WorkflowError(f"configuration.schema must be {CONFIG_SCHEMA}")
    nonempty_string(value.get("profile"), "configuration.profile")
    catalogs = value.get("catalogs")
    if not isinstance(catalogs, dict) or not catalogs:
        raise WorkflowError("configuration.catalogs must be a non-empty object")
    return path, value


def normalize_catalog(root: Path, catalog_id: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkflowError(f"catalogs.{catalog_id} must be an object")
    exact_keys(value, CATALOG_KEYS, f"catalogs.{catalog_id}")
    if value.get("format") != "csv":
        raise WorkflowError(f"catalogs.{catalog_id}.format must be csv")
    encoding = nonempty_string(
        value.get("encoding"), f"catalogs.{catalog_id}.encoding"
    )
    if encoding not in {"utf-8", "utf-8-sig"}:
        raise WorkflowError(
            f"catalogs.{catalog_id}.encoding must be utf-8 or utf-8-sig"
        )
    catalog_path = contained_file(
        root,
        nonempty_string(value.get("path"), f"catalogs.{catalog_id}.path"),
        f"catalogs.{catalog_id}.path",
    )
    governance_path = contained_file(
        root,
        nonempty_string(
            value.get("governance_document"),
            f"catalogs.{catalog_id}.governance_document",
        ),
        f"catalogs.{catalog_id}.governance_document",
    )
    statuses = value.get("eligible_document_statuses")
    if not isinstance(statuses, list) or not statuses:
        raise WorkflowError(
            f"catalogs.{catalog_id}.eligible_document_statuses must be a non-empty list"
        )
    eligible_statuses = [
        nonempty_string(
            item, f"catalogs.{catalog_id}.eligible_document_statuses item"
        )
        for item in statuses
    ]
    authority = nonempty_string(
        value.get("requirement_authority"),
        f"catalogs.{catalog_id}.requirement_authority",
    )
    if authority not in {"resolved", "unresolved"}:
        raise WorkflowError(
            f"catalogs.{catalog_id}.requirement_authority must be resolved or unresolved"
        )
    columns = value.get("columns")
    if not isinstance(columns, dict):
        raise WorkflowError(f"catalogs.{catalog_id}.columns must be an object")
    exact_keys(
        columns,
        REQUIRED_COLUMN_ROLES | OPTIONAL_COLUMN_ROLES,
        f"catalogs.{catalog_id}.columns",
    )
    missing_roles = sorted(REQUIRED_COLUMN_ROLES - set(columns))
    if missing_roles:
        raise WorkflowError(
            f"catalogs.{catalog_id}.columns is missing roles: {', '.join(missing_roles)}"
        )
    normalized_columns = {
        role: nonempty_string(header, f"catalogs.{catalog_id}.columns.{role}")
        for role, header in columns.items()
    }
    if len(set(normalized_columns.values())) != len(normalized_columns):
        raise WorkflowError(f"catalogs.{catalog_id}.columns must map to unique headers")
    return {
        "id": catalog_id,
        "path": catalog_path,
        "encoding": encoding,
        "governance_document": governance_path,
        "eligible_document_statuses": eligible_statuses,
        "requirement_authority": authority,
        "columns": normalized_columns,
    }


def document_status(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = re.fullmatch(r"status:\s*(.+)", line)
        if match:
            return match.group(1).strip().strip("\"'")
    return ""


def diagnostic(
    severity: str, code: str, message: str, *, case_id: str | None = None
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "severity": severity,
        "code": code,
        "message": message,
    }
    if case_id:
        value["case_id"] = case_id
    return value


def load_cases(
    catalog: dict[str, Any]
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    with catalog["path"].open(
        "r", encoding=catalog["encoding"], newline=""
    ) as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        duplicates = sorted(
            {header for header in headers if headers.count(header) > 1}
        )
        if duplicates:
            issues.append(
                diagnostic(
                    "error",
                    "duplicate_headers",
                    f"CSV contains duplicate headers: {', '.join(duplicates)}",
                )
            )
        missing_headers = sorted(set(catalog["columns"].values()) - set(headers))
        if missing_headers:
            issues.append(
                diagnostic(
                    "error",
                    "missing_headers",
                    f"CSV is missing configured headers: {', '.join(missing_headers)}",
                )
            )
        rows = list(reader)

    cases: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, start=2):
        normalized = {
            role: (row.get(header) or "").strip()
            for role, header in catalog["columns"].items()
        }
        case_id = normalized.get("id", "")
        if not case_id:
            issues.append(
                diagnostic("error", "missing_case_id", f"CSV row {index} has no case ID")
            )
        elif case_id in seen:
            issues.append(
                diagnostic(
                    "error",
                    "duplicate_case_id",
                    f"case ID is duplicated: {case_id}",
                    case_id=case_id,
                )
            )
        seen.add(case_id)
        result = normalized.get("result", "").upper()
        normalized["result"] = result
        if result and result not in RESULTS:
            issues.append(
                diagnostic(
                    "error",
                    "invalid_test_result",
                    f"test result must be one of: {', '.join(sorted(RESULTS))}",
                    case_id=case_id or None,
                )
            )
        cases.append(normalized)
    return cases, issues


def snapshot(root: Path, *paths: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    files: list[dict[str, Any]] = []
    for path in paths:
        data = path.read_bytes()
        relative = path.relative_to(root).as_posix()
        sha256 = hashlib.sha256(data).hexdigest()
        files.append({"path": relative, "sha256": sha256, "bytes": len(data)})
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
    return {"sha256": digest.hexdigest(), "files": files}


def case_summary(case: dict[str, str]) -> dict[str, str]:
    return {
        key: case.get(key, "")
        for key in (
            "id",
            "requirement",
            "priority",
            "title",
            "preconditions",
            "steps",
            "expected",
            "result",
            "actual",
            "execution_count",
            "test_date",
            "tester",
            "evidence",
        )
        if key in case
    }


def eligibility_issues(
    catalog: dict[str, Any],
    status: str,
    cases: list[dict[str, str]],
    issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    blockers = [
        item
        for item in issues
        if item["severity"] == "error" and item["code"] in CATALOG_BLOCKING_CODES
    ]
    if not status:
        blockers.append(
            diagnostic(
                "error",
                "missing_document_status",
                "the governance document does not expose a top-level status",
            )
        )
    elif status not in catalog["eligible_document_statuses"]:
        blockers.append(
            diagnostic(
                "error",
                "ineligible_document_status",
                f"document status {status!r} is not eligible for implementation",
            )
        )
    if catalog["requirement_authority"] != "resolved":
        blockers.append(
            diagnostic(
                "error",
                "requirement_authority_unresolved",
                "requirement authority must be resolved before cases drive implementation",
            )
        )
    if not cases:
        blockers.append(diagnostic("error", "empty_catalog", "the catalog has no cases"))
    return blockers


def selected_case_issues(
    case: dict[str, str] | None, case_id: str
) -> list[dict[str, Any]]:
    if case is None:
        return [
            diagnostic(
                "error",
                "case_not_found",
                f"case ID was not found: {case_id}",
                case_id=case_id,
            )
        ]
    issues: list[dict[str, Any]] = []
    for field in ("requirement", "title", "steps", "expected"):
        if not case.get(field, ""):
            issues.append(
                diagnostic(
                    "error",
                    "incomplete_case",
                    f"case is missing {field}",
                    case_id=case_id,
                )
            )
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("inspect", "plan", "verify"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--case-id")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    if args.operation in {"plan", "verify"} and not args.case_id:
        return failure(
            args.operation,
            f"{args.operation} requires --case-id",
            code="missing_parameter",
        )
    if args.limit < 0:
        return failure(
            args.operation,
            "--limit must be zero or greater",
            code="invalid_parameter",
        )

    try:
        root = Path(args.root).expanduser().resolve()
        if not root.is_dir():
            raise WorkflowError(f"project root is not a directory: {root}")
        configured = load_configuration(root)
        if configured is None:
            emit(
                {
                    "schema": SCHEMA,
                    "operation": args.operation,
                    "state": "not_configured",
                    "configuration": CONFIG_RELATIVE.as_posix(),
                    "next_actions": [
                        "Add a project-owned test-case-workflow.json configuration.",
                        "Keep product requirements authoritative over test cases.",
                    ],
                }
            )
            return 1
        config_path, config = configured
        catalogs = config["catalogs"]
        if args.catalog not in catalogs:
            raise WorkflowError(
                f"unknown catalog {args.catalog!r}; configured: {', '.join(sorted(catalogs))}"
            )
        catalog = normalize_catalog(root, args.catalog, catalogs[args.catalog])
        status = document_status(catalog["governance_document"])
        cases, issues = load_cases(catalog)
        selected = next(
            (case for case in cases if case.get("id") == (args.case_id or "")),
            None,
        )
        source_snapshot = snapshot(
            root, config_path, catalog["governance_document"], catalog["path"]
        )
    except (OSError, csv.Error, WorkflowError) as exc:
        return failure(args.operation, str(exc))

    blockers = eligibility_issues(catalog, status, cases, issues)
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "operation": args.operation,
        "catalog": {
            "id": args.catalog,
            "path": catalog["path"].relative_to(root).as_posix(),
            "governance_document": catalog["governance_document"]
            .relative_to(root)
            .as_posix(),
            "document_status": status,
            "eligible_document_statuses": catalog["eligible_document_statuses"],
            "requirement_authority": catalog["requirement_authority"],
            "case_count": len(cases),
        },
        "source_snapshot": source_snapshot,
        "policy": {
            "test_cases_define_product_semantics": False,
            "passing_result_activates_requirement": False,
            "passing_result_authorizes_release": False,
            "semantic_review_required": True,
        },
    }

    if args.operation == "inspect":
        chosen = [selected] if args.case_id and selected else cases
        available_count = len(chosen)
        if args.limit:
            chosen = chosen[: args.limit]
        if args.case_id:
            blockers.extend(selected_case_issues(selected, args.case_id))
        payload.update(
            {
                "state": "inspection_completed",
                "eligibility": (
                    "decision_required" if blockers else "implementation_preflight_ready"
                ),
                "cases": [case_summary(case) for case in chosen],
                "diagnostics": issues + [item for item in blockers if item not in issues],
                "truncated": bool(args.limit and available_count > args.limit),
            }
        )
        emit(payload)
        return 0

    case_issues = selected_case_issues(selected, args.case_id)
    if args.operation == "plan":
        blockers.extend(case_issues)
        payload.update(
            {
                "state": (
                    "decision_required" if blockers else "implementation_preflight_ready"
                ),
                "case": case_summary(selected) if selected else None,
                "diagnostics": blockers,
                "next_actions": (
                    [
                        "Resolve document review and requirement authority before implementation.",
                        "Resolve conflicts against requirements, baselines, contracts, and code.",
                    ]
                    if blockers
                    else [
                        "Perform semantic review against higher-authority sources.",
                        "Implement and verify only the impact-selected behavior.",
                    ]
                ),
            }
        )
        emit(payload)
        return 1 if blockers else 0

    verification_issues = [
        item
        for item in issues
        if not item.get("case_id") or item.get("case_id") == args.case_id
    ] + case_issues
    result = selected.get("result", "") if selected else ""
    if selected and result != "PASS":
        code = "test_not_run" if not result else "test_not_passed"
        verification_issues.append(
            diagnostic(
                "error",
                code,
                "the selected case has no PASS result"
                if not result
                else f"the selected case result is {result}",
                case_id=args.case_id,
            )
        )
    incomplete = any(item["severity"] == "error" for item in verification_issues)
    payload.update(
        {
            "state": (
                "verification_incomplete"
                if incomplete
                else "verification_evidence_available"
            ),
            "case": case_summary(selected) if selected else None,
            "diagnostics": verification_issues,
            "semantic_conclusion": "not_inferred",
        }
    )
    emit(payload)
    return 1 if incomplete else 0


if __name__ == "__main__":
    sys.exit(main())
