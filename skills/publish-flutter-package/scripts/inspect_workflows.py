import os
import re
import json
import sys
import glob

def parse_workflow(file_path):
    """
    Manually parse the YAML for specific fields to avoid external dependencies.
    Targets 'on.push.tags' and 'jobs.publish.uses'.
    """
    with open(file_path, 'r') as f:
        content = f.read()

    # Extract uses
    # Looking for: uses: dart-lang/setup-dart/.github/workflows/publish.yml
    uses_match = re.search(r'uses:\s+([^\s
]+publish\.yml[^\s
]*)', content)
    uses = uses_match.group(1) if uses_match else None

    # Extract tags
    # This is a bit trickier without a YAML parser if it's a list.
    # Looking for:
    # on:
    #   push:
    #     tags:
    #       - 'v*'
    tags = []
    
    # Try to find the tags section
    on_push_match = re.search(r'on:.*?push:.*?tags:(.*?)(?:
\w|#|$)', content, re.DOTALL | re.IGNORECASE)
    if on_push_match:
        tag_lines = on_push_match.group(1).splitlines()
        for line in tag_lines:
            # Match lines like "- 'v*'" or "- v*"
            m = re.search(r'-\s+['"]?([^'"]+)['"]?', line)
            if m:
                tags.append(m.group(1))

    return {
        "file": file_path,
        "uses": uses,
        "tags": tags
    }

def find_workflows(package_name=None):
    # Try to find the project root by looking for .git or .github
    curr = os.getcwd()
    root = None
    while curr != os.path.dirname(curr):
        if os.path.exists(os.path.join(curr, ".github")) or os.path.exists(os.path.join(curr, ".git")):
            root = curr
            break
        curr = os.path.dirname(curr)
    
    if not root:
        # Fallback to current dir if not found (but usually SKILL.md pre-check will catch this)
        root = os.getcwd()

    workflow_dir = os.path.join(root, ".github/workflows")
    if not os.path.exists(workflow_dir):
        return []

    files = glob.glob(os.path.join(workflow_dir, "publish*.yml"))
    results = []
    
    for f in files:
        data = parse_workflow(f)
        # Score the file based on package name match if provided
        score = 0
        if package_name:
            # If package name is in the filename, it's a strong match
            if package_name.lower() in os.path.basename(f).lower():
                score += 10
            
            # Check if package name (working-directory) is mentioned inside
            with open(f, 'r') as file_content:
                if package_name in file_content.read():
                    score += 5
        
        data["score"] = score
        results.append(data)

    # Sort by score (highest first)
    results.sort(key=lambda x: x["score"], reverse=True)
    return results

if __name__ == "__main__":
    pkg_name = sys.argv[1] if len(sys.argv) > 1 else None
    workflows = find_workflows(pkg_name)
    print(json.dumps(workflows, indent=2))
