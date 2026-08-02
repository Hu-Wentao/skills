from __future__ import annotations

import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "git_worktree.py"


def run(
    command: list[str],
    cwd: Path,
    *,
    check: bool = True,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        input=input_text,
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
        self,
        *arguments: str,
        check: bool = True,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), *arguments],
            self.repo,
            check=check,
            input_text=input_text,
        )

    def create(self, branch: str = "feat/demo") -> Path:
        result = self.cli("create", "--branch", branch)
        return Path(json.loads(result.stdout)["worktree"])

    def create_detached(self, name: str, base: str = "main") -> Path:
        worktree = self.root / name
        run(
            ["git", "worktree", "add", "--detach", str(worktree), base],
            self.repo,
        )
        return worktree

    def commit_file(self, worktree: Path, filename: str, contents: str) -> None:
        (worktree / filename).write_text(contents)
        run(["git", "add", filename], worktree)
        run(["git", "commit", "-m", f"add {filename}"], worktree)

    def commit_file_at(
        self,
        worktree: Path,
        filename: str,
        contents: str,
        committed_at: datetime,
    ) -> None:
        (worktree / filename).write_text(contents)
        run(["git", "add", filename], worktree)
        environment = os.environ.copy()
        timestamp = committed_at.isoformat()
        environment["GIT_AUTHOR_DATE"] = timestamp
        environment["GIT_COMMITTER_DATE"] = timestamp
        run(
            ["git", "commit", "-m", f"add {filename}"],
            worktree,
            env=environment,
        )

    def maintenance_audit(self) -> dict[str, object]:
        return json.loads(self.cli("maintenance-audit", "--all").stdout)

    def maintenance_plan(
        self,
        audit: dict[str, object],
        decisions: dict[str, tuple[str, str] | dict[str, object]],
    ) -> dict[str, object]:
        rendered: list[dict[str, object]] = []
        for candidate in audit["candidates"]:
            candidate_id = candidate["candidate_id"]
            value = decisions[candidate_id]
            if isinstance(value, tuple):
                decision, reason = value
                rendered.append(
                    {
                        "candidate_id": candidate_id,
                        "decision": decision,
                        "reason": reason,
                    }
                )
            else:
                rendered.append({"candidate_id": candidate_id, **value})
        return {
            "schema_version": audit["plan_schema_version"],
            "snapshot_id": audit["snapshot_id"],
            "target": audit["target"]["branch"],
            "decisions": rendered,
        }

    def run_maintenance_plan(
        self, plan: dict[str, object], *, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        return self.cli(
            "maintenance-run",
            check=check,
            input_text=json.dumps(plan),
        )

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

    def test_mark_complete_requires_exact_clean_branch_head(self) -> None:
        worktree = self.create("feat/completion-handoff")
        self.commit_file(worktree, "complete.txt", "complete\n")
        head = run(["git", "rev-parse", "HEAD"], worktree).stdout.strip()

        stale = run(
            [
                sys.executable,
                str(SCRIPT),
                "--repo",
                str(worktree),
                "mark-complete",
                "--expected-head",
                "0" * 40,
            ],
            worktree,
            check=False,
        )
        self.assertEqual(stale.returncode, 2)
        self.assertIn("HEAD changed since audit", stale.stderr)

        (worktree / "draft.txt").write_text("draft\n")
        dirty = run(
            [
                sys.executable,
                str(SCRIPT),
                "--repo",
                str(worktree),
                "mark-complete",
                "--expected-head",
                head,
            ],
            worktree,
            check=False,
        )
        self.assertEqual(dirty.returncode, 2)
        self.assertIn("is dirty", dirty.stderr)
        (worktree / "draft.txt").unlink()

        marked = json.loads(
            run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--repo",
                    str(worktree),
                    "mark-complete",
                    "--expected-head",
                    head,
                ],
                worktree,
            ).stdout
        )
        self.assertEqual(marked["branch"], "feat/completion-handoff")
        self.assertEqual(marked["head"], head)
        self.assertEqual(
            marked["completion_ref"],
            "refs/agents/completed/feat/completion-handoff",
        )
        self.assertEqual(
            run(
                ["git", "rev-parse", marked["completion_ref"]], self.repo
            ).stdout.strip(),
            head,
        )
        self.assertEqual(run(["git", "tag", "--list"], self.repo).stdout, "")

    def test_owner_status_discovers_preexisting_current_worktree(self) -> None:
        worktree = self.create("feat/preexisting-owner-task")
        self.commit_file(worktree, "complete.txt", "complete\n")
        head = run(["git", "rev-parse", "HEAD"], worktree).stdout.strip()

        inspected = json.loads(
            run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--repo",
                    str(worktree),
                    "owner-status",
                ],
                worktree,
            ).stdout
        )

        self.assertEqual(inspected["action"], "owner_status_inspected")
        self.assertEqual(inspected["worktree"]["path"], str(worktree))
        self.assertEqual(inspected["worktree"]["branch"], "feat/preexisting-owner-task")
        self.assertEqual(inspected["worktree"]["head"], head)
        self.assertFalse(inspected["worktree"]["main"])
        self.assertTrue(inspected["completion_eligible"])
        self.assertEqual(inspected["completion_blockers"], [])
        self.assertEqual(
            inspected["next_action"], "mark_complete_after_semantic_completion"
        )

        main = json.loads(self.cli("owner-status").stdout)
        self.assertFalse(main["completion_eligible"])
        self.assertIn("main_worktree", main["completion_blockers"])
        self.assertEqual(main["completion"]["status"], "not_applicable")
        self.assertIsNone(main["completion"]["ref"])

        (worktree / "draft.txt").write_text("draft\n")
        dirty = json.loads(
            run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--repo",
                    str(worktree),
                    "owner-status",
                ],
                worktree,
            ).stdout
        )
        self.assertFalse(dirty["completion_eligible"])
        self.assertTrue(
            any(blocker.endswith(":dirty") for blocker in dirty["completion_blockers"])
        )

    def test_maintenance_audit_reports_current_and_stale_completion(self) -> None:
        worktree = self.create("feat/completed-owner-task")
        self.commit_file(worktree, "first.txt", "first\n")
        completed_head = run(["git", "rev-parse", "HEAD"], worktree).stdout.strip()
        run(
            [
                sys.executable,
                str(SCRIPT),
                "--repo",
                str(worktree),
                "mark-complete",
                "--expected-head",
                completed_head,
            ],
            worktree,
        )

        current = json.loads(self.cli("maintenance-audit", "--all").stdout)
        candidate = next(
            item
            for item in current["candidates"]
            if item["candidate_id"] == "branch:feat/completed-owner-task"
        )
        self.assertEqual(candidate["completion"]["status"], "current")
        self.assertTrue(candidate["completion"]["matches_head"])
        self.assertTrue(
            candidate["decision_evidence"]["owner_handoff_completed"]
        )

        (worktree / "draft.txt").write_text("draft\n")
        blocked = json.loads(self.cli("maintenance-audit", "--all").stdout)
        candidate = next(
            item
            for item in blocked["candidates"]
            if item["candidate_id"] == "branch:feat/completed-owner-task"
        )
        self.assertEqual(candidate["completion"]["status"], "blocked")
        self.assertTrue(candidate["completion"]["matches_head"])
        self.assertFalse(candidate["completion"]["worktrees_clean"])
        self.assertFalse(
            candidate["decision_evidence"]["owner_handoff_completed"]
        )
        (worktree / "draft.txt").unlink()

        self.commit_file(worktree, "second.txt", "second\n")
        stale = json.loads(self.cli("maintenance-audit", "--all").stdout)
        candidate = next(
            item
            for item in stale["candidates"]
            if item["candidate_id"] == "branch:feat/completed-owner-task"
        )
        self.assertEqual(candidate["completion"]["status"], "stale")
        self.assertFalse(candidate["completion"]["matches_head"])
        self.assertTrue(candidate["completion"]["worktrees_clean"])
        self.assertFalse(
            candidate["decision_evidence"]["owner_handoff_completed"]
        )

    def test_maintenance_audit_snapshot_tracks_worktree_state(self) -> None:
        worktree = self.create("feat/snapshot")
        self.commit_file(worktree, "snapshot.txt", "snapshot\n")

        first = self.maintenance_audit()
        second = self.maintenance_audit()
        self.assertEqual(first["plan_schema_version"], 1)
        self.assertEqual(len(first["snapshot_id"]), 64)
        self.assertEqual(first["snapshot_id"], second["snapshot_id"])
        missing = {
            item["candidate_id"]: item["status"]
            for item in first["owner_handoff_missing"]
        }
        self.assertEqual(missing["branch:feat/snapshot"], "absent")

        (worktree / "draft.txt").write_text("draft\n")
        changed = self.maintenance_audit()
        self.assertNotEqual(first["snapshot_id"], changed["snapshot_id"])

    def test_maintenance_run_merges_branch_and_retains_worktree(self) -> None:
        worktree = self.create("feat/batch-merge")
        self.commit_file(worktree, "batch.txt", "batch\n")
        source_head = run(["git", "rev-parse", "HEAD"], worktree).stdout.strip()
        audit = self.maintenance_audit()
        plan = self.maintenance_plan(
            audit,
            {
                "branch:feat/batch-merge": ("merge", "feature is complete"),
                f"worktree:{worktree}": (
                    "retain",
                    "validate the merged target before cleanup",
                ),
            },
        )

        completed = json.loads(self.run_maintenance_plan(plan).stdout)
        self.assertEqual(completed["status"], "completed")
        self.assertTrue(completed["remote_refs_untouched"])
        self.assertTrue(Path(completed["repository_lock"]).exists())
        self.assertTrue(worktree.exists())
        self.assertEqual(
            run(
                ["git", "merge-base", "--is-ancestor", source_head, "main"],
                self.repo,
            ).returncode,
            0,
        )
        outcomes = {
            item["candidate_id"]: item
            for item in completed["terminal_decisions"]
        }
        self.assertEqual(
            outcomes[f"worktree:{worktree}"]["outcome"],
            "retained_without_mutation",
        )

    def test_maintenance_run_blocks_all_mutation_until_detached_head_is_rescued(
        self,
    ) -> None:
        merged = self.create("feat/already-merged")
        self.commit_file(merged, "merged.txt", "merged\n")
        self.cli("merge", "--source", "feat/already-merged")

        detached = self.create_detached("unrescued detached")
        self.commit_file(detached, "unique.txt", "unique\n")
        detached_head = run(
            ["git", "rev-parse", "HEAD"], detached
        ).stdout.strip()
        run(
            [
                "git",
                "update-ref",
                "refs/codex/snapshots/test-unrescued",
                detached_head,
            ],
            self.repo,
        )

        audit = self.maintenance_audit()
        decisions = {
            candidate["candidate_id"]: ("retain", "retain reviewed work")
            for candidate in audit["candidates"]
        }
        decisions["branch:feat/already-merged"] = ("delete", "already merged")
        decisions[f"worktree:{merged}"] = ("delete", "already merged")
        plan = self.maintenance_plan(audit, decisions)

        rejected = self.run_maintenance_plan(plan, check=False)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("blocked by unrescued detached worktree", rejected.stderr)
        self.assertIn(str(detached), rejected.stderr)
        self.assertIn("internal snapshot ref does not satisfy rescue", rejected.stderr)
        self.assertTrue(merged.exists())
        self.assertEqual(
            run(
                [
                    "git",
                    "show-ref",
                    "--verify",
                    "--quiet",
                    "refs/heads/feat/already-merged",
                ],
                self.repo,
                check=False,
            ).returncode,
            0,
        )

    def test_maintenance_run_rejects_stale_snapshot(self) -> None:
        worktree = self.create("feat/stale-plan")
        self.commit_file(worktree, "first.txt", "first\n")
        audit = self.maintenance_audit()
        plan = self.maintenance_plan(
            audit,
            {
                "branch:feat/stale-plan": ("merge", "feature is complete"),
                f"worktree:{worktree}": ("retain", "keep until validation"),
            },
        )
        self.commit_file(worktree, "second.txt", "second\n")

        rejected = self.run_maintenance_plan(plan, check=False)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("snapshot changed", rejected.stderr)
        self.assertEqual(
            run(
                ["git", "merge-base", "--is-ancestor", "feat/stale-plan", "main"],
                self.repo,
                check=False,
            ).returncode,
            1,
        )

    def test_maintenance_run_rejects_dirty_target_before_mutation(self) -> None:
        worktree = self.create("feat/dirty-target-plan")
        self.commit_file(worktree, "feature.txt", "feature\n")
        (self.repo / "target-draft.txt").write_text("draft\n")
        audit = self.maintenance_audit()
        plan = self.maintenance_plan(
            audit,
            {
                "branch:feat/dirty-target-plan": ("merge", "feature is complete"),
                f"worktree:{worktree}": ("retain", "retain through validation"),
            },
        )

        rejected = self.run_maintenance_plan(plan, check=False)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("Target worktree is not safe", rejected.stderr)
        self.assertEqual(
            run(
                [
                    "git",
                    "merge-base",
                    "--is-ancestor",
                    "feat/dirty-target-plan",
                    "main",
                ],
                self.repo,
                check=False,
            ).returncode,
            1,
        )

    def test_maintenance_run_deletes_merged_branch_and_worktree(self) -> None:
        worktree = self.create("feat/batch-delete")
        self.commit_file(worktree, "delete.txt", "delete\n")
        self.cli("merge", "--source", "feat/batch-delete")
        audit = self.maintenance_audit()
        plan = self.maintenance_plan(
            audit,
            {
                "branch:feat/batch-delete": ("delete", "already merged"),
                f"worktree:{worktree}": ("delete", "already merged"),
            },
        )

        completed = json.loads(self.run_maintenance_plan(plan).stdout)
        self.assertEqual(completed["status"], "completed")
        self.assertFalse(worktree.exists())
        self.assertEqual(
            run(
                [
                    "git",
                    "show-ref",
                    "--verify",
                    "--quiet",
                    "refs/heads/feat/batch-delete",
                ],
                self.repo,
                check=False,
            ).returncode,
            1,
        )
        outcomes = {
            item["candidate_id"]: item
            for item in completed["terminal_decisions"]
        }
        self.assertEqual(
            outcomes[f"worktree:{worktree}"]["outcome"],
            "removed_with_branch_delete",
        )

    def test_maintenance_run_requires_post_merge_cleanup_reaudit(self) -> None:
        worktree = self.create("feat/two-phase")
        self.commit_file(worktree, "phase.txt", "phase\n")
        audit = self.maintenance_audit()
        plan = self.maintenance_plan(
            audit,
            {
                "branch:feat/two-phase": ("merge", "feature is complete"),
                f"worktree:{worktree}": ("delete", "clean up after merge"),
            },
        )

        rejected = self.run_maintenance_plan(plan, check=False)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("Validate the merge, then audit again", rejected.stderr)
        self.assertEqual(
            run(
                ["git", "merge-base", "--is-ancestor", "feat/two-phase", "main"],
                self.repo,
                check=False,
            ).returncode,
            1,
        )

    def test_maintenance_run_reports_structured_merge_pause(self) -> None:
        worktree = self.create("feat/batch-conflict")
        (worktree / "base.txt").write_text("source\n")
        run(["git", "commit", "-am", "source change"], worktree)
        (self.repo / "base.txt").write_text("target\n")
        run(["git", "commit", "-am", "target change"], self.repo)
        audit = self.maintenance_audit()
        plan = self.maintenance_plan(
            audit,
            {
                "branch:feat/batch-conflict": ("merge", "behavior is required"),
                f"worktree:{worktree}": ("retain", "retain through validation"),
            },
        )

        paused = self.run_maintenance_plan(plan, check=False)
        self.assertEqual(paused.returncode, 2)
        report = json.loads(paused.stdout)
        self.assertEqual(report["status"], "paused")
        self.assertIn("Merge paused with conflicts", report["error"])
        self.assertEqual(report["target_state"]["operations"], ["merge"])
        self.assertTrue(report["target_state"]["dirty"])
        self.assertEqual(report["completed_decisions"], [])

    def test_maintenance_run_prunes_orphan_completion_refs(self) -> None:
        head = run(["git", "rev-parse", "HEAD"], self.repo).stdout.strip()
        ref = "refs/agents/completed/feat/deleted-owner"
        stale_plan = self.maintenance_plan(self.maintenance_audit(), {})
        run(["git", "update-ref", ref, head], self.repo)
        rejected = self.run_maintenance_plan(stale_plan, check=False)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("snapshot changed", rejected.stderr)

        audit = self.maintenance_audit()
        self.assertEqual(audit["candidates"], [])
        self.assertEqual(audit["orphan_completion_refs"][0]["ref"], ref)
        plan = self.maintenance_plan(audit, {})

        completed = json.loads(self.run_maintenance_plan(plan).stdout)
        self.assertEqual(completed["removed_orphan_completion_refs"][0]["ref"], ref)
        self.assertEqual(
            run(
                ["git", "show-ref", "--verify", "--quiet", ref],
                self.repo,
                check=False,
            ).returncode,
            1,
        )

    def test_mutating_commands_share_repository_lock(self) -> None:
        worktree = self.create("feat/blocked-by-lock")
        head = run(["git", "rev-parse", "HEAD"], worktree).stdout.strip()
        common = Path(
            run(["git", "rev-parse", "--git-common-dir"], self.repo).stdout.strip()
        )
        if not common.is_absolute():
            common = self.repo / common
        lock_path = common.resolve() / "agents-worktree.lock"
        with lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            rejected = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--repo",
                    str(worktree),
                    "mark-complete",
                    "--expected-head",
                    head,
                ],
                worktree,
                check=False,
            )
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

        self.assertEqual(rejected.returncode, 2)
        self.assertIn("holds the repository lock", rejected.stderr)
        self.assertEqual(
            run(
                [
                    "git",
                    "show-ref",
                    "--verify",
                    "--quiet",
                    "refs/agents/completed/feat/blocked-by-lock",
                ],
                self.repo,
                check=False,
            ).returncode,
            1,
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

    def test_branch_audit_selects_recent_count_by_commit_time(self) -> None:
        older = self.create("older")
        self.commit_file_at(
            older,
            "older.txt",
            "older\n",
            datetime.now(UTC) - timedelta(hours=2),
        )
        newer = self.create("newer")
        self.commit_file_at(
            newer,
            "newer.txt",
            "newer\n",
            datetime.now(UTC) - timedelta(hours=1),
        )

        result = json.loads(
            self.cli("branch-audit", "--recent-count", "1").stdout
        )
        self.assertEqual(result["scope"], "local_unmerged")
        self.assertEqual(result["total_unmerged"], 2)
        self.assertEqual([item["branch"] for item in result["branches"]], ["newer"])
        self.assertEqual(result["branches"][0]["ahead"], 1)

    def test_branch_audit_selects_recent_days(self) -> None:
        old = self.create("old")
        self.commit_file_at(
            old,
            "old.txt",
            "old\n",
            datetime.now(UTC) - timedelta(days=3),
        )
        recent = self.create("recent")
        self.commit_file(recent, "recent.txt", "recent\n")

        result = json.loads(
            self.cli("branch-audit", "--recent-days", "1").stdout
        )
        self.assertEqual([item["branch"] for item in result["branches"]], ["recent"])

    def test_branch_audit_detects_patch_equivalent_commit(self) -> None:
        worktree = self.create("equivalent")
        self.commit_file(worktree, "equivalent.txt", "equivalent\n")
        source_commit = run(["git", "rev-parse", "HEAD"], worktree).stdout.strip()
        (self.repo / "main-only.txt").write_text("main\n")
        run(["git", "add", "main-only.txt"], self.repo)
        run(["git", "commit", "-m", "advance main"], self.repo)
        run(["git", "cherry-pick", source_commit], self.repo)

        result = json.loads(
            self.cli("branch-audit", "--recent-count", "1").stdout
        )
        branch = result["branches"][0]
        self.assertEqual(branch["branch"], "equivalent")
        self.assertTrue(branch["patch_equivalent_to_target"])
        self.assertEqual(branch["patch_unique_commits"], 0)

    def test_branch_delete_requires_explicit_unmerged_authorization(self) -> None:
        worktree = self.create("obsolete")
        self.commit_file(worktree, "obsolete.txt", "obsolete\n")
        source_commit = run(["git", "rev-parse", "HEAD"], worktree).stdout.strip()
        target_commit = run(["git", "rev-parse", "HEAD"], self.repo).stdout.strip()

        rejected = self.cli(
            "branch-delete",
            "--branch",
            "obsolete",
            "--reason",
            "superseded",
            check=False,
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("--allow-unmerged", rejected.stderr)

        stale_review = self.cli(
            "branch-delete",
            "--branch",
            "obsolete",
            "--reason",
            "superseded",
            "--allow-unmerged",
            "--remove-worktree",
            check=False,
        )
        self.assertEqual(stale_review.returncode, 2)
        self.assertIn("--expected-target-head", stale_review.stderr)

        deleted = json.loads(
            self.cli(
                "branch-delete",
                "--branch",
                "obsolete",
                "--reason",
                "superseded",
                "--allow-unmerged",
                "--remove-worktree",
                "--expected-head",
                source_commit,
                "--expected-target-head",
                target_commit,
            ).stdout
        )
        self.assertFalse(deleted["merged_into_target"])
        self.assertEqual(deleted["commit"], source_commit)
        self.assertFalse(worktree.exists())
        self.assertNotIn(
            "obsolete",
            run(["git", "branch", "--format=%(refname:short)"], self.repo).stdout,
        )

    def test_branch_delete_refuses_dirty_worktree(self) -> None:
        worktree = self.create("dirty-delete")
        self.commit_file(worktree, "tracked.txt", "tracked\n")
        (worktree / "dirty.txt").write_text("dirty\n")
        target_commit = run(["git", "rev-parse", "HEAD"], self.repo).stdout.strip()

        rejected = self.cli(
            "branch-delete",
            "--branch",
            "dirty-delete",
            "--reason",
            "obsolete",
            "--allow-unmerged",
            "--remove-worktree",
            "--expected-target-head",
            target_commit,
            check=False,
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("dirty", rejected.stderr)

    def test_branch_delete_protects_release_and_hotfix_branches(self) -> None:
        worktree = self.create("release/v1.0.0")
        self.commit_file(worktree, "release.txt", "release\n")

        rejected = self.cli(
            "branch-delete",
            "--branch",
            "release/v1.0.0",
            "--reason",
            "obsolete",
            "--allow-unmerged",
            "--remove-worktree",
            check=False,
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("--allow-protected", rejected.stderr)
        self.assertTrue(worktree.exists())

    def test_branch_delete_also_protects_repair_branches(self) -> None:
        worktree = self.create("repair/v1.0.1")
        self.commit_file(worktree, "repair.txt", "repair\n")

        rejected = self.cli(
            "branch-delete",
            "--branch",
            "repair/v1.0.1",
            "--reason",
            "obsolete",
            "--allow-unmerged",
            "--remove-worktree",
            check=False,
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("--allow-protected", rejected.stderr)
        self.assertTrue(worktree.exists())

    def test_branch_delete_removes_merged_branch_and_clean_worktree(self) -> None:
        worktree = self.create("merged-cleanup")
        self.commit_file(worktree, "merged.txt", "merged\n")
        source_head = run(["git", "rev-parse", "HEAD"], worktree).stdout.strip()
        run(
            [
                sys.executable,
                str(SCRIPT),
                "--repo",
                str(worktree),
                "mark-complete",
                "--expected-head",
                source_head,
            ],
            worktree,
        )
        self.cli("merge", "--source", "merged-cleanup")

        deleted = json.loads(
            self.cli(
                "branch-delete",
                "--branch",
                "merged-cleanup",
                "--reason",
                "merged into main",
                "--remove-worktree",
            ).stdout
        )
        self.assertTrue(deleted["merged_into_target"])
        self.assertTrue(deleted["completion_ref_removed"])
        self.assertEqual(
            run(
                [
                    "git",
                    "show-ref",
                    "--verify",
                    "--quiet",
                    "refs/agents/completed/merged-cleanup",
                ],
                self.repo,
                check=False,
            ).returncode,
            1,
        )
        self.assertFalse(worktree.exists())

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

    def test_maintenance_audit_includes_merged_and_detached_work(self) -> None:
        merged = self.create("merged-topic")
        self.commit_file(merged, "merged.txt", "merged\n")
        self.cli("merge", "--source", "merged-topic")

        detached_unique = self.create_detached("detached unique")
        self.commit_file(detached_unique, "unique.txt", "unique\n")
        unique_head = run(
            ["git", "rev-parse", "HEAD"], detached_unique
        ).stdout.strip()
        run(
            [
                "git",
                "update-ref",
                "refs/codex/snapshots/test-unique",
                unique_head,
            ],
            self.repo,
        )

        detached_dirty = self.create_detached("detached dirty")
        (detached_dirty / "uncommitted.txt").write_text("uncommitted\n")

        result = json.loads(self.cli("maintenance-audit", "--all").stdout)
        candidates = {
            item["candidate_id"]: item for item in result["candidates"]
        }

        merged_item = candidates["branch:merged-topic"]
        self.assertTrue(merged_item["relation"]["contained_in_target"])
        self.assertEqual(
            merged_item["decision_evidence"]["possible_decisions"],
            ["delete", "retain"],
        )

        unique_item = candidates[f"worktree:{detached_unique.resolve()}"]
        self.assertFalse(unique_item["relation"]["contained_in_target"])
        self.assertTrue(unique_item["decision_evidence"]["rescue_required"])
        self.assertEqual(
            unique_item["decision_evidence"]["preservation_refs"], []
        )
        self.assertIn(
            "create a rescue branch at the exact HEAD before any terminal "
            "maintenance decision",
            unique_item["decision_evidence"]["requirements"],
        )

        dirty_item = candidates[f"worktree:{detached_dirty.resolve()}"]
        self.assertTrue(dirty_item["decision_evidence"]["dirty"])
        self.assertEqual(
            dirty_item["decision_evidence"]["possible_decisions"],
            ["retain"],
        )
        self.assertTrue(dirty_item["decision_evidence"]["mutation_blocked"])
        self.assertEqual(
            dirty_item["decision_evidence"]["default_decision"], "retain"
        )
        self.assertEqual(
            dirty_item["decision_evidence"]["retention_reasons"],
            ["dirty_worktree_presumed_active"],
        )
        self.assertIn(
            "?? uncommitted.txt",
            dirty_item["worktrees"][0]["changes"],
        )
        retained = result["retained_active_or_dirty_worktrees"]
        self.assertEqual(len(retained), 1)
        self.assertEqual(retained[0]["path"], str(detached_dirty.resolve()))
        self.assertIsNone(retained[0]["branch"])
        self.assertTrue(retained[0]["detached"])
        self.assertEqual(retained[0]["head"], dirty_item["head"])
        self.assertIn("?? uncommitted.txt", retained[0]["changes"])
        self.assertEqual(
            retained[0]["retention_reasons"],
            ["dirty_worktree_presumed_active"],
        )
        self.assertIn("merge", retained[0]["mutations_skipped"])
        self.assertIn("remove", retained[0]["mutations_skipped"])
        self.assertFalse(result["maintenance_run_eligible"])
        rescue_candidates = {
            item["candidate_id"] for item in result["rescue_required_worktrees"]
        }
        self.assertEqual(
            rescue_candidates,
            {f"worktree:{detached_unique.resolve()}"},
        )

    def test_maintenance_audit_accepts_exact_local_branch_and_tag_as_rescue(
        self,
    ) -> None:
        detached = self.create_detached("already preserved")
        self.commit_file(detached, "preserved.txt", "preserved\n")
        head = run(["git", "rev-parse", "HEAD"], detached).stdout.strip()
        run(["git", "branch", "feat/preserved-head", head], self.repo)
        run(["git", "tag", "-a", "preserved-v1", "-m", "preserved", head], self.repo)

        result = self.maintenance_audit()
        candidate = next(
            item
            for item in result["candidates"]
            if item["candidate_id"] == f"worktree:{detached.resolve()}"
        )

        self.assertFalse(candidate["decision_evidence"]["rescue_required"])
        self.assertEqual(
            candidate["decision_evidence"]["preservation_refs"],
            ["refs/heads/feat/preserved-head", "refs/tags/preserved-v1"],
        )
        self.assertEqual(result["rescue_required_worktrees"], [])
        self.assertTrue(result["maintenance_run_eligible"])

    def test_maintenance_audit_separates_protected_branch_and_worktree(self) -> None:
        worktree = self.create("release/v2.0.0")

        result = json.loads(self.cli("maintenance-audit", "--all").stdout)
        candidates = {
            item["candidate_id"]: item for item in result["candidates"]
        }
        branch_item = candidates["branch:release/v2.0.0"]
        worktree_item = candidates[f"worktree:{worktree}"]

        self.assertEqual(
            branch_item["decision_evidence"]["decision_scope"],
            "branch_and_committed_history",
        )
        self.assertEqual(
            branch_item["decision_evidence"]["possible_decisions"], ["retain"]
        )
        self.assertEqual(
            worktree_item["decision_evidence"]["decision_scope"],
            "worktree_only_branch_ref_retained",
        )
        self.assertEqual(
            worktree_item["decision_evidence"]["possible_decisions"],
            ["delete", "retain"],
        )

    def test_maintenance_audit_defaults_dirty_attached_branch_to_retain(self) -> None:
        worktree = self.create("feat/actively-edited")
        (worktree / "draft.txt").write_text("in progress\n")

        result = json.loads(self.cli("maintenance-audit", "--all").stdout)
        candidates = {
            item["candidate_id"]: item for item in result["candidates"]
        }
        branch_item = candidates["branch:feat/actively-edited"]
        worktree_item = candidates[f"worktree:{worktree}"]

        for item in (branch_item, worktree_item):
            evidence = item["decision_evidence"]
            self.assertEqual(evidence["possible_decisions"], ["retain"])
            self.assertEqual(evidence["default_decision"], "retain")
            self.assertTrue(evidence["mutation_blocked"])
            self.assertEqual(
                evidence["retention_reasons"],
                ["dirty_worktree_presumed_active"],
            )

        retained = result["retained_active_or_dirty_worktrees"]
        self.assertEqual(len(retained), 1)
        self.assertEqual(retained[0]["path"], str(worktree))
        self.assertEqual(retained[0]["branch"], "feat/actively-edited")
        self.assertFalse(retained[0]["detached"])
        self.assertEqual(retained[0]["changes"], ["?? draft.txt"])
        self.assertEqual(
            retained[0]["mutations_skipped"],
            [
                "modify",
                "stage",
                "commit",
                "switch",
                "merge",
                "delete",
                "remove",
                "rescue",
            ],
        )

    def test_maintenance_audit_reports_active_git_operation(self) -> None:
        worktree = self.create("operation-topic")
        marker = Path(
            run(
                ["git", "rev-parse", "--git-path", "CHERRY_PICK_HEAD"],
                worktree,
            ).stdout.strip()
        )
        marker.write_text(run(["git", "rev-parse", "HEAD"], worktree).stdout)

        result = json.loads(self.cli("maintenance-audit", "--all").stdout)
        item = next(
            candidate
            for candidate in result["candidates"]
            if candidate["candidate_id"] == "branch:operation-topic"
        )
        self.assertEqual(item["decision_evidence"]["operations"], ["cherry_pick"])
        self.assertEqual(
            item["decision_evidence"]["possible_decisions"],
            ["retain"],
        )
        self.assertEqual(item["decision_evidence"]["default_decision"], "retain")
        self.assertTrue(item["decision_evidence"]["mutation_blocked"])
        self.assertIn(
            "active_git_operation", item["decision_evidence"]["retention_reasons"]
        )

    def test_maintenance_audit_retains_uninspectable_worktree(self) -> None:
        worktree = self.create_detached("damaged worktree")
        git_file = worktree / ".git"
        saved_git_file = worktree / ".git.saved"
        git_file.rename(saved_git_file)
        try:
            result = json.loads(self.cli("maintenance-audit", "--all").stdout)
            item = next(
                candidate
                for candidate in result["candidates"]
                if candidate["candidate_id"] == f"worktree:{worktree.resolve()}"
            )
            self.assertFalse(item["worktrees"][0]["inspectable"])
            self.assertTrue(item["worktrees"][0]["inspection_error"])
            self.assertEqual(
                item["decision_evidence"]["possible_decisions"], ["retain"]
            )
            self.assertIn(
                "repair or independently inspect the worktree before mutation",
                item["decision_evidence"]["requirements"],
            )
        finally:
            saved_git_file.rename(git_file)

    def test_maintenance_audit_handles_unrelated_history(self) -> None:
        worktree = self.create_detached("orphan worktree")
        run(["git", "switch", "--orphan", "temporary-orphan"], worktree)
        (worktree / "orphan.txt").write_text("orphan\n")
        run(["git", "add", "-A"], worktree)
        run(["git", "commit", "-m", "orphan history"], worktree)
        run(["git", "switch", "--detach", "HEAD"], worktree)
        run(["git", "branch", "-D", "temporary-orphan"], self.repo)

        result = json.loads(self.cli("maintenance-audit", "--all").stdout)
        item = next(
            candidate
            for candidate in result["candidates"]
            if candidate["candidate_id"] == f"worktree:{worktree.resolve()}"
        )
        self.assertFalse(item["relation"]["history_related"])
        self.assertFalse(item["relation"]["contained_in_target"])
        self.assertFalse(item["relation"]["patch_equivalent_to_target"])
        self.assertGreater(item["relation"]["patch_unique_commits"], 0)

    def test_maintenance_audit_preserves_newline_filename_as_one_change(self) -> None:
        worktree = self.create_detached("newline filename")
        filename = "odd\nname.txt"
        (worktree / filename).write_text("draft\n")

        result = json.loads(self.cli("maintenance-audit", "--all").stdout)
        item = next(
            candidate
            for candidate in result["candidates"]
            if candidate["candidate_id"] == f"worktree:{worktree.resolve()}"
        )
        self.assertEqual(item["worktrees"][0]["changes"], [f"?? {filename}"])

    def test_rescue_detached_preserves_dirty_changes_and_checks_head(self) -> None:
        worktree = self.create_detached("detached rescue")
        (worktree / "draft.txt").write_text("draft\n")
        head = run(["git", "rev-parse", "HEAD"], worktree).stdout.strip()

        rejected = self.cli(
            "rescue-detached",
            "--worktree",
            str(worktree),
            "--branch",
            "feat/rescued",
            "--expected-head",
            "0" * 40,
            check=False,
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("HEAD changed since audit", rejected.stderr)

        rescued = json.loads(
            self.cli(
                "rescue-detached",
                "--worktree",
                str(worktree),
                "--branch",
                "feat/rescued",
                "--expected-head",
                head,
            ).stdout
        )
        self.assertEqual(rescued["head"], head)
        self.assertEqual(rescued["target"], "main")
        self.assertEqual(rescued["classification_status"], "pending")
        self.assertFalse(rescued["decision_terminal"])
        self.assertEqual(rescued["candidate"]["candidate_id"], "branch:feat/rescued")
        self.assertTrue(rescued["candidate"]["decision_evidence"]["dirty"])
        self.assertEqual(
            rescued["next_action"],
            {
                "action": "classify_rescued_branch",
                "candidate_id": "branch:feat/rescued",
                "target": "main",
            },
        )
        self.assertIn("?? draft.txt", rescued["dirty_changes_preserved"])
        self.assertEqual(
            run(["git", "branch", "--show-current"], worktree).stdout.strip(),
            "feat/rescued",
        )
        self.assertEqual((worktree / "draft.txt").read_text(), "draft\n")

    def test_rescued_clean_branch_is_returned_for_continued_maintenance(self) -> None:
        worktree = self.create_detached("detached completed work")
        self.commit_file(worktree, "completed.txt", "completed\n")
        head = run(["git", "rev-parse", "HEAD"], worktree).stdout.strip()

        rescued = json.loads(
            self.cli(
                "rescue-detached",
                "--worktree",
                str(worktree),
                "--branch",
                "feat/completed",
                "--expected-head",
                head,
                "--target",
                "main",
            ).stdout
        )

        candidate = rescued["candidate"]
        self.assertEqual(candidate["kind"], "branch")
        self.assertEqual(candidate["branch"], "feat/completed")
        self.assertEqual(candidate["head"], head)
        self.assertFalse(candidate["relation"]["contained_in_target"])
        self.assertEqual(
            candidate["decision_evidence"]["possible_decisions"],
            ["merge", "delete", "retain"],
        )

        target_head = run(["git", "rev-parse", "main"], self.repo).stdout.strip()
        merged = json.loads(
            self.cli(
                "merge",
                "--source",
                "feat/completed",
                "--target",
                "main",
                "--expected-source-head",
                head,
                "--expected-target-head",
                target_head,
            ).stdout
        )
        self.assertEqual(merged["source"], "feat/completed")
        self.assertEqual(merged["target"], "main")
        self.assertEqual(
            run(["git", "merge-base", "--is-ancestor", head, "main"], self.repo).returncode,
            0,
        )

    def test_remove_detached_requires_containment_evidence(self) -> None:
        worktree = self.create_detached("detached contained")
        head = run(["git", "rev-parse", "HEAD"], worktree).stdout.strip()

        rejected = self.cli(
            "remove", "--worktree", str(worktree), check=False
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("requires --expected-head", rejected.stderr)

        removed = json.loads(
            self.cli(
                "remove",
                "--worktree",
                str(worktree),
                "--require-contained-in",
                "main",
                "--expected-head",
                head,
            ).stdout
        )
        self.assertEqual(removed["head"], head)
        self.assertFalse(removed["branch_retained"])
        self.assertFalse(worktree.exists())

    def test_remove_detached_rejects_uncontained_head(self) -> None:
        worktree = self.create_detached("detached uncontained")
        self.commit_file(worktree, "unique.txt", "unique\n")
        head = run(["git", "rev-parse", "HEAD"], worktree).stdout.strip()

        rejected = self.cli(
            "remove",
            "--worktree",
            str(worktree),
            "--require-contained-in",
            "main",
            "--expected-head",
            head,
            check=False,
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("is not contained", rejected.stderr)
        self.assertTrue(worktree.exists())

    def test_prune_missing_requires_exact_set_and_preserves_branch(self) -> None:
        worktree = self.create("stale-topic")
        self.commit_file(worktree, "stale.txt", "stale\n")
        head = run(["git", "rev-parse", "HEAD"], worktree).stdout.strip()
        shutil.rmtree(worktree)

        rejected = self.cli(
            "prune-missing",
            "--expect",
            f"{worktree}={'0' * 40}",
            check=False,
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("set changed or was not fully reviewed", rejected.stderr)

        pruned = json.loads(
            self.cli(
                "prune-missing",
                "--expect",
                f"{worktree}={head}",
            ).stdout
        )
        self.assertTrue(pruned["branch_refs_retained"])
        self.assertTrue(pruned["branch_refs_verified_unchanged"])
        self.assertEqual(pruned["pruned"], [{"head": head, "path": str(worktree)}])
        self.assertEqual(
            run(
                ["git", "show-ref", "--verify", "refs/heads/stale-topic"],
                self.repo,
            ).returncode,
            0,
        )

    def test_branch_delete_rejects_target_head_changed_since_review(self) -> None:
        worktree = self.create("stale-target-review")
        self.commit_file(worktree, "topic.txt", "topic\n")
        source_commit = run(["git", "rev-parse", "HEAD"], worktree).stdout.strip()
        audited_target = run(["git", "rev-parse", "HEAD"], self.repo).stdout.strip()
        self.commit_file(self.repo, "target.txt", "target moved\n")

        rejected = self.cli(
            "branch-delete",
            "--branch",
            "stale-target-review",
            "--reason",
            "superseded",
            "--allow-unmerged",
            "--remove-worktree",
            "--expected-head",
            source_commit,
            "--expected-target-head",
            audited_target,
            check=False,
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("Target 'main' HEAD changed", rejected.stderr)
        self.assertTrue(worktree.exists())

    def test_merge_rejects_changed_heads_from_audit(self) -> None:
        worktree = self.create("moving-source")
        self.commit_file(worktree, "first.txt", "first\n")
        audited_source = run(["git", "rev-parse", "HEAD"], worktree).stdout.strip()
        audited_target = run(["git", "rev-parse", "HEAD"], self.repo).stdout.strip()
        self.commit_file(worktree, "second.txt", "second\n")

        rejected = self.cli(
            "merge",
            "--source",
            "moving-source",
            "--expected-source-head",
            audited_source,
            "--expected-target-head",
            audited_target,
            check=False,
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("Source 'moving-source' HEAD changed", rejected.stderr)


if __name__ == "__main__":
    unittest.main()
