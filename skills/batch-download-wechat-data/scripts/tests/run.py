#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import analyze_history  # noqa: E402
import download_urls  # noqa: E402
import start_metrics_service  # noqa: E402


class DownloaderTests(unittest.TestCase):
    def test_extracts_only_supported_urls_and_deduplicates(self) -> None:
        text = (
            "A https://mp.weixin.qq.com/s/abc。 "
            "A again https://mp.weixin.qq.com/s/abc, "
            "not https://example.com/s/abc"
        )
        self.assertEqual(download_urls.extract_urls_from_text(text), ["https://mp.weixin.qq.com/s/abc"] * 2)
        self.assertEqual(download_urls.read_urls([], [text]), ["https://mp.weixin.qq.com/s/abc"])

    def test_dry_run_reads_json_url_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "urls.json"
            path.write_text(json.dumps(["https://mp.weixin.qq.com/s/one"]), encoding="utf-8")
            self.assertEqual(download_urls.read_urls([str(path)], []), ["https://mp.weixin.qq.com/s/one"])


class HistoryTests(unittest.TestCase):
    def test_count_scopes_and_original_filter(self) -> None:
        records = [
            {
                "url": "https://mp.weixin.qq.com/s/one",
                "msgid": "m1",
                "itemidx": "1",
                "create_time": "1700000000",
                "raw": {"copyright_type": 1, "copyright_stat": 1},
            },
            {
                "url": "https://mp.weixin.qq.com/s/one",
                "msgid": "m1",
                "itemidx": "1",
                "create_time": "1700000000",
                "title": "richer duplicate",
                "raw": {"copyright_type": 1, "copyright_stat": 1},
            },
            {
                "url": "https://mp.weixin.qq.com/s/two",
                "msgid": "m1",
                "itemidx": "2",
                "create_time": "1700000010",
                "raw": {"copyright_type": 0, "copyright_stat": 0},
            },
            {
                "url": "https://mp.weixin.qq.com/s/three",
                "msgid": "m2",
                "itemidx": "1",
                "create_time": "1700000020",
                "raw": {"copyright_type": 1, "copyright_stat": 1},
            },
        ]
        deduped = analyze_history.dedupe_records(records)
        summary = analyze_history.build_summary(records, deduped)
        self.assertEqual(summary["expanded_url_items"], 3)
        self.assertEqual(summary["publish_groups"], 2)
        self.assertEqual(summary["original_articles"], 2)
        self.assertEqual(summary["duplicate_records_removed"], 1)

    def test_main_writes_normalized_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "history.json"
            output = root / "analysis"
            source.write_text(
                json.dumps(
                    [
                        {
                            "url": "https://mp.weixin.qq.com/s/one",
                            "msgid": "m1",
                            "itemidx": 1,
                            "create_time": 1700000000,
                            "raw": {"copyright_type": 1, "copyright_stat": 1},
                        }
                    ]
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                analyze_history.main(
                    ["--history-json", str(source), "--output-dir", str(output)]
                ),
                0,
            )
            self.assertTrue((output / "history.summary.json").exists())
            self.assertTrue((output / "urls.original.txt").exists())


class MetricsTests(unittest.TestCase):
    def test_dry_run_command_is_local(self) -> None:
        command = start_metrics_service.build_command(Path("/tmp/wxdown"), "65000", "65001", False)
        self.assertEqual(command[-4:], ["--port", "65000", "--wport", "65001"])


if __name__ == "__main__":
    unittest.main()
