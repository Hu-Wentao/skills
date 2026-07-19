#!/usr/bin/env python3
"""
Quick validation script for skills - minimal version
"""

import ast
import re
import sys
from pathlib import Path

import yaml

MAX_SKILL_NAME_LENGTH = 64


def _is_profile_expression(node):
    """Return whether an AST node reads a project profile identifier."""

    return (isinstance(node, ast.Name) and node.id == "profile") or (
        isinstance(node, ast.Attribute) and node.attr == "profile"
    )


def _contains_string_literal(node):
    """Return whether a comparison operand embeds a concrete string."""

    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
        return any(_contains_string_literal(element) for element in node.elts)
    return False


def find_literal_profile_branch(skill_path):
    """Find reusable Python code branching on a concrete project profile."""

    scripts = Path(skill_path) / "scripts"
    if not scripts.is_dir():
        return None
    for path in sorted(scripts.rglob("*.py")):
        if "tests" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                operands = [node.left, *node.comparators]
                if any(_is_profile_expression(item) for item in operands) and any(
                    _contains_string_literal(item) for item in operands
                ):
                    return path, node.lineno
            if isinstance(node, ast.Match) and _is_profile_expression(node.subject):
                for case in node.cases:
                    if isinstance(case.pattern, ast.MatchValue) and _contains_string_literal(
                        case.pattern.value
                    ):
                        return path, case.pattern.lineno
    return None


def validate_skill(skill_path):
    """Basic validation of a skill"""
    skill_path = Path(skill_path)

    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return False, "SKILL.md not found"

    content = skill_md.read_text()
    if not content.startswith("---"):
        return False, "No YAML frontmatter found"

    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return False, "Invalid frontmatter format"

    frontmatter_text = match.group(1)

    try:
        frontmatter = yaml.safe_load(frontmatter_text)
        if not isinstance(frontmatter, dict):
            return False, "Frontmatter must be a YAML dictionary"
    except yaml.YAMLError as e:
        return False, f"Invalid YAML in frontmatter: {e}"

    allowed_properties = {"name", "description", "license", "allowed-tools", "metadata"}

    unexpected_keys = set(frontmatter.keys()) - allowed_properties
    if unexpected_keys:
        allowed = ", ".join(sorted(allowed_properties))
        unexpected = ", ".join(sorted(unexpected_keys))
        return (
            False,
            f"Unexpected key(s) in SKILL.md frontmatter: {unexpected}. Allowed properties are: {allowed}",
        )

    if "name" not in frontmatter:
        return False, "Missing 'name' in frontmatter"
    if "description" not in frontmatter:
        return False, "Missing 'description' in frontmatter"

    name = frontmatter.get("name", "")
    if not isinstance(name, str):
        return False, f"Name must be a string, got {type(name).__name__}"
    name = name.strip()
    if name:
        if not re.match(r"^[a-z0-9-]+$", name):
            return (
                False,
                f"Name '{name}' should be hyphen-case (lowercase letters, digits, and hyphens only)",
            )
        if name.startswith("-") or name.endswith("-") or "--" in name:
            return (
                False,
                f"Name '{name}' cannot start/end with hyphen or contain consecutive hyphens",
            )
        if len(name) > MAX_SKILL_NAME_LENGTH:
            return (
                False,
                f"Name is too long ({len(name)} characters). "
                f"Maximum is {MAX_SKILL_NAME_LENGTH} characters.",
            )

    description = frontmatter.get("description", "")
    if not isinstance(description, str):
        return False, f"Description must be a string, got {type(description).__name__}"
    description = description.strip()
    if description:
        if "<" in description or ">" in description:
            return False, "Description cannot contain angle brackets (< or >)"
        if len(description) > 1024:
            return (
                False,
                f"Description is too long ({len(description)} characters). Maximum is 1024 characters.",
            )

    project_configured = (skill_path / "references/project_config.md").is_file()
    if project_configured:
        literal_branch = find_literal_profile_branch(skill_path)
        if literal_branch:
            path, line = literal_branch
            relative = path.relative_to(skill_path)
            return (
                False,
                f"{relative}:{line} branches on a concrete project profile. "
                "Treat profile names as opaque and move project behavior to "
                f".agents/skills-config/{name}/.",
            )

    return True, "Skill is valid!"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python quick_validate.py <skill_directory>")
        sys.exit(1)

    valid, message = validate_skill(sys.argv[1])
    print(message)
    sys.exit(0 if valid else 1)
