# 03. The package proxy cannot fetch from the mirrors over TLS

Date: 2026-10-11
Milestone: after 2, before toolchain integration

## Symptom

The orchestrator's security group allows TCP 80 to the internet for one reason: Ubuntu package mirrors. Closing it looked cheap. The worker would keep speaking plain HTTP to Squid, so the `GET` and `HEAD` limit from [ADR 0011](../decisions/0011-package-proxy-for-the-worker.md) stays, and Squid would fetch from the two mirrors on port 443.

The change to `/etc/squid/squid.conf` on the orchestrator:

```text
cache_peer archive.ubuntu.com parent 443 0 originserver tls no-query no-digest name=archive
cache_peer security.ubuntu.com parent 443 0 originserver tls no-query no-digest name=security
cache_peer_access archive allow to_archive
cache_peer_access security allow to_security
never_direct allow all
```

`squid -k parse` accepted it. From the worker, every refusal still worked and every allowed request broke:

| Request through the proxy | Before | After |
| --- | --- | --- |
| `GET` `archive.ubuntu.com` | 200 | 502 |
| `GET` `security.ubuntu.com` | 200 | 502 |
| Another host, `POST`, port 8080, `CONNECT` | 403 | 403 |

`apt-get update` on the worker failed with `502  Bad Gateway`.

## Cause

Two separate failures, both in how this Squid build talks TLS to a peer. The package is `squid` 7.2-2ubuntu2.2 from the `main` repository, which is built against GnuTLS.

**With TLS 1.3, the session ends on the first read.** Observed, cause not confirmed. With `debug_options ALL,1 83,5`, `cache.log` shows the handshake finishing, one write, and then the session being torn down:

```text
Handshake: TLS session info: (TLS1.3)-(ECDHE-SECP256R1)-(RSA-PSS-RSAE-SHA256)-(AES-256-GCM)
callBack: TLS setup ended for conn79 local=10.40.0.4:45056 remote=185.125.190.81:443 FIRSTUP_PARENT
tls_write_method: started for session=0x5cf2c06a31b0
tls_read_method: started for session=0x5cf2c06a31b0
tls_read_method: started for session=0x5cf2c06a31b0
operator(): gnutls_deinit session=0x5cf2c06a31b0
```

Hypothesis: the build treats a TLS 1.3 message that arrives after the handshake as the end of the connection. Limiting the peer to TLS 1.2 with `tls-options=NORMAL:-VERS-TLS1.3` made reads work, which fits, but does not prove it.

**With TLS 1.2, the mirror answers 421.** The mirror refuses a request whose TLS handshake names no server. The same request sent without a server name from the orchestrator gets the same answer:

```bash
printf 'GET /ubuntu/dists/resolute/InRelease HTTP/1.1\r\nHost: archive.ubuntu.com\r\nConnection: close\r\n\r\n' |
  openssl s_client -quiet -noservername -connect archive.ubuntu.com:443 2>/dev/null | head -1
```

```text
HTTP/1.1 421 Misdirected Request
```

Adding `tls-domain=archive.ubuntu.com` to the peer line changed nothing. So this build sends no server name on a peer connection and has no option that makes it. Squid's own handshake was not captured. The conclusion rests on the matching 421.

## Fix

None. The original configuration was restored and port 80 stays open. The worker's updates were broken for about four minutes.

Every way around the two failures costs more than the open port:

| Option | Why not |
| --- | --- |
| `squid-openssl` in place of `squid` | It is in `universe`, which is community-maintained. 0011 chose the `main` package for that reason, and this is the one service the untrusted side can reach |
| Let the worker tunnel HTTPS to the two mirrors with `CONNECT` | The proxy stops seeing requests. The `GET` and `HEAD` limit, which was 0011's answer to "package hosts accept uploads", is gone |
| Keep port 80 and allow only the mirrors' addresses | A security group matches addresses, not names. Nine addresses today. When they move, updates stop, and nothing alerts on that yet |

What the open port is worth to an attacker is small. Port 443 is open to every host from the same machine, and that is the accepted risk ([T05](../security/threat-model.md)). Port 80 adds a second, cleartext way out of a machine that already has an encrypted one. The worker gains nothing from it: it reaches the proxy and nothing else.

## Verification

After restoring the file, its checksum matched the backup taken before the change, and from the worker:

```text
archive 200
security 200
other_host 403
post 403
port8080 403
connect 403
```

`sudo apt-get update` on the worker completed with no failed index.

## Limits

- The orchestrator's own package source is `http://azure.archive.ubuntu.com`, which does not answer on port 443. `https://archive.ubuntu.com` does. The orchestrator was not moved: with the worker's path still on port 80 it closes nothing.
- Worth another look when the `main` package changes its TLS library or a later Squid sends a server name to peers.
