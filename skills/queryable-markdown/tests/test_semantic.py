from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any


SCRIPT = Path(__file__).parents[1] / "scripts" / "mdq-semantic.py"


class FakeOllamaHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        values = payload.get("input", [])
        if isinstance(values, str):
            values = [values]
        embeddings = []
        for value in values:
            text = str(value).casefold()
            embeddings.append(
                [
                    1.0 if "payment" in text or "支付" in text else 0.0,
                    1.0 if "wallet" in text or "钱包" in text else 0.0,
                ]
            )
        if self.path.endswith("/v1/embeddings"):
            body = json.dumps(
                {"data": [{"index": index, "embedding": value} for index, value in enumerate(embeddings)]}
            ).encode("utf-8")
        else:
            body = json.dumps({"embeddings": embeddings}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


class SemanticCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllamaHandler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.temp = tempfile.TemporaryDirectory(prefix="mdq-semantic-")
        self.root = Path(self.temp.name)
        self.docs = self.root / "docs"
        self.docs.mkdir()
        self.write_document(
            "requirements.md",
            """---
mdq:
  profile: project-governance/governed-document-v1
---

# Requirements

## REQ-001 — Payment integration

状态: Open

Payment settlement must be verified.

## REQ-002 — Wallet login

状态: Draft

Wallet login is deferred.
""",
        )
        self.write_document(
            "architecture.md",
            """---
mdq:
  profile: project-governance/governed-document-v1
---

# Architecture

## ARC-001 — Service boundary

状态: Frozen

The service boundary is stable.
""",
        )
        config = self.root / ".mdq" / "semantic" / "config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text(
            f"""schema: mdq.semantic.config.v1
backend: ollama
model: fake-v1
base_url: http://127.0.0.1:{self.server.server_port}
api_key_env: null
index: .mdq/semantic/index.sqlite3
""",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temp.cleanup()

    def write_document(self, name: str, content: str) -> None:
        (self.docs / name).write_text(content, encoding="utf-8")

    def run_cli(self, *args: str, expected: int = 0) -> dict[str, Any]:
        result = subprocess.run(
            ["uv", "run", str(SCRIPT), *args, "--project-root", str(self.root), "--output", "json"],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
            timeout=45,
        )
        self.assertEqual(result.returncode, expected, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def test_index_query_and_filter_are_semantic_but_return_mdq_sources(self) -> None:
        indexed = self.run_cli("index", "docs")
        self.assertEqual(indexed["status"], "indexed")
        self.assertEqual(indexed["indexed_sources"], 2)
        self.assertGreaterEqual(indexed["indexed_chunks"], 3)

        result = self.run_cli(
            "query",
            "docs",
            "--text",
            "payment settlement",
            "--where",
            "status=Open",
            "--top-k",
            "1",
        )
        self.assertEqual(result["schema"], "mdq.semantic.query.v1")
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["count"], 1)
        record = result["records"][0]
        self.assertEqual(record["key"], "REQ-001")
        self.assertEqual(record["title"], "Payment integration")
        self.assertEqual(record["relative_path"], "docs/requirements.md")
        self.assertEqual(record["line_start"], 8)
        self.assertIn("Payment settlement", record["snippet"])
        self.assertEqual(record["profile_source"], "shared-profile:project-governance/governed-document-v1")

        status = self.run_cli("status")
        self.assertEqual(status["status"], "ready")

    def test_omlx_uses_the_openai_compatible_embedding_transport(self) -> None:
        config = self.root / ".mdq" / "semantic" / "config.yaml"
        config.write_text(
            f"""schema: mdq.semantic.config.v1
backend: omlx
model: fake-v1
base_url: http://127.0.0.1:{self.server.server_port}/v1
api_key_env: null
index: .mdq/semantic/index.sqlite3
""",
            encoding="utf-8",
        )
        indexed = self.run_cli("index", "docs", "--rebuild")
        self.assertEqual(indexed["status"], "indexed")
        result = self.run_cli("query", "docs", "--text", "payment", "--top-k", "1")
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["records"][0]["key"], "REQ-001")

    def test_query_glob_limits_semantic_results_to_the_requested_scope(self) -> None:
        self.run_cli("index", "docs")
        result = self.run_cli(
            "query",
            "docs",
            "--glob",
            "**/requirements.md",
            "--text",
            "wallet",
            "--top-k",
            "10",
        )
        self.assertEqual(result["status"], "matched")
        self.assertTrue(result["records"])
        self.assertTrue(
            all(item["relative_path"] == "docs/requirements.md" for item in result["records"])
        )

    def test_reindex_prunes_deleted_sources_and_status_detects_new_sources(self) -> None:
        self.run_cli("index", "docs")
        (self.docs / "architecture.md").unlink()
        indexed = self.run_cli("index", "docs")
        self.assertEqual(indexed["indexed_sources"], 1)
        self.assertEqual(self.run_cli("status", "docs")["status"], "ready")

        self.write_document(
            "new.md",
            """---
mdq:
  profile: project-governance/governed-document-v1
---

# New

## NEW-001 — New record

状态: Open

Payment-related new record.
""",
        )
        stale = self.run_cli("status", "docs")
        self.assertEqual(stale["status"], "stale")
        self.assertIn(
            "semantic_index_incomplete",
            {item["code"] for item in stale["diagnostics"]},
        )

    def test_project_config_cannot_enable_remote_api_backend(self) -> None:
        result = self.run_cli(
            "configure",
            "--backend",
            "api",
            "--model",
            "text-embedding-test",
            "--base-url",
            "https://example.test/v1",
            "--api-key-env",
            "OPENAI_API_KEY",
            expected=3,
        )
        self.assertEqual(result["status"], "invalid")
        self.assertIn("semantic_cli_error", {item["code"] for item in result["diagnostics"]})

    def test_explicit_symlink_target_is_rejected(self) -> None:
        link = self.root / "linked.md"
        link.symlink_to(self.docs / "requirements.md")
        result = self.run_cli("index", "linked.md", expected=3)
        self.assertEqual(result["status"], "invalid")
        self.assertIn("semantic_path_unsafe", {item["code"] for item in result["diagnostics"]})

    def test_query_fails_closed_when_source_changes_after_indexing(self) -> None:
        self.run_cli("index", "docs")
        path = self.docs / "requirements.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nChanged after indexing.\n", encoding="utf-8")
        result = self.run_cli("query", "docs", "--text", "payment", expected=3)
        self.assertEqual(result["status"], "stale")
        self.assertIn("semantic_index_stale", {item["code"] for item in result["diagnostics"]})

    def test_status_reports_unconfigured_project(self) -> None:
        unconfigured = self.root / "unconfigured"
        unconfigured.mkdir()
        result = subprocess.run(
            ["uv", "run", str(SCRIPT), "status", "--project-root", str(unconfigured), "--output", "json"],
            cwd=unconfigured,
            capture_output=True,
            text=True,
            check=False,
            timeout=45,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "unconfigured")
        self.assertIn(
            "semantic_backend_unconfigured",
            {item["code"] for item in payload["diagnostics"]},
        )
