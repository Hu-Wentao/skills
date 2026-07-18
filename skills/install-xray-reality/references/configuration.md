# Xray REALITY Configuration

## Contents

- Installation command
- Minimal server configuration
- Client parameters and share link
- Validation and service checks
- Compatibility rules

## Installation Command

Use the official systemd installer on a supported Linux distribution:

```bash
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
```

The official defaults install the binary at `/usr/local/bin/xray`, JSON configuration under `/usr/local/etc/xray`, and systemd units under `/etc/systemd/system`.

Do not pipe an unexpected redirect or non-GitHub response into Bash. When higher assurance is required, download the script, inspect it, and verify its source before execution.

## Minimal Server Configuration

Substitute every `REPLACE_*` value. Keep the target hostname consistent between `target` and `serverNames`.

```json
{
  "log": {
    "loglevel": "warning"
  },
  "inbounds": [
    {
      "tag": "vless-reality-in",
      "listen": "0.0.0.0",
      "port": 443,
      "protocol": "vless",
      "settings": {
        "clients": [
          {
            "id": "REPLACE_UUID",
            "flow": "xtls-rprx-vision"
          }
        ],
        "decryption": "none"
      },
      "streamSettings": {
        "network": "raw",
        "security": "reality",
        "realitySettings": {
          "show": false,
          "target": "REPLACE_TARGET:443",
          "xver": 0,
          "serverNames": [
            "REPLACE_TARGET"
          ],
          "privateKey": "REPLACE_PRIVATE_KEY",
          "shortIds": [
            "REPLACE_SHORT_ID"
          ]
        }
      },
      "sniffing": {
        "enabled": true,
        "destOverride": [
          "http",
          "tls",
          "quic"
        ],
        "routeOnly": true
      }
    }
  ],
  "outbounds": [
    {
      "tag": "direct",
      "protocol": "freedom"
    },
    {
      "tag": "block",
      "protocol": "blackhole"
    }
  ]
}
```

Keep the configuration minimal. Do not add routing rules, DNS overrides, fallback rate limits, ML-DSA keys, reverse proxies, or additional inbounds unless the task requires them.

For an existing installation, determine the effective config path from the systemd unit before writing. The official default is commonly `/usr/local/etc/xray/config.json`.

## Client Parameters

Configure a compatible client with:

```text
Protocol: VLESS
Address: server public IP or hostname
Port: 443
UUID/ID: REPLACE_UUID
Flow: xtls-rprx-vision
Encryption: none
Transport: RAW or TCP
Security: REALITY
SNI/serverName: REPLACE_TARGET
Password/Public Key: REPLACE_PASSWORD_PUBLIC_KEY
Short ID: REPLACE_SHORT_ID
Fingerprint: chrome
```

Current Xray JSON uses `password` for the client-side REALITY value generated from the server private key. Many GUIs retain the label **Public Key**.

Share-link form:

```text
vless://REPLACE_UUID@REPLACE_SERVER:443?encryption=none&security=reality&sni=REPLACE_TARGET&fp=chrome&pbk=REPLACE_PASSWORD_PUBLIC_KEY&sid=REPLACE_SHORT_ID&type=tcp&flow=xtls-rprx-vision#xray-reality
```

Percent-encode the label and any query values that require it. Keep `type=tcp` in share links for broad GUI compatibility even when current Xray JSON uses `network: "raw"`.

## Validation and Service Checks

Validate the candidate file before activation:

```bash
/usr/local/bin/xray run -test -config /path/to/candidate.json
```

Then verify the managed service:

```bash
systemctl enable xray
systemctl restart xray
systemctl --no-pager --full status xray
journalctl -u xray -n 100 --no-pager
ss -lntp
```

Use `ss` output to confirm the exact requested listener. Do not rely on a broad text match that could select another service.

## Compatibility Rules

- Prefer `network: "raw"`; older configurations and many clients call it `tcp`.
- Prefer server-side `target`; `dest` is its supported legacy alias.
- Prefer client-side `password`; GUIs may call it `publicKey` or **Public Key**, while share links use `pbk`.
- Keep `flow: "xtls-rprx-vision"` identical on server and client.
- Keep client `serverName` within the server `serverNames` list and normally equal to the target hostname.
- Use an even-length hexadecimal Short ID of at most 16 characters.
- Do not place `target` or `dest` in a client REALITY configuration.
- Confirm client support before using newer optional fields such as ML-DSA verification.
