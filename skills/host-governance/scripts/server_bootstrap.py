#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pexpect>=4.9,<5"]
# ///
"""Plan and execute a guarded initial Linux server bootstrap transaction."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import getpass
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


SCHEMA = "host-governance.server-bootstrap.v1"
DEVICE_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
USER_RE = re.compile(r"[a-z_][a-z0-9_-]{0,31}")
TAG_RE = re.compile(r"tag:[a-zA-Z0-9-]{1,63}")


class BootstrapError(RuntimeError):
    """A bootstrap operation cannot continue safely."""


INSPECT_SCRIPT = r"""
set -eu
export LC_ALL=C
os_id=unknown
os_version=unknown
if [ -r /etc/os-release ]; then
  . /etc/os-release
  os_id=${ID:-unknown}
  os_version=${VERSION_ID:-unknown}
fi
ssh_port=22
if command -v sshd >/dev/null 2>&1; then
  ssh_port=$(sshd -T 2>/dev/null | awk '$1 == "port" {print $2; exit}')
  ssh_port=${ssh_port:-22}
fi
firewall=unknown
if command -v ufw >/dev/null 2>&1; then
  firewall=$(ufw status 2>/dev/null | awk 'NR == 1 {print tolower($2)}')
elif command -v nft >/dev/null 2>&1; then
  firewall=nftables
fi
tailscale_state=absent
tailscale_ipv4=
if command -v tailscale >/dev/null 2>&1; then
  tailscale_state=installed
  tailscale_ipv4=$(tailscale ip -4 2>/dev/null | head -n 1 || true)
fi
beszel_state=absent
if systemctl list-unit-files beszel-agent.service >/dev/null 2>&1; then
  beszel_state=$(systemctl is-active beszel-agent.service 2>/dev/null || true)
  beszel_state=${beszel_state:-installed}
fi
printf 'os_id=%s\n' "$os_id"
printf 'os_version=%s\n' "$os_version"
printf 'arch=%s\n' "$(uname -m)"
printf 'kernel=%s\n' "$(uname -r)"
printf 'hostname=%s\n' "$(hostname)"
printf 'init=%s\n' "$(ps -p 1 -o comm= 2>/dev/null | tr -d ' ')"
printf 'cpu_count=%s\n' "$(getconf _NPROCESSORS_ONLN 2>/dev/null || printf unknown)"
printf 'memory_kib=%s\n' "$(awk '/^MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null || true)"
printf 'root_disk=%s\n' "$(df -Pk / | awk 'NR == 2 {print $2 ":" $3 ":" $4}')"
printf 'ssh_port=%s\n' "$ssh_port"
printf 'firewall=%s\n' "$firewall"
printf 'tailscale_state=%s\n' "$tailscale_state"
printf 'tailscale_ipv4=%s\n' "$tailscale_ipv4"
printf 'beszel_state=%s\n' "$beszel_state"
printf 'reboot_required=%s\n' "$([ -e /var/run/reboot-required ] && printf true || printf false)"
printf 'listeners=%s\n' "$(ss -H -lnt 2>/dev/null | awk '{print $4}' | sort -u | head -n 64 | paste -sd, -)"
""".strip()


APPLY_SCRIPT = r"""
set -eu
umask 077
export LC_ALL=C
device_id=$1
admin_user=$2
desired_hostname=$3
public_key=$4
skip_upgrade=$5
enable_tailscale=$6
tailscale_tag=$7
enable_beszel=$8
beszel_key=$9

exec 9>/run/lock/friday-care-server-bootstrap.lock
flock -n 9 || { echo 'bootstrap lock is held' >&2; exit 20; }

. /etc/os-release
case "${ID:-}" in
  ubuntu|debian) ;;
  *) echo 'apply currently supports Debian and Ubuntu only' >&2; exit 21 ;;
esac
test "$(id -u)" -eq 0 || { echo 'apply requires root' >&2; exit 22; }

