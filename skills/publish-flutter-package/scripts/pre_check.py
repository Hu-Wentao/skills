import subprocess
import sys
import json

def run_command(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return None

def check_git_status():
    status = run_command(['git', 'status', '--porcelain'])
    if status is None:
        return {"error": "Not a git repository or git command failed"}
    
    uncommitted_files = [line.strip() for line in status.splitlines() if line.strip()]
    return {"uncommitted": uncommitted_files}

def check_remote_sync():
    # Fetch latest remote info
    run_command(['git', 'fetch'])
    
    # Get current branch
    branch = run_command(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    if not branch:
        return {"error": "Could not determine current branch"}

    # Check status against upstream
    status_output = run_command(['git', 'status', '-uno'])
    
    is_behind = "behind" in status_output if status_output else False
    is_ahead = "ahead" in status_output if status_output else False
    
    return {
        "branch": branch,
        "is_behind": is_behind,
        "is_ahead": is_ahead,
        "status_summary": status_output.splitlines()[1] if status_output and len(status_output.splitlines()) > 1 else "Up to date"
    }

if __name__ == "__main__":
    results = {
        "git_status": check_git_status(),
        "remote_sync": check_remote_sync()
    }
    print(json.dumps(results, indent=2))
