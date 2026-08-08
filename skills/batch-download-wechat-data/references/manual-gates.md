# Manual gates

Read this file before any workflow involving login, credentials, proxy,
certificates, or WeChat desktop.

## User must perform

- Scan the exporter login QR code.
- Select the correct Official Account or service account.
- Confirm use of any auth-key or credentials file.
- Open article/history pages in WeChat desktop when credential capture is
  required.
- Scroll the history list if a proxy/history fallback requires it.
- Inspect downloaded content when copyright, restricted access, or
  redistribution risk matters.

## Require explicit confirmation before

- Installing `mitmproxy` or `wxdown-service` dependencies.
- Trusting a mitmproxy root certificate.
- Enabling, disabling, or changing macOS system proxy settings.
- Starting a proxy that intercepts WeChat article HTTPS traffic.
- Storing credentials in a local file or Keychain.
- Using browser automation on the exporter UI after login.

## Never do

- Operate WeChat UI or submit actions inside WeChat.
- Publish, delete, mass-send, follow, unfollow, or send messages.
- Bypass login, paywalls, deleted/private content, or platform permissions.
- Use another person's account/session as an account pool.
- Print cookies, auth-key, tokens, `pass_ticket`, `key`, `uin`, credential JSON,
  or QR login secrets.
- Leave the system proxy pointing at a local interceptor after a run.

## Failure modes to report

- WeChat endpoint or markup changes.
- Public exporter rate limits or rejects requests.
- Expired credentials or hidden/disabled comments.
- Expiring image/media URLs.
- Conflicts with Clash or another upstream proxy.