state_root=/var/lib/friday-care/server-bootstrap
transaction_id=$(date -u +%Y%m%dT%H%M%SZ)-${device_id}
snapshot_root=$state_root/backups/$transaction_id
journal=$state_root/journal.jsonl
mkdir -p "$snapshot_root"
chmod 0700 "$state_root" "$state_root/backups" "$snapshot_root"
cp -a /etc/ssh/sshd_config "$snapshot_root/sshd_config" 2>/dev/null || true
cp -a /etc/ssh/sshd_config.d "$snapshot_root/sshd_config.d" 2>/dev/null || true
cp -a /etc/hostname "$snapshot_root/hostname" 2>/dev/null || true
ufw status numbered >"$snapshot_root/ufw-status.txt" 2>/dev/null || true
printf '{"transaction_id":"%s","device_id":"%s","phase":"snapshot","snapshot":"%s"}\n' \
  "$transaction_id" "$device_id" "$snapshot_root" >>"$journal"

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl sudo ufw unattended-upgrades
if [ "$skip_upgrade" != true ]; then
  apt-get upgrade -y
fi

hostnamectl set-hostname "$desired_hostname"
if ! id "$admin_user" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$admin_user"
fi
usermod -aG sudo "$admin_user"
passwd -l "$admin_user" >/dev/null 2>&1 || true
printf '%s ALL=(ALL:ALL) NOPASSWD:ALL\n' "$admin_user" >"/etc/sudoers.d/90-friday-care-$admin_user"
chmod 0440 "/etc/sudoers.d/90-friday-care-$admin_user"
visudo -cf "/etc/sudoers.d/90-friday-care-$admin_user"
install -d -m 0700 -o "$admin_user" -g "$admin_user" "/home/$admin_user/.ssh"
printf '%s\n' "$public_key" >"/home/$admin_user/.ssh/authorized_keys"
chown "$admin_user:$admin_user" "/home/$admin_user/.ssh/authorized_keys"
chmod 0600 "/home/$admin_user/.ssh/authorized_keys"

install -d -m 0755 /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/90-friday-care-baseline.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
EOF
sshd -t
systemctl reload ssh.service 2>/dev/null || systemctl reload sshd.service

ssh_port=$(sshd -T | awk '$1 == "port" {print $2; exit}')
ufw default deny incoming
ufw default allow outgoing
ufw allow "$ssh_port/tcp" comment 'bootstrap SSH'
ufw --force enable

cat > /etc/apt/apt.conf.d/52friday-care-unattended-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
Unattended-Upgrade::Automatic-Reboot "false";
EOF

if [ "$enable_tailscale" = true ]; then
  test -n "${TAILSCALE_AUTH_KEY:-}" || { echo 'TAILSCALE_AUTH_KEY is required' >&2; exit 23; }
  curl -fsSL https://tailscale.com/install.sh -o /tmp/friday-care-tailscale-install.sh
  sh /tmp/friday-care-tailscale-install.sh
  tailscale up --auth-key="$TAILSCALE_AUTH_KEY" --hostname="$desired_hostname" \
    --advertise-tags="$tailscale_tag" --accept-routes=false
  rm -f /tmp/friday-care-tailscale-install.sh
fi

if [ "$enable_beszel" = true ]; then
  test -n "$beszel_key" || { echo 'Beszel Hub public key is required' >&2; exit 24; }
  tailscale_ip=$(tailscale ip -4 2>/dev/null | head -n 1)
  test -n "$tailscale_ip" || { echo 'Beszel requires an active Tailscale IPv4' >&2; exit 25; }
  curl -fsSL https://get.beszel.dev -o /tmp/friday-care-install-beszel-agent.sh
  chmod 0700 /tmp/friday-care-install-beszel-agent.sh
  /tmp/friday-care-install-beszel-agent.sh -k "$beszel_key" -p "$tailscale_ip:45876" --auto-update false
  rm -f /tmp/friday-care-install-beszel-agent.sh
fi

printf '{"transaction_id":"%s","device_id":"%s","phase":"applied","snapshot":"%s"}\n' \
  "$transaction_id" "$device_id" "$snapshot_root" >>"$journal"
printf 'transaction_id=%s\n' "$transaction_id"
printf 'snapshot=%s\n' "$snapshot_root"
""".strip()


ROLLBACK_SCRIPT = r"""
set -eu
umask 077
export LC_ALL=C
device_id=$1
transaction_id=$2
exec 9>/run/lock/friday-care-server-bootstrap.lock
flock -n 9 || { echo 'bootstrap lock is held' >&2; exit 20; }
test "$(id -u)" -eq 0 || { echo 'rollback requires root' >&2; exit 22; }
case "$transaction_id" in
  *[!A-Za-z0-9._:-]*|'') echo 'invalid transaction ID' >&2; exit 26 ;;
