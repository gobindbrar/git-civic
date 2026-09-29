"""GIT Civic: small, self-hosted civic events service."""

import hashlib
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, request, send_from_directory
from services.integrations import IntegrationError, fetch_meetings, fetch_agenda_items, generate_brief
from services.band_brief import BandUnavailable, configured as band_configured, generate_band_brief
from services.legistar import CITY as SF_CITY, SourceError, fetch_event_details, fetch_upcoming
from services.meeting_brief import build_meeting_brief


BASE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("CIVIC_DB_PATH", str(BASE / "civic.db")))
app = Flask(__name__, static_folder="static")
app.json.sort_keys = False
attempts = {}
attempt_lock = threading.Lock()
feed_lock = threading.Lock()
feed_last_attempt = 0.0
feed_error = ""
brief_cache = {}
brief_lock = threading.Lock()
sf_lock = threading.Lock()
sf_last_attempt = 0.0
sf_status = {"state": "loading", "source": SF_CITY}


def now():
    return datetime.now(timezone.utc).isoformat()


def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                organizer TEXT NOT NULL,
                description TEXT NOT NULL,
                location TEXT NOT NULL,
                city TEXT NOT NULL,
                zip_code TEXT NOT NULL DEFAULT '',
                starts_at TEXT NOT NULL,
                source_url TEXT NOT NULL DEFAULT '',
                accessibility TEXT NOT NULL DEFAULT '',
                jurisdiction TEXT NOT NULL DEFAULT 'City',
                topics TEXT NOT NULL DEFAULT '[]',
                agenda_url TEXT NOT NULL DEFAULT '',
                is_demo INTEGER NOT NULL DEFAULT 0,
                source_status TEXT NOT NULL DEFAULT 'unverified',
                source_checked_at TEXT NOT NULL DEFAULT '',
                source_record_id TEXT NOT NULL DEFAULT '',
                time_zone TEXT NOT NULL DEFAULT '',
                source_provider TEXT NOT NULL DEFAULT '',
                source_revision TEXT NOT NULL DEFAULT '',
                agenda_status TEXT NOT NULL DEFAULT '',
                body_id INTEGER,
                code_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rsvps (
                event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                participant_id TEXT NOT NULL,
                PRIMARY KEY (event_id, participant_id)
            );
            CREATE TABLE IF NOT EXISTS check_ins (
                event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                participant_id TEXT NOT NULL,
                receipt TEXT NOT NULL UNIQUE,
                verified_at TEXT NOT NULL,
                method TEXT NOT NULL DEFAULT 'organizer_code',
                is_demo INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (event_id, participant_id)
            );
        """)
        # Keep existing local databases usable as the demo grows.
        event_columns = {row["name"] for row in conn.execute("PRAGMA table_info(events)")}
        for name, definition in {
            "jurisdiction": "TEXT NOT NULL DEFAULT 'City'",
            "zip_code": "TEXT NOT NULL DEFAULT ''",
            "topics": "TEXT NOT NULL DEFAULT '[]'",
            "agenda_url": "TEXT NOT NULL DEFAULT ''",
            "is_demo": "INTEGER NOT NULL DEFAULT 0",
            "source_status": "TEXT NOT NULL DEFAULT 'unverified'",
            "source_checked_at": "TEXT NOT NULL DEFAULT ''",
            "source_record_id": "TEXT NOT NULL DEFAULT ''",
            "time_zone": "TEXT NOT NULL DEFAULT ''",
            "source_provider": "TEXT NOT NULL DEFAULT ''",
            "source_revision": "TEXT NOT NULL DEFAULT ''",
            "agenda_status": "TEXT NOT NULL DEFAULT ''",
            "body_id": "INTEGER",
        }.items():
            if name not in event_columns:
                conn.execute(f"ALTER TABLE events ADD COLUMN {name} {definition}")
        checkin_columns = {row["name"] for row in conn.execute("PRAGMA table_info(check_ins)")}
        for name, definition in {
            "method": "TEXT NOT NULL DEFAULT 'organizer_code'",
            "is_demo": "INTEGER NOT NULL DEFAULT 0",
        }.items():
            if name not in checkin_columns:
                conn.execute(f"ALTER TABLE check_ins ADD COLUMN {name} {definition}")
        seed_demo_events(conn)
        conn.execute("UPDATE events SET zip_code='94102' WHERE is_demo=1 AND zip_code=''")
        conn.execute("UPDATE events SET zip_code='94103' WHERE id='demo-transportation-authority'")


def seed_demo_events(conn):
    """Clearly labeled, fictional preview listings; never claim to be live."""
    if conn.execute("SELECT 1 FROM events LIMIT 1").fetchone():
        return
    local = ZoneInfo("America/Los_Angeles")
    samples = [
        ("demo-sf-board-2026-09-29", "San Francisco Board of Supervisors", "Public meeting",
         "City", "San Francisco", "San Francisco City Hall",
         "1 Dr Carlton B Goodlett Place, San Francisco, CA",
         datetime(2026, 9, 29, 14, 0, tzinfo=local),
         "Demo agenda preview: review the posted agenda for the final order of business. This sample listing is not a live government notice.",
         ["Public comment", "City policy"], "This is a sample event for the hackathon demo. Confirm the meeting details with the official city calendar before attending."),
        ("demo-planning-commission", "Planning Commission", "Planning & Development",
         "City", "San Francisco", "City Hall, Room 400",
         "1 Dr Carlton B Goodlett Place, San Francisco, CA",
         datetime(2026, 10, 6, 17, 0, tzinfo=local),
         "Demo agenda preview: a planning commission may review land-use applications and development proposals. No real agenda is attached.",
         ["Planning", "Housing"], "Sample listing only. Check the relevant public body’s official notice for actual agenda and participation instructions."),
        ("demo-transportation-authority", "Transportation Authority Meeting", "Transportation",
         "County", "San Francisco", "Board meeting room",
         "1455 Market Street, San Francisco, CA",
         datetime(2026, 10, 8, 15, 0, tzinfo=local),
         "Demo agenda preview: transportation funding and project updates are example topics only; no official agenda is attached.",
         ["Transit", "Public comment"], "Sample listing only. Confirm date, venue, agenda, and public-comment rules through the official authority."),
        ("demo-school-board", "School Board Regular Meeting", "Education",
         "City", "San Francisco", "District board room",
         "555 Franklin Street, San Francisco, CA",
         datetime(2026, 10, 13, 18, 0, tzinfo=local),
         "Demo agenda preview: school board meetings can include district operations and public comment. This sample does not describe an actual agenda.",
         ["Schools", "Community"], "Sample listing only. Consult the district’s official meeting notice before attending."),
        ("demo-community-workshop", "Neighborhood Community Workshop", "Other",
         "City", "San Francisco", "Community meeting space",
         "San Francisco, CA",
         datetime(2026, 10, 17, 10, 0, tzinfo=local),
         "Demo agenda preview: an example community workshop about local priorities. The organizer and agenda are fictional demo details.",
         ["Community", "Workshop"], "Sample listing only. No real organizer or official source is connected."),
    ]
    for (identifier, title, category, jurisdiction, city, venue, address,
         starts, description, topics, accessibility) in samples:
        conn.execute(
            """INSERT INTO events
            (id,title,category,organizer,description,location,city,zip_code,starts_at,
             source_url,accessibility,jurisdiction,topics,agenda_url,is_demo,code_hash,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (identifier, title, category, title, description, address, city,
             "94103" if identifier == "demo-transportation-authority" else "94102",
             starts.astimezone(timezone.utc).isoformat(), "", accessibility,
             jurisdiction, json.dumps(topics), "", 1,
             hashlib.sha256(secrets.token_bytes(32)).hexdigest(), now()),
        )


