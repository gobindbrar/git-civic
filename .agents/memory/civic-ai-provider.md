---
name: Civic AI provider availability
description: Why the civic briefing provider uses a free routing option and needs live validation
---

For source-backed civic briefings, keep model access errors visible and preserve the non-AI preview; do not silently switch providers or present an uncited answer as a verified briefing.

**Why:** A paid default returned a credit-required response, while a listed free model hit a rate limit; a free routing option succeeded with the project's configured key. Model availability, quotas, and JSON support can change independently of code correctness. Crusoe's older Intelligence API hostname returned a Cloudflare 1010 denial from this environment, while its documented Inference hostname accepted the same key. The latter's live model catalog omitted the older `inference_available` field.

**How to apply:** When changing the briefing model or provider, check a real public agenda request and validate citation IDs against retrieved items. For Crusoe, prefer a live catalog check on the working hostname and accept the listed chat models when the legacy availability field is absent; do not silently equate a missing field with `false`. If the provider is unavailable, show the failure rather than upgrading a preview's evidence label.