esac
state_root=/var/lib/friday-care/server-bootstrap
snapshot_root=$state_root/backups/$transaction_id
test -d "$snapshot_root" || { echo 'bootstrap snapshot not found' >&2; exit 27; }
if [ -f "$snapshot_root/hostname" ]; then
  old_hostname=$(cat "$snapshot_root/hostname")
  hostnamectl set-hostname "$old_hostname"
fi
if [ -f "$snapshot_root/sshd_config" ]; then
  cp -a "$snapshot_root/sshd_config" /etc/ssh/sshd_config
fi
if [ -d "$snapshot_root/sshd_config.d" ]; then
  rm -rf /etc/ssh/sshd_config.d
  cp -a "$snapshot_root/sshd_config.d" /etc/ssh/sshd_config.d
fi
sshd -t
systemctl reload ssh.service 2>/dev/null || systemctl reload sshd.service
if grep -qi '^status: inactive' "$snapshot_root/ufw-status.txt" 2>/dev/null; then
  ufw --force disable
fi
printf '{"transaction_id":"%s","device_id":"%s","phase":"config_rolled_back","snapshot":"%s"}\n' \
  "$transaction_id" "$device_id" "$snapshot_root" >>"$state_root/journal.jsonl"
printf 'transaction_id=%s\n' "$transaction_id"
printf 'snapshot=%s\n' "$snapshot_root"
printf 'preserved_nonreversible=packages,admin-user,tailscale,beszel\n'
""".strip()


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def validate_device_id(value: str) -> str:
    if not DEVICE_RE.fullmatch(value):
        raise BootstrapError("device ID must be lowercase kebab-case")
    return value


def validate_user(value: str) -> str:
    if not USER_RE.fullmatch(value):
        raise BootstrapError("SSH and admin users must be safe POSIX account names")
    return value


def validate_target(value: str) -> str:
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        if DEVICE_RE.fullmatch(value):
            return value
    raise BootstrapError("target must be one exact IP address or lowercase SSH alias")


def run_ssh(args: argparse.Namespace, script: str, remote_args: list[str] | None = None) -> str:
    target = validate_target(args.target)
    user = validate_user(args.ssh_user)
    command = [
        "ssh",
        "-o", "ConnectTimeout=10",
        "-o", "ServerAliveInterval=5",
        "-o", "ServerAliveCountMax=2",
        "-o", "StrictHostKeyChecking=yes",
        f"{user}@{target}",
        "bash -s" if user == "root" else "sudo -n bash -s",
    ]
    if remote_args:
        command[-1] += " -- " + " ".join(shlex.quote(item) for item in remote_args)
    if getattr(args, "allow_password_bootstrap", False):
        import pexpect

        password = os.environ.get("SSH_BOOTSTRAP_PASSWORD") or getpass.getpass(
            f"Password for {user}@{target}: "
        )
        password_command = command[:1] + [
            "-o", "PreferredAuthentications=password",
            "-o", "PubkeyAuthentication=no",
            "-o", "KbdInteractiveAuthentication=no",
        ] + command[1:]
        try:
            child = pexpect.spawn(
                password_command[0],
                password_command[1:],
                encoding="utf-8",
                timeout=30,
            )
            match = child.expect([r"(?i)password:", r"Host key verification failed", pexpect.EOF])
            if match != 0:
                detail = child.before.strip().splitlines()[-1:] or ["password SSH bootstrap failed"]
                raise BootstrapError(detail[0])
            child.sendline(password)
            child.send(script)
            child.sendeof()
            child.expect(pexpect.EOF, timeout=1800)
            return child.before
        except (pexpect.TIMEOUT, pexpect.EOF) as exc:
            raise BootstrapError("password SSH bootstrap timed out or closed") from exc
    completed = subprocess.run(
        command[:1] + ["-o", "BatchMode=yes"] + command[1:],
        input=script,
        text=True,
        capture_output=True,
        check=False,
        timeout=1800,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()[-1:] or ["remote operation failed"]
        raise BootstrapError(detail[0])
    return completed.stdout


def parse_pairs(output: str) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if re.fullmatch(r"[a-z][a-z0-9_]*", key):
            facts[key] = value
    return facts


def generation_for(facts: dict[str, Any]) -> str:
    material = json.dumps(facts, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(material.encode()).hexdigest()


def host_key(args: argparse.Namespace) -> dict[str, Any]:
    target = validate_target(args.target)
    scanned = subprocess.run(
        ["ssh-keyscan", "-T", "10", target],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    lines = [line for line in scanned.stdout.splitlines() if line and not line.startswith("#")]
    if scanned.returncode != 0 or not lines:
        raise BootstrapError("no SSH host key was returned by the exact target")
    fingerprints: list[str] = []
    for line in lines:
        described = subprocess.run(
            ["ssh-keygen", "-lf", "-"],
            input=line + "\n",
            capture_output=True,
            text=True,
            check=False,
        )
        if described.returncode == 0:
            fingerprints.append(described.stdout.strip())
    return {
        "schema": SCHEMA,
        "operation": "host-key",
        "status": "server_bootstrap_host_key_observed",
        "target": target,
        "fingerprints": fingerprints,
        "trusted": False,
        "next_action": "verify out of band before adding to known_hosts",
    }


def inspect(args: argparse.Namespace) -> dict[str, Any]:
    facts = parse_pairs(run_ssh(args, INSPECT_SCRIPT))
    facts["device_id"] = validate_device_id(args.device_id)
    facts["target"] = validate_target(args.target)
    return {
        "schema": SCHEMA,
        "operation": "inspect",
        "status": "server_bootstrap_inspected",
        "facts": facts,
        "generation": generation_for(facts),
        "redaction": "secret-safe",
    }


def load_facts(args: argparse.Namespace) -> dict[str, Any]:
    if args.facts_file:
        payload = json.loads(Path(args.facts_file).read_text(encoding="utf-8"))
        if payload.get("schema") != SCHEMA or not isinstance(payload.get("facts"), dict):
            raise BootstrapError("facts file is not a server bootstrap inspection")
        facts = payload["facts"]
        if facts.get("device_id") != validate_device_id(args.device_id):
            raise BootstrapError("facts file device does not match the requested device")
        if facts.get("target") != validate_target(args.target):
            raise BootstrapError("facts file target does not match the requested target")
        if payload.get("generation") != generation_for(facts):
            raise BootstrapError("facts file generation does not match its content")
        return payload
    return inspect(args)


def build_actions(args: argparse.Namespace, facts: dict[str, Any]) -> list[dict[str, Any]]:
    observed = facts["facts"]
    actions: list[dict[str, Any]] = [
        {"id": "snapshot", "effect": "host_write", "rollback": "config snapshot"},
        {"id": "packages", "effect": "host_write", "rollback": "package upgrade is not fully reversible", "skip": bool(args.skip_package_upgrade)},
        {"id": "hostname", "effect": "host_write", "desired": args.hostname},
        {"id": "admin-key", "effect": "host_write", "desired": args.admin_user, "requires": "admin public key file"},
        {"id": "ssh-hardening", "effect": "host_write", "guard": "verify key login before closing bootstrap session"},
        {"id": "firewall", "effect": "host_write", "desired": f"allow TCP {observed.get('ssh_port', '22')} only by default"},
        {"id": "unattended-security-updates", "effect": "host_write", "automatic_reboot": False},
    ]
    if args.enable_tailscale:
        actions.extend([
            {"id": "tailscale-install", "effect": "host_write", "requires": "TAILSCALE_AUTH_KEY", "tag": args.tailscale_tag},
            {"id": "tailscale-policy", "effect": "external_write", "separate_authorization": True},
        ])
    if args.enable_beszel:
        actions.extend([
            {"id": "beszel-hub-record", "effect": "external_write", "separate_authorization": True},
            {"id": "beszel-agent", "effect": "host_write", "listen": "<tailscale-ip>:45876", "auto_update": False},
        ])
    return actions


def plan(args: argparse.Namespace) -> dict[str, Any]:
    facts = load_facts(args)
    return {
        "schema": SCHEMA,
        "operation": "plan",
        "status": "server_bootstrap_planned",
        "device_id": validate_device_id(args.device_id),
        "base_generation": facts["generation"],
        "actions": build_actions(args, facts),
        "authorization_required": ["host_write"] + (["external_write"] if args.enable_tailscale or args.enable_beszel else []),
    }


def read_public_key(path: str) -> str:
    value = Path(path).read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"ssh-(?:ed25519|rsa) [A-Za-z0-9+/=]+(?: [^\r\n]+)?", value):
        raise BootstrapError("admin public key file must contain one OpenSSH public key")
    return value


def apply(args: argparse.Namespace) -> dict[str, Any]:
    current = inspect(args)
    if current["generation"] != args.expected_generation:
        raise BootstrapError("live generation changed; inspect and plan again")
    public_key = read_public_key(args.admin_public_key_file)
    if args.enable_tailscale and not os.environ.get("TAILSCALE_AUTH_KEY"):
        raise BootstrapError("TAILSCALE_AUTH_KEY is required when Tailscale is enabled")
    if args.enable_beszel and not args.beszel_key:
        raise BootstrapError("--beszel-key is required when Beszel is enabled")
    secret_prefix = ""
    if args.enable_tailscale:
        secret_prefix = "export TAILSCALE_AUTH_KEY=" + shlex.quote(os.environ["TAILSCALE_AUTH_KEY"]) + "\n"
    output = run_ssh(
        args,
        secret_prefix + APPLY_SCRIPT,
        [
            validate_device_id(args.device_id),
            validate_user(args.admin_user),
            validate_device_id(args.hostname),
            public_key,
            str(bool(args.skip_package_upgrade)).lower(),
            str(bool(args.enable_tailscale)).lower(),
            args.tailscale_tag,
            str(bool(args.enable_beszel)).lower(),
            args.beszel_key or "",
        ],
    )
    result = parse_pairs(output)
    return {"schema": SCHEMA, "operation": "apply", "status": "server_bootstrap_applied", **result}


def verify(args: argparse.Namespace) -> dict[str, Any]:
    observed = inspect(args)
    facts = observed["facts"]
    findings: list[str] = []
    if facts.get("hostname") != args.hostname:
        findings.append("hostname_mismatch")
    if facts.get("firewall") not in {"active", "nftables"}:
        findings.append("firewall_not_active")
    if args.enable_tailscale and facts.get("tailscale_state") == "absent":
        findings.append("tailscale_missing")
    if args.enable_beszel and facts.get("beszel_state") != "active":
        findings.append("beszel_agent_not_active")
    return {
        "schema": SCHEMA,
        "operation": "verify",
        "status": "server_bootstrap_verified" if not findings else "server_bootstrap_verification_failed",
        "generation": observed["generation"],
        "findings": findings,
        "external_verification_required": bool(args.enable_tailscale or args.enable_beszel),
    }


def rollback(args: argparse.Namespace) -> dict[str, Any]:
    current = inspect(args)
    if current["generation"] != args.expected_generation:
        raise BootstrapError("live generation changed; inspect rollback target again")
    output = run_ssh(
        args,
        ROLLBACK_SCRIPT,
        [validate_device_id(args.device_id), args.transaction_id],
    )
    result = parse_pairs(output)
    return {
        "schema": SCHEMA,
        "operation": "rollback",
        "status": "server_bootstrap_config_rolled_back",
        **result,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    for name in ("host-key", "inspect", "plan", "apply", "verify", "rollback"):
        command = commands.add_parser(name)
        if name != "host-key":
            command.add_argument("--device-id", required=True)
        command.add_argument("--target", required=True)
        if name != "host-key":
            command.add_argument("--ssh-user", default="root")
            command.add_argument("--allow-password-bootstrap", action="store_true")
        if name not in {"inspect", "rollback"}:
            command.add_argument("--hostname", required=True)
            command.add_argument("--admin-user", default="wyatt")
            command.add_argument("--skip-package-upgrade", action="store_true")
            command.add_argument("--enable-tailscale", action="store_true")
            command.add_argument("--tailscale-tag", default="tag:server")
            command.add_argument("--enable-beszel", action="store_true")
            command.add_argument("--beszel-key", default="")
        if name == "plan":
            command.add_argument("--facts-file")
        if name == "apply":
            command.add_argument("--expected-generation", required=True)
            command.add_argument("--admin-public-key-file", required=True)
        if name == "rollback":
            command.add_argument("--expected-generation", required=True)
            command.add_argument("--transaction-id", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if hasattr(args, "tailscale_tag") and not TAG_RE.fullmatch(args.tailscale_tag):
            raise BootstrapError("Tailscale tag must use tag:<name>")
        result = {
            "host-key": host_key,
            "inspect": inspect,
            "plan": plan,
            "apply": apply,
            "verify": verify,
            "rollback": rollback,
        }[args.operation](args)
        emit(result)
        return 0 if not result.get("findings") else 3
    except (BootstrapError, OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        emit({"schema": SCHEMA, "operation": args.operation, "status": "server_bootstrap_failed", "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