init_db()


def error(message, status=400):
    return jsonify(error=message), status


def event_data(conn, row):
    data = dict(row)
    data.pop("code_hash", None)
    data["is_demo"] = bool(data.get("is_demo"))
    if data["is_demo"]:
        data["source_status"] = "demo"
    elif data.get("source_status") in ("verified_feed", "verified_site"):
        try:
            checked = datetime.fromisoformat(data["source_checked_at"])
            if datetime.now(timezone.utc) - checked > timedelta(hours=24):
                data["source_status"] = "stale_feed"
        except (ValueError, TypeError):
            data["source_status"] = "stale_feed"
    try:
        data["topics"] = json.loads(data.get("topics") or "[]")
    except (TypeError, json.JSONDecodeError):
        data["topics"] = []
    data["rsvp_count"] = conn.execute(
        "SELECT COUNT(*) FROM rsvps WHERE event_id = ?", (data["id"],)
    ).fetchone()[0]
    return data


def sync_sf_events():
    """Preserve the existing San Francisco source, including its official-site fallback."""
    global sf_last_attempt, sf_status
    if os.environ.get("CIVIC_LIVE_ENABLED", "1") == "0":
        return {"state": "disabled", "source": SF_CITY}
    if sf_last_attempt and time.monotonic() - sf_last_attempt < 600:
        return sf_status
    with sf_lock:
        if sf_last_attempt and time.monotonic() - sf_last_attempt < 600:
            return sf_status
        try:
            events, mode = fetch_upcoming()
            checked_at = now()
            with db() as conn:
                for event in events:
                    conn.execute(
                        """INSERT INTO events
                        (id,title,category,organizer,description,location,city,zip_code,
                        starts_at,source_url,accessibility,jurisdiction,topics,agenda_url,is_demo,
                        source_provider,source_status,source_checked_at,source_revision,source_record_id,
                        time_zone,agenda_status,body_id,code_hash,created_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(id) DO UPDATE SET
                        title=excluded.title,category=excluded.category,organizer=excluded.organizer,
                        location=excluded.location,starts_at=excluded.starts_at,
                        source_url=excluded.source_url,agenda_url=excluded.agenda_url,
                        source_provider=excluded.source_provider,source_status=excluded.source_status,
                        source_checked_at=excluded.source_checked_at,source_revision=excluded.source_revision,
                        source_record_id=excluded.source_record_id,time_zone=excluded.time_zone,
                        agenda_status=excluded.agenda_status,body_id=excluded.body_id
                        WHERE events.source_provider LIKE 'legistar:sfgov:%'""",
                        (event["id"],event["title"],event["category"],event["organizer"],
                         event["description"],event["location"],event["city"],event["zip_code"],
                         event["starts_at"],event["source_url"],event["accessibility"],
                         event["jurisdiction"],json.dumps(event["topics"]),event["agenda_url"],0,
                         event["source_provider"],
                         "verified_site" if mode == "official_site" else "verified_feed",
                         checked_at,event["source_revision"],event["id"].rsplit("-",1)[-1],
                         "America/Los_Angeles",event["agenda_status"] or "",event["body_id"],
                         hashlib.sha256(secrets.token_bytes(32)).hexdigest(),checked_at),
                    )
            sf_status = {"state": "live", "source": SF_CITY, "mode": mode,
                         "checked_at": checked_at, "count": len(events)}
            sf_last_attempt = time.monotonic()
        except (SourceError, sqlite3.Error) as exc:
            app.logger.warning("San Francisco Legistar unavailable: %s", exc)
            sf_status = {"state": "unavailable", "source": SF_CITY, "count": 0}
            sf_last_attempt = time.monotonic() - 480
        return sf_status


