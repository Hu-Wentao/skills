#!/usr/bin/env python3
"""Inspect, plan, preflight, and verify project documentation maintenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


SCHEMA = "project-governance.document-maintenance.v1"
AUDIT_SCHEMA = "project-governance.document-audit.v1"
EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    ".next",
    ".nuxt",
    ".output",
    ".turbo",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "vendor",
}
GOVERNED_PATTERNS = (
    "requirements.md",
    "requirements/**/*.md",
    "baseline/**/*.md",
    "plans/**/*.md",
    "evaluations/**/*.md",
    "defects/**/*.md",
    "archive/**/*.md",
    "*coverage*.md",
    "*verification*.md",
    "*traceability*.md",
)
LIFECYCLE_TARGETS = (
    "requirements.md",
    "plans",
    "evaluations",
    "defects",
    "archive",
)


class MaintenanceError(ValueError):
    """Raised when maintenance cannot safely inspect the selected project."""


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def canonical_root(value: str) -> Path:
    root = Path(value).resolve()
    if not root.is_dir():
        raise MaintenanceError(f"project root is not a directory: {root}")
    return root


def resolve_docs(root: Path, value: str) -> Path:
    raw = Path(value)
    docs = raw.resolve() if raw.is_absolute() else (root / raw).resolve()
    if not is_relative_to(docs, root):
        raise MaintenanceError("documentation root must stay inside the project root")
    return docs


def resolve_mdq_script(skill_root: Path) -> Path | None:
    user_root = Path.home()
    candidates = (
        skill_root.parent / "queryable-markdown" / "scripts" / "mdq.py",
        user_root / ".codex" / "skills" / "queryable-markdown" / "scripts" / "mdq.py",
        user_root / ".agents" / "skills" / "queryable-markdown" / "scripts" / "mdq.py",
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def markdown_inventory(root: Path, scope: str, docs: Path) -> list[Path]:
    selected_root = docs if scope == "governed" else root
    if not selected_root.is_dir():
        return []
    inventory: list[Path] = []
    for current, directory_names, file_names in os.walk(selected_root):
        current_path = Path(current)
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name not in EXCLUDED_DIRECTORY_NAMES
            and not (current_path / name).is_symlink()
            and not (
                name == ".cache"
                and current_path.name == ".agents"
            )
        )
        for name in sorted(file_names):
            path = current_path / name
            if name.endswith(".md") and path.is_file() and not path.is_symlink():
                inventory.append(path.resolve())
    return sorted(inventory)


def governed_files(docs: Path) -> list[Path]:
    if not docs.is_dir():
        return []
    selected: set[Path] = set()
    for pattern in GOVERNED_PATTERNS:
        selected.update(path.resolve() for path in docs.glob(pattern) if path.is_file())
    return sorted(selected)


def relative_path(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root).as_posix()


def source_snapshot(paths: list[Path], root: Path) -> tuple[str, list[dict[str, str]]]:
    entries: list[dict[str, str]] = []
    digest = hashlib.sha256()
    for path in paths:
        content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        relative = relative_path(path, root)
        entries.append({"path": relative, "sha256": content_hash})
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content_hash.encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest(), entries


def run_json(command: list[str], cwd: Path, accepted_codes: set[int]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode not in accepted_codes:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise MaintenanceError(
            f"command failed with exit {completed.returncode}: {' '.join(command)}"
            + (f"; {detail}" if detail else "")
        )
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise MaintenanceError(
            f"command returned invalid JSON: {exc}" + (f"; {detail}" if detail else "")
        ) from exc
    if not isinstance(value, dict):
        raise MaintenanceError("command JSON output must be an object")
    return value


def run_audit(root: Path, docs: Path, skill_root: Path, mdq_script: Path) -> dict[str, Any]:
    validator = skill_root / "scripts" / "validate-governance.mjs"
    report = run_json(
        [
            "node",
            str(validator),
            "--root",
            str(root),
            "--docs",
            str(docs),
            "--mdq-script",
            str(mdq_script),
            "--json",
        ],
        root,
        {0, 1},
    )
    if report.get("schema") != AUDIT_SCHEMA:
        raise MaintenanceError("document audit returned an unsupported schema")
    return report


def lifecycle_state(
    root: Path, docs: Path, mdq_script: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for relative_target in LIFECYCLE_TARGETS:
        target = docs / relative_target
        if not target.exists():
            continue
        report = run_json(
            [
                "uv",
                "run",
                str(mdq_script),
                "scan",
                str(target),
                "--glob",
                "**/*.md",
                "--field",
                "status",
                "--require-contract",
            ],
            root,
            {0, 3},
        )
        for record in report.get("records", []):
            if not isinstance(record, dict):
                continue
            document = Path(str(record.get("document", ""))).resolve()
            if document.name == "README.md" or not is_relative_to(document, root):
                continue
            records.append(
                {
                    "id": record.get("key"),
                    "path": relative_path(document, root),
                    "status": (record.get("fields") or {}).get("status"),
                    "line": record.get("line_start"),
                }
            )
        for diagnostic in report.get("diagnostics", []):
            if not isinstance(diagnostic, dict):
                continue
            document_value = diagnostic.get("document")
            if not document_value:
                continue
            document = Path(str(document_value)).resolve()
            if document.name == "README.md" or not is_relative_to(document, root):
                continue
            if diagnostic.get("severity") != "error":
                continue
            diagnostics.append(
                {
                    "level": "error",
                    "file": relative_path(document, root),
                    "line": diagnostic.get("line"),
                    "message": f"[{diagnostic.get('code')}] {diagnostic.get('message')}",
                }
            )
    records.sort(key=lambda item: (str(item["path"]), str(item.get("id"))))
    diagnostics.sort(
        key=lambda item: (str(item["file"]), int(item.get("line") or 0), str(item["message"]))
    )
    return records, diagnostics


def classify_issue(issue: dict[str, Any]) -> str:
    message = str(issue.get("message", "")).lower()
    path = str(issue.get("file", "")).lower()
    if any(
        token in message
        for token in (
            "persistent_contract_required",
            "profile_",
            "mdq",
            "unknown_field",
            "duplicate_key",
            "field_conflict",
            "missing_key",
        )
    ):
        return "contracts"
    if "defect" in message or "/defects/" in f"/{path}":
        return "defects"
    if "requirement" in message or "verification" in message or "traceability" in path:
        return "traceability"
    if "broken local link" in message:
        return "references"
    if "plan" in message or "status" in message or "lifecycle" in message:
        return "lifecycle"
    return "structure"


def merge_issues(
    audit: dict[str, Any], lifecycle_diagnostics: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, int, str], dict[str, Any]] = {}
    for raw in [*audit.get("issues", []), *lifecycle_diagnostics]:
        if not isinstance(raw, dict):
            continue
        item = {
            "level": str(raw.get("level", "error")),
            "file": str(raw.get("file", ".")),
            "line": raw.get("line"),
            "message": str(raw.get("message", "")),
        }
        item["class"] = classify_issue(item)
        key = (item["file"], int(item["line"] or 0), item["message"])
        merged[key] = item
    return sorted(
        merged.values(),
        key=lambda item: (
            item["file"],
            int(item["line"] or 0),
            item["message"],
        ),
    )


def select_issues(
    issues: list[dict[str, Any]], kind: str, limit: int
) -> list[dict[str, Any]]:
    selected = issues if kind == "all" else [item for item in issues if item["class"] == kind]
    return selected if limit == 0 else selected[:limit]


def batches(issues: list[dict[str, Any]], size: int = 20) -> list[dict[str, Any]]:
    by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for issue in issues:
        by_file[issue["file"]].append(issue)
    files = sorted(by_file)
    result: list[dict[str, Any]] = []
    for offset in range(0, len(files), size):
        selected_files = files[offset : offset + size]
        result.append(
            {
                "batch": len(result) + 1,
                "files": selected_files,
                "issue_count": sum(len(by_file[path]) for path in selected_files),
            }
        )
    return result


def build_report(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    root = canonical_root(args.root)
    docs = resolve_docs(root, args.docs)
    skill_root = Path(__file__).resolve().parents[1]
    mdq_script = resolve_mdq_script(skill_root)
    if mdq_script is None:
        raise MaintenanceError("queryable-markdown mdq.py is required")

    inventory = markdown_inventory(root, args.scope, docs)
    governed = governed_files(docs)
    snapshot_id, snapshot_entries = source_snapshot(inventory, root)
    audit = run_audit(root, docs, skill_root, mdq_script)
    lifecycle_records, lifecycle_diagnostics = lifecycle_state(root, docs, mdq_script)
    issues = merge_issues(audit, lifecycle_diagnostics)
    selected = select_issues(issues, args.kind, args.limit)
    errors = sum(item["level"] == "error" for item in issues)
    warnings = sum(item["level"] == "warning" for item in issues)

    phase_state = {
        "inspect": "inspection_completed",
        "plan": "maintenance_planned",
        "maintain": "maintenance_scope_ready",
        "verify": "maintenance_verified" if errors == 0 else "maintenance_incomplete",
    }[args.operation]
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "ready" if args.operation != "verify" or errors == 0 else "failed",
        "state": phase_state,
        "operation": args.operation,
        "root": str(root),
        "docs": relative_path(docs, root) if docs != root else ".",
        "scope": args.scope,
        "kind": args.kind,
        "snapshot_id": snapshot_id,
        "counts": {
            "inventory_files": len(inventory),
            "governed_files": len(governed),
            "lifecycle_records": len(lifecycle_records),
            "errors": errors,
            "warnings": warnings,
            "selected_issues": len(selected),
        },
        "issues": selected,
        "lifecycle_records": lifecycle_records,
        "semantic_decisions": [
            "requirement_status",
            "plan_completion",
            "baseline_extraction",
            "supersession_or_archive",
            "ambiguous_identity_or_authority",
        ],
    }
    if args.operation in {"plan", "maintain"}:
        report["batches"] = batches(selected)
        report["source_snapshot"] = snapshot_entries
        report["next_action"] = (
            "apply authorized scoped edits with queryable-markdown, then verify"
            if args.operation == "maintain"
            else "review semantic decisions and authorize the selected maintenance scope"
        )
    elif args.operation == "inspect":
        report["next_action"] = "create a maintenance plan or report no drift"
    else:
        report["next_action"] = (
            "complete"
            if errors == 0
            else "continue authorized repairs or request semantic decisions"
        )
    return report, 1 if args.operation == "verify" and errors else 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Maintain project Markdown inventory and governed-document lifecycle."
    )
    parser.add_argument("operation", choices=("inspect", "plan", "maintain", "verify"))
    parser.add_argument("--root", default=str(Path.cwd()))
    parser.add_argument("--docs", default="docs")
    parser.add_argument("--scope", choices=("governed", "all-markdown"), default="governed")
    parser.add_argument(
        "--kind",
        choices=("all", "contracts", "lifecycle", "references", "traceability", "defects", "structure"),
        default="all",
    )
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)
    if args.limit < 0:
        parser.error("--limit must be zero or greater")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        report, exit_code = build_report(args)
    except MaintenanceError as exc:
        print(
            json.dumps(
                {
                    "schema": SCHEMA,
                    "status": "failed",
                    "state": "maintenance_failed",
                    "operation": args.operation,
                    "error": str(exc),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
