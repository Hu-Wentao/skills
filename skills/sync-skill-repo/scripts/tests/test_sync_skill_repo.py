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


def configure_github_upstream(repo: Path) -> None:
    git(repo, "branch", "-M", "main")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(repo, "config", "branch.main.remote", "origin")
    git(repo, "config", "branch.main.merge", "refs/heads/main")


def publish_args(
    skill: Path,
    *,
    installed: Path | None = None,
    push: bool = True,
    reinstall: bool = True,
) -> SimpleNamespace:
    project_root = None
    if installed is not None:
        project_root = MODULE._project_root_from_installed_path(
            MODULE._absolute_path(installed), installed.name
        )
    return SimpleNamespace(
        skill_dir=str(skill),
        repo=None,
        destination=None,
        registry=str(Path.home() / ".codex" / "unused-test-registry.json"),
        message=None,
        push=push,
        reinstall=reinstall,
        project_root=str(project_root) if project_root else None,
        allow_dirty=False,
        expected_upstream_head=None,
        expected_source_head=None,
        push_attempts=3,
        push_retry_delay=0,
        attempts=3,
        retry_delay=0,
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

    def test_resolve_target_uses_legacy_default_when_skill_path_is_missing(self) -> None:
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
                            "demo-skill": {"source": "example/source"}
                        },
                    }
                ),
                encoding="utf-8",
            )
            MODULE.register_repository(source_repo, registry, None, [])

            target = MODULE.resolve_target(skill, "demo-skill", registry, None, None)

            self.assertEqual(
                target.destination,
                source_repo.resolve() / "skills" / "demo-skill",
            )

    def test_invalid_lock_skill_path_for_another_skill_fails_before_registry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            source_repo = root / "source"
            skill = project / ".agents" / "skills" / "demo-skill"
            destination = source_repo / "skills" / "other-skill"
            write_skill(skill, "demo-skill", "project content")
            write_skill(destination, "other-skill", "preserve destination")
            before = (destination / "SKILL.md").read_text(encoding="utf-8")
            (project / "skills-lock.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skills": {
                            "demo-skill": {
                                "source": "example/source",
                                "skillPath": "skills/other-skill/SKILL.md",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(MODULE, "load_registry") as registry:
                with self.assertRaisesRegex(
                    MODULE.SyncError, "present invalid skillPath"
                ):
                    MODULE.resolve_target(
                        skill,
                        "demo-skill",
                        root / "registry.json",
                        None,
                        None,
                    )

            registry.assert_not_called()
            self.assertEqual(
                (destination / "SKILL.md").read_text(encoding="utf-8"), before
            )

    def test_invalid_lock_skill_path_with_nested_git_fails_before_registry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            source_repo = root / "source"
            skill = project / ".agents" / "skills" / "demo-skill"
            destination = source_repo / "packages" / ".GIT" / "demo-skill"
            write_skill(skill, "demo-skill", "project content")
            write_skill(destination, "demo-skill", "preserve destination")
            before = (destination / "SKILL.md").read_text(encoding="utf-8")
            (project / "skills-lock.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skills": {
                            "demo-skill": {
                                "source": "example/source",
                                "skillPath": "packages/.GIT/demo-skill/SKILL.md",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(MODULE, "load_registry") as registry:
                with self.assertRaisesRegex(
                    MODULE.SyncError, "present invalid skillPath"
                ):
                    MODULE.resolve_target(
                        skill,
                        "demo-skill",
                        root / "registry.json",
                        None,
                        None,
                    )

            registry.assert_not_called()
            self.assertEqual(
                (destination / "SKILL.md").read_text(encoding="utf-8"), before
            )

    def test_project_private_tracked_skill_rejects_direct_source_publish(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "application"
            init_repo(project, "git@github.com:example/application.git")
            skill = project / ".agents" / "skills" / "demo-skill"
            write_skill(skill, "demo-skill")
            git(project, "add", ".")
            git(project, "commit", "-q", "-m", "init")
            configure_github_upstream(project)
            args = publish_args(skill, reinstall=False)

            with (
                patch.object(MODULE, "_direct_source_context") as direct,
                patch.object(MODULE, "load_registry") as registry,
                patch.object(MODULE, "_commit_skill") as commit,
                patch.object(MODULE, "push_source_with_retry") as push,
                patch.object(MODULE, "resolve_named_update_targets") as update,
            ):
                with self.assertRaisesRegex(
                    MODULE.SyncError,
                    "project-private skill source owned by the current project",
                ) as error:
                    MODULE.publish_skill(args)

            direct.assert_not_called()
            registry.assert_not_called()
            commit.assert_not_called()
            push.assert_not_called()
            update.assert_not_called()
            self.assertNotIn("Hu-Wentao/skills", str(error.exception))

    def test_project_private_untracked_skill_uses_same_classification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "application"
            init_repo(project, "git@github.com:example/application.git")
            (project / "README.md").write_text("app\n", encoding="utf-8")
            git(project, "add", "README.md")
            git(project, "commit", "-q", "-m", "init")
            configure_github_upstream(project)
            skill = project / ".agents" / "skills" / "demo-skill"
            write_skill(skill, "demo-skill")

            context = MODULE._project_skill_input(skill, "demo-skill")

            self.assertIsNotNone(context)
            assert context is not None
            self.assertTrue(context.is_private_source)
            self.assertEqual(context.project_root, MODULE._absolute_path(project))
            with self.assertRaisesRegex(MODULE.SyncError, "project-private"):
                MODULE.publish_skill(publish_args(skill, reinstall=False))

    def test_project_private_classification_preserves_logical_symlink_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "application"
            source = root / "shared-source"
            init_repo(project, "git@github.com:example/application.git")
            init_repo(source, "git@github.com:example/shared.git")
            shared_skill = source / "skills" / "demo-skill"
            write_skill(shared_skill, "demo-skill")
            git(source, "add", ".")
            git(source, "commit", "-q", "-m", "init")
            configure_github_upstream(source)
            installed = project / ".agents" / "skills" / "demo-skill"
            installed.parent.mkdir(parents=True)
            installed.symlink_to(shared_skill, target_is_directory=True)

            context = MODULE._project_skill_input(installed, "demo-skill")

            self.assertIsNotNone(context)
            assert context is not None
            self.assertTrue(context.is_private_source)
            with patch.object(MODULE, "_direct_source_context") as direct:
                with self.assertRaisesRegex(MODULE.SyncError, "project-private"):
                    MODULE.publish_skill(
                        publish_args(installed, reinstall=False)
                    )
            direct.assert_not_called()

    def test_reverse_global_symlink_to_project_private_rejects_publish(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "application"
            global_skills = root / "home" / ".agents" / "skills"
            init_repo(project, "git@github.com:example/application.git")
            project_skill = project / ".agents" / "skills" / "demo-skill"
            write_skill(project_skill, "demo-skill")
            git(project, "add", ".")
            git(project, "commit", "-q", "-m", "init")
            configure_github_upstream(project)
            alias = global_skills / "demo-skill"
            alias.parent.mkdir(parents=True)
            alias.symlink_to(project_skill, target_is_directory=True)

            with (
                patch.object(
                    MODULE, "_shared_global_skills_root", return_value=global_skills
                ),
                patch.object(MODULE, "_direct_source_context") as direct,
                patch.object(MODULE, "load_registry") as registry,
                patch.object(MODULE, "_commit_skill") as commit,
                patch.object(MODULE, "push_source_with_retry") as push,
                patch.object(MODULE, "resolve_named_update_targets") as update,
            ):
                with self.assertRaisesRegex(MODULE.SyncError, "project-private"):
                    MODULE.publish_skill(publish_args(alias))

            direct.assert_not_called()
            registry.assert_not_called()
            commit.assert_not_called()
            push.assert_not_called()
            update.assert_not_called()

    def test_global_symlink_to_shared_source_remains_direct_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "shared-source"
            global_skills = root / "home" / ".agents" / "skills"
            init_repo(source, "git@github.com:example/shared.git")
            shared_skill = source / "skills" / "demo-skill"
            write_skill(shared_skill, "demo-skill")
            git(source, "add", ".")
            git(source, "commit", "-q", "-m", "init")
            configure_github_upstream(source)
            alias = global_skills / "demo-skill"
            alias.parent.mkdir(parents=True)
            alias.symlink_to(shared_skill, target_is_directory=True)

            with patch.object(
                MODULE, "_shared_global_skills_root", return_value=global_skills
            ):
                receipt, local_skill, target = MODULE._resolve_publish_receipt(
                    publish_args(alias, reinstall=False)
                )

            self.assertEqual(local_skill, MODULE._absolute_path(alias))
            self.assertIsNone(target)
            self.assertEqual(receipt.source.repo, source.resolve())
            self.assertEqual(receipt.source.skill_dir, shared_skill.resolve())

    def test_reverse_global_symlink_to_project_private_rejects_sync_override(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "application"
            global_skills = root / "home" / ".agents" / "skills"
            destination = root / "shared-source"
            init_repo(project, "git@github.com:example/application.git")
            init_repo(destination, "git@github.com:example/shared.git")
            project_skill = project / ".agents" / "skills" / "demo-skill"
            write_skill(project_skill, "demo-skill")
            alias = global_skills / "demo-skill"
            alias.parent.mkdir(parents=True)
            alias.symlink_to(project_skill, target_is_directory=True)
            target = destination / "skills" / "demo-skill"
            write_skill(target, "demo-skill", "preserve destination")
            before = (target / "SKILL.md").read_text(encoding="utf-8")
            args = MODULE.build_parser().parse_args(
                [
                    "sync",
                    str(alias),
                    "--repo",
                    str(destination),
                    "--destination",
                    "skills/demo-skill",
                ]
            )

            with (
                patch.object(
                    MODULE, "_shared_global_skills_root", return_value=global_skills
                ),
                patch.object(MODULE, "load_registry") as registry,
                patch.object(MODULE, "push_with_retry") as push,
            ):
                with self.assertRaisesRegex(MODULE.SyncError, "project-private"):
                    MODULE.sync_skill(args)

            registry.assert_not_called()
            push.assert_not_called()
            self.assertEqual(
                (target / "SKILL.md").read_text(encoding="utf-8"), before
            )

    def test_resolved_project_private_boundary_ignores_target_basename(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "application"
            destination = root / "shared-source"
            init_repo(project, "git@github.com:example/application.git")
            init_repo(destination, "git@github.com:example/shared.git")
            project_skill = project / ".agents" / "skills" / "private-target"
            write_skill(project_skill, "demo-skill")
            alias = root / "aliases" / "demo-skill"
            alias.parent.mkdir(parents=True)
            alias.symlink_to(project_skill, target_is_directory=True)
            args = MODULE.build_parser().parse_args(
                [
                    "sync",
                    str(alias),
                    "--repo",
                    str(destination),
                    "--destination",
                    "skills/demo-skill",
                ]
            )

            with (
                patch.object(MODULE, "load_registry") as registry,
                patch.object(MODULE, "push_with_retry") as push,
            ):
                with self.assertRaisesRegex(MODULE.SyncError, "project-private"):
                    MODULE.sync_skill(args)

            registry.assert_not_called()
            push.assert_not_called()
            self.assertFalse((destination / "skills" / "demo-skill").exists())

    def test_project_private_ignores_same_name_global_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "application"
            global_skills = root / "global" / ".agents" / "skills"
            init_repo(project, "git@github.com:example/application.git")
            skill = project / ".agents" / "skills" / "demo-skill"
            write_skill(skill, "demo-skill")
            global_lock = global_skills.parent / ".skill-lock.json"
            global_lock.parent.mkdir(parents=True)
            global_lock.write_text(
                json.dumps(
                    {
                        "version": 3,
                        "skills": {
                            "demo-skill": {
                                "source": "example/shared",
                                "skillPath": "skills/demo-skill/SKILL.md",
                                "skillFolderHash": "a" * 40,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(
                MODULE, "_shared_global_skills_root", return_value=global_skills
            ):
                with patch.object(MODULE, "resolve_named_update_targets") as update:
                    with patch.object(MODULE, "load_registry") as registry:
                        with self.assertRaisesRegex(
                            MODULE.SyncError, "project-private"
                        ):
                            MODULE.publish_skill(publish_args(skill))

            update.assert_not_called()
            registry.assert_not_called()

    def test_valid_project_lock_precedes_tracked_direct_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "application"
            source_repo = root / "shared-source"
            registry = root / "registry.json"
            init_repo(project, "git@github.com:example/application.git")
            init_repo(source_repo, "git@github.com:example/shared.git")
            skill = project / ".agents" / "skills" / "demo-skill"
            write_skill(skill, "demo-skill")
            (project / "skills-lock.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skills": {
                            "demo-skill": {
                                "source": "example/shared",
                                "skillPath": "skills/demo-skill/SKILL.md",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            git(project, "add", ".")
            git(project, "commit", "-q", "-m", "init")
            configure_github_upstream(project)
            (source_repo / "README.md").write_text("source\n", encoding="utf-8")
            git(source_repo, "add", ".")
            git(source_repo, "commit", "-q", "-m", "init")
            configure_github_upstream(source_repo)
            MODULE.register_repository(
                source_repo, registry, "example/shared", []
            )
            args = publish_args(skill, reinstall=False)
            args.registry = str(registry)

            with patch.object(MODULE, "_direct_source_context") as direct:
                receipt, local_skill, target = MODULE._resolve_publish_receipt(args)

            direct.assert_not_called()
            self.assertEqual(local_skill, MODULE._absolute_path(skill))
            self.assertIsNotNone(target)
            assert target is not None
            self.assertEqual(target.repo, source_repo.resolve())
            self.assertEqual(receipt.source.repo, source_repo.resolve())

    def test_invalid_matching_project_lock_fails_closed_before_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "application"
            init_repo(project, "git@github.com:example/application.git")
            skill = project / ".agents" / "skills" / "demo-skill"
            write_skill(skill, "demo-skill")
            (project / "skills-lock.json").write_text(
                json.dumps(
                    {
                        "skills": {
                            "demo-skill": {
                                "source": "example/shared",
                                "skillPath": "skills/demo-skill/SKILL.md",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            git(project, "add", ".")
            git(project, "commit", "-q", "-m", "init")
            configure_github_upstream(project)

            with patch.object(MODULE, "_direct_source_context") as direct:
                with patch.object(MODULE, "load_registry") as registry:
                    with self.assertRaisesRegex(
                        MODULE.SyncError,
                        "invalid or incomplete; ownership is ambiguous",
                    ):
                        MODULE.publish_skill(
                            publish_args(skill, reinstall=False)
                        )

            direct.assert_not_called()
            registry.assert_not_called()

    def test_project_lock_directory_fails_closed_before_source_detection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "application"
            skill = project / ".agents" / "skills" / "demo-skill"
            write_skill(skill, "demo-skill")
            (project / "skills-lock.json").mkdir()

            with (
                patch.object(MODULE, "_direct_source_context") as direct,
                patch.object(MODULE, "load_registry") as registry,
            ):
                with self.assertRaisesRegex(
                    MODULE.SyncError, "not a usable regular file"
                ):
                    MODULE.publish_skill(publish_args(skill, reinstall=False))

            direct.assert_not_called()
            registry.assert_not_called()

    def test_broken_project_lock_symlink_fails_closed_before_source_detection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "application"
            skill = project / ".agents" / "skills" / "demo-skill"
            write_skill(skill, "demo-skill")
            (project / "skills-lock.json").symlink_to(
                project / "missing-lock-target.json"
            )

            with (
                patch.object(MODULE, "_direct_source_context") as direct,
                patch.object(MODULE, "load_registry") as registry,
            ):
                with self.assertRaisesRegex(
                    MODULE.SyncError, "not a usable regular file"
                ):
                    MODULE.publish_skill(publish_args(skill, reinstall=False))

            direct.assert_not_called()
            registry.assert_not_called()

    def test_valid_project_lock_symlink_fails_closed_before_source_detection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "application"
            skill = project / ".agents" / "skills" / "demo-skill"
            write_skill(skill, "demo-skill")
            external_lock = root / "external-lock.json"
            external_lock.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skills": {
                            "demo-skill": {
                                "source": "example/shared",
                                "skillPath": "skills/demo-skill/SKILL.md",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            (project / "skills-lock.json").symlink_to(external_lock)

            with (
                patch.object(MODULE, "_direct_source_context") as direct,
                patch.object(MODULE, "load_registry") as registry,
            ):
                with self.assertRaisesRegex(
                    MODULE.SyncError, "not a usable regular file"
                ):
                    MODULE.publish_skill(publish_args(skill, reinstall=False))

            direct.assert_not_called()
            registry.assert_not_called()

    def test_publish_repo_override_cannot_migrate_project_private_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "application"
            destination = root / "shared-source"
            init_repo(project, "git@github.com:example/application.git")
            init_repo(destination, "git@github.com:example/shared.git")
            skill = project / ".agents" / "skills" / "demo-skill"
            write_skill(skill, "demo-skill")
            args = publish_args(skill, reinstall=False)
            args.repo = str(destination)
            args.destination = "skills/demo-skill"

            with patch.object(MODULE, "load_registry") as registry:
                with self.assertRaisesRegex(MODULE.SyncError, "project-private"):
                    MODULE.publish_skill(args)

            registry.assert_not_called()
            self.assertFalse((destination / "skills" / "demo-skill").exists())

    def test_sync_repo_override_cannot_migrate_project_private_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "application"
            destination = root / "shared-source"
            init_repo(project, "git@github.com:example/application.git")
            init_repo(destination, "git@github.com:example/shared.git")
            skill = project / ".agents" / "skills" / "demo-skill"
            write_skill(skill, "demo-skill")
            args = MODULE.build_parser().parse_args(
                [
                    "sync",
                    str(skill),
                    "--repo",
                    str(destination),
                    "--destination",
                    "skills/demo-skill",
                ]
            )

            with patch.object(MODULE, "load_registry") as registry:
                with patch.object(MODULE, "push_with_retry") as push:
                    with self.assertRaisesRegex(
                        MODULE.SyncError, "project-private"
                    ):
                        MODULE.sync_skill(args)

            registry.assert_not_called()
            push.assert_not_called()
            self.assertFalse((destination / "skills" / "demo-skill").exists())

    def test_explicit_non_project_lockless_copy_remains_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy = root / "copies" / "demo-skill"
            destination = root / "shared-source"
            write_skill(copy, "demo-skill")
            init_repo(destination, "git@github.com:example/shared.git")

            target = MODULE.resolve_target(
                copy,
                "demo-skill",
                root / "unused-registry.json",
                destination,
                Path("packages/demo-skill"),
            )

            self.assertEqual(target.repo, destination.resolve())
            self.assertEqual(
                target.destination,
                destination.resolve() / "packages" / "demo-skill",
            )
            self.assertIsNone(target.lock_path)

    def test_project_skills_config_is_not_a_publication_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = (
                Path(temporary)
                / "application"
                / ".agents"
                / "skills-config"
                / "demo-skill"
            )
            config.mkdir(parents=True)
            (config / "config.yaml").write_text("schema: test\n", encoding="utf-8")
            args = publish_args(config, reinstall=False)

            with patch.object(MODULE, "load_registry") as registry:
                with self.assertRaisesRegex(
                    MODULE.SyncError,
                    "project-owned skill configuration, not a skill publication target",
                ):
                    MODULE.publish_skill(args)

            registry.assert_not_called()

    def test_project_skills_config_alias_is_not_a_publication_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = (
                root
                / "application"
                / ".agents"
                / "skills-config"
                / "demo-skill"
            )
            config.mkdir(parents=True)
            (config / "config.yaml").write_text("schema: test\n", encoding="utf-8")
            alias = root / "global" / ".agents" / "skills" / "demo-skill"
            alias.parent.mkdir(parents=True)
            alias.symlink_to(config, target_is_directory=True)

            with patch.object(MODULE, "load_registry") as registry:
                with self.assertRaisesRegex(
                    MODULE.SyncError,
                    "project-owned skill configuration, not a skill publication target",
                ):
                    MODULE.publish_skill(publish_args(alias, reinstall=False))

            registry.assert_not_called()

    def test_project_skills_config_alias_ignores_target_basename(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = (
                root
                / "application"
                / ".agents"
                / "skills-config"
                / "project-profile"
            )
            config.mkdir(parents=True)
            (config / "config.yaml").write_text("schema: test\n", encoding="utf-8")
            alias = root / "aliases" / "demo-skill"
            alias.parent.mkdir(parents=True)
            alias.symlink_to(config, target_is_directory=True)

            with patch.object(MODULE, "load_registry") as registry:
                with self.assertRaisesRegex(
                    MODULE.SyncError,
                    "project-owned skill configuration, not a skill publication target",
                ):
                    MODULE.publish_skill(publish_args(alias, reinstall=False))

            registry.assert_not_called()

    def test_reject_destination_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary).resolve()
            with self.assertRaises(MODULE.SyncError):
                MODULE.contained_path(repo, Path("../outside"))

    def test_reject_destination_with_nested_git_component(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary).resolve()
            for component in (".git", ".GIT", ".Git"):
                with self.subTest(component=component):
                    with self.assertRaisesRegex(
                        MODULE.SyncError, "Invalid destination"
                    ):
                        MODULE.contained_path(
                            repo, Path("packages") / component / "demo-skill"
                        )

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

    def test_publish_flags_default_to_push_and_reinstall(self) -> None:
        args = MODULE.build_parser().parse_args(["publish", "/tmp/demo-skill"])

        self.assertTrue(args.push)
        self.assertTrue(args.reinstall)

        disabled = MODULE.build_parser().parse_args(
            ["publish", "/tmp/demo-skill", "--no-push", "--no-reinstall"]
        )
        self.assertFalse(disabled.push)
        self.assertFalse(disabled.reinstall)

    def test_publish_requires_at_least_one_enabled_step(self) -> None:
        args = publish_args(
            Path("/tmp/demo-skill"), push=False, reinstall=False
        )

        with self.assertRaisesRegex(MODULE.SyncError, "at least one"):
            MODULE.publish_skill(args)

    def test_direct_source_publish_requires_a_matching_cli_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "source"
            project = root / "consumer"
            project.mkdir()
            init_repo(repo, "git@github.com:example/source.git")
            skill = repo / "skills" / "demo-skill"
            write_skill(skill, "demo-skill")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "init")
            configure_github_upstream(repo)
            args = publish_args(skill)
            args.project_root = str(project)

            with patch.object(
                MODULE,
                "_shared_global_skills_root",
                return_value=root / "global" / ".agents" / "skills",
            ):
                with self.assertRaisesRegex(
                    MODULE.SyncError, "not tracked by Skills CLI"
                ):
                    MODULE.publish_skill(args)

    def test_direct_source_publish_binds_project_reinstall_before_push(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "source"
            project = root / "consumer"
            init_repo(repo, "git@github.com:example/source.git")
            skill = repo / "skills" / "demo-skill"
            installed = project / ".agents" / "skills" / "demo-skill"
            write_skill(skill, "demo-skill", "before")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "init")
            configure_github_upstream(repo)
            write_skill(skill, "demo-skill", "after")
            write_skill(installed, "demo-skill", "before")
            (project / "skills-lock.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skills": {
                            "demo-skill": {
                                "source": "example/source",
                                "skillPath": "skills/demo-skill/SKILL.md",
                                "computedHash": "a" * 64,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            args = publish_args(skill, installed=installed)

            with patch.object(MODULE, "_refresh_source_upstream"):
                with patch.object(MODULE, "validate_skill"):
                    with patch.object(MODULE, "push_source_with_retry") as push:
                        with patch.object(MODULE, "refresh_named_skill") as refresh:
                            MODULE.publish_skill(args)

            self.assertEqual(push.call_count, 1)
            self.assertEqual(push.call_args.args[0].repo, repo.resolve())
            self.assertEqual(push.call_args.args[1:], (3, 0))
            refresh.assert_called_once()
            self.assertEqual(refresh.call_args.args[0], skill.resolve())
            self.assertEqual(
                refresh.call_args.args[1], MODULE._absolute_path(project)
            )
            targets = refresh.call_args.args[2]
            self.assertEqual(len(targets), 1)
            self.assertEqual(targets[0].scope, "project")
            self.assertEqual(
                targets[0].installed_skill, MODULE._absolute_path(installed)
            )

    def test_direct_source_publish_can_push_without_reinstall(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "source"
            init_repo(repo, "git@github.com:example/source.git")
            skill = repo / "skills" / "demo-skill"
            write_skill(skill, "demo-skill", "before")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "init")
            configure_github_upstream(repo)
            write_skill(skill, "demo-skill", "after")
            args = publish_args(skill, reinstall=False)

            with patch.object(MODULE, "_refresh_source_upstream"):
                with patch.object(MODULE, "validate_skill"):
                    with patch.object(MODULE, "push_source_with_retry") as push:
                        with patch.object(MODULE, "refresh_named_skill") as refresh:
                            MODULE.publish_skill(args)

            self.assertEqual(push.call_count, 1)
            self.assertEqual(push.call_args.args[0].repo, repo.resolve())
            self.assertEqual(push.call_args.args[1:], (3, 0))
            refresh.assert_not_called()
            self.assertIn(
                "after", (skill / "SKILL.md").read_text(encoding="utf-8")
            )

    def test_direct_source_publish_rejects_mismatched_installation_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "source"
            project = root / "consumer"
            init_repo(repo, "git@github.com:example/source.git")
            skill = repo / "skills" / "demo-skill"
            installed = project / ".agents" / "skills" / "demo-skill"
            write_skill(skill, "demo-skill")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "init")
            configure_github_upstream(repo)
            write_skill(installed, "demo-skill")
            (project / "skills-lock.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skills": {
                            "demo-skill": {
                                "source": "other/source",
                                "skillPath": "skills/demo-skill/SKILL.md",
                                "computedHash": "a" * 64,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                MODULE.SyncError, "does not match actual push endpoint"
            ):
                MODULE.publish_skill(publish_args(skill, installed=installed))

    def test_direct_source_binding_uses_actual_push_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "source"
            project = root / "consumer"
            init_repo(repo, "git@github.com:example/source.git")
            skill = repo / "skills" / "demo-skill"
            installed = project / ".agents" / "skills" / "demo-skill"
            write_skill(skill, "demo-skill")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "init")
            git(repo, "branch", "-M", "main")
            git(repo, "remote", "add", "publish", "git@github.com:other/source.git")
            git(repo, "update-ref", "refs/remotes/publish/main", "HEAD")
            git(repo, "config", "branch.main.remote", "publish")
            git(repo, "config", "branch.main.merge", "refs/heads/main")
            write_skill(installed, "demo-skill")
            (project / "skills-lock.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skills": {
                            "demo-skill": {
                                "source": "example/source",
                                "skillPath": "skills/demo-skill/SKILL.md",
                                "computedHash": "a" * 64,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                MODULE.SyncError, "does not match actual push endpoint"
            ):
                MODULE.publish_skill(publish_args(skill, installed=installed))

    def test_direct_source_binding_rejects_different_skill_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "source"
            project = root / "consumer"
            init_repo(repo, "git@github.com:example/source.git")
            skill = repo / "packages" / "demo-skill"
            installed = project / ".agents" / "skills" / "demo-skill"
            write_skill(skill, "demo-skill")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "init")
            configure_github_upstream(repo)
            write_skill(installed, "demo-skill")
            (project / "skills-lock.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skills": {
                            "demo-skill": {
                                "source": "example/source",
                                "skillPath": "skills/demo-skill/SKILL.md",
                                "computedHash": "a" * 64,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                MODULE.SyncError, "does not match publish skill path"
            ):
                MODULE.publish_skill(publish_args(skill, installed=installed))

    def test_direct_source_global_publish_preserves_project_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "source"
            project = root / "consumer"
            global_skills = root / "global" / ".agents" / "skills"
            project.mkdir()
            init_repo(repo, "git@github.com:example/source.git")
            skill = repo / "skills" / "demo-skill"
            installed = global_skills / "demo-skill"
            write_skill(skill, "demo-skill", "before")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "init")
            configure_github_upstream(repo)
            write_skill(skill, "demo-skill", "after")
            write_skill(installed, "demo-skill", "before")
            global_lock = global_skills.parent / ".skill-lock.json"
            global_lock.write_text(
                json.dumps(
                    {
                        "version": 3,
                        "skills": {
                            "demo-skill": {
                                "source": "example/source",
                                "skillPath": "skills/demo-skill/SKILL.md",
                                "skillFolderHash": "a" * 40,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            args = publish_args(skill, installed=installed)
            args.project_root = str(project)

            with patch.object(
                MODULE, "_shared_global_skills_root", return_value=global_skills
            ):
                with patch.object(MODULE, "_refresh_source_upstream"):
                    with patch.object(MODULE, "validate_skill"):
                        with patch.object(MODULE, "push_source_with_retry"):
                            with patch.object(
                                MODULE, "refresh_named_skill"
                            ) as refresh:
                                MODULE.publish_skill(args)

            self.assertEqual(
                refresh.call_args.args[1], MODULE._absolute_path(project)
            )
            targets = refresh.call_args.args[2]
            self.assertEqual(len(targets), 1)
            self.assertEqual(targets[0].scope, "global")
            self.assertEqual(
                targets[0].installed_skill, MODULE._absolute_path(installed)
            )

    def test_project_symlink_publish_keeps_originating_installation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "source"
            project = root / "consumer"
            registry = root / "registry.json"
            init_repo(repo, "git@github.com:example/source.git")
            skill = repo / "skills" / "demo-skill"
            installed = project / ".agents" / "skills" / "demo-skill"
            write_skill(skill, "demo-skill")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "init")
            configure_github_upstream(repo)
            installed.parent.mkdir(parents=True)
            installed.symlink_to(skill, target_is_directory=True)
            write_skill(skill, "demo-skill", "modified through project symlink")
            (project / "skills-lock.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skills": {
                            "demo-skill": {
                                "source": "example/source",
                                "skillPath": "skills/demo-skill/SKILL.md",
                                "computedHash": "a" * 64,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            MODULE.register_repository(repo, registry, None, [])
            args = publish_args(installed)
            args.registry = str(registry)

            with patch.object(MODULE, "_refresh_source_upstream"):
                with patch.object(MODULE, "validate_skill"):
                    with patch.object(MODULE, "push_source_with_retry"):
                        with patch.object(MODULE, "refresh_named_skill") as refresh:
                            MODULE.publish_skill(args)

            self.assertEqual(
                refresh.call_args.args[1], MODULE._absolute_path(project)
            )
            targets = refresh.call_args.args[2]
            self.assertEqual(len(targets), 1)
            self.assertEqual(targets[0].scope, "project")
            self.assertEqual(
                targets[0].installed_skill, MODULE._absolute_path(installed)
            )

    def test_no_push_rejects_source_behind_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "source"
            init_repo(repo, "git@github.com:example/source.git")
            skill = repo / "skills" / "demo-skill"
            write_skill(skill, "demo-skill", "first")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "first")
            configure_github_upstream(repo)
            write_skill(skill, "demo-skill", "second")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "second")
            remote_head = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            git(repo, "reset", "--hard", "HEAD~1")
            git(repo, "update-ref", "refs/remotes/origin/main", remote_head)
            context = MODULE._source_context(skill)

            with self.assertRaisesRegex(MODULE.SyncError, "behind or diverged"):
                MODULE._check_source_repo(
                    context,
                    allow_dirty=False,
                    allow_skill_changes=False,
                )

    def test_publish_rejects_unmerged_skill_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "source"
            init_repo(repo, "git@github.com:example/source.git")
            skill = repo / "skills" / "demo-skill"
            write_skill(skill, "demo-skill", "base")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "base")
            configure_github_upstream(repo)
            git(repo, "checkout", "-q", "-b", "side")
            write_skill(skill, "demo-skill", "side")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "side")
            git(repo, "checkout", "-q", "main")
            write_skill(skill, "demo-skill", "main")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "main")
            merge = subprocess.run(
                ["git", "-C", str(repo), "merge", "side"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(merge.returncode, 0)
            context = MODULE._source_context(skill)

            with self.assertRaisesRegex(MODULE.SyncError, "merge conflicts"):
                MODULE._check_source_repo(
                    context,
                    allow_dirty=True,
                    allow_skill_changes=True,
                )

    def test_project_copy_rejects_originating_worktree_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            init_repo(project)
            installed = project / ".agents" / "skills" / "demo-skill"
            write_skill(installed, "demo-skill")
            readme = project / "README.md"
            readme.write_text("base\n", encoding="utf-8")
            git(project, "add", ".")
            git(project, "commit", "-q", "-m", "base")
            git(project, "branch", "-M", "main")
            git(project, "checkout", "-q", "-b", "side")
            readme.write_text("side\n", encoding="utf-8")
            git(project, "add", "README.md")
            git(project, "commit", "-q", "-m", "side")
            git(project, "checkout", "-q", "main")
            readme.write_text("main\n", encoding="utf-8")
            git(project, "add", "README.md")
            git(project, "commit", "-q", "-m", "main")
            merge = subprocess.run(
                ["git", "-C", str(project), "merge", "side"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(merge.returncode, 0)

            with self.assertRaisesRegex(
                MODULE.SyncError, "Originating project has unresolved"
            ):
                MODULE._check_project_copy_worktree(installed)

    def test_installed_comparison_detects_installed_only_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source" / "demo-skill"
            installed = root / "installed" / "demo-skill"
            write_skill(source, "demo-skill")
            write_skill(installed, "demo-skill")
            (installed / "unexpected.txt").write_text(
                "unexpected\n", encoding="utf-8"
            )

            self.assertIn(
                ("REMOVE", Path("unexpected.txt")),
                MODULE.installed_content_changes(source, installed),
            )

    def test_named_update_ignores_unlocked_shared_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            repo = root / "source"
            global_skills = root / "global" / ".agents" / "skills"
            init_repo(repo, "git@github.com:example/source.git")
            skill = repo / "skills" / "demo-skill"
            write_skill(skill, "demo-skill")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "init")
            configure_github_upstream(repo)
            project.mkdir()
            (project / "skills-lock.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skills": {
                            "demo-skill": {
                                "source": "example/source",
                                "skillPath": "skills/demo-skill/SKILL.md",
                                "computedHash": "a" * 64,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            global_skills.mkdir(parents=True)
            (global_skills / "demo-skill").symlink_to(
                skill, target_is_directory=True
            )

            with patch.object(
                MODULE, "_shared_global_skills_root", return_value=global_skills
            ):
                targets = MODULE.resolve_named_update_targets(
                    project,
                    "demo-skill",
                    MODULE._source_context(skill),
                )

            self.assertEqual(len(targets), 1)
            self.assertEqual(targets[0].scope, "project")
            self.assertEqual(
                targets[0].installed_skill,
                MODULE._absolute_path(
                    project / ".agents" / "skills" / "demo-skill"
                ),
            )

    def test_named_update_rejects_lock_entry_without_skill_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            repo = root / "source"
            global_skills = root / "global" / ".agents" / "skills"
            init_repo(repo, "git@github.com:example/source.git")
            skill = repo / "skills" / "demo-skill"
            write_skill(skill, "demo-skill")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "init")
            configure_github_upstream(repo)
            project.mkdir()
            (project / "skills-lock.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skills": {
                            "demo-skill": {
                                "source": "example/source",
                                "computedHash": "a" * 64,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(
                MODULE, "_shared_global_skills_root", return_value=global_skills
            ):
                with self.assertRaisesRegex(MODULE.SyncError, "no skillPath"):
                    MODULE.resolve_named_update_targets(
                        project,
                        "demo-skill",
                        MODULE._source_context(skill),
                    )

    def test_named_update_rejects_global_lock_without_folder_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            repo = root / "source"
            global_skills = root / "global" / ".agents" / "skills"
            init_repo(repo, "git@github.com:example/source.git")
            skill = repo / "skills" / "demo-skill"
            write_skill(skill, "demo-skill")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "init")
            configure_github_upstream(repo)
            project.mkdir()
            global_lock = global_skills.parent / ".skill-lock.json"
            global_lock.parent.mkdir(parents=True)
            global_lock.write_text(
                json.dumps(
                    {
                        "version": 3,
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

            with patch.object(
                MODULE, "_shared_global_skills_root", return_value=global_skills
            ):
                with self.assertRaisesRegex(
                    MODULE.SyncError, "no skillFolderHash"
                ):
                    MODULE.resolve_named_update_targets(
                        project,
                        "demo-skill",
                        MODULE._source_context(skill),
                    )

    def test_named_update_ignores_versionless_project_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            repo = root / "source"
            global_skills = root / "global" / ".agents" / "skills"
            init_repo(repo, "git@github.com:example/source.git")
            skill = repo / "skills" / "demo-skill"
            write_skill(skill, "demo-skill")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "init")
            configure_github_upstream(repo)
            project.mkdir()
            (project / "skills-lock.json").write_text(
                json.dumps(
                    {
                        "skills": {
                            "demo-skill": {
                                "source": "example/source",
                                "skillPath": "skills/demo-skill/SKILL.md",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(
                MODULE, "_shared_global_skills_root", return_value=global_skills
            ):
                with self.assertRaisesRegex(
                    MODULE.SyncError, "not tracked by Skills CLI"
                ):
                    MODULE.resolve_named_update_targets(
                        project,
                        "demo-skill",
                        MODULE._source_context(skill),
                    )

    def test_cli_lock_version_matches_javascript_number_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / "skills-lock.json"
            payload = {"skills": {"demo-skill": {}}}

            lock.write_text(
                json.dumps({"version": True, **payload}), encoding="utf-8"
            )
            self.assertEqual(MODULE._cli_lock_skills(lock, "project"), {})

            lock.write_text(
                json.dumps({"version": 1.0, **payload}), encoding="utf-8"
            )
            self.assertIn(
                "demo-skill", MODULE._cli_lock_skills(lock, "project")
            )

    def test_global_lock_path_honors_xdg_state_home(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_home = Path(temporary) / "state"
            with patch.dict(
                MODULE.os.environ,
                {"XDG_STATE_HOME": str(state_home)},
                clear=False,
            ):
                lock = MODULE._global_skill_lock_path(
                    Path(temporary) / "home" / ".agents" / "skills"
                )

            self.assertEqual(lock, state_home / "skills" / ".skill-lock.json")

    def test_named_update_uses_skill_name_without_manual_scope_or_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            source = root / "source" / "demo-skill"
            installed = project / ".agents" / "skills" / "demo-skill"
            write_skill(source, "demo-skill", "published")
            write_skill(installed, "demo-skill", "published")
            lock = project / "skills-lock.json"
            lock.write_text(
                json.dumps(
                    {
                        "skills": {
                            "demo-skill": {"computedHash": "a" * 64}
                        }
                    }
                ),
                encoding="utf-8",
            )
            target = MODULE.UpdateTarget("project", lock, installed)
            succeeded = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="updated", stderr=""
            )

            with patch.object(MODULE.shutil, "which", return_value="/bin/pnpm"):
                with patch.object(
                    MODULE.subprocess, "run", return_value=succeeded
                ) as run:
                    with patch.object(MODULE, "_verify_installed_skill") as verify:
                        MODULE.refresh_named_skill(
                            source,
                            project,
                            (target,),
                            attempts=3,
                            retry_delay=0,
                        )

            self.assertEqual(
                run.call_args.args[0],
                [
                    "/bin/pnpm",
                    "dlx",
                    "skills",
                    "update",
                    "demo-skill",
                    "-y",
                ],
            )
            self.assertNotIn("-p", run.call_args.args[0])
            self.assertNotIn("-g", run.call_args.args[0])
            verify.assert_called_once_with(source, installed, lock, None)

    def test_named_update_retries_when_cli_succeeds_but_verification_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            source = root / "source" / "demo-skill"
            installed = project / ".agents" / "skills" / "demo-skill"
            write_skill(source, "demo-skill", "published")
            write_skill(installed, "demo-skill", "old")
            lock = project / "skills-lock.json"
            lock.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skills": {
                            "demo-skill": {"computedHash": "a" * 64}
                        },
                    }
                ),
                encoding="utf-8",
            )
            target = MODULE.UpdateTarget("project", lock, installed)
            succeeded = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="checked", stderr=""
            )

            with patch.object(MODULE.shutil, "which", return_value="/bin/pnpm"):
                with patch.object(
                    MODULE.subprocess, "run", return_value=succeeded
                ) as run:
                    with patch.object(
                        MODULE,
                        "_verify_installed_skill",
                        side_effect=[MODULE.SyncError("stale"), None],
                    ) as verify:
                        with patch("builtins.print") as output:
                            MODULE.refresh_named_skill(
                                source,
                                project,
                                (target,),
                                attempts=3,
                                retry_delay=0,
                            )

            self.assertEqual(run.call_count, 2)
            self.assertEqual(verify.call_count, 2)
            self.assertIn("stale", "\n".join(str(call) for call in output.call_args_list))

    def test_named_update_zero_exit_permission_failure_is_not_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            source = root / "source" / "demo-skill"
            installed = project / ".agents" / "skills" / "demo-skill"
            write_skill(source, "demo-skill", "published")
            write_skill(installed, "demo-skill", "old")
            lock = project / "skills-lock.json"
            lock.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skills": {
                            "demo-skill": {"computedHash": "a" * 64}
                        },
                    }
                ),
                encoding="utf-8",
            )
            target = MODULE.UpdateTarget("project", lock, installed)
            succeeded_with_error = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="EPERM: operation not permitted",
                stderr="",
            )

            with patch.object(MODULE.shutil, "which", return_value="/bin/pnpm"):
                with patch.object(
                    MODULE.subprocess,
                    "run",
                    return_value=succeeded_with_error,
                ) as run:
                    with patch.object(
                        MODULE,
                        "_verify_installed_skill",
                        side_effect=MODULE.SyncError("stale"),
                    ):
                        with self.assertRaisesRegex(
                            MODULE.SyncError, "non-retryable"
                        ):
                            MODULE.refresh_named_skill(
                                source,
                                project,
                                (target,),
                                attempts=3,
                                retry_delay=0,
                            )

            self.assertEqual(run.call_count, 1)

    def test_refresh_retries_exact_scoped_skill_and_verifies_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            init_repo(project)
            installed = project / ".agents" / "skills" / "demo-skill"
            source = root / "source" / "demo-skill"
            write_skill(installed, "demo-skill", "published")
            write_skill(source, "demo-skill", "published")
            installed_hash = MODULE._compute_skill_folder_hash(installed)
            (project / "skills-lock.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skills": {
                            "demo-skill": {
                                "computedHash": installed_hash,
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
                    MODULE, "_compute_skill_folder_hash", return_value=installed_hash
                ):
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
            installed_hash = MODULE._compute_skill_folder_hash(installed)
            lock = root / ".agents" / ".skill-lock.json"
            lock.parent.mkdir(exist_ok=True)
            lock.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skills": {
                            "demo-skill": {
                                "computedHash": installed_hash,
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
                        MODULE,
                        "_compute_skill_folder_hash",
                        return_value=installed_hash,
                    ):
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

    def test_global_lock_rejects_stale_legacy_git_tree_hash(self) -> None:
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

            with self.assertRaisesRegex(MODULE.SyncError, "stale"):
                MODULE._verified_lock_hash(
                    lock,
                    "demo-skill",
                    expected_git_tree_hash="e" * 40,
                )

            self.assertEqual(
                MODULE._verified_lock_hash(
                    lock,
                    "demo-skill",
                    expected_git_tree_hash="d" * 40,
                ),
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
            installed_hash = MODULE._compute_skill_folder_hash(installed)
            (root / "skills-lock.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skills": {
                            "demo-skill": {
                                "computedHash": installed_hash,
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
                    MODULE, "_compute_skill_folder_hash", return_value=installed_hash
                ):
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

    def test_source_context_rejects_non_github_upstream_remote(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "source"
            init_repo(repo, "git@github.com:example/source.git")
            skill = repo / "skills" / "demo-skill"
            write_skill(skill, "demo-skill")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "init")
            git(repo, "branch", "-M", "main")
            git(repo, "remote", "add", "evil", "https://gitlab.com/example/source.git")
            git(repo, "update-ref", "refs/remotes/evil/main", "HEAD")
            git(repo, "config", "branch.main.remote", "evil")
            git(repo, "config", "branch.main.merge", "refs/heads/main")

            with self.assertRaisesRegex(
                MODULE.SyncError, "upstream remote is not GitHub"
            ):
                MODULE._source_context(skill)

    def test_push_source_uses_explicit_upstream_and_verifies_remote_head(self) -> None:
        context = MODULE.SourceContext(
            repo=Path("/source/repo"),
            skill_dir=Path("/source/repo/skills/demo-skill"),
            skill_relative=Path("skills/demo-skill"),
            branch="main",
            upstream="origin/main",
            upstream_remote="origin",
            upstream_branch="main",
            upstream_push_url="git@github.com:example/source.git",
        )
        pushed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="pushed", stderr=""
        )
        local = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="abc123\n", stderr=""
        )
        remote = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="abc123\trefs/heads/main\n",
            stderr="",
        )
        updated = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        with patch.object(
            MODULE.subprocess,
            "run",
            side_effect=[pushed, local, remote, updated],
        ) as run:
            MODULE.push_source_with_retry(context, 3, 0)

        self.assertEqual(
            run.call_args_list[0].args[0],
            [
                "git",
                "-C",
                "/source/repo",
                "push",
                "git@github.com:example/source.git",
                "HEAD:refs/heads/main",
            ],
        )
        self.assertEqual(
            run.call_args_list[-1].args[0],
            [
                "git",
                "-C",
                "/source/repo",
                "update-ref",
                "refs/remotes/origin/main",
                "abc123",
            ],
        )

    def test_folder_hash_matches_skills_cli_locale_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = Path(temporary) / "demo-skill"
            skill.mkdir()
            (skill / ".hidden").write_text("hidden\n", encoding="utf-8")
            (skill / "_meta").write_text("meta\n", encoding="utf-8")
            (skill / "SKILL.md").write_text("skill\n", encoding="utf-8")

            self.assertEqual(
                MODULE._compute_skill_folder_hash(skill),
                "da3eb168b0fdecec37db610e43d3d3a1fa25253071729e40fa0bb015f088e569",
            )

    def test_verified_lock_rejects_stale_sha256_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installed = root / "demo-skill"
            write_skill(installed, "demo-skill")
            lock = root / "skills-lock.json"
            lock.write_text(
                json.dumps(
                    {
                        "skills": {
                            "demo-skill": {"computedHash": "a" * 64}
                        }
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(MODULE.SyncError, "stale"):
                MODULE._verified_lock_hash(lock, "demo-skill", installed)

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

    def test_validator_uses_mjs_and_skill_test_runner(self) -> None:
        self.assertEqual(MODULE.find_validator().name, "quick_validate.mjs")
        with tempfile.TemporaryDirectory() as temporary:
            skill = Path(temporary) / "demo-skill"
            write_skill(skill, "demo-skill")
            runner = skill / "scripts" / "tests" / "run.py"
            runner.parent.mkdir(parents=True)
            runner.write_text("print('ok')\n", encoding="utf-8")
            succeeded = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            with patch.object(MODULE.subprocess, "run", return_value=succeeded) as run:
                self.assertEqual(MODULE.run_skill_tests(skill), "passed")
            self.assertEqual(run.call_args.args[0][:3], ["uv", "run", "--script"])

    def test_named_update_runs_from_neutral_cwd_not_consumer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "consumer"
            source = root / "source" / "demo-skill"
            installed = project / ".agents" / "skills" / "demo-skill"
            write_skill(source, "demo-skill")
            write_skill(installed, "demo-skill")
            lock = project / "skills-lock.json"
            lock.write_text(json.dumps({"version": 1, "skills": {"demo-skill": {"computedHash": "a" * 64}}}), encoding="utf-8")
            target = MODULE.UpdateTarget("project", lock, installed)
            succeeded = subprocess.CompletedProcess(args=[], returncode=0, stdout="updated", stderr="")
            seen = {}

            def capture(command, **kwargs):
                seen["command"] = command
                seen["cwd"] = Path(kwargs["cwd"])
                seen["has_package"] = (seen["cwd"] / "package.json").exists()
                return succeeded

            with patch.object(MODULE.shutil, "which", return_value="/bin/pnpm"):
                with patch.object(MODULE.subprocess, "run", side_effect=capture):
                    with patch.object(MODULE, "_verify_installed_skill"):
                        MODULE.refresh_named_skill(source, project, (target,), attempts=1, retry_delay=0)
            self.assertEqual(seen["command"], ["/bin/pnpm", "dlx", "skills", "update", "demo-skill", "-y"])
            self.assertNotEqual(seen["cwd"], project)
            self.assertFalse(seen["has_package"])

    def test_batch_requires_exact_heads_for_existing_ahead_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "source"
            init_repo(repo, "git@github.com:example/source.git")
            skill = repo / "skills" / "demo-skill"
            write_skill(skill, "demo-skill", "one")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "one")
            configure_github_upstream(repo)
            upstream = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
            write_skill(skill, "demo-skill", "two")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "two")
            head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
            args = MODULE.build_parser().parse_args(["publish-batch", "--repo", str(repo), "--skill", "demo-skill", "--no-reinstall"])
            with patch.object(MODULE, "_refresh_source_upstream"):
                receipt = MODULE.publish_batch(args)
            self.assertFalse(receipt["completed"])
            args.expected_upstream_head = upstream
            args.expected_source_head = head
            with patch.object(MODULE, "_refresh_source_upstream"):
                with patch.object(MODULE, "validate_skill"):
                    with patch.object(MODULE, "run_skill_tests", return_value="not_present"):
                        with patch.object(MODULE, "push_source_with_retry"):
                            receipt = MODULE.publish_batch(args)
            self.assertTrue(receipt["completed"])

    def test_batch_existing_skill_runner_failure_blocks_commit_and_push(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "source"
            init_repo(repo, "git@github.com:example/source.git")
            skill = repo / "skills" / "demo-skill"
            write_skill(skill, "demo-skill", "before")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "base")
            configure_github_upstream(repo)
            write_skill(skill, "demo-skill", "after")
            runner = skill / "scripts" / "tests" / "run.py"
            runner.parent.mkdir(parents=True)
            runner.write_text("raise SystemExit(7)\n", encoding="utf-8")
            args = MODULE.build_parser().parse_args([
                "publish-batch", "--repo", str(repo),
                "--skill", "demo-skill", "--no-reinstall",
            ])
            with patch.object(MODULE, "_refresh_source_upstream"):
                with patch.object(MODULE, "push_source_with_retry") as push:
                    receipt = MODULE.publish_batch(args)
            self.assertFalse(receipt["completed"])
            self.assertIn("skill tests failed", receipt["error"])
            self.assertEqual(MODULE._source_ahead(MODULE._source_context(skill)), 0)
            push.assert_not_called()

    def test_batch_commits_once_and_update_failure_is_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "source"
            init_repo(repo, "git@github.com:example/source.git")
            for name in ("one-skill", "two-skill"):
                write_skill(repo / "skills" / name, name, "before")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "base")
            configure_github_upstream(repo)
            for name in ("one-skill", "two-skill"):
                write_skill(repo / "skills" / name, name, "after")
            args = MODULE.build_parser().parse_args([
                "publish-batch", "--repo", str(repo),
                "--skill", "one-skill", "--skill", "two-skill",
            ])
            with patch.object(MODULE, "_refresh_source_upstream"):
                with patch.object(MODULE, "validate_skill"):
                    with patch.object(MODULE, "run_skill_tests", return_value="not_present"):
                        with patch.object(MODULE, "resolve_named_update_targets", return_value=()):
                            with patch.object(MODULE, "push_source_with_retry"):
                                with patch.object(MODULE, "refresh_named_skill", side_effect=[None, MODULE.SyncError("update failed")]):
                                    receipt = MODULE.publish_batch(args)
            self.assertFalse(receipt["completed"])
            self.assertEqual(receipt["git"]["push"], "succeeded")
            self.assertEqual(receipt["skills"][0]["update"], "verified")
            self.assertEqual(receipt["skills"][1]["update"], "failed")
            self.assertEqual(MODULE._source_ahead(MODULE._source_context(repo / "skills" / "one-skill")), 1)

    def test_package_node_modules_input_fails_closed(self) -> None:
        with self.assertRaisesRegex(MODULE.SyncError, "package/node_modules"):
            MODULE._reject_package_input(Path("/tmp/package/node_modules/demo-skill"), "Skill input")


if __name__ == "__main__":
    unittest.main()
