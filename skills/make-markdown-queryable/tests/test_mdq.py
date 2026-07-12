from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "mdq.py"


def profile(*, fields: str = "", index: bool = False) -> str:
    index_line = "index: .mdq/index.json\n" if index else ""
    return f"""<!-- mdq
version: 1
records:
  boundary:
    source: heading
    levels: [2]
    level_tolerance: 1
  key:
    source: heading
    pattern: '^(?P<id>REQ-[0-9]+)(?:[ ：:-]+(?P<title>.*))?$'
    group: id
fields:
{fields or "  title:\n    source: heading\n    group: title"}
tolerance:
  incomplete: true
{index_line}-->
"""


class MdqCliTests(unittest.TestCase):
    def run_cli(self, root: Path, *args: str, expected: int = 0) -> dict:
        completed = subprocess.run(
            ["uv", "run", str(SCRIPT), *args],
            cwd=root,
            check=False,
            text=True,
            capture_output=True,
            timeout=15,
        )
        self.assertEqual(
            completed.returncode, expected, completed.stderr + completed.stdout
        )
        return json.loads(completed.stdout)

    def document(self, root: Path, content: str) -> Path:
        path = root / "requirements.md"
        path.write_text(content, encoding="utf-8")
        return path

    def test_exact_lookup_ignores_prose_and_code_headings(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = self.document(
                root,
                profile()
                + """
## REQ-1: Login

The detail refers to REQ-2.

```md
## REQ-999: Fake
```

## REQ-2: Reset
""",
            )
            exact = self.run_cli(root, "query", str(path), "--id", "REQ-1")
            prose = self.run_cli(root, "query", str(path), "--id", "REQ-999")
            self.assertEqual(exact["status"], "matched")
            self.assertEqual(exact["count"], 1)
            self.assertEqual(prose["status"], "not_found")

    def test_commented_out_heading_is_not_a_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = self.document(
                root,
                profile()
                + """
<!--
## REQ-5: Removed requirement
-->

## REQ-1: Active
""",
            )
            removed = self.run_cli(root, "query", str(path), "--id", "REQ-5")
            self.assertEqual(removed["status"], "not_found")

    def test_inline_comment_preserves_heading_and_label(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fields = "  status:\n    source: label\n    labels: [状态]"
            path = self.document(
                root,
                profile(fields=fields)
                + "\n## REQ-1: Annotated <!-- pending -->\n\n- 状态：draft <!-- note -->\n",
            )
            result = self.run_cli(root, "query", str(path), "--id", "REQ-1")
            self.assertEqual(result["status"], "matched")
            self.assertEqual(result["records"][0]["fields"]["status"], "draft")

    def test_profile_and_marker_inside_fence_are_inert(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fenced_profile = self.document(
                root, "```md\n" + profile() + "```\n\n## REQ-1: No active profile\n"
            )
            missing = self.run_cli(
                root, "query", str(fenced_profile), "--id", "REQ-1", expected=3
            )
            self.assertIn(
                "profile_missing", {item["code"] for item in missing["diagnostics"]}
            )

            active = profile(fields="  body:\n    source: body")
            fenced_marker = self.document(
                root,
                active + '\n```md\n<!-- mdq:record id="REQ-FAKE" -->\nFake\n```\n',
            )
            fake = self.run_cli(root, "query", str(fenced_marker), "--id", "REQ-FAKE")
            self.assertEqual(fake["status"], "not_found")

    def test_unclosed_comment_and_opaque_openers_inside_fence_do_not_leak(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for opener in (
                "<!-- unclosed example",
                "<pre>",
                "<Component>",
                "{{< highlight markdown >}}",
            ):
                path = self.document(
                    root,
                    profile()
                    + f"\n```html\n{opener}\n```\n\n## REQ-1: Real after example\n",
                )
                result = self.run_cli(root, "query", str(path), "--id", "REQ-1")
                self.assertEqual(result["status"], "matched", opener)

    def test_comment_syntax_inside_indented_and_inline_code_is_inert(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for example in (
                "    <!-- unclosed code example",
                "Use `<!--` to show a comment opener.",
                "Use ``<!--`` with a longer code span.",
            ):
                path = self.document(
                    root, profile() + f"\n{example}\n\n## REQ-1: Real after code\n"
                )
                result = self.run_cli(root, "query", str(path), "--id", "REQ-1")
                self.assertEqual(result["status"], "matched", example)

    def test_comment_syntax_inside_multiline_code_span_is_inert(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = self.document(
                root,
                profile()
                + "\nUse `<!--\nas literal code` here.\n\n## REQ-1: Real after span\n",
            )
            result = self.run_cli(root, "query", str(path), "--id", "REQ-1")
            self.assertEqual(result["status"], "matched")

    def test_comment_syntax_inside_container_fences_is_inert(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            examples = (
                "> ```md\n> <!-- unclosed\n> ```",
                "- ```md\n  <!-- unclosed\n  ```",
            )
            for example in examples:
                path = self.document(
                    root, profile() + f"\n{example}\n\n## REQ-1: Real after fence\n"
                )
                result = self.run_cli(root, "query", str(path), "--id", "REQ-1")
                self.assertEqual(result["status"], "matched", example)

    def test_opaque_code_containers_are_inert(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            content = (
                profile()
                + """
<pre>
## REQ-999: HTML fake
</pre>

<CodeBlock>
## REQ-999: MDX fake
</CodeBlock>

{{< highlight markdown >}}
## REQ-999: Hugo fake
{{< /highlight >}}

## REQ-1: Real
"""
            )
            path = self.document(root, content)
            fake = self.run_cli(root, "query", str(path), "--id", "REQ-999")
            real = self.run_cli(root, "query", str(path), "--id", "REQ-1")
            self.assertEqual(fake["status"], "not_found")
            self.assertEqual(real["status"], "matched")

    def test_unclosed_comment_inside_opaque_block_does_not_leak(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            blocks = (
                "<pre>\n<!-- unclosed sample\n</pre>",
                "<CodeBlock>\n<!-- unclosed sample\n</CodeBlock>",
                "{{< highlight markdown >}}\n<!-- unclosed sample\n{{< /highlight >}}",
            )
            for block in blocks:
                path = self.document(
                    root, profile() + f"\n{block}\n\n## REQ-1: Real after opaque\n"
                )
                result = self.run_cli(root, "query", str(path), "--id", "REQ-1")
                self.assertEqual(result["status"], "matched", block)

    def test_opaque_closer_inside_fence_is_literal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            content = (
                profile()
                + """
<Panel>
```md
</Panel>
```
## REQ-999: Still inside component
</Panel>

## REQ-1: Real outside component
"""
            )
            path = self.document(root, content)
            fake = self.run_cli(root, "query", str(path), "--id", "REQ-999")
            real = self.run_cli(root, "query", str(path), "--id", "REQ-1")
            self.assertEqual(fake["status"], "not_found")
            self.assertEqual(real["status"], "matched")

    def test_duplicate_key_is_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = self.document(root, profile() + "\n## REQ-1: A\n\n## REQ-1: B\n")
            result = self.run_cli(root, "query", str(path), "--id", "REQ-1")
            self.assertEqual(result["status"], "ambiguous")
            self.assertEqual(result["count"], 2)
            self.assertIn(
                "duplicate_key", {item["code"] for item in result["diagnostics"]}
            )

    def test_marker_recovers_deleted_heading(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = self.document(
                root,
                profile(fields="  body:\n    source: body")
                + '\n<!-- mdq:record id="REQ-7" -->\nHeading was deleted.\n',
            )
            result = self.run_cli(root, "query", str(path), "--id", "REQ-7")
            self.assertEqual(result["status"], "matched")
            self.assertEqual(result["records"][0]["confidence"], 0.8)

    def test_label_key_recovers_heading_level_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            content = """<!-- mdq
version: 1
records:
  boundary:
    source: heading
    levels: [2]
    level_tolerance: 1
  key:
    source: label
    labels: [ID, 编号]
    pattern: '^(?P<id>REQ-[0-9]+)$'
    group: id
fields:
  title:
    source: heading
tolerance:
  incomplete: true
-->

### Login heading drifted one level

- ID: REQ-4
"""
            path = self.document(root, content)
            result = self.run_cli(root, "query", str(path), "--id", "REQ-4")
            self.assertEqual(result["status"], "matched")
            self.assertEqual(result["records"][0]["confidence"], 0.8)
            self.assertIn(
                "heading_level_drift", {item["code"] for item in result["diagnostics"]}
            )

    def test_conflicting_label_keys_are_candidates_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            content = """<!-- mdq
version: 1
records:
  boundary: {source: heading, levels: [2]}
  key:
    source: label
    labels: [ID]
    pattern: '^(REQ-[0-9]+)$'
fields: {}
tolerance: {incomplete: true}
-->

## Conflicting identity

- ID: REQ-4
- ID: REQ-5
"""
            path = self.document(root, content)
            result = self.run_cli(root, "query", str(path), "--id", "REQ-4")
            self.assertEqual(result["status"], "not_found")
            self.assertEqual(result["count"], 0)
            self.assertEqual(len(result["candidates"]), 1)
            self.assertIn(
                "key_conflict", {item["code"] for item in result["diagnostics"]}
            )

    def test_marker_conflict_is_candidate_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = self.document(
                root,
                profile() + '\n<!-- mdq:record id="REQ-7" -->\n## REQ-8: Conflicting\n',
            )
            result = self.run_cli(root, "query", str(path), "--id", "REQ-7")
            self.assertEqual(result["status"], "not_found")
            self.assertEqual(result["count"], 0)
            self.assertEqual(len(result["candidates"]), 1)
            self.assertIn(
                "marker_conflict", {item["code"] for item in result["diagnostics"]}
            )

    def test_conflicting_scalar_field_resolves_to_null(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fields = "  status:\n    source: label\n    labels: [状态]"
            path = self.document(
                root,
                profile(fields=fields)
                + "\n## REQ-1: Conflict\n\n- 状态：draft\n- 状态：done\n",
            )
            result = self.run_cli(root, "query", str(path), "--id", "REQ-1")
            self.assertIsNone(result["records"][0]["fields"]["status"])
            self.assertIn(
                "field_conflict", {item["code"] for item in result["diagnostics"]}
            )

    def test_two_profiles_are_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            frontmatter = """---
mdq:
  version: 1
  records:
    boundary: {source: heading, levels: [2]}
    key: {source: heading}
---
"""
            path = self.document(root, frontmatter + profile() + "\n## REQ-1: A\n")
            result = self.run_cli(root, "query", str(path), "--id", "REQ-1", expected=3)
            self.assertEqual(result["status"], "invalid")
            self.assertIn(
                "profile_conflict", {item["code"] for item in result["diagnostics"]}
            )

    def test_missing_capture_group_is_profile_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            content = profile().replace("(?P<id>REQ-[0-9]+)", "(REQ-[0-9]+)")
            path = self.document(root, content + "\n## REQ-1: A\n")
            result = self.run_cli(root, "validate", str(path), expected=3)
            self.assertEqual(result["status"], "invalid")
            self.assertIn(
                "profile_invalid", {item["code"] for item in result["diagnostics"]}
            )

    def test_malformed_frontmatter_returns_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = self.document(root, "---\n? [a, b]\n: 1\n---\n\n# Notes\n")
            result = self.run_cli(root, "inspect", str(path))
            self.assertIn(
                "frontmatter_invalid", {item["code"] for item in result["diagnostics"]}
            )

    def test_comment_profile_after_json_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            json_frontmatter = json.dumps({"title": "Requirements"}, indent=2) + "\n"
            path = self.document(
                root, json_frontmatter + profile() + "\n## REQ-1: JSON frontmatter\n"
            )
            result = self.run_cli(root, "query", str(path), "--id", "REQ-1")
            self.assertEqual(result["status"], "matched")

    def test_yaml_aliases_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            content = profile().replace(
                "version: 1", "version: 1\nx-base: &base [one, two]\nx-copy: *base"
            )
            path = self.document(root, content + "\n## REQ-1: Alias\n")
            result = self.run_cli(root, "validate", str(path), expected=3)
            self.assertEqual(result["status"], "invalid")
            self.assertIn(
                "profile_invalid", {item["code"] for item in result["diagnostics"]}
            )

    def test_stale_index_falls_back_to_current_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fields = "  status:\n    source: label\n    labels: [状态]"
            path = self.document(
                root,
                profile(fields=fields, index=True)
                + "\n## REQ-1: Indexed\n\n- 状态：old\n",
            )
            self.run_cli(root, "index", str(path))
            path.write_text(
                path.read_text(encoding="utf-8").replace("状态：old", "状态：new"),
                encoding="utf-8",
            )
            result = self.run_cli(root, "query", str(path), "--id", "REQ-1")
            self.assertEqual(result["records"][0]["fields"]["status"], "new")
            self.assertIn(
                "index_stale", {item["code"] for item in result["diagnostics"]}
            )

    def test_index_cannot_overwrite_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            content = profile(index=True).replace(
                "index: .mdq/index.json", "index: requirements.md"
            )
            path = self.document(root, content + "\n## REQ-1: Safe\n")
            before = path.read_bytes()
            result = self.run_cli(root, "index", str(path), expected=4)
            self.assertEqual(result["status"], "invalid")
            self.assertEqual(path.read_bytes(), before)
            self.assertIn(
                "index_unsafe", {item["code"] for item in result["diagnostics"]}
            )

    def test_unsafe_index_invalidates_validation_and_query(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            content = profile(index=True).replace(
                "index: .mdq/index.json", "index: ../outside.json"
            )
            path = self.document(root, content + "\n## REQ-1: Safe\n")
            validated = self.run_cli(root, "validate", str(path), expected=3)
            queried = self.run_cli(
                root, "query", str(path), "--id", "REQ-1", expected=3
            )
            self.assertEqual(validated["status"], "invalid")
            self.assertEqual(queried["status"], "invalid")
            self.assertFalse((root.parent / "outside.json").exists())

    def test_corrupt_matching_index_falls_back_to_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = self.document(root, profile(index=True) + "\n## REQ-1: Current\n")
            indexed = self.run_cli(root, "index", str(path))
            sidecar = Path(indexed["index"])
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            payload["records"] = [None]
            sidecar.write_text(json.dumps(payload), encoding="utf-8")
            result = self.run_cli(root, "query", str(path), "--id", "REQ-1")
            self.assertEqual(result["status"], "matched")
            self.assertEqual(result["records"][0]["fields"]["title"], "Current")
            self.assertIn(
                "index_invalid", {item["code"] for item in result["diagnostics"]}
            )

    def test_profile_regex_timeout_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            content = (
                """<!-- mdq
version: 1
records:
  boundary: {source: heading, levels: [2]}
  key:
    source: heading
    pattern: '^(a|aa)+$'
fields: {}
tolerance: {incomplete: true}
-->

## """
                + ("a" * 4000)
                + "!\n"
            )
            path = self.document(root, content)
            result = self.run_cli(root, "validate", str(path), expected=3)
            self.assertIn(
                "regex_timeout", {item["code"] for item in result["diagnostics"]}
            )

    def test_unclosed_fence_blocks_structured_heading(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = self.document(root, profile() + "\n```md\n## REQ-9: Not a record\n")
            result = self.run_cli(root, "query", str(path), "--id", "REQ-9")
            self.assertEqual(result["status"], "not_found")
            self.assertIn(
                "unclosed_fence", {item["code"] for item in result["diagnostics"]}
            )


if __name__ == "__main__":
    unittest.main()
