# Task 15 — Story B6: Wake-on-LAN orchestration
# Attach: 00-PROJECT-CONTEXT.md · AGENTS.md · docs/PRD.md (Epic B) · docs/ARCHITECTURE.md (§6)
# Pre-req: worker heartbeat exists (B3); REQUIRES Track B hardware state
# (Ethernet-connected GPU node with WoL enabled in BIOS + ethtool).
# NOTE: on the current WSL2 interim setup this story can only be
# integration-tested partially — implement fully, mark the e2e test
# @pytest.mark.hardware and document manual verification steps.

Implement story B6: the control plane wakes the sleeping GPU node when
work is waiting.

Scope:
1. Model: extend `workers` (or create if B3 kept it implicit) — hostname,
   mac_address, tailscale_ip, last_heartbeat, status derived
   (ONLINE if heartbeat < 30s old). Worker agent already heartbeats to
   Redis; persist/refresh the row too (cheap upsert every beat).
2. Waker service in the API (asyncio background task via lifespan):
   every 20s — if queue depth > 0 AND no worker ONLINE AND last wake
   attempt > 3 min ago → send WoL magic packet (raw UDP broadcast to
   port 9, standard 6xFF + 16xMAC frame; implement in ~20 lines, no
   dependency needed) → record attempt in a Redis key + log.
3. Grace behavior: a woken node needs ~60-90s to boot + start the agent;
   the 3-min attempt spacing covers this. After 3 failed wake cycles,
   emit a WARNING log and set a Redis flag the dashboard reads.
4. Dashboard: worker status chip (online/offline/waking) on the jobs
   page; "GPU node is waking up — job will start automatically" banner
   on queued jobs when the flag/status warrants.
5. Admin route: `POST /api/v1/admin/workers/{id}/wake` — manual trigger.
6. Config: WOL_ENABLED (default false), WOL_BROADCAST_ADDR. Everything
   no-ops cleanly when disabled — WSL2 setups keep working unchanged.
7. Tests: magic-packet frame bytes correct for a known MAC; waker
   triggers only under (queue>0 ∧ no worker ∧ spacing); disabled flag
   no-ops; status derivation from heartbeat age.

Out of scope: auto-sleep of the idle node (document the manual
`systemctl suspend` + rtcwake option in docs/GPU-NODE.md), multi-node
scheduling.

Commit message:
feat(B6): demand-driven node wakeup via raw magic-packet orchestration

The control plane now watches queue depth against worker liveness and
wakes the GPU node with a hand-rolled WoL frame when jobs would
otherwise wait. Attempt pacing absorbs boot latency, repeated failures
surface to the dashboard, and the whole subsystem degrades to a no-op
where the hardware can't play along.