def sync_feed():
    """Refresh periodically; never reclassify community links as checked sources."""
    global feed_last_attempt, feed_error
    if (feed_last_attempt and time.monotonic() - feed_last_attempt < 900) or not feed_lock.acquire(blocking=False):
        return
    try:
        feed_last_attempt = time.monotonic()
        meetings = fetch_meetings()
        with db() as conn:
            seen = {meeting["id"] for meeting in meetings}
            for meeting in meetings:
                existing = conn.execute("SELECT 1 FROM events WHERE id=?", (meeting["id"],)).fetchone()
                if existing:
                    conn.execute(
                        """UPDATE events SET title=:title, category=:category, organizer=:organizer,
                        description=:description, location=:location, city=:city, zip_code=:zip_code,
                        starts_at=:starts_at, source_url=:source_url, agenda_url=:agenda_url,
                        accessibility=:accessibility, jurisdiction=:jurisdiction, topics=:topics,
                        source_checked_at=:source_checked_at, time_zone=:time_zone, source_status='verified_feed'
                        WHERE id=:id AND source_record_id=:source_record_id AND is_demo=0""",
                        meeting,
                    )
                else:
                    conn.execute(
                        """INSERT INTO events (id,title,category,organizer,description,location,city,
                        zip_code,starts_at,source_url,agenda_url,accessibility,jurisdiction,topics,
                        is_demo,source_status,source_checked_at,source_record_id,time_zone,code_hash,created_at)
                        VALUES (:id,:title,:category,:organizer,:description,:location,:city,
                        :zip_code,:starts_at,:source_url,:agenda_url,:accessibility,:jurisdiction,:topics,
                        :is_demo,:source_status,:source_checked_at,:source_record_id,:time_zone,:code_hash,:created_at)""",
                        {**meeting, "code_hash": hashlib.sha256(secrets.token_bytes(32)).hexdigest(), "created_at": now()},
                    )
            # A removed/cancelled upcoming event must not retain a checked-feed label.
            for row in conn.execute(
                "SELECT id FROM events WHERE source_status='verified_feed' AND source_provider='' AND starts_at>=?",
                (now(),),
            ):
                if row["id"] not in seen:
                    conn.execute("UPDATE events SET source_status='stale_feed' WHERE id=?", (row["id"],))
        feed_error = ""
    except (IntegrationError, sqlite3.Error) as exc:
        feed_error = str(exc)
        app.logger.warning("Official feed refresh failed: %s", exc)
    finally:
        feed_lock.release()


