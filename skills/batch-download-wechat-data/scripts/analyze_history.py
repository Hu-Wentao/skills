#!/usr/bin/env python3
"""Normalize and analyze WeChat Official Account history exports."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


CSV_FIELDS = [
    "row",
    "account_name",
    "account_alias",
    "fakeid",
    "aid",
    "title",
    "url",
    "digest",
    "author",
    "publish_time_iso",
    "update_time_iso",
    "create_time",
    "update_time",
    "msgid",
    "appmsgid",
    "itemidx",
    "comment_id",
    "is_deleted",
    "is_original",
    "copyright_type",
    "copyright_stat",
    "cover_url",
    "_chunk_file",
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def unwrap_records(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("records", "items", "data", "list", "history"):
            nested = payload.get(key)
            if isinstance(nested, list):
                return [dict(item) for item in nested if isinstance(item, dict)]
    raise ValueError("history input must contain a JSON array or a supported record list")


def raw_value(item: Dict[str, Any], key: str) -> Any:
    raw = item.get("raw")
    if isinstance(raw, dict) and key in raw:
        return raw.get(key)
    return item.get(key)


def as_int(value: Any) -> Optional[int]:
    try:
        if value in (None, ""):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def iso_time(value: Any) -> str:
    stamp = as_int(value)
    if stamp is None:
        return ""
    if stamp > 10_000_000_000:
        stamp //= 1000
    try:
        return dt.datetime.fromtimestamp(stamp, tz=dt.timezone.utc).astimezone().isoformat()
    except (OverflowError, OSError, ValueError):
        return ""


def is_original(item: Dict[str, Any]) -> bool:
    if as_bool(item.get("is_original")):
        return True
    return (
        as_int(raw_value(item, "copyright_type")) == 1
        and as_int(raw_value(item, "copyright_stat")) == 1
        and not as_bool(item.get("is_deleted"))
    )


def load_records(history_json: Optional[Path], chunk_dir: Optional[Path]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    if history_json:
        records.extend(unwrap_records(read_json(history_json)))
    if chunk_dir:
        paths = sorted(
            {
                *chunk_dir.glob("history-chunk-*.json"),
                *chunk_dir.glob("*-history-chunk-*.json"),
            }
        )
        for path in paths:
            try:
                chunk = unwrap_records(read_json(path))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            for item in chunk:
                item.setdefault("_chunk_file", path.name)
                records.append(item)
    if not records:
        raise ValueError("no history records found")
    return records


def record_key(item: Dict[str, Any]) -> str:
    for key in ("url", "aid"):
        value = item.get(key)
        if value:
            return f"{key}:{value}"
    return ":".join(
        str(item.get(key) or "") for key in ("appmsgid", "msgid", "itemidx", "title")
    )


def record_richness(item: Dict[str, Any]) -> int:
    return sum(1 for value in item.values() if value not in (None, "", [], {}))


def dedupe_records(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    selected: Dict[str, Dict[str, Any]] = {}
    for item in records:
        key = record_key(item)
        if key not in selected or record_richness(item) > record_richness(selected[key]):
            selected[key] = dict(item)

    deduped = list(selected.values())
    deduped.sort(
        key=lambda item: (
            as_int(item.get("create_time")) or 0,
            as_int(item.get("itemidx")) or 0,
        ),
        reverse=True,
    )
    for index, item in enumerate(deduped, 1):
        item["row"] = index
        item["itemidx"] = as_int(item.get("itemidx")) or item.get("itemidx") or ""
        item["publish_time_iso"] = item.get("publish_time_iso") or iso_time(item.get("create_time"))
        item["update_time_iso"] = item.get("update_time_iso") or iso_time(item.get("update_time"))
        item["is_deleted"] = as_bool(item.get("is_deleted"))
        item["is_original"] = is_original(item)
        item["copyright_type"] = raw_value(item, "copyright_type")
        item["copyright_stat"] = raw_value(item, "copyright_stat")
    return deduped


def write_csv(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def counter_to_dict(counter: Counter) -> Dict[str, int]:
    return {str(key): value for key, value in counter.most_common()}


def build_summary(records: Sequence[Dict[str, Any]], deduped: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    original = [item for item in deduped if item.get("is_original")]
    publish_group_ids = {item.get("msgid") for item in deduped if item.get("msgid") not in (None, "")}
    headline_count = sum(1 for item in deduped if as_int(item.get("itemidx")) == 1)
    publish_groups = len(publish_group_ids) or headline_count
    return {
        "raw_records": len(records),
        "expanded_url_items": len(deduped),
        "unique_urls": len({item.get("url") for item in deduped if item.get("url")}),
        "publish_groups": publish_groups,
        "headline_items": headline_count,
        "original_articles": len(original),
        "not_deleted_items": sum(1 for item in deduped if not item.get("is_deleted")),
        "deleted_items": sum(1 for item in deduped if item.get("is_deleted")),
        "duplicate_records_removed": len(records) - len(deduped),
        "first_publish_time": deduped[-1].get("publish_time_iso") if deduped else "",
        "last_publish_time": deduped[0].get("publish_time_iso") if deduped else "",
        "itemidx_counts": counter_to_dict(Counter(item.get("itemidx") for item in deduped)),
        "copyright_type_counts": counter_to_dict(
            Counter(raw_value(item, "copyright_type") for item in deduped)
        ),
        "copyright_stat_counts": counter_to_dict(
            Counter(raw_value(item, "copyright_stat") for item in deduped)
        ),
        "counting_notes": [
            "expanded_url_items counts every unique article URL after expanding multi-article messages.",
            "publish_groups counts unique msgid values, roughly one WeChat publish/message group.",
            "original_articles uses copyright_type=1, copyright_stat=1, and is_deleted=false.",
        ],
    }


def write_markdown_summary(path: Path, summary: Dict[str, Any]) -> None:
    lines = [
        "# WeChat History Count Summary",
        "",
        f"- Raw records: {summary['raw_records']}",
        f"- Expanded URL items: {summary['expanded_url_items']}",
        f"- Unique URLs: {summary['unique_urls']}",
        f"- Publish groups: {summary['publish_groups']}",
        f"- Headline items: {summary['headline_items']}",
        f"- Original articles: {summary['original_articles']}",
        f"- Deleted items: {summary['deleted_items']}",
        f"- First publish time: {summary['first_publish_time']}",
        f"- Last publish time: {summary['last_publish_time']}",
        "",
        "## Counting Notes",
        "",
        "- `expanded_url_items`: every unique article URL after expanding multi-article messages.",
        "- `publish_groups`: unique `msgid` values, roughly one WeChat publish/message group.",
        "- `original_articles`: `copyright_type=1`, `copyright_stat=1`, and `is_deleted=false`.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze WeChat account history count scopes")
    parser.add_argument("--history-json", help="merged history JSON array or record container")
    parser.add_argument("--chunk-dir", help="directory containing history chunk JSON files")
    parser.add_argument("--output-dir", help="directory for normalized outputs")
    parser.add_argument("--prefix", default="history", help="output file prefix")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.history_json and not args.chunk_dir:
        raise SystemExit("provide --history-json or --chunk-dir")
    history_json = Path(args.history_json).expanduser() if args.history_json else None
    chunk_dir = Path(args.chunk_dir).expanduser() if args.chunk_dir else None
    records = load_records(history_json, chunk_dir)
    deduped = dedupe_records(records)
    original = [item for item in deduped if item.get("is_original")]
    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser()
    elif history_json:
        output_dir = history_json.parent
    else:
        output_dir = chunk_dir or Path.cwd()
    output_dir.mkdir(parents=True, exist_ok=True)

    prefix = args.prefix
    files = {
        "dedup_json": output_dir / f"{prefix}.dedup.json",
        "dedup_csv": output_dir / f"{prefix}.dedup.csv",
        "all_urls": output_dir / "urls.all.txt",
        "original_json": output_dir / f"{prefix}.original.json",
        "original_csv": output_dir / f"{prefix}.original.csv",
        "original_urls": output_dir / "urls.original.txt",
        "summary_json": output_dir / f"{prefix}.summary.json",
        "summary_md": output_dir / f"{prefix}.summary.md",
    }
    files["dedup_json"].write_text(json.dumps(deduped, ensure_ascii=False, indent=2), encoding="utf-8")
    files["original_json"].write_text(json.dumps(original, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(files["dedup_csv"], deduped)
    write_csv(files["original_csv"], original)
    files["all_urls"].write_text(
        "\n".join(str(item.get("url") or "") for item in deduped if item.get("url")) + "\n",
        encoding="utf-8",
    )
    files["original_urls"].write_text(
        "\n".join(str(item.get("url") or "") for item in original if item.get("url")) + "\n",
        encoding="utf-8",
    )
    summary = build_summary(records, deduped)
    summary["files"] = {key: str(path) for key, path in files.items()}
    files["summary_json"].write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown_summary(files["summary_md"], summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
