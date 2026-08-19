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
            installed = root / ".agents" / "skills" / "demo-skill"
            source = root / "source" / "demo-skill"
            lock = root / ".agents" / ".skill-lock.json"
            write_skill(installed, "demo-skill")
            write_skill(source, "demo-skill")
            lock.write_text(
                json.dumps({"skills": {"demo-skill": {"skillFolderHash": "a" * 40}}}),
                encoding="utf-8",
            )
            args = SimpleNamespace(
                skill_dir=str(installed),
                source_skill_dir=str(source),
                scope="global",
                project_root=str(root),
                lock=str(lock),
                attempts=2,
                retry_delay=0,
            )
            failed = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="network error", stderr="detail"
            )

            with patch.object(
                MODULE,
                "_shared_global_skills_root",
                return_value=root / ".agents" / "skills",
            ):
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

    def test_scope_auto_resolves_project_installation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            installed = project / ".agents" / "skills" / "demo-skill"
            write_skill(installed, "demo-skill")
            (project / "skills-lock.json").write_text(
                json.dumps({"skills": {"demo-skill": {"computedHash": "a" * 64}}}),
                encoding="utf-8",
            )

            scope = MODULE.resolve_installation_scope(
                installed,
                "demo-skill",
                "auto",
                None,
                None,
                require_tracked=True,
            )

            self.assertEqual(scope.name, "project")
            self.assertEqual(
                scope.project_root, MODULE._absolute_path(project)
            )
            self.assertEqual(
                scope.lock_path,
                MODULE._absolute_path(project / "skills-lock.json"),
            )

    def test_scope_auto_resolves_global_installation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            global_skills = root / ".agents" / "skills"
            installed = global_skills / "demo-skill"
            write_skill(installed, "demo-skill")
            global_lock = global_skills.parent / ".skill-lock.json"
            global_lock.write_text(
                json.dumps({"skills": {"demo-skill": {"skillFolderHash": "b" * 40}}}),
                encoding="utf-8",
            )

            with patch.object(
                MODULE, "_shared_global_skills_root", return_value=global_skills
            ):
                scope = MODULE.resolve_installation_scope(
                    installed,
                    "demo-skill",
                    "auto",
                    None,
                    None,
                    require_tracked=True,
                    allow_no_project_context=True,
                )

            self.assertEqual(scope.name, "global")
            self.assertEqual(
                scope.lock_path, MODULE._absolute_path(global_lock)
            )

    def test_scope_rejects_global_without_project_context_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            global_skills = root / ".agents" / "skills"
            installed = global_skills / "demo-skill"
            write_skill(installed, "demo-skill")

            with patch.object(
                MODULE, "_shared_global_skills_root", return_value=global_skills
            ):
                with self.assertRaisesRegex(
                    MODULE.SyncError, "requires --project-root"
                ):
                    MODULE.resolve_installation_scope(
                        installed,
                        "demo-skill",
                        "auto",
                        None,
                        None,
                        require_tracked=False,
                    )

    def test_scope_rejects_explicit_scope_path_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            installed = project / ".agents" / "skills" / "demo-skill"
            write_skill(installed, "demo-skill")

            with self.assertRaisesRegex(MODULE.SyncError, "conflicts with installed path"):
                MODULE.resolve_installation_scope(
                    installed,
                    "demo-skill",
                    "global",
                    project,
                    None,
                    require_tracked=False,
                )

    def test_scope_rejects_project_and_global_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            global_skills = root / "global" / ".agents" / "skills"
            installed = project / ".agents" / "skills" / "demo-skill"
            global_installed = global_skills / "demo-skill"
            write_skill(installed, "demo-skill")
            write_skill(global_installed, "demo-skill")
            (project / "skills-lock.json").write_text(
                json.dumps({"skills": {"demo-skill": {"computedHash": "a" * 64}}}),
                encoding="utf-8",
            )
            global_lock = global_skills.parent / ".skill-lock.json"
            global_lock.write_text(
                json.dumps({"skills": {"demo-skill": {"skillFolderHash": "b" * 40}}}),
                encoding="utf-8",
            )

            with patch.object(
                MODULE, "_shared_global_skills_root", return_value=global_skills
            ):
                with self.assertRaisesRegex(
                    MODULE.SyncError, "Conflicting project and global installations"
                ):
                    MODULE.resolve_installation_scope(
                        installed,
                        "demo-skill",
                        "auto",
                        project,
                        None,
                        require_tracked=True,
                    )

    def test_scope_rejects_project_install_when_global_is_active(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            global_skills = root / "global" / ".agents" / "skills"
            global_installed = global_skills / "demo-skill"
            write_skill(global_installed, "demo-skill")
            global_lock = global_skills.parent / ".skill-lock.json"
            global_lock.write_text(
                json.dumps({"skills": {"demo-skill": {"skillFolderHash": "b" * 40}}}),
                encoding="utf-8",
            )

            with patch.object(
                MODULE, "_shared_global_skills_root", return_value=global_skills
            ):
                with self.assertRaisesRegex(
                    MODULE.SyncError, "active global installation already exists"
                ):
                    MODULE.resolve_installation_scope(
                        project / ".agents" / "skills" / "demo-skill",
                        "demo-skill",
                        "auto",
                        project,
                        None,
                        require_tracked=False,
                    )

    def test_scope_rejects_global_install_when_project_is_active(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            global_skills = root / "global" / ".agents" / "skills"
            project_installed = project / ".agents" / "skills" / "demo-skill"
            write_skill(project_installed, "demo-skill")
            (project / "skills-lock.json").write_text(
                json.dumps({"skills": {"demo-skill": {"computedHash": "a" * 64}}}),
                encoding="utf-8",
            )

            with patch.object(
                MODULE, "_shared_global_skills_root", return_value=global_skills
            ):
                with self.assertRaisesRegex(
                    MODULE.SyncError, "active project installation already exists"
                ):
                    MODULE.resolve_installation_scope(
                        global_skills / "demo-skill",
                        "demo-skill",
                        "auto",
                        project,
                        None,
                        require_tracked=False,
                    )

    def test_scope_inference_preserves_global_symlink_location(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            global_skills = root / ".agents" / "skills"
            source = root / "source" / "demo-skill"
            installed = global_skills / "demo-skill"
            write_skill(source, "demo-skill")
            global_skills.mkdir(parents=True)
            installed.symlink_to(source, target_is_directory=True)
            global_lock = global_skills.parent / ".skill-lock.json"
            global_lock.write_text(
                json.dumps({"skills": {"demo-skill": {"skillFolderHash": "b" * 40}}}),
                encoding="utf-8",
            )

            with patch.object(
                MODULE, "_shared_global_skills_root", return_value=global_skills
            ):
                scope = MODULE.resolve_installation_scope(
                    installed,
                    "demo-skill",
                    "auto",
                    None,
                    None,
                    require_tracked=True,
                    allow_no_project_context=True,
                )

            self.assertEqual(scope.name, "global")
            self.assertEqual(
                scope.expected_skill, MODULE._absolute_path(installed)
            )

    def test_scope_inference_preserves_project_symlink_location(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            source = root / "source" / "demo-skill"
            installed = project / ".agents" / "skills" / "demo-skill"
            write_skill(source, "demo-skill")
            installed.parent.mkdir(parents=True)
            installed.symlink_to(source, target_is_directory=True)
            (project / "skills-lock.json").write_text(
                json.dumps({"skills": {"demo-skill": {"computedHash": "a" * 64}}}),
                encoding="utf-8",
            )

            scope = MODULE.resolve_installation_scope(
                installed,
                "demo-skill",
                "auto",
                project,
                None,
                require_tracked=True,
            )

            self.assertEqual(scope.name, "project")
            self.assertEqual(
                scope.expected_skill, MODULE._absolute_path(installed)
            )

    def test_scope_inference_preserves_symlinked_global_skills_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            agents_root = root / "logical" / ".agents"
            storage_skills = root / "storage" / "skills"
            agents_root.mkdir(parents=True)
            storage_skills.mkdir(parents=True)
            (agents_root / "skills").symlink_to(storage_skills, target_is_directory=True)
            installed = agents_root / "skills" / "demo-skill"
            write_skill(installed, "demo-skill")
            global_lock = agents_root / ".skill-lock.json"
            global_lock.write_text(
                json.dumps({"skills": {"demo-skill": {"skillFolderHash": "b" * 40}}}),
                encoding="utf-8",
            )

            with patch.object(
                MODULE,
                "_shared_global_skills_root",
                return_value=agents_root / "skills",
            ):
                scope = MODULE.resolve_installation_scope(
                    installed,
                    "demo-skill",
                    "auto",
                    None,
                    None,
                    require_tracked=True,
                    allow_no_project_context=True,
                )

            self.assertEqual(scope.name, "global")
            self.assertEqual(scope.lock_path, MODULE._absolute_path(global_lock))

    def test_scope_inference_preserves_symlinked_project_agents_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            storage_agents = root / "storage" / ".agents"
            project.mkdir()
            (storage_agents / "skills").mkdir(parents=True)
            (project / ".agents").symlink_to(storage_agents, target_is_directory=True)
            installed = project / ".agents" / "skills" / "demo-skill"
            write_skill(installed, "demo-skill")
            (project / "skills-lock.json").write_text(
                json.dumps({"skills": {"demo-skill": {"computedHash": "a" * 64}}}),
                encoding="utf-8",
            )

            scope = MODULE.resolve_installation_scope(
                installed,
                "demo-skill",
                "auto",
                project,
                None,
                require_tracked=True,
            )

            self.assertEqual(scope.name, "project")
            self.assertEqual(scope.project_root, MODULE._absolute_path(project))

    def test_scope_rejects_lock_override_from_another_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            global_skills = root / "global" / ".agents" / "skills"
            project_installed = project / ".agents" / "skills" / "demo-skill"
            global_installed = global_skills / "demo-skill"
            write_skill(project_installed, "demo-skill")
            write_skill(global_installed, "demo-skill")
            (project / "skills-lock.json").write_text(
                json.dumps({"skills": {"demo-skill": {"computedHash": "a" * 64}}}),
                encoding="utf-8",
            )
            custom_lock = root / "custom-global-lock.json"
            custom_lock.write_text(
                json.dumps({"skills": {"demo-skill": {"skillFolderHash": "b" * 40}}}),
                encoding="utf-8",
            )

            with patch.object(
                MODULE, "_shared_global_skills_root", return_value=global_skills
            ):
                with self.assertRaisesRegex(
                    MODULE.SyncError, "does not belong to global installation"
                ):
                    MODULE.resolve_installation_scope(
                        global_installed,
                        "demo-skill",
                        "global",
                        project,
                        custom_lock,
                        require_tracked=True,
                    )

    def test_install_global_targets_only_codex(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installed = root / ".agents" / "skills" / "demo-skill"
            source = root / "source" / "demo-skill"
            write_skill(installed, "demo-skill", "published")
            write_skill(source, "demo-skill", "published")
            lock = root / ".agents" / ".skill-lock.json"
            lock.parent.mkdir(exist_ok=True)
            lock.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skills": {
                            "demo-skill": {
                                "computedHash": "b" * 64,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            args = SimpleNamespace(
                source="Hu-Wentao/skills",
                skill_dir=str(installed),
                source_skill_dir=str(source),
                scope="global",
                agent="codex",
                project_root=str(root),
                lock=str(lock),
                attempts=3,
                retry_delay=0,
            )
            succeeded = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="installed", stderr=""
            )

            with patch.object(
                MODULE,
                "_shared_global_skills_root",
                return_value=root / ".agents" / "skills",
            ):
                with patch.object(MODULE.shutil, "which", return_value="/bin/pnpm"):
                    with patch.object(
                        MODULE.subprocess,
                        "run",
                        return_value=succeeded,
                    ) as run:
                        MODULE.install_skill(args)

            self.assertEqual(
                run.call_args.args[0],
                [
                    "/bin/pnpm",
                    "dlx",
                    "skills",
                    "add",
                    "Hu-Wentao/skills",
                    "--skill",
                    "demo-skill",
                    "--agent",
                    "codex",
                    "--global",
                    "--yes",
                ],
            )
            self.assertNotIn("--copy", run.call_args.args[0])
            self.assertNotIn("*", run.call_args.args[0])

    def test_global_lock_accepts_legacy_git_tree_skill_folder_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / ".skill-lock.json"
            lock.write_text(
                json.dumps(
                    {
                        "version": 3,
                        "skills": {
                            "demo-skill": {
                                "skillFolderHash": "d" * 40,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                MODULE._verified_lock_hash(lock, "demo-skill"),
                "d" * 40,
            )

    def test_global_lock_accepts_sha256_skill_folder_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / ".skill-lock.json"
            lock.write_text(
                json.dumps(
                    {
                        "version": 3,
                        "skills": {
                            "demo-skill": {
                                "skillFolderHash": "e" * 64,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                MODULE._verified_lock_hash(lock, "demo-skill"),
                "e" * 64,
            )

    def test_global_lock_rejects_unknown_skill_folder_hash_length(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / ".skill-lock.json"
            lock.write_text(
                json.dumps(
                    {
                        "version": 3,
                        "skills": {
                            "demo-skill": {
                                "skillFolderHash": "f" * 63,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                MODULE.SyncError,
                "invalid demo-skill skillFolderHash",
            ):
                MODULE._verified_lock_hash(lock, "demo-skill")

    def test_install_project_omits_global_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installed = root / ".agents" / "skills" / "demo-skill"
            source = root / "source" / "demo-skill"
            write_skill(installed, "demo-skill", "published")
            write_skill(source, "demo-skill", "published")
            (root / "skills-lock.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skills": {
                            "demo-skill": {
                                "computedHash": "c" * 64,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            args = SimpleNamespace(
                source="Hu-Wentao/skills",
                skill_dir=str(installed),
                source_skill_dir=str(source),
                scope="project",
                agent="codex",
                project_root=str(root),
                lock=None,
                attempts=3,
                retry_delay=0,
            )
            succeeded = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="installed", stderr=""
            )

            with patch.object(MODULE.shutil, "which", return_value="/bin/pnpm"):
                with patch.object(
                    MODULE.subprocess,
                    "run",
                    return_value=succeeded,
                ) as run:
                    MODULE.install_skill(args)

            self.assertNotIn("--global", run.call_args.args[0])
            self.assertIn("codex", run.call_args.args[0])

    def test_install_rejects_wildcard_agent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source" / "demo-skill"
            write_skill(source, "demo-skill", "published")
            args = SimpleNamespace(
                source="Hu-Wentao/skills",
                skill_dir=str(root / ".agents" / "skills" / "demo-skill"),
                source_skill_dir=str(source),
                scope="global",
                agent="*",
                project_root=str(root),
                lock=None,
                attempts=3,
                retry_delay=0,
            )

            with patch.object(MODULE.shutil, "which", return_value="/bin/pnpm"):
                with self.assertRaisesRegex(
                    MODULE.SyncError,
                    "one explicit agent",
                ):
                    MODULE.install_skill(args)

    def test_permission_failure_is_not_retried(self) -> None:
        failed = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="EPERM: operation not permitted, unlink '/home/me/.agents/skills'",
        )
        with patch.object(
            MODULE.subprocess,
            "run",
            return_value=failed,
        ) as run:
            with self.assertRaisesRegex(
                MODULE.SyncError,
                "non-retryable filesystem permission error",
            ):
                MODULE._run_installer_with_retry(
                    ["pnpm", "dlx", "skills", "add"],
                    cwd=Path("/tmp"),
                    attempts=3,
                    retry_delay=0,
                    action="Install",
                )

        self.assertEqual(run.call_count, 1)

    def test_installed_comparison_allows_normalized_executable_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            installed = root / "installed"
            write_skill(source, "source")
            write_skill(installed, "source")
            source_script = source / "scripts" / "tool.py"
            installed_script = installed / "scripts" / "tool.py"
            source_script.parent.mkdir()
            installed_script.parent.mkdir()
            source_script.write_text("print('ok')\n", encoding="utf-8")
            installed_script.write_text("print('ok')\n", encoding="utf-8")
            source_script.chmod(0o755)
            installed_script.chmod(0o644)

            self.assertEqual(
                MODULE.installed_content_changes(source, installed),
                [],
            )
            changes, _ = MODULE.copy_plan(source, installed)
            self.assertIn(("UPDATE", Path("scripts/tool.py")), changes)

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
