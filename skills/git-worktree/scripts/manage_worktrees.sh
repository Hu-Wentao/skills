#!/bin/bash

# Manage git worktrees: List and optionally remove.
# Usage: ./manage_worktrees.sh <project_path>

PROJECT_PATH=$1

if [ -z "$PROJECT_PATH" ]; then
  echo "Error: Missing project path."
  exit 1
fi

if ! cd "$PROJECT_PATH" 2>/dev/null; then
  echo "Error: Cannot access project path $PROJECT_PATH"
  exit 1
fi

# List all worktrees
echo "Current Git Worktrees:"
git worktree list --porcelain | grep "^worktree " | cut -d' ' -f2- | cat -n

# Check if there are worktrees (other than the main one)
WORKTREE_COUNT=$(git worktree list | wc -l)
if [ "$WORKTREE_COUNT" -le 1 ]; then
  echo "No additional worktrees found."
  exit 0
fi

echo ""
read -p "Enter the number of the worktree you want to remove (or press Enter to exit): " CHOICE

if [ -z "$CHOICE" ]; then
  echo "Exiting."
  exit 0
fi

# Get the path of the selected worktree
WORKTREE_PATH=$(git worktree list --porcelain | grep "^worktree " | cut -d' ' -f2- | sed -n "${CHOICE}p")

if [ -z "$WORKTREE_PATH" ]; then
  echo "Invalid choice."
  exit 1
fi

# Check if it's the main worktree (usually the first one, but let's be safe)
MAIN_WORKTREE=$(git worktree list --porcelain | head -n 1 | cut -d' ' -f2-)
if [ "$WORKTREE_PATH" == "$MAIN_WORKTREE" ]; then
  echo "Error: Cannot remove the main worktree."
  exit 1
fi

read -p "Are you sure you want to remove worktree at $WORKTREE_PATH? (y/N): " CONFIRM
if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
  echo "Removing worktree: $WORKTREE_PATH..."
  git worktree remove "$WORKTREE_PATH"
  if [ $? -eq 0 ]; then
    echo "Worktree removed successfully."
  else
    echo "Failed to remove worktree."
    exit 1
  fi
else
  echo "Aborted."
fi
