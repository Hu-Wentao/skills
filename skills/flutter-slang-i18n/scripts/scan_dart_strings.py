#!/usr/bin/env python3
"""Scan Dart files for likely hardcoded Flutter UI strings."""

from __future__ import annotations

import argparse
import bisect
import json
import re
from dataclasses import dataclass
from pathlib import Path


EXCLUDED_DIRS = {
    ".dart_tool",
    ".fvm",
    ".git",
    ".idea",
    "android",
    "build",
    "ios",
    "linux",
    "macos",
    "web",
    "windows",
}

GENERATED_SUFFIXES = (
    ".freezed.dart",
    ".g.dart",
    ".gr.dart",
    ".mocks.dart",
    ".mock.dart",
)

UI_CONTEXT_RE = re.compile(
    r"\b("
    r"Text|SelectableText|TextSpan|RichText|ElevatedButton|TextButton|OutlinedButton|"
    r"FilledButton|CupertinoButton|AppBar|SnackBar|AlertDialog|SimpleDialog|Tooltip|"
    r"Semantics|InputDecoration|BottomNavigationBarItem|NavigationDestination|Tab"
    r")\b|"
    r"\b(label|labelText|hintText|helperText|errorText|tooltip|semanticLabel|"
    r"title|subtitle|message|content|placeholder)\s*:",
    re.MULTILINE,
)

NON_UI_CONTEXT_RE = re.compile(
    r"\b(import|export|part)\s+|"
    r"\b(debugPrint|print|log|logger|trace|analytics|eventName|routeName|"
    r"asset|assets|path|uri|url|endpoint|collection|document|storageKey|"
    r"restorationId|heroTag|debugLabel)\b|"
    r"\b(ValueKey|ObjectKey|UniqueKey|PageStorageKey|Key)\s*\(",
    re.IGNORECASE | re.MULTILINE,
)

HUMAN_TEXT_RE = re.compile(r"[A-Za-z\u00C0-\u024F\u3040-\u30FF\u3400-\u9FFF]")
ONLY_TOKEN_RE = re.compile(r"^[a-z0-9_.:/#?&=%-]+$")
ASSET_OR_URI_RE = re.compile(
    r"^(package:|dart:|file:|https?://|assets?/|images?/|icons?/|lib/|/)"
    r"|(\.(png|jpe?g|svg|gif|json|yaml|yml|dart|arb|db|mp3|mp4|riv|ttf|otf|woff2?))$",
    re.IGNORECASE,
)


@dataclass
class StringLiteral:
    path: Path
    line: int
    column: int
    value: str
    context: str
    confidence: str
    score: int
    reasons: list[str]


def line_starts(text: str) -> list[int]:
    starts = [0]
    for index, char in enumerate(text):
        if char == "\n":
            starts.append(index + 1)
    return starts


def line_col(starts: list[int], index: int) -> tuple[int, int]:
    line_index = bisect.bisect_right(starts, index) - 1
    return line_index + 1, index - starts[line_index] + 1


def iter_dart_files(root: Path, include_tests: bool) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.dart"):
        parts = set(path.relative_to(root).parts)
        if parts & EXCLUDED_DIRS:
            continue
        if not include_tests and "test" in parts:
            continue
        if path.name.endswith(GENERATED_SUFFIXES) or path.name == "translations.g.dart":
            continue
        files.append(path)
    return sorted(files)


def extract_string_literals(text: str, path: Path) -> list[tuple[int, int, int, str]]:
    starts = line_starts(text)
    literals: list[tuple[int, int, int, str]] = []
    i = 0
    length = len(text)
    in_block_comment = False
    in_line_comment = False

    while i < length:
        char = text[i]
        next_char = text[i + 1] if i + 1 < length else ""

        if in_line_comment:
            if char == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue

        if char == "/" and next_char == "/":
            in_line_comment = True
            i += 2
            continue

        if char == "/" and next_char == "*":
            in_block_comment = True
            i += 2
            continue

        raw_prefix = char in {"r", "R"} and next_char in {"'", '"'}
        if char in {"'", '"'} or raw_prefix:
            quote_index = i + 1 if raw_prefix else i
            quote = text[quote_index]
            triple = text[quote_index : quote_index + 3] == quote * 3
            content_start = quote_index + (3 if triple else 1)
            j = content_start

            while j < length:
                if not raw_prefix and text[j] == "\\":
                    j += 2
                    continue
                if triple and text[j : j + 3] == quote * 3:
                    content = text[content_start:j]
                    line, column = line_col(starts, quote_index)
                    literals.append((line, column, quote_index, content))
                    i = j + 3
                    break
                if not triple and text[j] == quote:
                    content = text[content_start:j]
                    line, column = line_col(starts, quote_index)
                    literals.append((line, column, quote_index, content))
                    i = j + 1
                    break
                j += 1
            else:
                i = quote_index + 1
            continue

        i += 1

    return literals