def participant_id(data):
    value = data.get("participant_id", "")
    try:
        return str(uuid.UUID(value)) if isinstance(value, str) else None
    except ValueError:
        return None


def payload():
    return request.get_json(silent=True) if request.is_json else None


@app.get("/api/events")
def list_events():
    sf = sync_sf_events()
    sync_feed()
    with db() as conn:
        rows = conn.execute(
            """SELECT * FROM events WHERE
            source_provider NOT LIKE 'legistar:sfgov:%'
            OR (? = 'live' AND starts_at >= ?)
            ORDER BY starts_at ASC""", (sf["state"], now())
        ).fetchall()
        return jsonify(events=[event_data(conn, row) for row in rows],
                       feed_error=feed_error, live_status=sf)


@app.post("/api/events")
def create_event():
    data = payload()
    if not isinstance(data, dict):
        return error("Send a JSON event.")
    limits = {
        "title": 180, "category": 60, "organizer": 120,
        "description": 3000, "location": 180, "city": 120,
        "starts_at": 60, "source_url": 500, "accessibility": 1200,
        "jurisdiction": 40, "agenda_url": 500, "zip_code": 10,
    }
    required = {"title", "category", "organizer", "description", "location", "city", "starts_at"}
    values = {}
    for field, limit in limits.items():
        value = data.get(field, "")
        if not isinstance(value, str) or len(value.strip()) > limit:
            return error(f"{field.replace('_', ' ').capitalize()} is too long or invalid.")
        values[field] = value.strip() or ("City" if field == "jurisdiction" else "")
        if field in required and not values[field]:
            return error(f"{field.replace('_', ' ').capitalize()} is required.")
    topics = data.get("topics", [])
    if not isinstance(topics, list) or len(topics) > 12 or any(not isinstance(t, str) or len(t) > 60 for t in topics):
        return error("Topics must be a list of up to 12 short labels.")
    values["topics"] = json.dumps([t.strip() for t in topics if t.strip()])
    if values["zip_code"] and not re.fullmatch(r"\d{5}(?:-\d{4})?", values["zip_code"]):
        return error("ZIP code must be five digits (optionally with a four-digit extension).")
    try:
        start = datetime.fromisoformat(values["starts_at"].replace("Z", "+00:00"))
        if start.tzinfo is None:
            return error("Event time must include a timezone.")
        if start <= datetime.now(timezone.utc):
            return error("Event time must be in the future.")
        values["starts_at"] = start.astimezone(timezone.utc).isoformat()
    except ValueError:
        return error("Enter a valid event date and time.")
    if values["source_url"]:
        parsed = urlparse(values["source_url"])
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return error("Source link must be an http or https URL.")
    if values["agenda_url"]:
        parsed = urlparse(values["agenda_url"])
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return error("Agenda link must be an http or https URL.")
    code = secrets.token_urlsafe(12)
    identifier = str(uuid.uuid4())
    with db() as conn:
        conn.execute(
            """INSERT INTO events
            (id,title,category,organizer,description,location,city,zip_code,starts_at,
             source_url,accessibility,jurisdiction,topics,agenda_url,code_hash,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (identifier, *(values[k] for k in (
                "title", "category", "organizer", "description", "location", "city",
                "zip_code", "starts_at", "source_url", "accessibility", "jurisdiction"
             )), values["topics"], values["agenda_url"],
             hashlib.sha256(code.encode()).hexdigest(), now()),
        )
        row = conn.execute("SELECT * FROM events WHERE id = ?", (identifier,)).fetchone()
        result = event_data(conn, row)
    return jsonify(event=result, check_in_code=code), 201


@app.get("/api/events/<event_id>")
def get_event(event_id):
    if event_id.startswith("legistar-sfgov-"):
        sync_sf_events()
    elif event_id.startswith("legistar-"):
        sync_feed()
    with db() as conn:
        row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        if row is None:
            return error("Event not found.", 404)
        event = event_data(conn, row)
    if not event["source_provider"].startswith("legistar:sfgov:"):
        return jsonify(event=event)
    match = re.fullmatch(r"legistar-sfgov-(\d+)", event_id)
    if not match:
        return error("Invalid official event ID.", 404)
    try:
        details = fetch_event_details(match.group(1), event["source_url"])
    except SourceError:
        return jsonify(event=event, agenda_items=[],
                       agenda_error="Official agenda is temporarily unavailable. View the official source for details.",
                       meeting_brief=build_meeting_brief(event, []))
    with db() as conn:
        conn.execute(
            """UPDATE events SET location=?, agenda_url=?, agenda_status=?, body_id=?,
            source_provider=?, source_checked_at=?, source_status=? WHERE id=?""",
            ((details["location"] or event["location"])[:180],
             details["agenda_url"] or event["agenda_url"],
             details["agenda_status"] or event["agenda_status"],
             details["body_id"] or event["body_id"],
             f"legistar:sfgov:{details['source_mode']}", now(),
             "verified_site" if details["source_mode"] == "official_site" else "verified_feed",
             event_id),
        )
        event = event_data(conn, conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone())
    return jsonify(event=event, agenda_items=details["agenda_items"],
                   meeting_brief=build_meeting_brief(event, details["agenda_items"]))


@app.post("/api/events/<event_id>/brief")
def event_brief(event_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if row is None:
            return error("Event not found.", 404)
        event = event_data(conn, row)
    if event["source_status"] not in ("verified_feed", "verified_site"):
        return error("A recently checked official source is required for an AI briefing.", 409)
    try:
        if event["source_provider"].startswith("legistar:sfgov:"):
            details = fetch_event_details(event["source_record_id"], event["source_url"])
            # Bound the model input on long agendas and say exactly what was included.
            # The IDs are page row numbers, not independent legislative file IDs.
            items = [{"id": str(i + 1), "title": (item.get("title") or item.get("description") or "")[:240]}
                     for i, item in enumerate(details["agenda_items"][:6])
                     if item.get("title") or item.get("description")]
        else:
            items = fetch_agenda_items(event["source_record_id"])
        scope = (f"First {min(len(details['agenda_items']), 6)} of {len(details['agenda_items'])} official agenda rows"
                 if event["source_provider"].startswith("legistar:sfgov:") else "")
        evidence = {**event, "agenda_scope": scope} if scope else event
        if not items:
            raise IntegrationError("No published agenda items are available for a cited briefing.")
        fingerprint = hashlib.sha256(json.dumps(
            [event["title"], event["starts_at"], event["source_url"], scope, items],
            sort_keys=True).encode()).hexdigest()
        try:
            # Band remains opt-in and experimental, never part of the submission demo path.
            brief = (generate_band_brief(evidence, items)
                     if os.environ.get("BAND_BRIEF_ENABLED") == "1" and band_configured() else None)
        except BandUnavailable:
            brief = None
        if brief is None:
            try:
                brief = generate_brief(evidence, items)
                brief.update(mode="fallback", source_verification="NOT RUN",
                             civic_critic="NOT RUN", revision_requested=False,
                             workflow=["Official government data retrieved"])
            except IntegrationError:
                with brief_lock:
                    cached = brief_cache.get(event_id)
                if not cached or cached[0] != fingerprint:
                    raise
                brief = {**cached[1], "mode": "cached", "source_checked_at": event["source_checked_at"]}
                return jsonify(brief=brief)
        cited = set(brief.pop("cited_item_ids"))
        brief["citations"] = [{"title": item["title"], "url": event["source_url"], "item_id": item["id"]}
                              for item in items if item["id"] in cited]
        brief["source_checked_at"] = event["source_checked_at"]
        if scope:
            brief["agenda_scope"] = scope
        with brief_lock:
            brief_cache[event_id] = (fingerprint, brief)
        return jsonify(brief=brief)
    except (IntegrationError, SourceError) as exc:
        return error(str(exc), 503)


@app.post("/api/events/<event_id>/rsvp")
def rsvp(event_id):
    data = payload()
    if not isinstance(data, dict) or not participant_id(data) or type(data.get("going")) is not bool:
        return error("A participant ID and going status are required.")
    person = participant_id(data)
    with db() as conn:
        if not conn.execute("SELECT 1 FROM events WHERE id = ?", (event_id,)).fetchone():
            return error("Event not found.", 404)
        if data["going"]:
            conn.execute("INSERT OR IGNORE INTO rsvps VALUES (?, ?)", (event_id, person))
        else:
            conn.execute("DELETE FROM rsvps WHERE event_id = ? AND participant_id = ?", (event_id, person))
        count = conn.execute("SELECT COUNT(*) FROM rsvps WHERE event_id = ?", (event_id,)).fetchone()[0]
    return jsonify(going=data["going"], rsvp_count=count)


@app.get("/api/activity")
def activity():
    person = participant_id(request.args)
    if not person:
        return error("A valid participant ID is required.")
    with db() as conn:
        rsvps = conn.execute(
            "SELECT e.* FROM events e JOIN rsvps r ON e.id=r.event_id WHERE r.participant_id=? ORDER BY e.starts_at",
            (person,),
        ).fetchall()
        checked = conn.execute(
            "SELECT e.*, c.receipt, c.verified_at, c.method, c.is_demo AS checkin_is_demo FROM events e JOIN check_ins c ON e.id=c.event_id WHERE c.participant_id=? ORDER BY c.verified_at DESC",
            (person,),
        ).fetchall()
        return jsonify(
            rsvps=[event_data(conn, row) for row in rsvps],
            check_ins=[
                {"event": event_data(conn, row), "receipt": row["receipt"],
                 "verified_at": row["verified_at"], "method": row["method"],
                 "is_demo": bool(row["checkin_is_demo"])}
                for row in checked
            ],
        )


@app.post("/api/events/<event_id>/check-in")
def check_in(event_id):
    data = payload()
    if not isinstance(data, dict) or not participant_id(data):
        return error("A valid participant ID is required.")
    person = participant_id(data)
    method = data.get("method", "organizer_code")
    if method not in ("organizer_code", "self_reported", "presence_demo", "document_demo"):
        return error("Choose a supported check-in method.")
    if method == "organizer_code" and not isinstance(data.get("code"), str):
        return error("An organizer check-in code is required.")
    with db() as conn:
        row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        if row is None:
            return error("Event not found.", 404)
        previous = conn.execute(
            "SELECT receipt, verified_at, method, is_demo FROM check_ins WHERE event_id=? AND participant_id=?",
            (event_id, person),
        ).fetchone()
        if previous:
            return jsonify({**dict(previous), "is_demo": bool(previous["is_demo"])})
        # A code can only confirm attendance once the event has begun.
        if datetime.fromisoformat(row["starts_at"]) > datetime.now(timezone.utc):
            return error("Check-in opens when the event begins.")
        is_demo = method in ("presence_demo", "document_demo")
        if method == "organizer_code":
            key = (event_id, request.remote_addr)
            with attempt_lock:
                recent = [t for t in attempts.get(key, []) if time.monotonic() - t < 600]
                if len(recent) >= 5:
                    return error("Too many attempts. Try again in 10 minutes.", 429)
                recent.append(time.monotonic())
                attempts[key] = recent
            expected = row["code_hash"]
            submitted = hashlib.sha256(data["code"].strip().encode()).hexdigest()
            if not secrets.compare_digest(submitted, expected):
                return error("That check-in code is not correct.")
        receipt = str(uuid.uuid4())
        verified_at = now()
        conn.execute(
            "INSERT INTO check_ins (event_id,participant_id,receipt,verified_at,method,is_demo) VALUES (?,?,?,?,?,?)",
            (event_id, person, receipt, verified_at, method, int(is_demo)),
        )
    return jsonify(receipt=receipt, verified_at=verified_at, method=method, is_demo=is_demo), 201


@app.get("/")
@app.get("/events/<event_id>")
@app.get("/new")
@app.get("/my-activity")
@app.get("/passport")
@app.get("/how-it-works")
@app.get("/about")
def frontend(event_id=None):
    return send_from_directory(app.static_folder, "index.html")


@app.errorhandler(404)
def not_found(exc):
    if request.path.startswith("/api/"):
        return error("Not found.", 404)
    return send_from_directory(app.static_folder, "index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))