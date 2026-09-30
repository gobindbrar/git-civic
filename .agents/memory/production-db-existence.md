---
name: Production database existence
description: A published app and a Replit-managed production PostgreSQL database are separate facts.
---

Verify the actual production datastore before planning a data migration. A successful public deployment does not, by itself, prove that Replit-managed production PostgreSQL exists or that the app uses it.

**Why:** A published app can serve live records while the read-only production SQL interface reports no managed production database. Public API listings may also be filtered and cannot substitute for a full database count.

**How to apply:** Establish the deployed app's datastore and obtain a trustworthy export before comparing records or planning a cutover; label any public-API counts as partial observations.