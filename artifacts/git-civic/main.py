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
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from functools import wraps
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx
import psycopg
from clerk_backend_api import Clerk
from clerk_backend_api.security.authenticaterequest import AuthenticateRequestOptions
from flask import Flask, g, jsonify, request, send_from_directory
from services.integrations import IntegrationError, fetch_meetings, fetch_agenda_items, generate_brief
from services.band_brief import BandUnavailable, configured as band_configured, generate_band_brief
from services.legistar import CITY as SF_CITY, SourceError, fetch_event_details, fetch_upcoming
from services.meeting_brief import build_meeting_brief


BASE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("CIVIC_DB_PATH", str(BASE / "civic.db")))
app = Flask(__name__, static_folder="static")
app.json.sort_keys = False
clerk_client = Clerk(bearer_auth=os.environ.get("CLERK_SECRET_KEY", ""))
feed_lock = threading.Lock()
feed_last_attempt = 0.0
feed_error = ""
BRIEF_RATE_LIMIT_PER_HOUR = 5
BRIEF_RATE_WINDOW_SECONDS = 60 * 60
BRIEF_GENERATION_LEASE_SECONDS = 180
sf_lock = threading.Lock()
sf_last_attempt = 0.0
sf_status = {"state": "loading", "source": SF_CITY}


def now():
    return datetime.now(timezone.utc).isoformat()


class HybridRow(dict):
    """PostgreSQL mapping row that preserves the old SQLite numeric access."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)

def _pg_row(cursor):
    columns = [column.name for column in cursor.description or ()]
    return lambda values: HybridRow(zip(columns, values))


class PgConnection:
    """Small SQL adapter while the existing API is migrated to PostgreSQL."""

    def __init__(self, connection):
        self.connection = connection

    def execute(self, statement, params=None):
        ignore = bool(re.search(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", statement, re.I))
        statement = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", statement, flags=re.I)
        # Convert the legacy SQLite placeholders without interpreting colons,
        # question marks, or percent signs inside SQL string literals.
        parts = re.split(r"('(?:''|[^'])*')", statement)
        for index, part in enumerate(parts):
            if index % 2:
                if params is not None:
                    parts[index] = part.replace("%", "%%")
                continue
            part = part.replace("?", "%s")
            part = re.sub(r"(?<!:):([A-Za-z_]\w*)", r"%(\1)s", part)
            if params is not None:
                part = re.sub(r"%(?!s|%|\([A-Za-z_]\w*\)s)", "%%", part)
            parts[index] = part
        statement = "".join(parts)
        if ignore:
            statement = statement.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
        return self.connection.execute(statement, params)


@contextmanager
def db():
    if os.environ.get("GIT_CIVIC_TEST_SQLITE") == "1":
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(DB_PATH)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required; GIT Civic no longer writes to local SQLite.")
    with psycopg.connect(database_url, row_factory=_pg_row, connect_timeout=8) as connection:
        yield PgConnection(connection)


def init_db():
    # Schema is managed from schema.sql and applied to development PostgreSQL;
    # Replit's Publish flow promotes the development schema to production.
    if os.environ.get("GIT_CIVIC_TEST_SQLITE") == "1":
        with db() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS app_users (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                    public_passport INTEGER NOT NULL DEFAULT 0, share_slug TEXT UNIQUE);
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL,
                    organizer TEXT NOT NULL, description TEXT NOT NULL, location TEXT NOT NULL,
                    city TEXT NOT NULL, zip_code TEXT NOT NULL DEFAULT '', starts_at TEXT NOT NULL,
                    source_url TEXT NOT NULL DEFAULT '', accessibility TEXT NOT NULL DEFAULT '',
                    jurisdiction TEXT NOT NULL DEFAULT 'City', topics TEXT NOT NULL DEFAULT '[]',
                    agenda_url TEXT NOT NULL DEFAULT '', is_demo INTEGER NOT NULL DEFAULT 0,
                    source_status TEXT NOT NULL DEFAULT 'unverified', source_checked_at TEXT NOT NULL DEFAULT '',
                    source_record_id TEXT NOT NULL DEFAULT '', time_zone TEXT NOT NULL DEFAULT '',
                    source_provider TEXT NOT NULL DEFAULT '', source_revision TEXT NOT NULL DEFAULT '',
                    agenda_status TEXT NOT NULL DEFAULT '', body_id INTEGER, code_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL, owner_id TEXT,
                    cancelled_at TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS rsvps (
                    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                    participant_id TEXT NOT NULL, PRIMARY KEY(event_id, participant_id));
                CREATE TABLE IF NOT EXISTS check_ins (
                    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                    participant_id TEXT NOT NULL, receipt TEXT NOT NULL UNIQUE,
                    verified_at TEXT NOT NULL, method TEXT NOT NULL DEFAULT 'organizer_code',
                    is_demo INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(event_id, participant_id));
                CREATE TABLE IF NOT EXISTS checkin_attempts (
                    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
                    window_started_at REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(event_id, user_id));
                CREATE TABLE IF NOT EXISTS generated_briefs (
                    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                    fingerprint TEXT NOT NULL, brief_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, PRIMARY KEY(event_id, fingerprint));
                CREATE TABLE IF NOT EXISTS brief_rate_limits (
                    user_id TEXT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
                    window_start BIGINT NOT NULL, requests INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(user_id, window_start));
                CREATE TABLE IF NOT EXISTS brief_generation_locks (
                    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                    fingerprint TEXT NOT NULL, lease_token TEXT NOT NULL,
                    locked_until BIGINT NOT NULL, PRIMARY KEY(event_id, fingerprint));
            """)
            seed_demo_events(conn)
        return
    with db() as conn:
        seed_demo_events(conn)
        conn.execute("UPDATE events SET zip_code='94102' WHERE is_demo=1 AND zip_code=''")
        conn.execute("UPDATE events SET zip_code='94103' WHERE id='demo-transportation-authority'")


