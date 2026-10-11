# 02. SSH through the subnet router stalls after the banner

Date: 2026-10-11
Milestone: 2, platform compute

## Symptom

From the workstation, over the mesh VPN:

- SSH to the orchestrator worked.
- TCP port 22 on the worker opened and the SSH banner arrived. Then the session hung. `ssh-keyscan` printed the banner and no key.
- SSH from the orchestrator to the worker worked.

So the route, the rules, and the worker were fine. Only connections routed through the orchestrator broke, and only once the packets got large.

## Cause

Confirmed with a capture. The path has two packet sizes and the worker never learns about the smaller one.

| Interface on the orchestrator | MTU |
| --- | --- |
| `eth0` | 1500 |
| `tailscale0` | 1280 |

The worker sends full-size segments. The orchestrator cannot forward them into the 1280-byte tunnel, so it answers with an ICMP "fragmentation needed" message. The worker's network security group allows SSH from the orchestrator and nothing else inbound, so the ICMP message is dropped. The worker retransmits the same oversized segment until the client gives up.

```bash
sudo tcpdump -ni eth0 "host 10.40.0.36 and (icmp or (tcp port 22 and greater 1200))"
```

```text
IP 10.40.0.36.22 > 10.40.0.4.61268: Flags [P.], seq 1:1533, ... length 1532
IP 10.40.0.4 > 10.40.0.36: ICMP 10.40.0.4 unreachable - need to frag (mtu 1280), length 556
IP 10.40.0.36.22 > 10.40.0.4.61268: Flags [.], seq 1:1399, ... length 1398
IP 10.40.0.4 > 10.40.0.36: ICMP 10.40.0.4 unreachable - need to frag (mtu 1280), length 556
IP 10.40.0.36.22 > 10.40.0.4.61268: Flags [.], seq 1:1399, ... length 1398
IP 10.40.0.4 > 10.40.0.36: ICMP 10.40.0.4 unreachable - need to frag (mtu 1280), length 556
```

The SSH key exchange is the first large packet in a session, which is why the banner got through and nothing after it. The orchestrator had no rule that adjusts the segment size: `nft list ruleset` contained no `maxseg` rule.

## Fix

The orchestrator rewrites the maximum segment size on every routed TCP handshake, so neither end sends a segment the tunnel cannot carry. 1240 is the tunnel MTU minus 40 bytes of IPv4 and TCP headers.

```text
table inet aisec_mss {
  chain forward {
    type filter hook forward priority mangle; policy accept;
    iifname "tailscale0" tcp flags syn tcp option maxseg size set 1240
    oifname "tailscale0" tcp flags syn tcp option maxseg size set 1240
  }
}
```

The table is in `/etc/aisec/mss-clamp.nft`, loaded by `aisec-mss-clamp.service` before the mesh VPN agent starts. Both files come from the orchestrator's cloud-init. On the running orchestrator they were installed by hand with the same content, because the VM's custom data is not reapplied after creation.

The obvious alternative is to let the ICMP message through. That is the wrong trade here. A security group rule cannot select one ICMP type, so it would mean allowing all ICMP from the orchestrator into the worker and into every target subnet. The clamp fixes it in one place and opens nothing.

## Verification

With the table loaded, from the workstation:

```bash
ssh-keyscan -T 10 -t ed25519 10.40.0.36 | ssh-keygen -lf -
ssh aisec@10.40.0.36 hostname
```

The scan returned the worker's host key, with the fingerprint printed in its serial log, and the login returned `aisec-worker`. After a restart of the orchestrator VM the service was `active`, the table was loaded, and the worker was reachable again.

## Limits

- The clamp covers TCP. A UDP or ICMP flow routed through the tunnel with packets over 1280 bytes still fails the same way. Nothing in the design routes one today.
- The value is fixed. If the tunnel MTU changes, the number has to change with it.
