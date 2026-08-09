# Generic Linux Server Bootstrap

Use `scripts/server_bootstrap.py` only through a project-owned
`host-governance.config.v2` operation contract. The script provides a guarded
default baseline and makes Tailscale and Beszel explicit boolean options.
Run `host-key` first and verify one returned fingerprint through the provider
console before trusting it or starting `inspect`.

## Transport and local identity contract

Keep the direct target, device ID, destination SSH alias, and jump-host SSH
alias separate. A project contract that requires a jump host must fix or
validate that alias explicitly and use the same route for `host-key`,
`inspect`, `plan`, `apply`, key verification, and `finalize`; never retry by
silently falling back to the controller's direct public IP.

A password-bootstrap executor must disable remote PTY allocation, wait for an
authenticated ready marker before sending the remote script, terminate the
script explicitly, and distinguish a pre-auth connection close from a remote
password rejection. Add a focused successful-authentication regression test;
testing only failures leaves the credential path unproved.

Model local SSH configuration as its own contracted local-host mutation. It
must atomically update one exact `Host` block, set the declared `ProxyJump` and
new `IdentityFile`, remove password-bearing comments without copying them into
a backup, validate `ssh -G`, prove a batch-mode new-key login, and only then
retire the old local key. Filesystem sandbox denial is an explicit local
permission blocker, not permission to bypass the contract or claim completion.

## Completion contract

Treat a user request to initialize a server as an outcome request, not a
request to create a proposal. Local SSH configuration, a device manifest, a
new key pair, a host-key observation, `inspect`, `plan`, and `apply` are only
intermediate evidence. Never describe any of them as an initialized server.

End the task in exactly one of these states:

- `verified complete`: prove a fresh administrator-key login on the desired
  SSH port, prove password authentication and prohibited root login are
  rejected, verify the firewall and enabled native services, and finish any
  contracted key retirement or old-port closure.
- `explicitly blocked`: name the failed operation, state whether authentication
  was actually attempted, list every local and remote change already made, and
  provide the exact safe next action. A missing credential, unreachable SSH
  listener, or unverified host key is blocked, not complete.
- `rolled back`: identify the transaction and restored configuration, and list
  every deliberately preserved or non-reversible change.

`server_bootstrap_applied` means pending verification. Only a clean
`server_bootstrap_verified` result plus all required negative-path and finalize
checks permits a completion claim. A registered proposal is never evidence of
remote initialization.

## Credential and provider boundary

SSH public-key authentication is the default. Use `--allow-password-bootstrap`
only for a reviewed first connection: the controller reads the password from a
hidden interactive prompt or `SSH_BOOTSTRAP_PASSWORD`, forces password-only SSH
for that connection, and never places the value in argv or output. Stop using
the option after administrator key login succeeds. Consume an available
bootstrap password immediately for the contracted connection or report it as
unavailable; never claim a password attempt when only `ssh-keyscan`, TCP
probing, or key authentication ran. Never write the password to a repository,
task transcript, journal, shell history, local SSH config, or provider page.

An SSH failure does not authorize a provider-console detour. Do not open or
operate the provider Dashboard, inspect a login page or browser autofill,
submit provider credentials, reset a password, reboot, or use rescue mode
unless the user separately authorizes that exact action. Ask the user to verify
the host-key fingerprint or recovery-path availability out of band when the
bootstrap contract requires it; do not turn that prerequisite into permission
to operate the provider account.

## Default baseline

The default plan snapshots the current configuration, updates Debian or Ubuntu
packages, sets the hostname, creates an administrator with one SSH public key,
locks that account's password, grants it passwordless sudo through one validated
drop-in, hardens SSH, enables a default-deny firewall, and enables unattended security
updates without automatic reboot. Package upgrades are not fully reversible;
use `--skip-package-upgrade` only after the reviewed plan accepts that gap.

`apply` requires an exact live generation from the latest `inspect` and refuses
unsupported operating systems. Keep the bootstrap SSH session open until a
second public-key session succeeds. A provider console or rescue path must be
available before hardening SSH or enabling the firewall, but availability does
not authorize the agent to operate it.

Before migrating an SSH port, inspect `sshd -T`, live listeners, and
`ssh.socket`. Snapshot `/etc/ssh`, the applicable systemd socket override, and
the socket activation state. On socket-activated Debian or Ubuntu systems,
install and restart a validated `ssh.socket` override for both the recovery and
desired ports; reloading `ssh.service` alone does not activate the new port.
Require a fresh new-key connection to the desired listener before the finalize
transaction removes the recovery listener. If that connection fails, keep the
old listener open and report the transaction as blocked.

`rollback` restores the snapshotted hostname and SSH configuration and disables
UFW only when it was previously inactive. Package changes, the administrator
account, Tailscale enrollment, and Beszel installation are deliberately
preserved and reported as non-reversible; removing any of them is a separate
authorized transaction.

## Optional Tailscale and Beszel

- `--enable-tailscale` installs the official stable Linux package, disables
  route acceptance, and uses the requested hostname and tag. Prefer a
  contracted `TAILSCALE_AUTH_KEY` secret source for unattended provisioning.
  When no auth key is available and the project contract provides an
  interactive enrollment operation, run it on the exact target and capture
  only the canonical `https://login.tailscale.com/a/...` URL from Tailscale's
  output. Return the URL to the user immediately, even while the remote command
  is still waiting, and report the intermediate state as
  `awaiting-tailnet-auth`. Do not open an Admin Console as a substitute, ask the
  user to paste an auth key into chat, or disable Tailscale and dependent
  Beszel work without explicitly reporting that scope change. Never store the
  login URL in Git, snapshots, journals, caches, or task artifacts. After the
  user completes the URL flow, resume the same transaction and verify the live
  node name, Tailscale IP, requested tag, route preferences, and update
  readiness. Tailnet policy and device-tag changes remain a separately
  authorized external transaction. If a v2 contract lacks interactive
  enrollment, stop with that exact contract blocker instead of bypassing it.
- `--enable-beszel` installs only the native Agent, requires the existing Hub
  public key, binds it to the live Tailscale IPv4 on TCP `45876`, and leaves
  automatic Agent updates disabled. Creating the Hub system record and proving
  Hub-to-Agent connectivity remain separate external verification steps.

Never put passwords, auth keys, private keys, or Hub credentials in contract
parameters, repository files, snapshots, journals, or command output.
