from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "collect_git_work.py"
SPEC = importlib.util.spec_from_file_location("collect_git_work", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return result.stdout.strip()


def init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q")
    git(path, "config", "user.name", "Alice Example")
    git(path, "config", "user.email", "alice@example.test")


def commit(
    repo: Path,
    filename: str,
    content: str,
    message: str,
    author_name: str,
    author_email: str,
    date: str,
) -> str:
    target = repo / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    git(repo, "add", filename)
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": author_name,
            "GIT_AUTHOR_EMAIL": author_email,
            "GIT_AUTHOR_DATE": date,
            "GIT_COMMITTER_NAME": author_name,
            "GIT_COMMITTER_EMAIL": author_email,
            "GIT_COMMITTER_DATE": date,
        }
    )
    git(repo, "commit", "-q", "-m", message, env=env)
    return git(repo, "rev-parse", "HEAD")


class CollectGitWorkTests(unittest.TestCase):
    def test_defaults_to_configured_user_and_last_seven_days(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            init_repo(repo)
            commit(
                repo,
                "src/app.txt",
                "first\nsecond\n",
                "feat: add report source",
                "Alice Example",
                "alice@example.test",
                "2026-08-03T10:00:00+08:00",
            )

            now = datetime.fromisoformat("2026-08-04T12:00:00+08:00")
            report = MODULE.collect_report(repo, now=now)

            self.assertEqual(report["query"]["author"], "alice@example.test")
            self.assertEqual(report["query"]["authorSource"], "git_config_user_email")
            self.assertEqual(report["summary"]["commitCount"], 1)
            self.assertEqual(report["summary"]["filesChanged"], 1)
            self.assertEqual(report["summary"]["insertions"], 2)
            self.assertEqual(report["commits"][0]["subject"], "feat: add report source")

    def test_supports_author_and_time_range(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            init_repo(repo)
            commit(
                repo,
                "alice.txt",
                "alice\n",
                "feat: alice work",
                "Alice Example",
                "alice@example.test",
                "2026-07-20T10:00:00+08:00",
            )
            expected_hash = commit(
                repo,
                "bob.txt",
                "bob\n",
                "fix: bob work",
                "Bob Example",
                "bob@example.test",
                "2026-08-02T10:00:00+08:00",
            )
            commit(
                repo,
                "late.txt",
                "late\n",
                "docs: outside range",
                "Bob Example",
                "bob@example.test",
                "2026-08-05T10:00:00+08:00",
            )

            report = MODULE.collect_report(
                repo,
                author="bob@example.test",
                since="2026-08-01T00:00:00+08:00",
                until="2026-08-04T23:59:59+08:00",
            )

            self.assertEqual(report["query"]["authorSource"], "argument")
            self.assertEqual(report["summary"]["commitCount"], 1)
            self.assertEqual(report["commits"][0]["hash"], expected_hash)

    def test_returns_empty_evidence_for_no_matching_commits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            init_repo(repo)
            commit(
                repo,
                "work.txt",
                "work\n",
                "feat: completed work",
                "Alice Example",
                "alice@example.test",
                "2026-08-02T10:00:00+08:00",
            )

            report = MODULE.collect_report(
                repo,
                author="nobody@example.test",
                since="2026-08-01",
                until="2026-08-04",
            )

            self.assertEqual(report["summary"]["commitCount"], 0)
            self.assertEqual(report["summary"]["filesChanged"], 0)
            self.assertEqual(report["commits"], [])

    def test_parse_numstat_preserves_rename_paths_and_binary_counts(self) -> None:
        value = (
            b"3\t1\tplain.txt\0"
            b"-\t-\timage.png\0"
            b"0\t0\t\0old.txt\0new.txt\0"
        )

        changes = MODULE.parse_numstat(value)

        self.assertEqual(changes[0]["insertions"], 3)
        self.assertTrue(changes[1]["binary"])
        self.assertEqual(changes[2]["previousPath"], "old.txt")
        self.assertEqual(changes[2]["path"], "new.txt")


if __name__ == "__main__":
    unittest.main()
