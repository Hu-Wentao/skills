#!/usr/bin/env python3
"""Integration tests for the project-neutral managed release workflow."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[2]
RUNNER = SKILL_ROOT / "scripts" / "project-governance.py"


class ManagedReleaseWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="managed-release-")
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Release Test")
        self.git("config", "user.email", "release-test@example.invalid")
        (self.root / "package.json").write_text(
            json.dumps({"name": "release-test", "version": "1.0.0"}, indent=2) + "\n",
            encoding="utf-8",
        )
        (self.root / "hooks.py").write_text(
            "import json,os,sys\n"
            "mode=sys.argv[1]\n"
            "if mode == 'freeze':\n"
            " target=os.environ['PROJECT_GOVERNANCE_RELEASE_TARGET']\n"
            " print(json.dumps({'schema':'project-governance.artifact-freeze.v1','artifacts':[{'name':'app','digest':'sha256:'+target}]}))\n"
            "elif mode in {'gate','deploy','verify'}:\n"
            " print(mode)\n"
            "else:\n"
            " raise SystemExit(2)\n",
            encoding="utf-8",
        )
        config_root = self.root / ".agents" / "skills-config" / "project-governance"
        config_root.mkdir(parents=True)
        (config_root / "release-workflow.json").write_text(
            json.dumps(
                {
                    "schema": "project-governance.release-workflow.v1",
                    "integration_branch": "main",
                    "version": {"kind": "package-json", "path": "package.json"},
                    "gates": [[sys.executable, "hooks.py", "gate"]],
                    "artifact": {"freeze": [sys.executable, "hooks.py", "freeze"]},
                    "targets": {
                        "test": {
                            "deploy": [sys.executable, "hooks.py", "deploy"],
                            "verify": [sys.executable, "hooks.py", "verify"],
                        },
                        "production": {
                            "deploy": [sys.executable, "hooks.py", "deploy"],
                            "verify": [sys.executable, "hooks.py", "verify"],
                        }
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        self.git("add", ".")
        self.git("commit", "-m", "initial")
        self.main_commit = self.git("rev-parse", "HEAD")

    def tearDown(self) -> None:
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=self.root,
            capture_output=True,
            check=False,
        )
        self.temp.cleanup()

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            self.fail(result.stderr)
        return result.stdout.strip()

    def invoke(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(RUNNER), "--cwd", str(self.root), *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )

    def events(self, result: subprocess.CompletedProcess[str]) -> list[dict[str, object]]:
        return [json.loads(line) for line in result.stdout.splitlines() if line.strip().startswith("{")]

    def test_dirty_control_worktree_is_preserved_during_prepare(self) -> None:
        (self.root / "package.json").write_text(
            json.dumps({"name": "release-test", "version": "9.9.9"}, indent=2) + "\n",
            encoding="utf-8",
        )
        (self.root / "staged.txt").write_text("keep me staged\n", encoding="utf-8")
        self.git("add", "staged.txt")
        (self.root / "unrelated.txt").write_text("keep me dirty\n", encoding="utf-8")

        prepared = self.invoke(
            "--authorized",
            "release",
            "prepare",
            "--version",
            "1.1.0",
            "--target",
            "test",
        )

        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        self.assertEqual(self.git("rev-parse", "main"), self.main_commit)
        self.assertTrue((self.root / "unrelated.txt").is_file())
        status = self.git("status", "--short")
        self.assertIn("M package.json", status)
        self.assertIn("A  staged.txt", status)
        self.assertIn("?? unrelated.txt", status)
        self.assertTrue(self.git("show-ref", "--verify", "refs/heads/release/v1.1.0"))
        event = self.events(prepared)[-1]
        self.assertEqual(event["event"], "release_prepared")
        self.assertEqual(event["sourceCommit"], self.main_commit)
        self.assertTrue(event["controlWorktreeAfter"]["dirty"])
        self.assertEqual(
            event["releaseBoundary"],
            {
                "identityAuthority": "retained_lineage",
                "controlWorktreeAfterFreeze": "excluded",
                "postReleaseIntegration": "separate",
            },
        )

    def test_control_worktree_changes_after_prepare_do_not_block_release(self) -> None:
        prepared = self.invoke(
            "--authorized", "release", "prepare", "--version", "1.1.0", "--target", "test"
        )
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        (self.root / "after-prepare.txt").write_text("not part of the release\n", encoding="utf-8")

        released = self.invoke(
            "--authorized", "release", "run", "--version", "1.1.0", "--target", "test"
        )

        self.assertEqual(released.returncode, 0, released.stderr)
        self.assertEqual(self.git("rev-parse", "main"), self.main_commit)
        self.assertIn("?? after-prepare.txt", self.git("status", "--short"))
        event = self.events(released)[-1]
        self.assertEqual(event["event"], "release_completed")
        self.assertEqual(event["releaseBoundary"]["identityAuthority"], "retained_lineage")
        self.assertEqual(event["releaseBoundary"]["postReleaseIntegration"], "separate")

    def test_dirty_required_main_sync_is_not_reported_as_release_failure(self) -> None:
        self.git("switch", "-c", "legacy-release")
        (self.root / "legacy.txt").write_text("legacy release\n", encoding="utf-8")
        self.git("add", "legacy.txt")
        self.git("commit", "-m", "legacy release")
        self.git("tag", "-a", "v1.0.1", "-m", "Release v1.0.1")
        self.git("switch", "main")
        (self.root / "unrelated.txt").write_text("keep me dirty\n", encoding="utf-8")

        blocked = self.invoke("--authorized", "release", "sync-main")

        self.assertEqual(blocked.returncode, 2, blocked.stderr)
        event = self.events(blocked)[-1]
        self.assertEqual(event["event"], "main_sync_failed")
        self.assertEqual(event["scope"], "integration_branch")
        self.assertEqual(event["releaseStatus"], "unchanged")
        self.assertEqual(event["code"], "MAIN_SYNC_REQUIRES_CLEAN_CONTROL_WORKTREE")

    def test_release_run_tags_then_fixed_tag_retry_reuses_artifact(self) -> None:
        prepared = self.invoke(
            "--authorized", "release", "prepare", "--version", "1.1.0", "--target", "test"
        )
        self.assertEqual(prepared.returncode, 0, prepared.stderr)

        released = self.invoke(
            "--authorized", "release", "run", "--version", "1.1.0", "--target", "test"
        )
        self.assertEqual(released.returncode, 0, released.stderr)
        tag_commit = self.git("rev-parse", "v1.1.0^{commit}")
        self.assertEqual(tag_commit, self.git("rev-parse", "release/v1.1.0"))
        self.assertEqual(self.git("cat-file", "-t", "refs/tags/v1.1.0"), "tag")

        retried = self.invoke(
            "--authorized", "release", "retry", "--tag", "v1.1.0", "--target", "test"
        )
        self.assertEqual(retried.returncode, 0, retried.stderr)
        retry_event = self.events(retried)[-1]
        self.assertEqual(retry_event["event"], "release_retry_completed")
        self.assertEqual(retry_event["commit"], tag_commit)

    def test_promote_same_release_commit_freezes_new_target_without_source_commit(self) -> None:
        prepared = self.invoke(
            "--authorized", "release", "prepare", "--version", "1.1.0", "--target", "test"
        )
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        released = self.invoke(
            "--authorized", "release", "run", "--version", "1.1.0", "--target", "test"
        )
        self.assertEqual(released.returncode, 0, released.stderr)
        release_commit = self.git("rev-parse", "v1.1.0^{commit}")
        branch_commit = self.git("rev-parse", "release/v1.1.0")

        config_path = self.root / ".agents" / "skills-config" / "project-governance" / "release-workflow.json"
        moving_config = json.loads(config_path.read_text(encoding="utf-8"))
        del moving_config["targets"]["production"]
        config_path.write_text(json.dumps(moving_config, indent=2) + "\n", encoding="utf-8")
        self.git("add", str(config_path.relative_to(self.root)))
        self.git("commit", "-m", "change moving deployment config")

        planned = self.invoke(
            "release", "promote-plan", "--tag", "v1.1.0", "--target", "production"
        )
        self.assertEqual(planned.returncode, 0, planned.stderr)
        self.assertEqual(self.events(planned)[-1]["artifactAction"], "freeze_first_for_target")

        promoted = self.invoke(
            "--authorized", "release", "promote", "--tag", "v1.1.0", "--target", "production"
        )
        self.assertEqual(promoted.returncode, 0, promoted.stderr)
        event = self.events(promoted)[-1]
        self.assertEqual(event["event"], "release_promoted")
        self.assertEqual(event["commit"], release_commit)
        self.assertEqual(self.git("rev-parse", "release/v1.1.0"), branch_commit)
        self.assertEqual(self.git("rev-parse", "v1.1.0^{commit}"), release_commit)

        dev_tags = self.git("tag", "--list", "deploy/test/*/v1.1.0").splitlines()
        production_tags = self.git("tag", "--list", "deploy/production/*/v1.1.0").splitlines()
        self.assertEqual(len(dev_tags), 1)
        self.assertEqual(len(production_tags), 1)
        self.assertEqual(self.git("rev-parse", f"{dev_tags[0]}^{{commit}}"), release_commit)
        self.assertEqual(self.git("rev-parse", f"{production_tags[0]}^{{commit}}"), release_commit)
        annotation = self.git("for-each-ref", "--format=%(contents)", f"refs/tags/{production_tags[0]}")
        evidence = json.loads(annotation)
        self.assertEqual(evidence["releaseCommit"], release_commit)
        self.assertEqual(evidence["target"], "production")
        self.assertEqual(evidence["artifacts"], [{"digest": "sha256:production", "name": "app"}])

        planned_again = self.invoke(
            "release", "promote-plan", "--tag", "v1.1.0", "--target", "production"
        )
        self.assertEqual(planned_again.returncode, 0, planned_again.stderr)
        self.assertEqual(self.events(planned_again)[-1]["artifactAction"], "reuse")
        manifest = Path(event["artifactManifest"])
        frozen_bytes = manifest.read_bytes()
        promoted_again = self.invoke(
            "--authorized", "release", "promote", "--tag", "v1.1.0", "--target", "production"
        )
        self.assertEqual(promoted_again.returncode, 0, promoted_again.stderr)
        self.assertEqual(manifest.read_bytes(), frozen_bytes)

    def test_retry_reads_legacy_single_target_manifest(self) -> None:
        prepared = self.invoke(
            "--authorized", "release", "prepare", "--version", "1.1.0", "--target", "test"
        )
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        released = self.invoke(
            "--authorized", "release", "run", "--version", "1.1.0", "--target", "test"
        )
        self.assertEqual(released.returncode, 0, released.stderr)
        manifest = Path(self.events(released)[-1]["artifactManifest"])
        legacy = manifest.parent.parent / "v1.1.0.json"
        manifest.replace(legacy)

        retried = self.invoke(
            "--authorized", "release", "retry", "--tag", "v1.1.0", "--target", "test"
        )
        self.assertEqual(retried.returncode, 0, retried.stderr)
        self.assertEqual(Path(self.events(retried)[-1]["artifactManifest"]), legacy)

        promoted = self.invoke(
            "--authorized", "release", "promote", "--tag", "v1.1.0", "--target", "production"
        )
        self.assertEqual(promoted.returncode, 0, promoted.stderr)
        production_manifest = Path(self.events(promoted)[-1]["artifactManifest"])
        self.assertNotEqual(production_manifest, legacy)
        self.assertEqual(json.loads(production_manifest.read_text())["target"], "production")

    def test_failed_artifact_freeze_does_not_create_stable_tag(self) -> None:
        path = self.root / ".agents" / "skills-config" / "project-governance" / "release-workflow.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        config["artifact"]["freeze"] = [sys.executable, "hooks.py", "bad"]
        path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        self.git("add", str(path.relative_to(self.root)))
        self.git("commit", "-m", "configure failing freeze")
        prepared = self.invoke(
            "--authorized", "release", "prepare", "--version", "1.1.0", "--target", "test"
        )
        self.assertEqual(prepared.returncode, 0, prepared.stderr)

        released = self.invoke(
            "--authorized", "release", "run", "--version", "1.1.0", "--target", "test"
        )
        self.assertEqual(released.returncode, 1)
        self.assertIn("ARTIFACT_FREEZE_FAILED", released.stdout)
        self.assertFalse(self.git("tag", "--list", "v1.1.0"))

    def test_missing_release_config_fails_closed_without_fallback_deploy(self) -> None:
        path = self.root / ".agents" / "skills-config" / "project-governance" / "release-workflow.json"
        path.unlink()
        self.git("add", "-u")
        self.git("commit", "-m", "remove release config")

        inspected = self.invoke("release", "inspect")
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertEqual(self.events(inspected)[-1]["status"], "bootstrap_required")

        blocked = self.invoke(
            "release", "prepare-plan", "--version", "1.1.0", "--target", "test"
        )
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("RELEASE_WORKFLOW_NOT_CONFIGURED", blocked.stdout)
        self.assertFalse(self.git("branch", "--list", "release/v1.1.0"))

    def test_authorized_bootstrap_writes_scaffold_but_does_not_invent_target(self) -> None:
        path = self.root / ".agents" / "skills-config" / "project-governance" / "release-workflow.json"
        path.unlink()
        self.git("add", "-u")
        self.git("commit", "-m", "remove release config")

        result = self.invoke(
            "--authorized", "release", "bootstrap", "--preset", "node-pnpm"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        scaffold = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(scaffold["version"]["kind"], "package-json")
        self.assertEqual(scaffold["targets"], {})
        self.assertEqual(scaffold["artifact"]["freeze"], [])
        self.assertEqual(self.events(result)[-1]["status"], "hooks_required")

    def test_repair_preparation_requires_immediate_next_patch(self) -> None:
        self.git("tag", "-a", "v1.0.0", "-m", "Release v1.0.0")
        blocked = self.invoke(
            "release",
            "repair-prepare-plan",
            "--base-tag",
            "v1.0.0",
            "--version",
            "1.0.2",
            "--target",
            "test",
        )
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("INVALID_REPAIR_VERSION", blocked.stdout)


if __name__ == "__main__":
    unittest.main()