def authenticated_user_id():
    if not os.environ.get("CLERK_SECRET_KEY") or not os.environ.get("CLERK_PUBLISHABLE_KEY"):
        return None
    if not request.headers.get("Authorization") and not request.headers.get("Cookie"):
        return None
    authorized = ["https://git-civic.replit.app"]
    configured_hosts = [
        os.environ.get("REPLIT_DEV_DOMAIN", ""),
        *os.environ.get("REPLIT_DOMAINS", "").split(","),
    ]
    for configured_host in configured_hosts:
        host = configured_host.strip().lower()
        if host.startswith(("https://", "http://")):
            host = urlparse(host).hostname or ""
        if host and re.fullmatch(r"[A-Za-z0-9.-]+", host):
            authorized.append(f"https://{host}")
    try:
        signed_request = httpx.Request(
            method=request.method,
            url=str(request.url),
            headers=dict(request.headers),
        )
        auth_state = clerk_client.authenticate_request(
            signed_request,
            AuthenticateRequestOptions(
                secret_key=os.environ["CLERK_SECRET_KEY"],
                authorized_parties=authorized,
            ),
        )
        if auth_state.is_signed_in and auth_state.payload:
            return auth_state.payload.get("sub")
    except Exception as exc:
        app.logger.info("Clerk session could not be verified: %s", exc)
    return None


def require_auth(handler):
    @wraps(handler)
    def protected(*args, **kwargs):
        user_id = getattr(g, "user_id", None)
        if not user_id:
            return error("Sign in to continue.", 401)
        g.user_id = user_id
        with db() as conn:
            conn.execute(
                "INSERT INTO app_users(id, created_at) VALUES (?, ?) ON CONFLICT(id) DO NOTHING",
                (user_id, now()),
            )
        return handler(*args, **kwargs)
    return protected


@app.before_request
def hydrate_optional_identity():
    g.user_id = authenticated_user_id()


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
    data["is_mine"] = bool(getattr(g, "user_id", None) and data.get("owner_id") == g.user_id)
    data["is_cancelled"] = bool(data.get("cancelled_at"))
    data["has_organizer_code"] = bool(
        not data.get("is_demo")
        and not data.get("source_provider")
        and data.get("source_status") not in ("verified_feed", "verified_site", "stale_feed")
    )
    data.pop("owner_id", None)
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


