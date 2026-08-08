# Generic Linux Server Bootstrap

Use `scripts/server_bootstrap.py` only through a project-owned
`host-governance.config.v2` operation contract. The script provides a guarded
default baseline and makes Tailscale and Beszel explicit boolean options.
Run `host-key` first and verify one returned fingerprint through the provider
console before trusting it or starting `inspect`.

SSH public-key authentication is the default. Use `--allow-password-bootstrap`
only for a reviewed first connection: the controller reads the password from a
hidden interactive prompt or `SSH_BOOTSTRAP_PASSWORD`, forces password-only SSH
for that connection, and never places the value in argv or output. Stop using
the option after administrator key login succeeds.

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
available before hardening SSH or enabling the firewall.

`rollback` restores the snapshotted hostname and SSH configuration and disables
UFW only when it was previously inactive. Package changes, the administrator
account, Tailscale enrollment, and Beszel installation are deliberately
preserved and reported as non-reversible; removing any of them is a separate
authorized transaction.

## Optional Tailscale and Beszel

- `--enable-tailscale` installs the official stable Linux package, requires
  `TAILSCALE_AUTH_KEY` at runtime, disables route acceptance, and uses the
  requested hostname and tag. Tailnet policy and device-tag changes remain a
  separately authorized external transaction.
- `--enable-beszel` installs only the native Agent, requires the existing Hub
  public key, binds it to the live Tailscale IPv4 on TCP `45876`, and leaves
  automatic Agent updates disabled. Creating the Hub system record and proving
  Hub-to-Agent connectivity remain separate external verification steps.

Never put passwords, auth keys, private keys, or Hub credentials in contract
parameters, repository files, snapshots, journals, or command output.
