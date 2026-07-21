from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "sync_skill_repo.py"
SPEC = importlib.util.spec_from_file_location("sync_skill_repo", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def init_repo(path: Path, remote: str | None = None) -> None:
    path.mkdir(parents=True)
    git(path, "init", "-q")
    git(path, "config", "user.name", "Sync Skill Repo Test")
    git(path, "config", "user.email", "sync-skill-repo@example.test")
    if remote:
        git(path, "remote", "add", "origin", remote)


def write_skill(path: Path, name: str, body: str = "body") -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Test skill.\n---\n\n# Test\n\n{body}\n",
        encoding="utf-8",
    )


class SyncSkillRepoTests(unittest.TestCase):
    def test_normalize_source_variants(self) -> None:
        expected = "github.com/hu-wentao/skills"
        self.assertEqual(MODULE.normalize_source("Hu-Wentao/skills"), expected)
        self.assertEqual(
            MODULE.normalize_source("git@github.com:Hu-Wentao/skills.git"), expected
        )
        self.assertEqual(
            MODULE.normalize_source("https://github.com/Hu-Wentao/skills.git"), expected
        )

    def test_register_and_resolve_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "source"
            registry = root / "registry.json"
            init_repo(repo, "git@github.com:Hu-Wentao/skills.git")

            MODULE.register_repository(repo, registry, None, ["Hu-Wentao/wyatt_skills"])
            MODULE.register_repository(repo, registry, None, [])
            data = MODULE.load_registry(registry)

            self.assertEqual(
                MODULE.resolve_registered_repo(data, "hu-wentao/skills"), repo.resolve()
            )
            self.assertEqual(
                MODULE.resolve_registered_repo(data, "Hu-Wentao/wyatt_skills"),
                repo.resolve(),
            )

    def test_resolve_target_from_skills_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            source_repo = root / "source"
            registry = root / "registry.json"
            init_repo(project)
            init_repo(source_repo, "git@github.com:example/source.git")
            skill = project / ".agents" / "skills" / "demo-skill"
            write_skill(skill, "demo-skill")
            (project / "skills-lock.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skills": {
                            "demo-skill": {
                                "source": "example/source",
                                "skillPath": "packages/skills/demo-skill/SKILL.md",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            MODULE.register_repository(source_repo, registry, None, [])

            target = MODULE.resolve_target(skill, "demo-skill", registry, None, None)

            self.assertEqual(target.repo, source_repo.resolve())
            self.assertEqual(
                target.destination,
                source_repo.resolve() / "packages" / "skills" / "demo-skill",
            )
            self.assertEqual(target.source_id, "example/source")

    def test_reject_destination_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary).resolve()
            with self.assertRaises(MODULE.SyncError):
                MODULE.contained_path(repo, Path("../outside"))

    def test_copy_plan_preserves_destination_only_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            destination = root / "destination"
            write_skill(source, "source", "new")
            write_skill(destination, "source", "old")
            (destination / "legacy.txt").write_text("keep", encoding="utf-8")
            (source / "__pycache__").mkdir()
            (source / "__pycache__" / "ignored.pyc").write_bytes(b"ignored")

            changes, preserved = MODULE.copy_plan(source, destination)

            self.assertIn(("UPDATE", Path("SKILL.md")), changes)
            self.assertIn(Path("legacy.txt"), preserved)
            self.assertNotIn(
                Path("__pycache__/ignored.pyc"), [item[1] for item in changes]
            )

    def test_sync_to_registered_repository_and_push(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            bare = root / "remote.git"
            subprocess.run(
                ["git", "init", "--bare", "-q", str(bare)],
                check=True,
                capture_output=True,
                text=True,
            )

            source_repo = root / "project"
            destination_repo = root / "source"
            registry = root / "registry.json"
            init_repo(source_repo)
            init_repo(destination_repo, str(bare))

            (destination_repo / "README.md").write_text("source\n", encoding="utf-8")
            git(destination_repo, "add", "README.md")
            git(destination_repo, "commit", "-q", "-m", "init")
            git(destination_repo, "branch", "-M", "main")
            git(destination_repo, "push", "-q", "-u", "origin", "main")

            skill = source_repo / ".agents" / "skills" / "demo-skill"
            write_skill(skill, "demo-skill", "before")
            (source_repo / "skills-lock.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skills": {
                            "demo-skill": {
                                "source": "example/source",
                                "skillPath": "skills/demo-skill/SKILL.md",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            git(source_repo, "add", ".agents/skills/demo-skill", "skills-lock.json")
            git(source_repo, "commit", "-q", "-m", "init")
            write_skill(skill, "demo-skill", "after")

            MODULE.register_repository(destination_repo, registry, "example/source", [])
            dry_run = MODULE.main(
                [
                    "sync",
                    str(skill),
                    "--registry",
                    str(registry),
                    "--allow-source-dirty",
                    "--dry-run",
                ]
            )
            self.assertEqual(dry_run, 0)
            self.assertFalse((destination_repo / "skills" / "demo-skill").exists())

            result = MODULE.main(
                [
                    "sync",
                    str(skill),
                    "--registry",
                    str(registry),
                    "--allow-source-dirty",
                ]
            )

            self.assertEqual(result, 0)
            synchronized = destination_repo / "skills" / "demo-skill" / "SKILL.md"
            self.assertIn("after", synchronized.read_text(encoding="utf-8"))
            message = subprocess.run(
                ["git", "-C", str(destination_repo), "log", "-1", "--format=%s"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(message, "feat: sync demo-skill skill")

    def test_refresh_retries_exact_scoped_skill_and_verifies_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            init_repo(project)
            installed = project / ".agents" / "skills" / "demo-skill"
            source = root / "source" / "demo-skill"
            write_skill(installed, "demo-skill", "published")
            write_skill(source, "demo-skill", "published")
            (project / "skills-lock.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skills": {
                            "demo-skill": {
                                "computedHash": "a" * 64,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            args = SimpleNamespace(
                skill_dir=str(installed),
                source_skill_dir=str(source),
                scope="project",
                project_root=str(project),
                lock=None,
                attempts=3,
                retry_delay=0,
            )
            failed = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="temporary failure", stderr=""
            )
            succeeded = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="updated", stderr=""
            )

            with patch.object(MODULE.shutil, "which", return_value="/bin/pnpm"):
                with patch.object(
                    MODULE.subprocess,
                    "run",
                    side_effect=[failed, succeeded],
                ) as run:
                    MODULE.refresh_skill(args)

            self.assertEqual(run.call_count, 2)
            command = run.call_args.args[0]
            self.assertEqual(
                command,
                [
                    "/bin/pnpm",
                    "dlx",
                    "skills",
                    "update",
                    "demo-skill",
                    "-p",
                    "-y",
                ],
            )
            self.assertNotIn("--help", command)

    def test_refresh_failure_reports_every_attempt_and_command(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installed = root / "installed" / "demo-skill"
            source = root / "source" / "demo-skill"
            write_skill(installed, "demo-skill")
            write_skill(source, "demo-skill")
            args = SimpleNamespace(
                skill_dir=str(installed),
                source_skill_dir=str(source),
                scope="global",
                project_root=str(root),
                lock=None,
                attempts=2,
                retry_delay=0,
            )
            failed = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="network error", stderr="detail"
            )

            with patch.object(MODULE.shutil, "which", return_value="/bin/pnpm"):
                with patch.object(
                    MODULE.subprocess,
                    "run",
                    side_effect=[failed, failed],
                ):
                    with self.assertRaisesRegex(
                        MODULE.SyncError,
                        "(?s)attempt 1/2.*network error.*attempt 2/2",
                    ):
                        MODULE.refresh_skill(args)

    def test_push_retries_transient_failure_with_complete_diagnostics(self) -> None:
        failed = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="connection closed"
        )
        succeeded = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="pushed", stderr=""
        )
        with patch.object(
            MODULE.subprocess,
            "run",
            side_effect=[failed, succeeded],
        ) as run:
            MODULE.push_with_retry(Path("/source/repo"), 3, 0)

        self.assertEqual(run.call_count, 2)
        self.assertEqual(
            run.call_args.args[0],
            ["git", "-C", "/source/repo", "push"],
        )


if __name__ == "__main__":
    unittest.main()
