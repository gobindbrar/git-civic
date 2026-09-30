import os
import hashlib
import tempfile
import unittest
import uuid
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

# The app initializes its SQLite database on import. Keep tests off the live DB.
test_dir = tempfile.TemporaryDirectory()
os.environ["CIVIC_DB_PATH"] = os.path.join(test_dir.name, "civic.sqlite")
os.environ["GIT_CIVIC_TEST_SQLITE"] = "1"
import main

from services.integrations import (CRUSOE_INFERENCE_URL, IntegrationError,
                                   TransientProviderError, generate_brief, official_url)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        # Fixture-level source/AI mocks must not start external Band agents.
        self.identity = patch("main.authenticated_user_id", return_value="test-user")
        self.identity.start()
        self.addCleanup(self.identity.stop)
        self.band_mode = patch("main.band_configured", return_value=False)
        self.band_mode.start()
        self.addCleanup(self.band_mode.stop)
        self.crusoe_off = patch.dict(os.environ, {"CRUSOE_API_KEY": ""})
        self.crusoe_off.start()
        self.addCleanup(self.crusoe_off.stop)

    def insert_event(self, *, owner_id=None, starts_at=None, source_status="unverified",
                     source_provider="", source_record_id="", source_url=""):
        event_id = f"test-event-{uuid.uuid4()}"
        code = "organizer-test-code"
        with main.db() as conn:
            if owner_id:
                conn.execute(
                    "INSERT INTO app_users(id,created_at) VALUES(?,?) ON CONFLICT(id) DO NOTHING",
                    (owner_id, main.now()),
                )
            conn.execute(
                """INSERT INTO events
                (id,title,category,organizer,description,location,city,starts_at,source_url,
                 source_status,source_checked_at,source_record_id,source_provider,code_hash,
                 created_at,owner_id)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (event_id, "Test public meeting", "Public meeting", "Test Council",
                 "A test meeting notice.", "City Hall", "Test City",
                 starts_at or (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                 source_url, source_status, main.now(), source_record_id, source_provider,
                 hashlib.sha256(code.encode()).hexdigest(), main.now(), owner_id),
            )
        return event_id, code

    def test_postgres_adapter_preserves_quoted_sql_patterns(self):
        class RecordingConnection:
            def execute(self, statement, params):
                self.statement = statement
                self.params = params
                return self

        connection = RecordingConnection()
        main.PgConnection(connection).execute(
            "SELECT id FROM events WHERE source_provider NOT LIKE 'legistar:sfgov:%' AND id=?",
            ("event-1",),
        )
        self.assertEqual(
            connection.statement,
            "SELECT id FROM events WHERE source_provider NOT LIKE 'legistar:sfgov:%%' AND id=%s",
        )
        self.assertEqual(connection.params, ("event-1",))

        main.PgConnection(connection).execute(
            "SELECT 'https://example.org/name' AS source WHERE id=:event_id",
            {"event_id": "event-1"},
        )
        self.assertEqual(
            connection.statement,
            "SELECT 'https://example.org/name' AS source WHERE id=%(event_id)s",
        )
        self.assertEqual(connection.params, {"event_id": "event-1"})

    def test_tenant_matching(self):
        self.assertTrue(official_url("https://Seattle.legistar.com/MeetingDetail.aspx?LEGID=7", "Seattle"))
        self.assertFalse(official_url("http://seattle.legistar.com/MeetingDetail.aspx?LEGID=7", "Seattle"))
        self.assertFalse(official_url("https://seattle.legistar.com.evil.org/MeetingDetail.aspx", "Seattle"))
        self.assertFalse(official_url("https://oakland.legistar.com/MeetingDetail.aspx", "Seattle"))
        self.assertTrue(official_url("https://legistar2.granicus.com/seattle/meetings/2026/9/a.pdf", "Seattle", "agenda"))

    def test_brief_and_passport_routes_require_authentication(self):
        with main.app.test_client() as client, \
             patch("main.authenticated_user_id", return_value=None), \
             patch("main.fetch_agenda_items") as agenda, \
             patch("main.generate_brief") as model:
            self.assertEqual(client.post("/api/events/not-found/brief").status_code, 401)
            self.assertEqual(client.get("/api/activity").status_code, 401)
            self.assertEqual(client.patch("/api/account/privacy", json={"public": True}).status_code, 401)
            self.assertEqual(
                client.delete("/api/passport/check-ins/not-a-receipt").status_code, 401
            )
            agenda.assert_not_called()
            model.assert_not_called()

    def test_checkin_attempts_are_scoped_to_user_and_event(self):
        event_id, _ = self.insert_event()
        other_event_id, _ = self.insert_event()
        with main.app.test_client() as client:
            with patch("main.authenticated_user_id", return_value="attempt-user-a"):
                for _ in range(5):
                    response = client.post(
                        f"/api/events/{event_id}/check-in", json={"code": "wrong"}
                    )
                    self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    client.post(f"/api/events/{event_id}/check-in", json={"code": "wrong"}).status_code,
                    429,
                )
                # The same account gets an independent attempt window for another event.
                self.assertEqual(
                    client.post(f"/api/events/{other_event_id}/check-in", json={"code": "wrong"}).status_code,
                    400,
                )
            with patch("main.authenticated_user_id", return_value="attempt-user-b"):
                # A second account at the same client address has its own event limit.
                self.assertEqual(
                    client.post(f"/api/events/{event_id}/check-in", json={"code": "wrong"}).status_code,
                    400,
                )

    def test_official_meeting_can_be_self_reported_after_it_starts(self):
        event_id, _ = self.insert_event(
            starts_at=(datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
            source_status="verified_feed",
            source_provider="legistar:test",
            source_record_id="123",
            source_url="https://test.legistar.com/MeetingDetail.aspx?LEGID=123",
        )
        with main.app.test_client() as client, \
             patch("main.authenticated_user_id", return_value="self-reporter"):
            response = client.post(
                f"/api/events/{event_id}/check-in", json={"method": "self_reported"}
            )
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json["method"], "self_reported")
            self.assertFalse(response.json["is_demo"])
            repeated = client.post(
                f"/api/events/{event_id}/check-in", json={"method": "self_reported"}
            )
            self.assertEqual(repeated.status_code, 200)
            self.assertEqual(repeated.json["receipt"], response.json["receipt"])
        with main.db() as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM check_ins WHERE event_id=? AND participant_id=?",
                    (event_id, "self-reporter"),
                ).fetchone()[0],
                1,
            )

    def test_official_meeting_cannot_be_self_reported_before_it_starts(self):
        event_id, _ = self.insert_event(
            starts_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            source_status="verified_feed",
            source_provider="legistar:test",
            source_record_id="124",
            source_url="https://test.legistar.com/MeetingDetail.aspx?LEGID=124",
        )
        with main.app.test_client() as client, \
             patch("main.authenticated_user_id", return_value="early-self-reporter"):
            response = client.post(
                f"/api/events/{event_id}/check-in", json={"method": "self_reported"}
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn("after the event begins", response.json["error"])
        with main.db() as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM check_ins WHERE event_id=?", (event_id,)).fetchone()[0],
                0,
            )

    def test_demo_event_cannot_create_real_passport_attendance(self):
        event_id, _ = self.insert_event()
        with main.db() as conn:
            conn.execute("UPDATE events SET is_demo=1 WHERE id=?", (event_id,))
        with main.app.test_client() as client, \
             patch("main.authenticated_user_id", return_value="demo-self-reporter"):
            response = client.post(
                f"/api/events/{event_id}/check-in", json={"method": "self_reported"}
            )
            self.assertEqual(response.status_code, 409)
        with main.db() as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM check_ins WHERE event_id=?", (event_id,)).fetchone()[0],
                0,
            )

    def test_checkin_history_is_owned_by_participant(self):
        event_id, code = self.insert_event()
        with main.app.test_client() as client:
            with patch("main.authenticated_user_id", return_value="passport-owner-a"):
                checked = client.post(f"/api/events/{event_id}/check-in", json={"code": code})
                self.assertEqual(checked.status_code, 201)
                receipt = checked.json["receipt"]
            with patch("main.authenticated_user_id", return_value="passport-owner-b"):
                activity = client.get("/api/activity")
                self.assertEqual(activity.status_code, 200)
                self.assertEqual(activity.json["check_ins"], [])
                self.assertEqual(
                    client.delete(f"/api/passport/check-ins/{receipt}").status_code, 404
                )
            with patch("main.authenticated_user_id", return_value="passport-owner-a"):
                self.assertEqual(
                    client.delete(f"/api/passport/check-ins/{receipt}").status_code, 200
                )

    def test_owner_cannot_modify_another_users_event(self):
        starts_at = (datetime.now(timezone.utc) + timedelta(days=4)).isoformat()
        with main.app.test_client() as client:
            with patch("main.authenticated_user_id", return_value="event-owner-b"):
                created = client.post("/api/events", json={
                    "title": "Owner B meeting", "category": "Public meeting",
                    "organizer": "Owner B", "description": "Original description",
                    "location": "Room 1", "city": "Test City", "starts_at": starts_at,
                })
                self.assertEqual(created.status_code, 201)
                event_id = created.json["event"]["id"]
            with patch("main.authenticated_user_id", return_value="event-owner-a"):
                self.assertEqual(client.put(f"/api/events/{event_id}", json={
                    "title": "Changed by A", "description": "Changed",
                    "location": "Room 2", "starts_at": starts_at,
                }).status_code, 404)
                self.assertEqual(client.delete(f"/api/events/{event_id}").status_code, 404)
            with patch("main.authenticated_user_id", return_value="event-owner-b"):
                event = client.get(f"/api/events/{event_id}").json["event"]
                self.assertEqual(event["title"], "Owner B meeting")
                self.assertFalse(event["is_cancelled"])

    def test_event_cancellation_preserves_rsvps_and_checkins(self):
        event_id, code = self.insert_event(owner_id="event-organizer")
        with main.app.test_client() as client:
            with patch("main.authenticated_user_id", return_value="event-attendee"):
                self.assertEqual(
                    client.post(f"/api/events/{event_id}/rsvp", json={"going": True}).status_code,
                    200,
                )
                checked = client.post(f"/api/events/{event_id}/check-in", json={"code": code})
                self.assertEqual(checked.status_code, 201)
            with patch("main.authenticated_user_id", return_value="event-organizer"):
                cancelled = client.delete(f"/api/events/{event_id}")
                self.assertEqual(cancelled.status_code, 200)
                self.assertTrue(cancelled.json["cancelled"])
            with patch("main.authenticated_user_id", return_value="event-attendee"):
                event = client.get(f"/api/events/{event_id}").json["event"]
                self.assertTrue(event["is_cancelled"])
                self.assertEqual(
                    client.post(f"/api/events/{event_id}/rsvp", json={"going": True}).status_code,
                    409,
                )
                activity = client.get("/api/activity").json
                self.assertEqual([item["id"] for item in activity["rsvps"]], [event_id])
                self.assertEqual(activity["check_ins"][0]["event"]["id"], event_id)
            with main.db() as conn:
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM rsvps WHERE event_id=?", (event_id,)).fetchone()[0],
                    1,
                )
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM check_ins WHERE event_id=?", (event_id,)).fetchone()[0],
                    1,
                )

    def test_public_passport_shares_only_redacted_participation_fields(self):
        event_id, _ = self.insert_event()
        with main.db() as conn:
            conn.execute(
                """INSERT INTO check_ins
                (event_id,participant_id,receipt,verified_at,method,is_demo)
                VALUES(?,?,?,?,?,0)""",
                (event_id, "public-passport-user", "private-receipt", main.now(),
                 "organizer_code"),
            )
        with main.app.test_client() as client, \
             patch("main.authenticated_user_id", return_value="public-passport-user"):
            settings = client.patch("/api/account/privacy", json={"public": True})
            self.assertEqual(settings.status_code, 200)
            public = client.get(f"/api/passport/shared/{settings.json['share_slug']}")
            self.assertEqual(public.status_code, 200)
            self.assertEqual(len(public.json["activities"]), 1)
            activity = public.json["activities"][0]
            self.assertEqual(
                set(activity),
                {"title", "city", "jurisdiction", "verified_at", "method", "is_demo"},
            )

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
        with main.app.test_client() as client, patch("main.fetch_agenda_items") as agenda, \
             patch("main.generate_brief") as model:
            agenda.return_value = [{"id": "42", "title": "Budget"}]
            model.return_value = {"summary": "Budget", "topics": "Budget",
                                  "why_it_matters": "Budget", "participation": "See notice",
                                  "cited_item_ids": ["42"], "model": "live-model"}
            self.assertEqual(client.post(f"/api/events/{event_id}/brief").status_code, 200)
            cached = client.post(f"/api/events/{event_id}/brief")
            self.assertEqual(cached.status_code, 200)
            self.assertEqual(cached.json["brief"]["mode"], "cached")
            self.assertEqual(cached.json["brief"]["citations"][0]["item_id"], "42")
            self.assertEqual(model.call_count, 1)
            model.side_effect = IntegrationError("AI provider unavailable")
            agenda.return_value = [{"id": "42", "title": "Changed agenda"}]
            self.assertEqual(client.post(f"/api/events/{event_id}/brief").status_code, 503)
            self.assertEqual(model.call_count, 2)

    def test_brief_generation_is_limited_to_five_uncached_runs_per_hour(self):
        event_id, _ = self.insert_event(
            starts_at=(datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            source_status="verified_feed",
            source_provider="legistar:test",
            source_record_id="77",
            source_url="https://test.legistar.com/MeetingDetail.aspx?LEGID=77",
        )
        agenda_number = {"value": 0}

        def fetch_agenda(_record_id):
            agenda_number["value"] += 1
            return [{"id": "42", "title": f"Agenda version {agenda_number['value']}"}]

        def generate_test_brief(_event, _items):
            return {
                "summary": "Budget", "topics": "Budget", "why_it_matters": "Budget",
                "participation": "See notice", "cited_item_ids": ["42"], "model": "test-model",
            }

        with main.app.test_client() as client, \
             patch("main.authenticated_user_id", return_value=f"brief-user-{uuid.uuid4()}"), \
             patch("main.fetch_agenda_items", side_effect=fetch_agenda), \
             patch("main.generate_brief", side_effect=generate_test_brief) as model:
            for _ in range(5):
                response = client.post(f"/api/events/{event_id}/brief")
                self.assertEqual(response.status_code, 200)
            self.assertEqual(model.call_count, 5)
            limited = client.post(f"/api/events/{event_id}/brief")
            self.assertEqual(limited.status_code, 429)
            self.assertEqual(model.call_count, 5)


if __name__ == "__main__":
    unittest.main()