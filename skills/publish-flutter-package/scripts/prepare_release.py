import subprocess
import re
import sys
from datetime import datetime

def get_last_tag():
    try:
        tag = subprocess.check_output(['git', 'describe', '--tags', '--abbrev=0'], stderr=subprocess.STDOUT).decode('utf-8').strip()
        return tag
    except subprocess.CalledProcessError:
        return None

def get_commits_since(tag):
    if tag:
        range_str = f"{tag}..HEAD"
    else:
        range_str = "HEAD"
    
    try:
        commits = subprocess.check_output(['git', 'log', '--pretty=format:%s', range_str]).decode('utf-8').splitlines()
        return commits
    except subprocess.CalledProcessError:
        return []

def parse_semver(version):
    # Matches v1.2.3 or 1.2.3
    match = re.match(r'v?(\d+)\.(\d+)\.(\d+)', version)
    if match:
        return [int(x) for x in match.groups()]
    return [0, 0, 0]

def suggest_version(current_version, commits):
    major, minor, patch = parse_semver(current_version)
    
    has_breaking = False
    has_feat = False
    has_fix = False
    
    for commit in commits:
        if '!' in commit or 'BREAKING CHANGE' in commit:
            has_breaking = True
        elif commit.startswith('feat'):
            has_feat = True
        elif commit.startswith('fix'):
            has_fix = True
            
    if has_breaking:
        major += 1
        minor = 0
        patch = 0
    elif has_feat:
        minor += 1
        patch = 0
    elif has_fix:
        patch += 1
    else:
        patch += 1 # Default to patch if unknown
        
    return f"{major}.{minor}.{patch}"

def format_changelog_entry(version, commits):
    date = datetime.now().strftime('%Y-%m-%d')
    header = f"## {version} {date}"
    entries = []
    for commit in commits:
        # Simple heuristic to clean up commit messages for changelog
        clean_commit = commit.strip()
        if clean_commit:
            entries.append(f"* {clean_commit}")
    
    return f"{header}
" + "
".join(entries) + "
"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python prepare_release.py <current_version>")
        sys.exit(1)
        
    current_version = sys.argv[1]
    last_tag = get_last_tag()
    commits = get_commits_since(last_tag)
    
    if not commits:
        print("No changes since last tag.")
        sys.exit(0)
        
    suggested = suggest_version(current_version, commits)
    changelog_entry = format_changelog_entry(suggested, commits)
    
    print("SUGGESTED_VERSION:" + suggested)
    print("CHANGELOG_ENTRY_START")
    print(changelog_entry)
    print("CHANGELOG_ENTRY_END")
