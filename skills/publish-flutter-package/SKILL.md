---
name: publish-flutter-package
description: Automates the Flutter package release process via git tags and GitHub Actions. Handles multi-package workspaces, SemVer versioning suggestions based on git history, updating pubspec.yaml and CHANGELOG.md, and dry-run validation. Use when the user wants to "release", "publish", or "version" a Flutter package.
---

# Publish Flutter Package

This skill automates the Flutter package release workflow triggered by git tags.

## Workflow

### 0. Detect Packages (Workspace Support)
Read the root `pubspec.yaml` file.
- Check for the `workspace:` field.
- If present, parse the paths (e.g., `- pkgs/*`) to find all nested packages.
- Ask the user which package to publish if multiple are detected.

### 1. GitHub Actions Verification
#### 1.1 Configuration Check
Check `.github/workflows/publish*.yml`.
- Multi-package projects often have separate workflows (e.g., `publish-core.yml`, `publish-ui.yml`).
- Verify that `jobs.publish.uses` points to `dart-lang/setup-dart/.github/workflows/publish.yml`.
- In multi-package workspaces, if multiple publish workflows exist, **recommend the one matching the selected package name and ask the user to confirm**.
- **If the user skips or provides no alternative, proceed with the recommended workflow.**
- If no matching workflow is found, show the [Github Action Template](references/github_action_template.md) and guide the user to create one.

#### 1.2 Tag Format
Read the `on.push.tags` field to identify the required tag format (e.g., `v[0-9]+.[0-9]+.[0-9]+`).

### 2. Versioning Strategy (SemVer)
- Use `scripts/prepare_release.py <current_version>` to analyze git history since the last tag.
- This script provides a suggested version based on commit types (feat/fix/breaking) and generates a formatted `CHANGELOG.md` entry.
- Present the suggestion and the draft changelog entry to the user. **If the user skips or provides no alternative, proceed with the suggested values.**
- Allow the user to edit the version or the content before proceeding.

### 3. Documentation Updates
#### 3.1 pubspec.yaml
Update the `version` field in the relevant package's `pubspec.yaml` with the chosen version.

#### 3.2 CHANGELOG.md
Insert the confirmed `CHANGELOG.md` entry at the top of the file (after any initial headers).
Format requirement:
```markdown
## <Version> <YYYY-MM-DD>
* feat/fix/... [**important**] <content>
```
Note: Ensure the format matches the user's project-specific conventions if they differ from the suggested draft.

### 4. Git Tagging
Add a new git tag matching the format found in Step 1.2 using `git tag`.
- Example: If the tag format is `v[0-9]+.[0-9]+.[0-9]+`, the tag should be `v<version>`.
- Use the exact tag format detected from the workflow file.

### 5. Validation
Run `dart pub publish --dry-run` to verify the package contents and configuration.

## Resources

### scripts/
- `prepare_release.py`: Analyze git history to suggest SemVer version and generate `CHANGELOG.md` entry.
  - Arguments: `<current_version>`

### references/
- `github_action_template.md`: A template for setting up the GitHub Action for publishing.
