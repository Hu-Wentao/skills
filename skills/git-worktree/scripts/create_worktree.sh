#!/bin/bash

# Create a git worktree at the same level as the current project directory.
# Usage: ./create_worktree.sh <project_path> <new_branch> <base_branch>

PROJECT_PATH=$1

if [ -z "$PROJECT_PATH" ]; then
  echo "Error: Missing project path."
  echo "Usage: $0 <project_path> [new_branch] [base_branch]"
  exit 1
fi

# Ensure we are in a git repository and get the top-level path
if ! cd "$PROJECT_PATH" 2>/dev/null; then
  echo "Error: Cannot access project path $PROJECT_PATH"
  exit 1
fi

TOP_LEVEL=$(git rev-parse --show-toplevel 2>/dev/null)
if [ $? -ne 0 ]; then
  echo "Error: $PROJECT_PATH is not a git repository."
  exit 1
fi

PROJECT_NAME=$(basename "$TOP_LEVEL")

# Set defaults if not provided
if [ -z "$2" ]; then
  # Suggest a descriptive name if not provided (e.g., feat-project-name-260221)
  NEW_BRANCH="feat-${PROJECT_NAME}-$(date +%y%m%d)"
else
  NEW_BRANCH=$2
fi

if [ -z "$3" ]; then
  # Default base branch is the current branch
  BASE_BRANCH=$(git branch --show-current 2>/dev/null)
  BASE_BRANCH=${BASE_BRANCH:-"main"}
else
  BASE_BRANCH=$3
fi

PARENT_DIR=$(dirname "$TOP_LEVEL")

# Define worktree name and path
WORKTREE_NAME="${PROJECT_NAME}-T-${NEW_BRANCH}"
WORKTREE_PATH="${PARENT_DIR}/${WORKTREE_NAME}"

# Check if the directory already exists
if [ -d "$WORKTREE_PATH" ]; then
  echo "Error: Directory already exists at $WORKTREE_PATH"
  exit 1
fi

# Create the worktree
echo "Creating worktree for project: $PROJECT_NAME"
echo "Target path: $WORKTREE_PATH"
echo "New branch: $NEW_BRANCH (based on: $BASE_BRANCH)"

git worktree add -b "$NEW_BRANCH" "$WORKTREE_PATH" "$BASE_BRANCH"

if [ $? -eq 0 ]; then
  echo "Worktree created successfully."
  echo "---"
  echo "Location: $WORKTREE_PATH"
  
  # Optional: Attempt to run setup commands if common files are found
  cd "$WORKTREE_PATH" || exit 1
  
  if [ -f "pubspec.yaml" ]; then
    echo "Detected Flutter/Dart project. Running 'flutter pub get'..."
    flutter pub get
  elif [ -f "package.json" ]; then
    echo "Detected Node.js project. Running 'npm install'..."
    npm install
  elif [ -f "requirements.txt" ]; then
    echo "Detected Python project. Running 'pip install -r requirements.txt'..."
    pip install -r requirements.txt
  fi
  
  echo "---"
  echo "Setup complete. You can now switch to the new worktree."
else
  echo "Failed to create worktree."
  exit 1
fi
