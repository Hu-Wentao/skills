from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "git_worktree.py"


def run(
    command: list[str], cwd: Path, *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"Command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


class GitWorktreeCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="git worktree tests ")
        self.root = Path(self.temporary.name)
        self.repo = self.root / "example repo"
        self.repo.mkdir()
        run(["git", "init", "-b", "main"], self.repo)
        run(["git", "config", "user.name", "Test User"], self.repo)
        run(["git", "config", "user.email", "test@example.com"], self.repo)
        (self.repo / "base.txt").write_text("base\n")
        run(["git", "add", "base.txt"], self.repo)
        run(["git", "commit", "-m", "initial"], self.repo)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def cli(
        self, *arguments: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        return run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), *arguments],
            self.repo,
            check=check,
        )

    def create(self, branch: str = "feat/demo") -> Path:
        result = self.cli("create", "--branch", branch)
        return Path(json.loads(result.stdout)["worktree"])

    def commit_file(self, worktree: Path, filename: str, contents: str) -> None:
        (worktree / filename).write_text(contents)
        run(["git", "add", filename], worktree)
        run(["git", "commit", "-m", f"add {filename}"], worktree)

    def test_create_and_list_worktree_with_sanitized_default_path(self) -> None:
        worktree = self.create()
        self.assertEqual(worktree.name, "example repo-T-feat-demo")
        self.assertTrue(worktree.is_dir())

        listed = json.loads(self.cli("list").stdout)["worktrees"]
        self.assertEqual(len(listed), 2)
        self.assertTrue(listed[0]["main"])
        self.assertEqual(listed[1]["branch"], "feat/demo")

    def test_merge_auto_selects_single_source_and_creates_merge_commit(self) -> None:
        worktree = self.create("feature")
        self.commit_file(worktree, "feature.txt", "feature\n")

        result = json.loads(self.cli("merge").stdout)
        self.assertEqual(result["source"], "feature")
        parents = run(["git", "rev-list", "--parents", "-n", "1", "HEAD"], self.repo)
        self.assertEqual(len(parents.stdout.split()), 3)

    def test_merge_rejects_dirty_source_worktree(self) -> None:
        worktree = self.create("dirty-source")
        (worktree / "dirty.txt").write_text("dirty\n")

        result = self.cli("merge", "--source", "dirty-source", check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("is dirty", result.stderr)
        self.assertEqual(
            run(["git", "branch", "--show-current"], self.repo).stdout.strip(), "main"
        )

    def test_merge_conflict_is_left_for_resolution(self) -> None:
        worktree = self.create("conflict")
        (worktree / "base.txt").write_text("source\n")
        run(["git", "commit", "-am", "source change"], worktree)
        (self.repo / "base.txt").write_text("target\n")
        run(["git", "commit", "-am", "target change"], self.repo)

        result = self.cli("merge", "--source", "conflict", check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("paused with conflicts", result.stderr)
        self.assertEqual(
            run(
                ["git", "rev-parse", "--verify", "--quiet", "MERGE_HEAD"],
                self.repo,
                check=False,
            ).returncode,
            0,
        )
        run(["git", "merge", "--abort"], self.repo)

    def test_remove_requires_merged_branch_when_requested(self) -> None:
        worktree = self.create("cleanup")
        self.commit_file(worktree, "cleanup.txt", "cleanup\n")

        rejected = self.cli(
            "remove",
            "--worktree",
            str(worktree),
            "--require-merged-into",
            "main",
            check=False,
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("is not merged", rejected.stderr)

        self.cli("merge", "--source", "cleanup")
        removed = json.loads(
            self.cli(
                "remove",
                "--worktree",
                str(worktree),
                "--require-merged-into",
                "main",
            ).stdout
        )
        self.assertTrue(removed["branch_retained"])
        self.assertFalse(worktree.exists())
        self.assertEqual(
            run(
                ["git", "show-ref", "--verify", "--quiet", "refs/heads/cleanup"],
                self.repo,
                check=False,
            ).returncode,
            0,
        )

    def test_remove_refuses_main_worktree(self) -> None:
        result = self.cli("remove", "--worktree", str(self.repo), check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("main worktree cannot be removed", result.stderr)


if __name__ == "__main__":
    unittest.main()
