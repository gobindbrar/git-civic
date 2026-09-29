import os
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

# The app initializes its SQLite database on import. Keep tests off the live DB.
test_dir = tempfile.TemporaryDirectory()
os.environ["CIVIC_DB_PATH"] = os.path.join(test_dir.name, "civic.sqlite")
import main

from services.integrations import IntegrationError, generate_brief, official_url


class IntegrationTests(unittest.TestCase):
    def test_tenant_matching(self):
        self.assertTrue(official_url("https://Seattle.legistar.com/MeetingDetail.aspx?LEGID=7", "Seattle"))
        self.assertFalse(official_url("http://seattle.legistar.com/MeetingDetail.aspx?LEGID=7", "Seattle"))
        self.assertFalse(official_url("https://seattle.legistar.com.evil.org/MeetingDetail.aspx", "Seattle"))
        self.assertFalse(official_url("https://oakland.legistar.com/MeetingDetail.aspx", "Seattle"))
        self.assertTrue(official_url("https://legistar2.granicus.com/seattle/meetings/2026/9/a.pdf", "Seattle", "agenda"))

    def test_community_links_never_qualify_for_ai(self):
        with main.app.test_client() as client:
            response = client.get("/api/events/demo-sf-board-2026-09-29")
            self.assertEqual(response.json["event"]["source_status"], "demo")
            response = client.post("/api/events/demo-sf-board-2026-09-29/brief")
            self.assertEqual(response.status_code, 409)
            start = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
            response = client.post("/api/events", json={
                "title": "Community meeting", "category": "Public meeting", "organizer": "Residents",
                "description": "Discuss local issues", "location": "Town hall", "city": "Seattle",
                "starts_at": start, "source_url": "https://seattle.legistar.com/MeetingDetail.aspx?LEGID=6763"
            })
            self.assertEqual(response.status_code, 201)
            event = response.json["event"]
            self.assertEqual(event["source_status"], "unverified")
            self.assertEqual(client.post(f"/api/events/{event['id']}/brief").status_code, 409)

    def test_checked_feed_can_return_only_retrieved_citations(self):
        with main.db() as conn:
            conn.execute("""INSERT OR IGNORE INTO events
                (id,title,category,organizer,description,location,city,starts_at,
                source_url,source_status,source_checked_at,source_record_id,code_hash,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("legistar-seattle-42", "Council", "Public meeting", "Council", "Notice",
                 "City Hall", "Seattle", (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                 "https://seattle.legistar.com/MeetingDetail.aspx?LEGID=42", "verified_feed",
                 main.now(), "42", "hash", main.now()))
        with main.app.test_client() as client:
            with patch("main.fetch_agenda_items", return_value=[{"id": "7", "title": "Budget"}]), \
                 patch("main.generate_brief", return_value={
                     "summary": "Budget", "topics": "Budget", "why_it_matters": "Budget",
                     "participation": "See notice", "cited_item_ids": ["7"], "model": "test-model"
                 }):
                response = client.post("/api/events/legistar-seattle-42/brief")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["brief"]["citations"][0]["item_id"], "7")
            self.assertEqual(response.json["brief"]["citations"][0]["url"],
                             "https://seattle.legistar.com/MeetingDetail.aspx?LEGID=42")

    def test_ai_requires_real_agenda_and_known_citations(self):
        event = {"title": "Committee", "starts_at": "2026-10-01T12:00:00+00:00"}
        items = [{"id": "42", "title": "Proposed budget"}]
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test"}, clear=False):
            with patch("services.integrations._json_request", return_value={
                "choices": [{"message": {"content": '{"summary":"Budget","topics":"Budget",'
                            '"why_it_matters":"Budget","participation":"See notice",'
                            '"cited_item_ids":["999"]}'}}]
            }):
                with self.assertRaises(IntegrationError):
                    generate_brief(event, items)
            with patch("services.integrations._json_request", return_value={
                "choices": [{"message": {"content": '{"summary":"Budget","topics":"Budget",'
                            '"why_it_matters":"Budget","participation":"See notice",'
                            '"cited_item_ids":["42"]}'}}]
            }):
                self.assertEqual(generate_brief(event, items)["cited_item_ids"], ["42"])


if __name__ == "__main__":
    unittest.main()