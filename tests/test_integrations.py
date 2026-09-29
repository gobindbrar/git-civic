import os
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

# The app initializes its SQLite database on import. Keep tests off the live DB.
test_dir = tempfile.TemporaryDirectory()
os.environ["CIVIC_DB_PATH"] = os.path.join(test_dir.name, "civic.sqlite")
import main

from services.integrations import (CRUSOE_INFERENCE_URL, IntegrationError,
                                   TransientProviderError, generate_brief, official_url)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        # Fixture-level source/AI mocks must not start external Band agents.
        self.band_mode = patch("main.band_configured", return_value=False)
        self.band_mode.start()
        self.addCleanup(self.band_mode.stop)
        self.crusoe_off = patch.dict(os.environ, {"CRUSOE_API_KEY": ""})
        self.crusoe_off.start()
        self.addCleanup(self.crusoe_off.stop)

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

    def test_sf_site_fallback_keeps_agenda_and_cites_only_retrieved_rows(self):
        event_id = "legistar-sfgov-12345"
        url = "https://sfgov.legistar.com/MeetingDetail.aspx?ID=12345"
        start = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        source = {
            "id": event_id, "title": "Supervisors", "category": "Public meeting",
            "organizer": "Supervisors", "description": "Official meeting",
            "location": "City Hall", "city": "San Francisco", "zip_code": "",
            "starts_at": start, "source_url": url, "accessibility": "",
            "jurisdiction": "City", "topics": [], "agenda_url": url,
            "source_provider": "legistar:sfgov:official_site", "source_revision": "",
            "agenda_status": "Published", "body_id": 1,
        }
        with patch("main.fetch_upcoming", return_value=([source], "official_site")):
            main.sf_last_attempt = 0
            self.assertEqual(main.sync_sf_events()["state"], "live")
        details = {
            "location": "Room 250", "agenda_url": url, "agenda_status": "Published",
            "body_id": 1, "source_mode": "official_site",
            "agenda_items": [{"title": f"Agenda topic {i}", "file_number": str(i)} for i in range(20)],
        }
        with main.app.test_client() as client, patch("main.fetch_event_details", return_value=details):
            response = client.get(f"/api/events/{event_id}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json["agenda_items"]), 20)
            self.assertEqual(response.json["event"]["source_status"], "verified_site")

            def mock_brief(event, items):
                self.assertEqual(len(items), 6)
                self.assertEqual(items[0]["id"], "1")
                self.assertEqual(event["agenda_scope"], "First 6 of 20 official agenda rows")
                return {"summary": "Topic", "topics": "Topic", "why_it_matters": "Topic",
                        "participation": "See official notice", "cited_item_ids": ["6"],
                        "model": "test-model"}

            with patch("main.generate_brief", side_effect=mock_brief):
                response = client.post(f"/api/events/{event_id}/brief")
            self.assertEqual(response.status_code, 200)
            brief = response.json["brief"]
            self.assertEqual(brief["agenda_scope"], "First 6 of 20 official agenda rows")
            self.assertEqual(brief["citations"][0]["url"], url)
            self.assertEqual(brief["citations"][0]["item_id"], "6")

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

    def test_crusoe_selects_available_chat_model_and_keeps_citations(self):
        event = {"title": "Committee", "starts_at": "2026-10-01T12:00:00+00:00"}
        items = [{"id": "42", "title": "Proposed budget"}]
        calls = []
        def provider(url, payload=None, headers=None):
            calls.append(url)
            if url.endswith("/models"):
                return {"data": [
                    {"id": "old", "inference_available": False, "type": "chat"},
                    {"id": "current-flash", "inference_available": True, "type": "chat",
                     "supported_parameters": ["response_format"]},
                ]}
            self.assertEqual(payload["model"], "current-flash")
            return {"choices": [{"message": {"content": '{"summary":"Budget","topics":"Budget",'
                    '"why_it_matters":"Budget","participation":"See notice",'
                    '"cited_item_ids":["42"]}'}}]}
        with patch.dict(os.environ, {"CRUSOE_API_KEY": "test", "CRUSOE_BASE_URL": CRUSOE_INFERENCE_URL,
                                     "OPENROUTER_API_KEY": "test"}), \
             patch("services.integrations._json_request", side_effect=provider):
            brief = generate_brief(event, items)
        self.assertEqual(brief["provider"], "Crusoe Intelligence Foundry")
        self.assertEqual(brief["cited_item_ids"], ["42"])
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(url.startswith(CRUSOE_INFERENCE_URL) for url in calls))

    def test_crusoe_transient_retry_before_openrouter(self):
        event = {"title": "Committee", "starts_at": "2026-10-01T12:00:00+00:00"}
        items = [{"id": "42", "title": "Proposed budget"}]
        calls = []
        def provider(url, payload=None, headers=None):
            calls.append(url)
            if url.endswith("/models"):
                return {"data": [{"id": "fast", "type": "chat", "top_provider": {"context_length": 16000}}]}
            if "crusoecloud" in url:
                raise TransientProviderError("AI provider returned HTTP 503.")
            return {"choices": [{"message": {"content": '{"summary":"Budget","topics":"Budget",'
                    '"why_it_matters":"Budget","participation":"See notice",'
                    '"cited_item_ids":["42"]}'}}]}
        with patch.dict(os.environ, {"CRUSOE_API_KEY": "test", "CRUSOE_BASE_URL": CRUSOE_INFERENCE_URL,
                                     "OPENROUTER_API_KEY": "test"}), \
             patch("services.integrations._json_request", side_effect=provider), \
             patch("services.integrations.time.sleep"):
            brief = generate_brief(event, items)
        self.assertEqual(brief["provider"], "OpenRouter")
        self.assertEqual(sum(u.endswith("/chat/completions") and "crusoecloud" in u for u in calls), 3)
        self.assertTrue(calls[-1].startswith("https://openrouter.ai/"))

    def test_cached_brief_requires_identical_agenda_and_is_labeled(self):
        with main.db() as conn:
            conn.execute("""INSERT OR IGNORE INTO events
                (id,title,category,organizer,description,location,city,starts_at,
                source_url,source_status,source_checked_at,source_record_id,code_hash,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("legistar-seattle-43", "Council", "Public meeting", "Council", "Notice",
                 "City Hall", "Seattle", (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                 "https://seattle.legistar.com/MeetingDetail.aspx?LEGID=43", "verified_feed",
                 main.now(), "43", "hash", main.now()))
        event_id = "legistar-seattle-43"
        main.brief_cache.pop(event_id, None)
        with main.app.test_client() as client, patch("main.fetch_agenda_items") as agenda, \
             patch("main.generate_brief") as model:
            agenda.return_value = [{"id": "42", "title": "Budget"}]
            model.return_value = {"summary": "Budget", "topics": "Budget",
                                  "why_it_matters": "Budget", "participation": "See notice",
                                  "cited_item_ids": ["42"], "model": "live-model"}
            self.assertEqual(client.post(f"/api/events/{event_id}/brief").status_code, 200)
            model.side_effect = IntegrationError("AI provider unavailable")
            cached = client.post(f"/api/events/{event_id}/brief")
            self.assertEqual(cached.status_code, 200)
            self.assertEqual(cached.json["brief"]["mode"], "cached")
            self.assertEqual(cached.json["brief"]["citations"][0]["item_id"], "42")
            agenda.return_value = [{"id": "42", "title": "Changed agenda"}]
            self.assertEqual(client.post(f"/api/events/{event_id}/brief").status_code, 503)


if __name__ == "__main__":
    unittest.main()