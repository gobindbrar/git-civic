---
name: Band room replay and provider quotas
description: Why per-request Band agents should not replay old room work
---

For a per-request Band briefing, do not let short-lived SDK agents automatically subscribe to all existing rooms. Verify a room's participant IDs against Band's participant list, and route through explicit mentions for the current room only.

**Why:** Unfinished messages in prior rooms can be recovered when agents reconnect. During multi-agent testing this can consume OpenRouter's limited daily free requests without advancing the current briefing; a real 429 then prevents both a new Band run and the live single-agent fallback.

**How to apply:** When changing Band room lifecycle or re-running a live test, check old-room replay settings and the provider's remaining quota before requesting multiple long agent turns. Do not claim a completed critic veto on the basis of a timeout or a partial room trace.