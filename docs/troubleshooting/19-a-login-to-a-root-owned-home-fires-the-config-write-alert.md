# 19. A login to a root-owned home fires the config-write alert

Date: 2026-11-01
Milestone: 6, operational and containment drills

## Symptom

`audit-config-write` fired at 08:11 and 09:31 UTC on 2026-10-31, after the host audit's install and its new baselines were done. Nobody changed a platform file then. The records behind both were from the worker, ten in all between 08:08 and 09:53 UTC:

```text
type=SYSCALL ... syscall=34 success=no exit=-13 ... auid=997 uid=0 ... fsuid=997 ... comm="sshd-session" exe="/usr/lib/openssh/sshd-session" key="aisec-config" SYSCALL=mkdirat AUID="aisec-feed"
type=PATH ... item=1 name="/home/aisec-feed/.cache" nametype=CREATE
```

## Cause

Confirmed from the records, the homes, and the PAM module.

- **pam_motd marks the legal notice once per account.** Ubuntu's `pam_motd.so` (`libpam-modules 1.7.0-5ubuntu3.2`) shows `/etc/legal` at an account's first login and then creates `~/.cache/motd.legal-displayed`, as the account. The module holds the strings `/etc/legal`, `%s/.cache`, and `%s/motd.legal-displayed`.
- **The homes are root's.** `aisec-job` and `aisec-feed` were made with root-owned homes and no `.cache`, so the `mkdir` fails with `EACCES` and the next login tries again. `aisec-logexport` had its own `.cache` from before its home became root's, and its logins left no record.
- **The rule records a denied write, and the alert counts it.** The audit rule on each home has `perm=wa`, which matches the attempt whatever its outcome. The alert's query matches any `SYSCALL` record with the key.

Each check run logs in to `aisec-feed` once, and each job to `aisec-job` once (`05:53` on 2026-10-31, the job `syn-10310532`). A rebuilt worker would be worse: the host audit install makes the export account's home root's after that account's own install, so every journal pull, every five minutes, would fire the alert.

## Fix

The host audit install makes `.cache/motd.legal-displayed` root's in all three homes, after the line that makes the homes root's ([`install-host-audit.sh`](../../platform/host-audit/install-host-audit.sh)). `F.10` reads the three marks. A denied write by these accounts still fires the alert.

Counting only successful writes in the alert was the other option. It needs an apply, and it would stop alerting on an account that tries to write where it may not.

## Verification

On the live worker, 2026-11-01 07:38 to 08:04 UTC. Before the change `F.10` failed alone, reading only the export account's own mark, and two logins to the feed account left four denied `mkdirat` records. The install made the three marks `root root 644`, and AIDE reported the four new entries and the export account's two as changed, with the files the install rewrites, before a new baseline.

After it, two logins to the feed account and four journal pulls by 08:05 UTC left no denied record, and every check passed, 442 of 442. A job's login was not tried: it runs the same PAM session, so the result for it is reasoned.
