#!/usr/bin/env python3
"""Inspect and verify project domain-concept documents through MDQ."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


SCHEMA = "project-governance.domain-knowledge.v1"
ID_PATTERN = re.compile(r"^CONCEPT-[A-Z0-9-]+$")
REFERENCE_PATTERN = re.compile(r"\bCONCEPT-[A-Z0-9-]+\b")
SEMANTIC_STATUSES = {"proposed", "accepted", "deprecated"}
REQUIRED_FIELDS = {
    "lite": ("title", "semantic_status", "definition", "sources"),
    "catalog": (
        "title",
        "semantic_status",
        "kind",
        "scope_note",
        "definition",
        "sources",
    ),
    "bounded": (
        "title",
        "semantic_status",
        "kind",
        "context",
        "scope_note",
        "definition",
        "sources",
    ),
}
RELATION_FIELDS = ("broader", "narrower", "related")


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


def resolve_project_root(value: str) -> Path:
    root = Path(value).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"project root is not a directory: {root}")
    return root


def resolve_docs(project_root: Path, value: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = project_root / candidate
    candidate = candidate.resolve(strict=False)
    try:
        candidate.relative_to(project_root)
    except ValueError as exc:
        raise ValueError(f"domain docs must stay inside project root: {candidate}") from exc
    return candidate


def resolve_mdq_script(skill_root: Path) -> Path:
    candidates = (
        skill_root.parent / "queryable-markdown" / "scripts" / "mdq.py",
        Path.home() / ".codex" / "skills" / "queryable-markdown" / "scripts" / "mdq.py",
        Path.home() / ".agents" / "skills" / "queryable-markdown" / "scripts" / "mdq.py",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise ValueError("queryable-markdown mdq.py was not found in a supported skill location")


def markdown_sources(target: Path) -> list[Path]:
    if target.is_file():
        return [target] if target.suffix.lower() == ".md" else []
    if target.is_dir():
        return sorted(
            path
            for path in target.rglob("*.md")
            if path.is_file() and not path.is_symlink()
        )
    return []


def source_snapshot(project_root: Path, sources: list[Path]) -> dict[str, Any] | None:
    if not sources:
        return None
    digest = hashlib.sha256()
    entries: list[dict[str, Any]] = []
    for source in sources:
        data = source.read_bytes()
        relative = source.relative_to(project_root).as_posix()
        sha256 = hashlib.sha256(data).hexdigest()
        entries.append({"path": relative, "sha256": sha256, "bytes": len(data)})
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
    return {"sha256": digest.hexdigest(), "files": entries}


def run_mdq(
    mdq_script: Path,
    target: Path,
    *,
    record_id: str | None = None,
    text: str | None = None,
    limit: int = 0,
) -> tuple[int, dict[str, Any]]:
    command = [
        "uv",
        "run",
        str(mdq_script),
        "scan",
        str(target),
        "--require-contract",
    ]
    if record_id:
        command.extend(["--id", record_id])
    if text:
        command.extend(["--text", text])
    if limit:
        command.extend(["--limit", str(limit)])
    completed = subprocess.run(command, capture_output=True, check=False, text=True)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no output"
        raise ValueError(f"mdq returned invalid JSON: {detail}") from exc
    return completed.returncode, payload


def record_fields(record: dict[str, Any]) -> dict[str, Any]:
    fields = record.get("fields")
    return fields if isinstance(fields, dict) else {}


def scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def split_terms(value: Any) -> list[str]:
    return [term.strip() for term in re.split(r"[,，;；\n]+", scalar(value)) if term.strip()]


def diagnostic(
    severity: str,
    code: str,
    message: str,
    *,
    record_id: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if record_id:
        result["record_id"] = record_id
    return result


def mdq_diagnostics(report: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics = report.get("diagnostics")
    if not isinstance(diagnostics, list):
        return []
    return [dict(item) for item in diagnostics if isinstance(item, dict)]


def records_from(report: dict[str, Any]) -> list[dict[str, Any]]:
    records = report.get("records")
    if not isinstance(records, list):
        return []
    results: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        copied = dict(record)
        relative_path = scalar(copied.get("relative_path"))
        if relative_path:
            copied.setdefault("document", relative_path)
        results.append(copied)
    return results


def validate_records(
    records: list[dict[str, Any]],
    mode: str,
    *,
    validate_relationships: bool = True,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    known_ids: set[str] = set()
    for record in records:
        record_id = scalar(record.get("key"))
        if not ID_PATTERN.fullmatch(record_id):
            issues.append(
                diagnostic("error", "invalid_concept_id", f"invalid concept ID: {record_id!r}")
            )
        elif record_id in known_ids:
            issues.append(
                diagnostic(
                    "error",
                    "duplicate_concept_id",
                    f"concept ID is duplicated: {record_id}",
                    record_id=record_id,
                )
            )
        known_ids.add(record_id)

    term_owners: dict[tuple[str, str], str] = {}
    for record in records:
        record_id = scalar(record.get("key"))
        fields = record_fields(record)
        for field in REQUIRED_FIELDS[mode]:
            if not scalar(fields.get(field)):
                issues.append(
                    diagnostic(
                        "error",
                        "missing_profile_field",
                        f"{mode} requires field {field}",
                        record_id=record_id or None,
                    )
                )

        status = scalar(fields.get("semantic_status")).lower()
        if status and status not in SEMANTIC_STATUSES:
            issues.append(
                diagnostic(
                    "error",
                    "invalid_semantic_status",
                    "semantic_status must be proposed, accepted, or deprecated",
                    record_id=record_id or None,
                )
            )

        context = scalar(fields.get("context")).casefold() if mode == "bounded" else ""
        terms = [scalar(fields.get("title"))]
        if mode in {"catalog", "bounded"}:
            terms.extend(split_terms(fields.get("aliases")))
        for term in (item for item in terms if item):
            key = (context, term.casefold())
            owner = term_owners.get(key)
            if owner and owner != record_id:
                scope = f" in context {context!r}" if mode == "bounded" else ""
                issues.append(
                    diagnostic(
                        "error",
                        "ambiguous_domain_term",
                        f"term {term!r}{scope} is shared with {owner}",
                        record_id=record_id or None,
                    )
                )
            else:
                term_owners[key] = record_id

        if validate_relationships and mode in {"catalog", "bounded"}:
            for field in RELATION_FIELDS:
                for target in REFERENCE_PATTERN.findall(scalar(fields.get(field))):
                    if target == record_id:
                        issues.append(
                            diagnostic(
                                "error",
                                "self_referential_concept",
                                f"{field} cannot reference the same concept",
                                record_id=record_id or None,
                            )
                        )
                    elif target not in known_ids:
                        issues.append(
                            diagnostic(
                                "error",
                                "unknown_concept_reference",
                                f"{field} references unknown concept {target}",
                                record_id=record_id or None,
                            )
                        )
    return issues


def has_errors(diagnostics: list[dict[str, Any]]) -> bool:
    return any(scalar(item.get("severity")).lower() == "error" for item in diagnostics)


def relative_target(project_root: Path, target: Path) -> str:
    return target.relative_to(project_root).as_posix()


def not_configured_payload(
    operation: str,
    mode: str,
    project_root: Path,
    target: Path,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "operation": operation,
        "state": "not_configured",
        "mode": mode,
        "project_root": str(project_root),
        "docs": relative_target(project_root, target),
        "records": [],
        "diagnostics": [],
        "next_actions": [
            "Run domain plan with the intended profile.",
            "Create an MDQ-contracted concept document, then run domain verify.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation", choices=("inspect", "get", "search", "plan", "maintain", "verify")
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--docs", default="docs/domain-concepts.md")
    parser.add_argument("--mode", choices=tuple(REQUIRED_FIELDS), default="lite")
    parser.add_argument("--id")
    parser.add_argument("--text")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    if args.operation == "get" and not args.id:
        return failure(args.operation, "get requires --id", code="missing_parameter")
    if args.id and not ID_PATTERN.fullmatch(args.id):
        return failure(
            args.operation,
            "--id must match CONCEPT-[A-Z0-9-]+",
            code="invalid_parameter",
        )
    if args.operation == "search" and not args.text:
        return failure(args.operation, "search requires --text", code="missing_parameter")
    if args.limit < 0:
        return failure(args.operation, "--limit must be zero or greater", code="invalid_parameter")

    try:
        project_root = resolve_project_root(args.root)
        target = resolve_docs(project_root, args.docs)
        sources = markdown_sources(target)
    except (OSError, ValueError) as exc:
        return failure(args.operation, str(exc))

    if not sources:
        payload = not_configured_payload(args.operation, args.mode, project_root, target)
        if args.operation == "maintain":
            payload["state"] = "maintenance_scope_ready"
            payload["ready_to_create"] = True
            payload["source_snapshot"] = None
        elif args.operation == "plan":
            payload["state"] = "plan_ready"
            payload["target_profile"] = args.mode
            payload["profile_requirements"] = list(REQUIRED_FIELDS[args.mode])
            payload["source_snapshot"] = None
        emit(payload)
        return 0

    try:
        skill_root = Path(__file__).resolve().parent.parent
        mdq_script = resolve_mdq_script(skill_root)
        record_id = args.id if args.operation == "get" else None
        text = args.text if args.operation == "search" else None
        returncode, report = run_mdq(
            mdq_script,
            target,
            record_id=record_id,
            text=text,
            limit=args.limit if args.operation == "search" else 0,
        )
        if returncode not in {0, 3}:
            return failure(args.operation, f"mdq failed with exit code {returncode}")
        records = records_from(report)
        diagnostics = mdq_diagnostics(report)
        diagnostics.extend(
            validate_records(
                records,
                args.mode,
                validate_relationships=args.operation not in {"get", "search"},
            )
        )
        snapshot = source_snapshot(project_root, sources)
    except (OSError, ValueError) as exc:
        return failure(args.operation, str(exc))

    states = {
        "inspect": "inspection_completed",
        "get": "lookup_completed",
        "search": "search_completed",
        "plan": "plan_ready",
        "maintain": "maintenance_scope_ready",
        "verify": "verified",
    }
    state = states[args.operation]
    error_state = has_errors(diagnostics) or returncode == 3
    if args.operation == "verify" and error_state:
        state = "verification_incomplete"
    elif args.operation == "maintain" and error_state:
        state = "maintenance_blocked"

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "operation": args.operation,
        "state": state,
        "mode": args.mode,
        "project_root": str(project_root),
        "docs": relative_target(project_root, target),
        "source_snapshot": snapshot,
        "counts": {
            "records": len(records),
            "errors": sum(
                1 for item in diagnostics if scalar(item.get("severity")).lower() == "error"
            ),
            "warnings": sum(
                1 for item in diagnostics if scalar(item.get("severity")).lower() == "warning"
            ),
        },
        "records": records[: args.limit] if args.operation == "inspect" and args.limit else records,
        "diagnostics": diagnostics,
    }
    if args.operation == "inspect" and args.limit:
        payload["truncated"] = len(records) > args.limit
    if args.operation == "plan":
        payload["target_profile"] = args.mode
        payload["profile_requirements"] = list(REQUIRED_FIELDS[args.mode])
    if args.operation == "maintain":
        payload["ready_to_create"] = False
        payload["authorized_scope"] = [relative_target(project_root, path) for path in sources]

    emit(payload)
    if args.operation in {"verify", "maintain"} and error_state:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
