# Harden and Update an Existing Host

Use this workflow when the user explicitly authorizes firewall changes, SSH exposure reduction, operating-system updates, or reboot-related repair around an existing Xray node.

## Contents

- Establish the network boundary
- Back up and preserve recovery
- Apply a minimal UFW policy
- Validate from an independent network
- Update and reboot safely
- Handle services bound to Tailscale
- Preserve per-device credentials

## Establish the Network Boundary

Before changing anything, record:

- IPv4 and IPv6 INPUT policies and the effective UFW/nftables/iptables rules.
- Every TCP and UDP listener, including its bound interface and owning process.
- Docker-published ports and the `DOCKER-USER` policy; Docker may bypass ordinary UFW expectations.
- Whether a provider firewall exists. Treat it as unknown when it cannot be inspected from the host.
- The active SSH route and whether it is public, Tailscale, or both.
- Services bound to a Tailscale address, because a reboot can expose startup-order races.

Do not infer public exposure only from a process listening on `0.0.0.0`; combine listener, host-firewall, and provider-firewall evidence.

## Back Up and Preserve Recovery

Before enabling a firewall or installing updates:

1. Back up the effective Xray config with mode `0600`.
2. Save `iptables-save`, `ip6tables-save`, the current package list, and any unit file that may be changed.
3. Keep the backup directory root-only.
4. Verify a second SSH connection over the management path.
5. Record `ufw disable` as the immediate firewall rollback when using UFW.
6. Validate the unchanged Xray configuration before proceeding.

Never close the known-good management session until the new policy has been verified.

## Apply a Minimal UFW Policy

For a host whose public data plane is Xray on TCP 443 and whose management plane is Tailscale, the minimal policy is:

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 443/tcp comment 'Xray REALITY'
ufw allow in on tailscale0 comment 'Tailnet management'
ufw allow 41641/udp comment 'Tailscale direct connectivity'
ufw --force enable
```

Before enabling it:

- Confirm `/etc/default/ufw` has IPv6 enabled so the policy covers both families.
- Confirm Tailscale SSH or ordinary SSH over the tailnet works.
- Keep public SSH closed unless the user explicitly requires it; if required, restrict it to named source addresses where possible.
- Treat allowing all input on `tailscale0` as relying on tailnet identity and ACLs. Use narrower tailnet rules when the environment requires them.

After enabling, inspect the actual INPUT policy and UFW-generated chains, not only `ufw status`.

## Validate from an Independent Network

Verify at least:

- Tailnet SSH still works in a new session.
- Public TCP 443 is reachable.
- Public TCP 22 is blocked when SSH was intentionally restricted.
- Xray's expected TLS/REALITY fallback still completes.
- Tailnet-only monitoring or management ports remain reachable from an authorized tailnet peer.

Use an independent external host for public-port tests. A workstation whose traffic is routed through the Xray node can create a self-connection and falsely report a blocked public port as reachable. When results conflict with the firewall policy, inspect INPUT counters, UFW logs, and the observed connection source before changing rules.

Do not open a monitoring port publicly merely because its dashboard reports the agent offline; first verify its bind address, expected path, and actual socket.

## Update and Reboot Safely

For Ubuntu or Debian, refresh package metadata and install the approved updates non-interactively. Report repository warnings, such as duplicate source definitions, but do not rewrite sources unless that cleanup is explicitly in scope.

After package installation:

1. Confirm no packages remain pending.
2. Compare the running kernel with the newly installed kernel.
3. Validate Xray before reboot.
4. Confirm Xray, Tailscale, SSH, and the firewall are healthy.
5. Reboot when required to load a new kernel.
6. Wait for the management path to return.
7. Re-check kernel version, IPv4 and IPv6 policies, listeners, Xray config, service logs, and independent reachability.

Installing current updates does not implicitly authorize unattended upgrades or automatic reboot policy; treat those as separate choices.

## Handle Services Bound to Tailscale

After reboot, a service can report `active` while its expected socket is absent if it attempted to bind a Tailscale address before `tailscale0` received that address. Diagnose in this order:

1. Compare the service's configured address with `tailscale ip -4` or `tailscale ip -6`.
2. Check the exact listener with `ss`; do not rely on service state alone.
3. Check firewall logs for the port.
4. Restart the service after Tailscale is online. If the socket appears, treat startup ordering as the likely cause.
5. Verify connectivity from an authorized tailnet peer.

Prevent recurrence with a systemd override that both orders the service after Tailscale and waits for the configured address:

```ini
[Unit]
Wants=tailscaled.service
After=tailscaled.service

[Service]
ExecStartPre=/bin/sh -c 'i=0; while [ "$i" -lt 30 ]; do /usr/bin/tailscale ip -4 | /usr/bin/grep -qx REPLACE_TAILSCALE_IP && exit 0; i=$((i + 1)); /usr/bin/sleep 1; done; exit 1'
```

Place this in a drop-in under `/etc/systemd/system/NAME.service.d/`, run `systemd-analyze verify`, reload systemd, restart the service, and verify its socket. Back up the original unit first. Do not add a public firewall rule when the service is intentionally tailnet-only.

## Preserve Per-Device Credentials

Count devices and active client entries before changing credentials:

- One device with one UUID and one Short ID already satisfies per-device isolation. Do not rotate it merely to restate the policy.
- When adding a device, generate a new UUID and a separate Short ID, retain existing credentials during migration, and remove only credentials the user has retired.
- Do not rotate the REALITY key, target, port, or existing device credentials as a side effect of host hardening.

Report every client-visible change. Adding or removing a client entry is a compatibility change even when the listener and REALITY key stay the same.
