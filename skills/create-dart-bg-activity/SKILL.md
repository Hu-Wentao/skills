---
name: create-dart-bg-activity
description: Create a Dart-based macOS background activity process managed by launchd. Use when Codex needs to scaffold or fix a LaunchAgent for a Dart program, generate the executable entrypoint, write the plist, or ensure App Background Activity shows the intended process name instead of a shell wrapper.
---

# Create Dart Background Activity Process

## Workflow

1. Check repo and environment first.
   - Run `git status --short` in the target repo and follow its change-safety policy before editing files.
   - If the repo uses FVM, run Dart and Flutter commands through `fvm`.
   - Prefer a checked-in executable entrypoint path such as `daemon/bin/<service_name>` or `bin/<service_name>`.

2. Define the background process shape.
   - Choose a stable launchd `Label`, for example `com.example.sync_agent`.
   - Decide whether the process is:
     - a pure Dart CLI launched with `dart run`
     - an AOT-compiled Dart executable
     - a wrapper script that resolves the Dart SDK and then `exec`s the real process
   - Prefer an AOT executable or a checked-in launcher script over `/bin/zsh -lc ...`.

3. Create the Dart entrypoint.
   - Add or update a dedicated CLI entrypoint such as `bin/<service_name>.dart`.
   - Keep startup deterministic:
     - parse config from env vars or a config file
     - initialize logging early
     - trap termination signals if graceful shutdown matters
     - keep the main isolate alive with the long-running task loop
   - If the service needs restart safety, make failures exit non-zero and let launchd restart it.

4. Create a real executable for launchd.
   - Do not register `/bin/zsh`, `/bin/bash`, or `sh` as `ProgramArguments[0]`.
   - Preferred options:
     - AOT build:
       ```bash
       dart compile exe bin/<service_name>.dart -o daemon/bin/<service_name>
       ```
     - Launcher script:
       ```bash
       #!/bin/bash
       set -euo pipefail
       SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
       REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
       exec dart run "$REPO_ROOT/bin/<service_name>.dart"
       ```
   - The executable path itself should represent the intended service identity so App Background Activity shows the right name.

5. Write the LaunchAgent plist.
   - Store it at `~/Library/LaunchAgents/<label>.plist` for per-user jobs unless the user explicitly needs a system daemon.
   - Include at minimum:
     - `Label`
     - `ProgramArguments` with the real executable as the first item
     - `RunAtLoad`
     - `KeepAlive` if continuous restart is desired
     - `WorkingDirectory` if the service depends on relative paths
     - `StandardOutPath` and `StandardErrorPath` for debugging
   - If environment variables are required, prefer `EnvironmentVariables` in the plist or explicit setup in the launcher script.

6. Load and verify the service.
   - Unload any stale job before replacing the plist:
     ```bash
     uid=$(id -u)
     launchctl bootout "gui/$uid/<label>" >/dev/null 2>&1 || true
     ```
   - Load the service:
     ```bash
     launchctl bootstrap "gui/$uid" "$HOME/Library/LaunchAgents/<label>.plist"
     ```
   - Verify launchd state:
     ```bash
     launchctl print "gui/$uid/<label>"
     plutil -p "$HOME/Library/LaunchAgents/<label>.plist"
     ```
   - Confirm `program` or `arguments[0]` points to the intended executable path, not a shell wrapper.

7. Validate runtime behavior.
   - Check service logs:
     ```bash
     tail -n 100 "$HOME/Library/Logs/<app>/<stderr-log>"
     ```
   - Confirm the process is running with the expected name:
     ```bash
     ps aux | rg "<service_name>"
     ```
   - If the process exposes ports, inspect listeners separately:
     ```bash
     lsof -nP -iTCP:<port> -sTCP:LISTEN
     ```
   - Distinguish launchd registration problems from Dart runtime failures such as missing SDK paths, bad env vars, or application exceptions.

8. Reflect the result back into source code.
   - Commit the Dart entrypoint, launcher, plist template, and any service-management scripts together.
   - If the repo generates plists automatically, update the generator so future installs keep the same executable-first pattern.
   - If this renames an existing service, call out the compatibility impact clearly because installed plist names, labels, and process names will change.

## Notes

- App Background Activity naming follows the executable launchd registers, not only the final child process title.
- `exec -a` is not a durable fix if `ProgramArguments[0]` is still a shell.
- For macOS user agents, `~/Library/LaunchAgents` is the default target; use `LaunchDaemons` only when the user explicitly needs a machine-wide service.
- If the repo ships a launcher script, keep it stable and executable so plist updates do not silently drift from the checked-in source.
