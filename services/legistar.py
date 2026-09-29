"""Read-only San Francisco Legistar integration.

The public sfgov Events API is attempted first. If its server-side settings
prevent Events access, read the same government's public Legistar calendar and
meeting page instead; never substitute another jurisdiction's meetings.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup


CLIENT = "sfgov"
CITY = "San Francisco"
API = "https://webapi.legistar.com/v1/sfgov"
SITE = "https://sfgov.legistar.com/"
CALENDAR = SITE + "Calendar.aspx"
LOCAL_TIME = ZoneInfo("America/Los_Angeles")
MAX_BYTES = 2_000_000
BOARD_MEETING_URL = (
    SITE + "MeetingDetail.aspx?GUID=82BD7CE6-C773-4BF3-A2FA-3A59A473DBB1"
    "&ID=1449004&Options=&Search="
)


class SourceError(RuntimeError):
    pass


def fetch(url):
    request = urllib.request.Request(
        url, headers={"User-Agent": "GITCivic/1.0", "Accept": "application/json, text/html"}
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise SourceError("Official source response is too large.")
            return body
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SourceError("Official Legistar source is unavailable.") from exc


def api_json(url):
    try:
        result = json.loads(fetch(url))
    except (ValueError, UnicodeError) as exc:
        raise SourceError("Legistar API returned an invalid response.") from exc
    return result


def official_link(url):
    if not url:
        return ""
    absolute = urllib.parse.urljoin(SITE, url)
    parts = urllib.parse.urlsplit(absolute)
    if parts.scheme != "https" or (parts.hostname or "").lower() not in {
        "sfgov.legistar.com", "sfgov.legistar1.com", "legistar.granicus.com"
    }:
        return ""
    return absolute


def meeting_start(date_text, time_text):
    try:
        date = datetime.fromisoformat(date_text).date() if "-" in date_text else datetime.strptime(date_text, "%m/%d/%Y").date()
        for fmt in ("%I:%M %p", "%I %p", "%H:%M"):
            try:
                clock = datetime.strptime(time_text.strip().upper(), fmt).time()
                return datetime.combine(date, clock, tzinfo=LOCAL_TIME).astimezone(timezone.utc).isoformat()
            except ValueError:
                continue
    except (TypeError, ValueError):
        pass
    return None


def category_for(body):
    body = body.lower()
    for word, category in (
        ("transport", "Transportation"), ("planning", "Planning & Development"),
        ("school", "Education"), ("education", "Education"),
        ("safety", "Public Safety"), ("police", "Public Safety"),
    ):
        if word in body:
            return category
    return "Public meeting"


def normalized(identifier, body, starts_at, location, source_url, agenda_url,
               agenda_status=None, body_id=None, mode="api", revision=""):
    if not (identifier and body and starts_at and source_url):
        return None
    start = datetime.fromisoformat(starts_at)
    now = datetime.now(timezone.utc)
    if start < now - timedelta(hours=8) or start > now + timedelta(days=60):
        return None
    body = re.sub(r"^\s*\*+\s*", "", body).strip()
    return {
        "id": f"legistar-sfgov-{int(identifier)}",
        "title": body if "meeting" in body.lower() else f"{body} Meeting",
        "category": category_for(body),
        "organizer": body,
        "description": (
            "Official San Francisco meeting record from Legistar. "
            "Open the official agenda for its published items and participation details."
        ),
        "location": (location or "See official meeting notice").strip()[:180],
        "city": CITY,
        "zip_code": "",
        "starts_at": starts_at,
        "source_url": source_url,
        "agenda_url": agenda_url or "",
        "accessibility": "",
        "jurisdiction": "City",
        "topics": [body[:60]],
        "agenda_status": agenda_status,
        "body_id": body_id,
        "source_provider": f"legistar:sfgov:{mode}",
        "source_revision": revision,
    }


def api_events():
    since = (datetime.now(LOCAL_TIME) - timedelta(days=1)).date().isoformat()
    query = urllib.parse.urlencode({
        "$filter": f"EventDate ge datetime'{since}'", "$orderby": "EventDate asc", "$top": "80"
    })
    records = api_json(f"{API}/Events?{query}")
    if not isinstance(records, list):
        raise SourceError("Legistar Events API returned an unexpected format.")
    events = []
    for record in records:
        start = meeting_start(record.get("EventDate"), record.get("EventTime"))
        event = normalized(
            record.get("EventId"), record.get("EventBodyName"), start,
            record.get("EventLocation"), official_link(record.get("EventInSiteURL")),
            official_link(record.get("EventAgendaFile")),
            record.get("EventAgendaStatusName"), record.get("EventBodyId"),
            "api", record.get("EventLastModifiedUtc") or "",
        )
        if event:
            events.append(event)
    return events


def calendar_events():
    soup = BeautifulSoup(fetch(CALENDAR), "html.parser")
    table = soup.find("table", id=lambda value: value and value.endswith("gridCalendar_ctl00"))
    if table is None:
        raise SourceError("Official calendar did not contain a meeting list.")
    # The Bodies API works even when this client's Events endpoint is misconfigured.
    try:
        bodies = api_json(f"{API}/Bodies")
        body_ids = {
            body["BodyName"]: body["BodyId"]
            for body in bodies if body.get("BodyName") and body.get("BodyId")
        } if isinstance(bodies, list) else {}
    except SourceError:
        body_ids = {}
    events = []
    for row in table.select("tr.rgRow, tr.rgAltRow"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 7:
            continue
        detail_link = cells[5].find("a", href=True)
        if not detail_link:
            continue
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(detail_link["href"]).query)
        identifier = (params.get("ID") or [None])[0]
        agenda_link = cells[6].find("a", href=True)
        body = cells[0].get_text(" ", strip=True)
        event = normalized(
            identifier, body,
            meeting_start(cells[1].get_text(" ", strip=True), cells[3].get_text(" ", strip=True)),
            cells[4].get_text(" ", strip=True),
            official_link(detail_link["href"]),
            official_link(agenda_link["href"]) if agenda_link else "",
            body_id=body_ids.get(body), mode="official_site",
        )
        if event:
            events.append(event)
    return events


def fetch_upcoming():
    """Return (events, source mode); no sample data is ever returned as live."""
    try:
        events = api_events()
        return events, "api"
    except SourceError:
        events = calendar_events()
        return events, "official_site"


def api_event_detail(event_id):
    record = api_json(f"{API}/Events/{event_id}")
    items = api_json(
        f"{API}/Events/{event_id}/EventItems?"
        "AgendaNote=true&MinutesNote=false&Attachments=false"
    )
    if not isinstance(record, dict) or not isinstance(items, list):
        raise SourceError("Legistar event detail returned an unexpected format.")
    return {
        "body_id": record.get("EventBodyId"),
        "agenda_status": record.get("EventAgendaStatusName"),
        "location": record.get("EventLocation"),
        "agenda_url": official_link(record.get("EventAgendaFile")),
        "source_url": official_link(record.get("EventInSiteURL")),
        "agenda_items": [
            {
                "file_number": item.get("EventItemMatterFile"),
                "title": item.get("EventItemMatterName") or item.get("EventItemTitle"),
                "type": item.get("EventItemMatterType"),
                "status": item.get("EventItemMatterStatus"),
                "description": item.get("EventItemTitle"),
                "agenda_number": item.get("EventItemAgendaNumber"),
            }
            for item in items
        ],
        "source_mode": "api",
    }


def site_event_detail(event_id, source_url=None):
    url = official_link(source_url) or (BOARD_MEETING_URL if str(event_id) == "1449004" else "")
    if not url or urllib.parse.urlsplit(url).hostname != "sfgov.legistar.com":
        raise SourceError("No official meeting page is available for this event.")
    soup = BeautifulSoup(fetch(url), "html.parser")
    table = soup.find("table", id=lambda value: value and value.endswith("gridMain_ctl00"))
    if table is None:
        raise SourceError("Official meeting page did not contain an agenda table.")

    def field(suffix):
        element = soup.find(id=f"ctl00_ContentPlaceHolder1_{suffix}")
        return element.get_text(" ", strip=True) if element else None

    items = []
    for row in table.select("tr.rgRow, tr.rgAltRow"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 7:
            continue
        title = cells[3].get_text(" ", strip=True)
        description = cells[6].get_text(" ", strip=True)
        if title or description:
            items.append({
                "file_number": cells[0].get_text(" ", strip=True) or None,
                "title": title or None,
                "type": cells[4].get_text(" ", strip=True) or None,
                "status": cells[5].get_text(" ", strip=True) or None,
                "description": description or None,
                "agenda_number": cells[2].get_text(" ", strip=True) or None,
            })
    agenda_link = soup.find(id="ctl00_ContentPlaceHolder1_hypAgenda")
    return {
        "body_id": None,  # Not exposed by the public meeting HTML.
        "agenda_status": field("lblAgendaStatus"),
        "location": field("lblLocation"),
        "agenda_url": official_link(agenda_link.get("href")) if agenda_link else "",
        "source_url": url,
        "agenda_items": items,
        "source_mode": "official_site",
    }


def fetch_event_details(event_id, source_url=None):
    if not str(event_id).isdigit():
        raise SourceError("Invalid Legistar event identifier.")
    try:
        return api_event_detail(event_id)
    except SourceError:
        return site_event_detail(event_id, source_url)