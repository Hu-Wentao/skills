---
name: install-xray-reality
description: Install, upgrade, configure, validate, repair, and maintain Xray-core with a minimal VLESS + XTLS Vision + REALITY server and matching client parameters. Use when deploying Xray to a Linux server, configuring or repairing a REALITY node, selecting or replacing a REALITY target/serverName, generating credentials or share links, checking an existing Xray service, or upgrading its core and configuration.
---

# Install Xray REALITY

Deploy the smallest production-usable VLESS + XTLS Vision + REALITY node. Inspect before changing, preserve existing access, validate before restart, and report every generated client parameter without exposing the server private key.

## Use Current Sources

Check current official documentation before installation because Xray syntax and key labels evolve:

- [XTLS/Xray-install](https://github.com/XTLS/Xray-install)
- [Xray REALITY reference](https://xtls.github.io/config/transports/reality.html)
- [Xray VLESS reference](https://xtls.github.io/config/inbounds/vless.html)
- [XTLS/REALITY example](https://github.com/XTLS/REALITY#readme)

Follow current official documentation when it conflicts with project documents, old examples, or community comments. State any resulting compatibility change.

## Establish Scope

1. Read the repository `AGENTS.md`, server inventory, and existing deployment documents.
2. Identify the requested server, connection method, public listening port, and whether the task is install, upgrade, repair, target replacement, inspection, or client-output only.
3. Inspect the remote host without mutation:
   - OS, architecture, init system, time synchronization, and available disk space.
   - Effective public IPv4/IPv6 and approximate network location.
   - Existing Xray binary, version, unit files, configuration paths, and service status.
   - Listeners on the requested port and current firewall state.
   - Other public or tailnet-bound services that a firewall change or reboot could affect.
4. Never print SSH private keys, REALITY private keys, full existing client secrets, passwords, or tokens into project files or logs.

Treat a request to install or repair the named server as authorization for normal in-scope package, configuration, and service changes. Stop for direction when a port is occupied, an existing configuration would be replaced, SSH access could be affected, the OS is unsupported by the official installer, or the requested change expands to firewall, panel, reverse proxy, DNS, or unrelated services.

## Choose the Workflow

- For target selection or replacement, read [references/target-selection.md](references/target-selection.md) and execute its measured evaluation workflow.
- For installation, upgrade, repair, client configuration, or a share link, read [references/configuration.md](references/configuration.md) before making changes.
- For host firewall changes, operating-system updates, SSH exposure reduction, or post-reboot verification, read [references/hardening-and-updates.md](references/hardening-and-updates.md) before making changes.
- For an existing healthy node, modify only the fields required by the request. Do not rotate UUID, REALITY key, Short ID, target, or port without a concrete reason.
- For inspection-only requests, run diagnostics and report; do not install, restart, or rewrite files.

## Prepare a Safe Change

Before installation or configuration:

1. Record the current binary version, service state, listeners, and configuration path.
2. Back up every existing file that will be changed with a timestamp and restrictive permissions.
3. Record a rollback command or file restoration sequence.
4. Confirm that TCP 443, or the requested alternative port, is not owned by another service.
5. Preserve the active SSH path. Do not enable, reset, or broadly rewrite a firewall as a side effect.
6. When the firewall change is in scope, verify a second management session and record dependent listeners before enabling it.

If the host already has a panel-managed Xray installation, do not edit its generated files directly until the management boundary is known. Use the panel's supported mechanism or ask the user to choose between panel-managed and standalone Xray.

## Install or Upgrade Xray

Use the official `XTLS/Xray-install` script on supported systemd distributions. Download over HTTPS from the official repository and inspect the resolved source when the environment or request requires supply-chain review.

After installation, verify the expected official layout instead of assuming success:

```text
/usr/local/bin/xray
/usr/local/etc/xray/
/etc/systemd/system/xray.service
```

Run `xray version` and record the installed version. Do not use unofficial one-click installers or install a web panel unless explicitly requested.

## Generate Parameters

Generate each value on the server with the installed Xray binary:

```bash
xray uuid
xray x25519
openssl rand -hex 8
```

Map the output carefully:

- UUID: server client `id` and client UUID.
- `PrivateKey`: server-only `privateKey`.
- `Password (PublicKey)`: client REALITY password; many GUIs call this **Public Key**, and share links encode it as `pbk`.
- Random hexadecimal value: one server `shortIds` entry and matching client `shortId`/`sid`.

Never include the private key in a client configuration or final response. Generate separate UUIDs for separate users or devices when requested; do not add account management beyond the task.

## Configure and Validate

Use the minimal current configuration in [references/configuration.md](references/configuration.md). Render it with the selected target and generated values into a temporary file, validate that file with the installed Xray version, then place it at the service's effective configuration path.

Validation is mandatory before restart:

```bash
xray run -test -config /path/to/candidate.json
```

If validation fails, do not restart. Diagnose the reported field, keep the existing service running when possible, and restore the backup if the invalid file replaced the active file.

## Start and Verify

After a valid configuration:

1. Reload systemd only when unit files changed.
2. Enable and restart the Xray service.
3. Check service state, recent journal entries, and the expected listening socket.
4. Confirm no unexpected management port was exposed.
5. Test a real client connection and ordinary HTTPS traffic when a compatible client is available.
6. Re-check service state after the client test.

After a host reboot, verify sockets and end-to-end reachability rather than relying only on `systemctl active`. A service that binds a Tailscale address can remain active without listening if it started before that address existed; use the hardening reference to diagnose and prevent this race.

Do not declare success based only on `systemctl active`; require a valid configuration, expected listener, clean startup log, and preferably an end-to-end client test.

## Deliver Client Output

Provide:

- Server address and port.
- UUID.
- Flow: `xtls-rprx-vision`.
- Transport: RAW/TCP as named by the client.
- Security: REALITY.
- SNI/serverName.
- REALITY password/Public Key.
- Short ID.
- Fingerprint: `chrome`, unless compatibility requires another supported value.
- A share link using the compatibility rules in [references/configuration.md](references/configuration.md).

Separate sensitive client material from durable project documentation. Do not commit live UUIDs, passwords/public keys, Short IDs, server addresses marked private, or share links unless the user explicitly asks and accepts the exposure.

## Report and Roll Back

Report the installed version, changed paths, backup location, selected target evidence, service/listener status, client-test result, and any untested assumption. List all breaking changes and compatibility choices.

On failure after restart:

1. Capture the service error without leaking secrets.
2. Restore the previous configuration and unit files.
3. Validate the restored configuration.
4. Restart and verify the previous service state.
5. Report the failure cause and restored state; do not continue with unrelated changes.
