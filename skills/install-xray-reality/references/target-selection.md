# Select a REALITY Target

Use current Xray documentation as authoritative and Issue #2005 as community discovery guidance.

## Contents

- Build candidates
- Apply criteria
- Account for relay risk
- Verify from the VPS and client
- Rank and report
- Sources

## Build Candidates

Prefer several candidates. Discover them with one or more of:

1. Query the VPS IP at `https://bgp.tools/`, select **DNS**, then **Show Forward DNS**.
2. Open `https://myip.ms/<VPS-IP>`, then **Other Sites on IP** under **Owner IP Range**. This service may be unavailable or restricted.
3. Search the VPS CIDR at `https://search.dnslytics.com/`.
4. Run [RealiTLScanner](https://github.com/XTLS/RealiTLScanner) from the relevant client network.
5. Use a stable well-known site only as a fallback when protecting target uniqueness is not a priority.

Do not equate numerical IP proximity with network proximity. Anycast, CDN routing, and announced address space can place adjacent IPs in different regions. Measure from the VPS.

## Apply Criteria

Require:

- Reliable reachability from the VPS on TCP 443.
- TLS 1.3.
- HTTP/2 (`h2`) on the main document, not only a secondary asset.
- A valid certificate for the chosen SNI.
- Direct reachability from the relevant client network.
- No redirect to an unrelated hostname; a bare-domain-to-`www` redirect is acceptable when configured consistently.

Prefer:

- Low, stable handshake latency from the VPS.
- Network location plausibly close to the VPS.
- X25519 or a modern key exchange reported by `xray tls ping`.
- OCSP stapling.
- A target that is not overused for REALITY.
- A target in the same ASN when suitable, as recommended by current Xray documentation.

## Account for Relay Risk

Resolve every candidate and identify its current network owner. Xray forwards failed REALITY authentication traffic to `target`; a target on a general-purpose CDN can make the VPS usable as a forwarding entry point for that CDN.

Do not rank a CDN target first solely because it has the lowest latency. Report the owner and risk, then prefer a sufficiently fast non-CDN or narrower-hosting target. If a CDN target is unavoidable, treat SNI filtering or fallback rate limits as a separate change requiring explicit scope.

Historical measurements are not durable recommendations: re-check DNS, ASN, protocol support, and latency every time.

## Verify from the VPS

Substitute the candidate hostname:

```bash
domain=example.com
openssl s_client \
  -connect "${domain}:443" \
  -servername "${domain}" \
  -verify_hostname "${domain}" \
  -tls1_3 \
  -alpn h2 \
  -status </dev/null
```

Confirm certificate verification, TLS 1.3, and `ALPN protocol: h2`. Treat stapled OCSP as a bonus.

When available, run:

```bash
xray tls ping example.com:443
```

Use repeated IPv4 and IPv6 tests matching the server's resolver and routing behavior. Record the resolved address, TCP connection time, TLS handshake time, HTTP protocol, status, redirect, and failures. Do not claim proximity from one result.

## Verify from the Client

Access the site directly without the REALITY node:

1. Reload with browser Developer Tools open.
2. Confirm TLS 1.3 in **Security**.
3. Enable **Protocol** and **Remote Address** in **Network**.
4. Confirm `h2` on the main document.
5. Record the final hostname and redirects.

## Rank and Report

Use a compact evidence table:

| Candidate | TLS 1.3 | Main h2 | Valid SNI/cert | VPS latency/stability | Redirect | Network/relay risk | Result |
|---|---|---|---|---|---|---|---|

Reject failures of required criteria. Choose the most stable low-latency passing target with acceptable relay risk. Mark community heuristics separately from measured facts.

Configure the selected hostname consistently:

```json
"target": "example.com:443",
"serverNames": ["example.com"]
```

If a healthy node becomes intermittently slow or unreachable, re-test the target and try the next passing candidate before changing unrelated protocol settings.

## Sources

- [Xray REALITY reference](https://xtls.github.io/config/transports/reality.html)
- [XTLS/REALITY target criteria](https://github.com/XTLS/REALITY#readme)
- [XTLS/Xray-core Issue #2005](https://github.com/XTLS/Xray-core/issues/2005)
- [Akamai network description](https://www.akamai.com/global-services/support)
