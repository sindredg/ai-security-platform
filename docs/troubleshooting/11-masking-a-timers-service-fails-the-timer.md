# 11. Masking a timer's service fails the timer

Date: 2026-10-19
Milestone: 3, toolchain integration

## Symptom

The first rollout for [#124](https://github.com/sindredg/ai-security-platform/issues/124) ran `systemctl mask --now` on six units at once on all four VMs, two timers and their services among them ([worklog](../worklogs/0003-toolchain-integration.md#ubuntus-own-requests)). `.21` passed afterwards. The next check run failed `.1`, no failed systemd unit, on every VM:

```text
● motd-news.timer            masked failed failed motd-news.timer
● update-notifier-motd.timer masked failed failed update-notifier-motd.timer
```

The journal of each timer, at the second of the rollout:

```text
motd-news.timer: Unit to trigger vanished.
motd-news.timer: Failed with result 'resources'.
```

## Cause

Confirmed from the journal. Both timers were running. The mask took their services away while the timers still pointed at them, and systemd fails a running timer whose service disappears. `--now` stops the units too, but the timer had already failed when it was stopped. A first boot from the templates in that form would have left the same two failed units, and `.1` would fail on every rebuilt VM.

## Fix

Stop the timers first, then mask. The four templates now run:

```bash
systemctl stop motd-news.timer update-notifier-motd.timer
systemctl mask esm-cache.service apt-news.service motd-news.timer motd-news.service \
  update-notifier-motd.timer update-notifier-motd.service
```

On the running VMs, `systemctl reset-failed` on the two timers clears the state.

## Verification

On each VM at 18:43 UTC: the failed timers reset, the six units unmasked, and both timers started, as after a boot. Then the two commands above. Read on all four: 2 failed units before, `active active` while the timers ran, 0 failed units after, and `.21`'s probe `masked masked masked masked 644`. The check run at 19:00 passed `.1` and `.21` on all four.
