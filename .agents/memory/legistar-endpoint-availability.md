---
name: Legistar endpoint availability
description: Per-client Legistar API endpoints can have different public availability; distinguish API and website provenance.
---

Do not treat a successful Legistar Bodies API response as evidence that the same client's Events or EventItems API is usable. Check each public endpoint independently, and keep an official-site fallback distinct from a successful API integration.

**Why:** San Francisco's public Events endpoint returned a server-side agenda-visibility configuration error and EventItems returned a server error, while Bodies and the official Legistar calendar/meeting pages remained accessible. Repeated query variations did not bypass the Events configuration error.

**How to apply:** Before describing government records as API-backed, test the exact Events and EventItems calls. If an official page is used instead, surface that method and do not claim the API succeeded; if all official paths fail, show only clearly labeled samples.