def load_cached_brief(conn, event_id, fingerprint, event):
    row = conn.execute(
        "SELECT brief_json FROM generated_briefs WHERE event_id=? AND fingerprint=?",
        (event_id, fingerprint),
    ).fetchone()
    if not row:
        return None
    brief = json.loads(row["brief_json"])
    if not isinstance(brief, dict):
        raise ValueError("Stored AI briefing has an invalid format.")
    brief["mode"] = "cached"
    brief["source_checked_at"] = event["source_checked_at"]
    return brief


def reserve_brief_generation(event_id, fingerprint, user_id, event):
    """Return an unchanged cached brief, or atomically reserve one provider run."""
    timestamp = int(time.time())
    token = uuid.uuid4().hex
    window_start = timestamp // BRIEF_RATE_WINDOW_SECONDS
    with db() as conn:
        cached = load_cached_brief(conn, event_id, fingerprint, event)
        if cached:
            return {"status": "cached", "brief": cached}
        lease = conn.execute(
            """INSERT INTO brief_generation_locks(event_id,fingerprint,lease_token,locked_until)
            VALUES(?,?,?,?)
            ON CONFLICT(event_id,fingerprint) DO UPDATE
            SET lease_token=excluded.lease_token,locked_until=excluded.locked_until
            WHERE brief_generation_locks.locked_until<=?
            RETURNING lease_token""",
            (event_id, fingerprint, token,
             timestamp + BRIEF_GENERATION_LEASE_SECONDS, timestamp),
        ).fetchone()
        if not lease:
            cached = load_cached_brief(conn, event_id, fingerprint, event)
            if cached:
                return {"status": "cached", "brief": cached}
            return {"status": "busy"}
        count = conn.execute(
            """INSERT INTO brief_rate_limits(user_id,window_start,requests) VALUES(?,?,1)
            ON CONFLICT(user_id,window_start) DO UPDATE
            SET requests=brief_rate_limits.requests+1
            RETURNING requests""",
            (user_id, window_start),
        ).fetchone()[0]
        if count > BRIEF_RATE_LIMIT_PER_HOUR:
            conn.execute(
                "DELETE FROM brief_generation_locks WHERE event_id=? AND fingerprint=? AND lease_token=?",
                (event_id, fingerprint, token),
            )
            return {"status": "limited"}
    return {"status": "reserved", "lease_token": token}


def release_brief_generation(event_id, fingerprint, token):
    with db() as conn:
        conn.execute(
            "DELETE FROM brief_generation_locks WHERE event_id=? AND fingerprint=? AND lease_token=?",
            (event_id, fingerprint, token),
        )


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
        except (SourceError, psycopg.Error, sqlite3.Error) as exc:
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
    except (IntegrationError, psycopg.Error, sqlite3.Error) as exc:
        feed_error = str(exc)
        app.logger.warning("Official feed refresh failed: %s", exc)
    finally:
        feed_lock.release()


def payload():
    return request.get_json(silent=True) if request.is_json else None


@app.get("/api/events")
def list_events():
    sf = sync_sf_events()
    sync_feed()
    with db() as conn:
        rows = conn.execute(
            """SELECT * FROM events WHERE cancelled_at='' AND (
            source_provider NOT LIKE 'legistar:sfgov:%'
            OR (? = 'live' AND starts_at >= ?))
            ORDER BY starts_at ASC""", (sf["state"], now())
        ).fetchall()
        return jsonify(events=[event_data(conn, row) for row in rows],
                       feed_error=feed_error, live_status=sf)