def context_for_line(lines: list[str], line: int, radius: int = 2) -> str:
    start = max(1, line - radius)
    end = min(len(lines), line + radius)
    return "\n".join(lines[start - 1 : end])


def looks_like_interpolation(value: str) -> bool:
    return "$" in value or "{{" in value or "}" in value


def score_literal(value: str, ui_context: str, non_ui_context: str) -> tuple[int, list[str]]:
    stripped = " ".join(value.strip().split())
    reasons: list[str] = []
    score = 0

    if not stripped:
        return -10, ["empty string"]
    if not HUMAN_TEXT_RE.search(stripped):
        return -9, ["no human-language characters"]
    if len(stripped) == 1 and stripped.isascii():
        return -8, ["single ASCII character"]

    score += 1
    reasons.append("contains human-language characters")

    if UI_CONTEXT_RE.search(ui_context):
        score += 4
        reasons.append("near Flutter UI API")

    if NON_UI_CONTEXT_RE.search(non_ui_context):
        score -= 4
        reasons.append("near non-UI API or identifier")

    if ASSET_OR_URI_RE.search(stripped):
        score -= 5
        reasons.append("looks like URI, route, or asset path")

    if ONLY_TOKEN_RE.fullmatch(stripped) and not re.search(r"\s", stripped):
        score -= 2
        reasons.append("looks like machine token")

    if re.search(r"\s", stripped):
        score += 1
        reasons.append("contains spaces")

    if re.search(r"[.!?。！？:：]", stripped):
        score += 1
        reasons.append("contains sentence punctuation")

    if looks_like_interpolation(stripped):
        score += 1
        reasons.append("contains interpolation")

    return score, reasons


def confidence_for_score(score: int) -> str:
    if score >= 5:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def scan(root: Path, include_tests: bool) -> list[StringLiteral]:
    results: list[StringLiteral] = []
    for path in iter_dart_files(root, include_tests):
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        for line, column, start_index, value in extract_string_literals(text, path):
            context = context_for_line(lines, line)
            before = text[max(0, start_index - 120) : start_index]
            after = text[start_index : min(len(text), start_index + len(value) + 120)]
            current_line_start = text.rfind("\n", 0, start_index) + 1
            before_same_line = text[current_line_start:start_index]
            score, reasons = score_literal(value, before + after, before_same_line[-100:])
            confidence = confidence_for_score(score)
            display_value = " ".join(value.strip().split())
            results.append(
                StringLiteral(
                    path=path,
                    line=line,
                    column=column,
                    value=display_value,
                    context=context.strip(),
                    confidence=confidence,
                    score=score,
                    reasons=reasons,
                )
            )
    return results


def min_score(confidence: str) -> int:
    return {"low": -999, "medium": 2, "high": 5}[confidence]


def to_json(result: StringLiteral, root: Path) -> dict[str, object]:
    return {
        "path": str(result.path.relative_to(root)),
        "line": result.line,
        "column": result.column,
        "value": result.value,
        "confidence": result.confidence,
        "score": result.score,
        "reasons": result.reasons,
        "context": result.context,
    }


def print_text(results: list[StringLiteral], root: Path) -> None:
    for result in results:
        rel = result.path.relative_to(root)
        print(
            f"{rel}:{result.line}:{result.column} "
            f"[{result.confidence}, score={result.score}] {result.value!r}"
        )
        print(f"  reasons: {', '.join(result.reasons)}")
        print("  context:")
        for line in result.context.splitlines():
            print(f"    {line.rstrip()}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan Dart files for likely hardcoded Flutter UI strings."
    )
    parser.add_argument("--root", default=".", help="Flutter project root to scan")
    parser.add_argument(
        "--include-tests", action="store_true", help="Include test/ directories"
    )
    parser.add_argument(
        "--min-confidence",
        choices=["low", "medium", "high"],
        default="medium",
        help="Minimum confidence to print",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    threshold = min_score(args.min_confidence)
    results = [item for item in scan(root, args.include_tests) if item.score >= threshold]

    if args.json:
        print(json.dumps([to_json(item, root) for item in results], indent=2))
    else:
        print_text(results, root)
        print(f"Found {len(results)} candidate string(s). Review context before editing.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
