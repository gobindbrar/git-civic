# GIT Civic — Get Involved Today

**Find it. Show up. Prove it.**

GIT Civic is a nonpartisan hackathon MVP for discovering public meetings, understanding how to participate, and keeping an evidence-labeled Civic Passport. Local civic information can be difficult to find or understand; this demo brings meeting details and participation tracking into one approachable place.

## What works

- A responsive landing page and discovery calendar with city/text, subject, and jurisdiction filters.
- Live San Francisco meetings from the official Legistar API or public website fallback, public Seattle Legistar feed records (or another configured API client), and five **clearly labeled fictional demo listings**. Community members can add **unverified** optional links.
- San Francisco meeting detail pages show published agenda items (file number, title, type, status, and description where available). Events also have neutral non-AI previews, optional cited AI briefs for checked official records, calendar invites, RSVPs, and browser-specific activity history.
- A check-in flow with self-reported attendance, private organizer code, and **explicitly simulated** presence/document modes.
- A private-by-default Civic Passport with evidence labels, a separate sample history, and CSV export.
- GIT Intelligence visualizes a **simulated** agent workflow, not running agents.

## Run on Replit

Start the **Start application** workflow, or run `python main.py`. It serves the app at `0.0.0.0:5000`. Python 3.13 and Flask are declared in `pyproject.toml`; install dependencies with the Replit package manager if needed. Open the Replit preview. Data lives in `civic.db` by default and is excluded from Git.

No API key is needed for the official sources. The San Francisco `sfgov` Events API currently returns HTTP 400 because its public agenda status is not configured at the source, so `services/legistar.py` falls back to the official San Francisco Legistar calendar and meeting pages. It labels that path as an official-website fallback, **not** an API success. Set `CIVIC_LIVE_ENABLED=0` to disable San Francisco fetching. The independently configured Legistar API feed defaults to Seattle and refreshes when the calendar is requested (at most every 15 minutes); if refresh fails, checks older than 24 hours are shown as expired. Configure `LEGISTAR_CLIENT`, `LEGISTAR_CITY`, and `LEGISTAR_TIMEZONE` together for another API tenant; the client is a tenant name, not a URL. API fetches use `webapi.legistar.com`, and meeting pages/agenda PDFs are only marked checked when their domains and tenant match the feed record. Both paths establish source provenance, **not** independent fact-checking. Cancelled meetings are excluded from new API imports; always confirm details directly with the organizer.

For optional AI briefing generation, put `OPENROUTER_API_KEY` in Replit Secrets and optionally set `OPENROUTER_MODEL` (default `openrouter/free`; free-model availability and rate limits can change). A briefing request retrieves official agenda-item titles for a recently checked meeting and sends those titles, the meeting name, and date to OpenRouter. The output is labeled AI-generated and cites retrieved item IDs or numbered San Francisco website agenda rows linked to the official meeting page; unrecognized citations are rejected. No AI request is made for a sample or community listing. If the provider or agenda is unavailable, the non-AI preview remains visible with an error. Do not commit credentials or confidential meeting details.

## Stack and planned architecture

The working MVP uses Python/Flask, SQLite, Beautiful Soup for official San Francisco site parsing, and dependency-free HTML/CSS/JavaScript. The frontend calls JSON API endpoints in `main.py`; persistence is local SQLite. `services/legistar.py` handles San Francisco records and `services/integrations.py` handles the other public Legistar API tenant plus OpenRouter briefing. No search or multi-agent coordination provider is connected. Future work includes identity/account support and participation evidence review.

## Privacy and verification

An anonymous browser-generated ID connects RSVPs and activity to this browser; there are no user accounts. Switching browsers or clearing local storage loses access to that ID's history. The privacy selector is stored locally and **does not publish a profile** or provide a real sharing service. Avoid entering sensitive information in public event descriptions.

Evidence labels represent **different standards**, not government certification: Self Reported means no external check; Organizer code confirms possession of a code but not identity; Presence Verified and Document Verified in this demo are **simulated only** and do not access GPS, accept documents, or review evidence. “Officially Verified” is a future level and is not awarded by this MVP. Meeting details, especially demo listings and briefing previews, must be confirmed with the relevant official public source before attending.

The original license remains in `LICENSE`.