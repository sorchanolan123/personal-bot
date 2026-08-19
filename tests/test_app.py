"""Tests for Flask app endpoints."""

import datetime as dt
import unittest
from unittest.mock import patch, MagicMock

from conftest import BotTestCase
import db
import app as app_module
import morning as morning_module


class FlaskTestCase(BotTestCase):
    """Base class that also provides a Flask test client."""

    def setUp(self):
        super().setUp()
        # Mock outgoing HTTP requests from telegram module
        self._req_post_patch = patch("telegram.requests.post", return_value=MagicMock(
            json=lambda: {"ok": True, "result": {"message_id": 1}}
        ))
        self._req_get_patch = patch("telegram.requests.get", return_value=MagicMock(
            json=lambda: {"ok": True, "result": {"url": "https://test.com/webhook"}}
        ))
        self._req_post_patch.start()
        self._req_get_patch.start()

        # Also patch send_message in app and morning modules (they import it directly)
        def fake_send(chat_id, text, parse_mode="Markdown", reply_markup=None):
            self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
            return {"ok": True, "result": {"message_id": len(self.sent)}}

        self._app_send_patch = patch.object(app_module, "send_message", side_effect=fake_send)
        self._morning_send_patch = patch.object(morning_module, "send_message", side_effect=fake_send)
        self._app_send_patch.start()
        self._morning_send_patch.start()

        from app import app
        app.config["TESTING"] = True
        self.client = app.test_client()

        from config import CRON_SECRET
        self.cron_secret = CRON_SECRET

    def tearDown(self):
        self._req_post_patch.stop()
        self._req_get_patch.stop()
        self._app_send_patch.stop()
        self._morning_send_patch.stop()
        super().tearDown()


class TestWebhook(FlaskTestCase):
    def test_text_message(self):
        resp = self.client.post("/webhook", json={
            "message": {"chat": {"id": 123}, "text": "/start"}
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json["status"], "ok")

    def test_callback_query(self):
        db.create_list("todo")
        db.add_item("todo", "test")
        resp = self.client.post("/webhook", json={
            "callback_query": {
                "id": "cb1", "data": "done:todo:1",
                "message": {"chat": {"id": 123}, "message_id": 42},
            }
        })
        self.assertEqual(resp.status_code, 200)

    def test_empty_body(self):
        resp = self.client.post("/webhook", data="", content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_error_handling_returns_200(self):
        with patch("handlers.handle_message", side_effect=Exception("boom")):
            resp = self.client.post("/webhook", json={
                "message": {"chat": {"id": 123}, "text": "crash"}
            })
            self.assertEqual(resp.status_code, 200)


class TestCronAuth(FlaskTestCase):
    def test_missing_key(self):
        resp = self.client.get("/trigger/morning")
        self.assertEqual(resp.status_code, 403)

    def test_wrong_key(self):
        resp = self.client.get("/trigger/morning?key=wrong")
        self.assertEqual(resp.status_code, 403)

    def test_correct_key(self):
        resp = self.client.get(f"/trigger/morning?key={self.cron_secret}")
        self.assertEqual(resp.status_code, 200)


class TestCronTriggers(FlaskTestCase):
    def test_morning(self):
        self.populate_db()
        resp = self.client.get(f"/trigger/morning?key={self.cron_secret}")
        self.assertEqual(resp.json["status"], "sent")

    def test_evening(self):
        self.populate_db()
        resp = self.client.get(f"/trigger/evening?key={self.cron_secret}")
        self.assertEqual(resp.json["status"], "sent")

    def test_stale_nothing(self):
        resp = self.client.get(f"/trigger/stale?key={self.cron_secret}")
        self.assertEqual(resp.json["status"], "nothing stale")

    def test_stale_with_items(self):
        db.create_list("todo")
        db.add_item("todo", "old thing")
        conn = db.get_db()
        conn.execute("UPDATE items SET created_at = '2020-01-01 00:00:00'")
        conn.commit()
        conn.close()
        resp = self.client.get(f"/trigger/stale?key={self.cron_secret}")
        self.assertEqual(resp.json["status"], "sent")

    def test_deadline_nothing(self):
        resp = self.client.get(f"/trigger/deadline?key={self.cron_secret}")
        self.assertEqual(resp.json["status"], "nothing due tomorrow")

    def test_deadline_with_items(self):
        db.create_list("todo")
        tomorrow = (dt.datetime.now() + dt.timedelta(days=1)).strftime("%Y-%m-%d")
        db.add_item("todo", "urgent", due_date=tomorrow)
        resp = self.client.get(f"/trigger/deadline?key={self.cron_secret}")
        self.assertEqual(resp.json["status"], "sent")

    def test_habits_no_habits(self):
        resp = self.client.get(f"/trigger/habits?key={self.cron_secret}")
        self.assertEqual(resp.json["status"], "all logged")

    def test_habits_unlogged(self):
        db.create_habit("meditate")
        resp = self.client.get(f"/trigger/habits?key={self.cron_secret}")
        self.assertEqual(resp.json["status"], "sent")

    def test_habits_all_logged(self):
        db.create_habit("meditate")
        db.log_habit("meditate")
        resp = self.client.get(f"/trigger/habits?key={self.cron_secret}")
        self.assertEqual(resp.json["status"], "all logged")

    def test_smallthing_nothing(self):
        resp = self.client.get(f"/trigger/smallthing?key={self.cron_secret}")
        self.assertEqual(resp.json["status"], "nothing pending")

    def test_smallthing_with_items(self):
        db.create_list("todo")
        db.add_item("todo", "do a thing")
        resp = self.client.get(f"/trigger/smallthing?key={self.cron_secret}")
        self.assertEqual(resp.json["status"], "sent")

    def test_weekly(self):
        resp = self.client.get(f"/trigger/weekly?key={self.cron_secret}")
        self.assertEqual(resp.json["status"], "sent")
        self.assertIsNotNone(db.get_active_review())

    def test_healthcheck_ok(self):
        from config import WEBHOOK_URL
        self._req_get_patch.stop()
        self._req_get_patch = patch("telegram.requests.get", return_value=MagicMock(
            json=lambda: {"ok": True, "result": {"url": WEBHOOK_URL, "last_error_message": ""}}
        ))
        self._req_get_patch.start()
        resp = self.client.get(f"/trigger/healthcheck?key={self.cron_secret}")
        self.assertEqual(resp.json["status"], "ok")

    def test_healthcheck_reregisters(self):
        self._req_get_patch.stop()
        self._req_get_patch = patch("telegram.requests.get", return_value=MagicMock(
            json=lambda: {"ok": True, "result": {"url": "", "last_error_message": ""}}
        ))
        self._req_get_patch.start()
        resp = self.client.get(f"/trigger/healthcheck?key={self.cron_secret}")
        self.assertEqual(resp.json["status"], "re-registered")


class TestHealth(FlaskTestCase):
    def test_root(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Bot is running", resp.data)


if __name__ == "__main__":
    unittest.main()
