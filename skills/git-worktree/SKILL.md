---
name: git-worktree
description: Create a git worktree for the current repository at the same directory level as the project root. This skill automates branch creation, directory naming according to the format project-T-branch, and initial project setup (e.g., dependency installation). Use this when the user wants to work on a new feature or fix without switching their current workspace.
---

# Git Worktree

## Overview

This skill allows you to quickly create a new git worktree for the current project. The worktree is created in the same parent directory as the current project's root, following the naming convention `PROJECT-NAME-T-BRANCH-NAME`.

## Workflow

1.  **Verification**: 
    -   Verify the current directory is within a Git repository.
    -   Identify the absolute path of the project's root.
2.  **User Interaction**: Ask the user for:
    -   **New branch name**: The name of the branch to be created in the new worktree.
    -   **Base branch**: The branch to base the new branch on (default is the current branch).
3.  **Path Calculation**: Calculate the new worktree path at the same directory level as the project root. For example, if the project is in `/Users/user/my-project`, the worktree will be created at `/Users/user/my-project-T-NEW-BRANCH`.
4.  **Creation**: Execute `scripts/create_worktree.sh` to:
    -   Create the new worktree and branch.
    -   Perform initial project setup (e.g., `flutter pub get`, `npm install`).
5.  **Confirmation**: Report the location of the new worktree and any initial setup status.

## Usage Example

**User**: "Create a worktree for this repo for the feature-login branch."
**Gemini**: "I can help you create a worktree for that. Which branch should 'feature-login' be based on? (Default is 'main')"
**User**: "Base it on main."
**Gemini**: [Runs the script and confirms the path `/Users/huwentao/_proj/foo_proj-T-feature-login`]

## Resources

### scripts/

*   `create_worktree.sh`: A bash script that calculates the paths, runs `git worktree add`, and performs initial project setup.
    *   Arguments: `project_path` `new_branch` `base_branch`