@app.post("/api/events")
@require_auth
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
             source_url,accessibility,jurisdiction,topics,agenda_url,code_hash,created_at,owner_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (identifier, *(values[k] for k in (
                "title", "category", "organizer", "description", "location", "city",
                "zip_code", "starts_at", "source_url", "accessibility", "jurisdiction"
             )), values["topics"], values["agenda_url"],
             hashlib.sha256(code.encode()).hexdigest(), now(), g.user_id),
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
@require_auth
def event_brief(event_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if row is None:
            return error("Event not found.", 404)
        event = event_data(conn, row)
    if event["is_cancelled"]:
        return error("This event has been cancelled.", 409)
    if event["source_status"] not in ("verified_feed", "verified_site"):
        return error("A recently checked official source is required for an AI briefing.", 409)
    lease_token = None
    saved = False
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
            [event["id"], event["title"], event["starts_at"], event["source_provider"],
             event["source_record_id"], event["source_url"], scope, items],
            sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        reservation = reserve_brief_generation(event_id, fingerprint, g.user_id, event)
        if reservation["status"] == "cached":
            return jsonify(brief=reservation["brief"])
        if reservation["status"] == "busy":
            return error("A briefing for this meeting is already being generated. Try again shortly.", 409)
        if reservation["status"] == "limited":
            return error(
                "You have reached the limit of 5 new AI briefings this hour. Cached briefings remain available.",
                429,
            )
        lease_token = reservation["lease_token"]
        try:
            # Band remains opt-in and experimental, never part of the submission demo path.
            brief = (generate_band_brief(evidence, items)
                     if os.environ.get("BAND_BRIEF_ENABLED") == "1" and band_configured() else None)
        except BandUnavailable:
            brief = None
        if brief is None:
            brief = generate_brief(evidence, items)
            brief.update(mode="fallback", source_verification="NOT RUN",
                         civic_critic="NOT RUN", revision_requested=False,
                         workflow=["Official government data retrieved"])
        cited = set(brief.pop("cited_item_ids"))
        brief["citations"] = [{"title": item["title"], "url": event["source_url"], "item_id": item["id"]}
                              for item in items if item["id"] in cited]
        brief["source_checked_at"] = event["source_checked_at"]
        if scope:
            brief["agenda_scope"] = scope
        with db() as conn:
            conn.execute(
                """INSERT INTO generated_briefs(event_id,fingerprint,brief_json,created_at)
                VALUES(?,?,?,?) ON CONFLICT(event_id,fingerprint) DO UPDATE
                SET brief_json=excluded.brief_json,created_at=excluded.created_at""",
                (event_id, fingerprint, json.dumps(brief, separators=(",", ":")), now()),
            )
            conn.execute(
                "DELETE FROM brief_generation_locks WHERE event_id=? AND fingerprint=? AND lease_token=?",
                (event_id, fingerprint, lease_token),
            )
        saved = True
        return jsonify(brief=brief)
    except (IntegrationError, SourceError) as exc:
        return error(str(exc), 503)
    finally:
        if lease_token and not saved:
            release_brief_generation(event_id, fingerprint, lease_token)


@app.post("/api/events/<event_id>/rsvp")
@require_auth
def rsvp(event_id):
    data = payload()
    if not isinstance(data, dict) or type(data.get("going")) is not bool:
        return error("A going status is required.")
    person = g.user_id
    with db() as conn:
        event = conn.execute(
            "SELECT cancelled_at FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        if not event:
            return error("Event not found.", 404)
        if event["cancelled_at"] and data["going"]:
            return error("This event has been cancelled.", 409)
        if data["going"]:
            conn.execute("INSERT INTO rsvps VALUES (?, ?) ON CONFLICT DO NOTHING", (event_id, person))
        else:
            conn.execute("DELETE FROM rsvps WHERE event_id = ? AND participant_id = ?", (event_id, person))
        count = conn.execute("SELECT COUNT(*) FROM rsvps WHERE event_id = ?", (event_id,)).fetchone()[0]
    return jsonify(going=data["going"], rsvp_count=count)


@app.get("/api/activity")
@require_auth
def activity():
    person = g.user_id
    with db() as conn:
        rsvps = conn.execute(
            """SELECT DISTINCT e.* FROM events e JOIN rsvps r ON e.id=r.event_id
            WHERE r.participant_id=? ORDER BY e.starts_at""",
            (person,),
        ).fetchall()
        checked = conn.execute(
            """SELECT DISTINCT e.*, c.receipt, c.verified_at, c.method,
            c.is_demo AS checkin_is_demo FROM events e JOIN check_ins c ON e.id=c.event_id
            WHERE c.participant_id=? ORDER BY c.verified_at DESC""",
            (person,),
        ).fetchall()
        owned = conn.execute(
            "SELECT * FROM events WHERE owner_id=? ORDER BY created_at DESC", (person,)
        ).fetchall()
        account = conn.execute(
            "SELECT public_passport, share_slug FROM app_users WHERE id=?", (person,)
        ).fetchone()
        return jsonify(
            rsvps=[event_data(conn, row) for row in rsvps],
            owned_events=[event_data(conn, row) for row in owned],
            public_passport=bool(account["public_passport"]),
            share_slug=account["share_slug"],
            check_ins=[
                {"event": event_data(conn, row), "receipt": row["receipt"],
                 "verified_at": row["verified_at"], "method": row["method"],
                 "is_demo": bool(row["checkin_is_demo"])}
                for row in checked
            ],
        )


@app.post("/api/events/<event_id>/check-in")
@require_auth
def check_in(event_id):
    data = payload()
    if not isinstance(data, dict):
        return error("Submit an attendance method or organizer code.")
    requested_method = data.get("method")
    if requested_method not in (None, "organizer_code", "self_reported"):
        return error("Choose a supported attendance method.")
    self_reported = requested_method == "self_reported"
    if not self_reported and not isinstance(data.get("code"), str):
        return error("An organizer check-in code is required.")
    person = g.user_id
    with db() as conn:
        row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        if row is None:
            return error("Event not found.", 404)
        if row["is_demo"]:
            return error("Demo events cannot create real Passport attendance.", 409)
        previous = conn.execute(
            "SELECT receipt, verified_at, method, is_demo FROM check_ins WHERE event_id=? AND participant_id=?",
            (event_id, person),
        ).fetchone()
        if previous:
            return jsonify({**dict(previous), "is_demo": bool(previous["is_demo"])})
        if row["cancelled_at"]:
            return error("This event has been cancelled.", 409)
        official_legistar = (
            bool(row["source_record_id"])
            and row["source_status"] in ("verified_feed", "verified_site", "stale_feed")
        )
        if self_reported and not official_legistar:
            return error("Self-reported attendance is only available for official Legistar meetings.", 409)
        if not self_reported and official_legistar:
            return error("Official Legistar attendance must be recorded as Self Reported.", 409)
        if datetime.fromisoformat(row["starts_at"]) > datetime.now(timezone.utc):
            return error("Attendance can only be recorded after the event begins.")
        if self_reported:
            method = "self_reported"
        else:
            attempt = conn.execute(
                "SELECT window_started_at, attempts FROM checkin_attempts WHERE event_id=? AND user_id=?",
                (event_id, person),
            ).fetchone()
            timestamp = time.time()
            if attempt and timestamp - attempt["window_started_at"] < 600 and attempt["attempts"] >= 5:
                return error("Too many attempts. Try again in 10 minutes.", 429)
            if not attempt or timestamp - attempt["window_started_at"] >= 600:
                conn.execute(
                    """INSERT INTO checkin_attempts(event_id,user_id,window_started_at,attempts)
                    VALUES(?,?,?,0) ON CONFLICT(event_id,user_id) DO UPDATE
                    SET window_started_at=excluded.window_started_at,attempts=0""",
                    (event_id, person, timestamp),
                )
            expected = row["code_hash"]
            submitted = hashlib.sha256(data["code"].strip().encode()).hexdigest()
            if not secrets.compare_digest(submitted, expected):
                conn.execute(
                    "UPDATE checkin_attempts SET attempts=attempts+1 WHERE event_id=? AND user_id=?",
                    (event_id, person),
                )
                return error("That check-in code is not correct.")
            method = "organizer_code"
        is_demo = False
        receipt = str(uuid.uuid4())
        verified_at = now()
        conn.execute(
            "INSERT INTO check_ins (event_id,participant_id,receipt,verified_at,method,is_demo) VALUES (?,?,?,?,?,?)",
            (event_id, person, receipt, verified_at, method, int(is_demo)),
        )
    return jsonify(receipt=receipt, verified_at=verified_at, method=method, is_demo=is_demo), 201


@app.patch("/api/account/privacy")
@require_auth
def update_passport_privacy():
    data = payload()
    if not isinstance(data, dict) or type(data.get("public")) is not bool:
        return error("Choose whether to make your Passport public.")
    with db() as conn:
        account = conn.execute("SELECT share_slug FROM app_users WHERE id=?", (g.user_id,)).fetchone()
        slug = account["share_slug"] or uuid.uuid4().hex if data["public"] else None
        conn.execute(
            "UPDATE app_users SET public_passport=?,share_slug=? WHERE id=?",
            (int(data["public"]), slug, g.user_id),
        )
    return jsonify(public=data["public"], share_slug=slug)


@app.get("/api/passport/shared/<slug>")
def shared_passport(slug):
    with db() as conn:
        account = conn.execute(
            "SELECT id FROM app_users WHERE public_passport=1 AND share_slug=?", (slug,)
        ).fetchone()
        if not account:
            return error("This Civic Passport is private or unavailable.", 404)
        user_id = account["id"]
        checked = conn.execute(
            """SELECT e.title,e.city,e.jurisdiction,c.verified_at,c.method,c.is_demo
            FROM check_ins c JOIN events e ON e.id=c.event_id
            WHERE c.participant_id=?
            ORDER BY c.verified_at DESC""",
            (user_id,),
        ).fetchall()
    return jsonify(activities=[dict(row) for row in checked])


@app.put("/api/events/<event_id>")
@require_auth
def update_owned_event(event_id):
    data = payload()
    fields = {"title": 180, "description": 3000, "location": 180, "starts_at": 60}
    if not isinstance(data, dict) or any(
        not isinstance(data.get(key), str) or len(data[key].strip()) > limit
        for key, limit in fields.items()
    ):
        return error("Provide a valid title, description, location, and start time.")
    try:
        starts = datetime.fromisoformat(data["starts_at"].replace("Z", "+00:00"))
        if starts.tzinfo is None or starts <= datetime.now(timezone.utc):
            return error("Event time must be in the future and include a timezone.")
    except ValueError:
        return error("Enter a valid event date and time.")
    with db() as conn:
        result = conn.execute(
            """UPDATE events SET title=?,description=?,location=?,starts_at=?
            WHERE id=? AND owner_id=?""",
            (data["title"].strip(), data["description"].strip(), data["location"].strip(),
             starts.astimezone(timezone.utc).isoformat(), event_id, g.user_id),
        )
        if result.rowcount != 1:
            return error("Event not found or you do not own it.", 404)
    return jsonify(updated=True)


@app.delete("/api/events/<event_id>")
@require_auth
def cancel_owned_event(event_id):
    with db() as conn:
        result = conn.execute(
            """UPDATE events SET cancelled_at=CASE
            WHEN cancelled_at='' THEN ? ELSE cancelled_at END
            WHERE id=? AND owner_id=?""",
            (now(), event_id, g.user_id),
        )
        if result.rowcount != 1:
            return error("Event not found or you do not own it.", 404)
        cancelled_at = conn.execute(
            "SELECT cancelled_at FROM events WHERE id=?", (event_id,)
        ).fetchone()["cancelled_at"]
    return jsonify(cancelled=True, cancelled_at=cancelled_at)


@app.post("/api/events/<event_id>/organizer-code")
@require_auth
def rotate_organizer_code(event_id):
    code = secrets.token_urlsafe(24)
    with db() as conn:
        result = conn.execute(
            "UPDATE events SET code_hash=? WHERE id=? AND owner_id=?",
            (hashlib.sha256(code.encode()).hexdigest(), event_id, g.user_id),
        )
        if result.rowcount != 1:
            return error("Event not found or you do not own it.", 404)
    return jsonify(check_in_code=code)


@app.delete("/api/passport/check-ins/<receipt>")
@require_auth
def revoke_check_in(receipt):
    with db() as conn:
        result = conn.execute(
            "DELETE FROM check_ins WHERE receipt=? AND participant_id=?",
            (receipt, g.user_id),
        )
        if result.rowcount != 1:
            return error("Check-in not found in your Passport.", 404)
    return jsonify(deleted=True)


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