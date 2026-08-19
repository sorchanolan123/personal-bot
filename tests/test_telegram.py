"""Tests for Telegram API wrapper."""

import unittest
from unittest.mock import patch, MagicMock

from telegram import parse_update, make_keyboard, send_message, edit_message, answer_callback


class TestParseUpdate(unittest.TestCase):
    def test_text_message(self):
        update = {"message": {"chat": {"id": 123}, "text": "hello"}}
        chat_id, text, callback = parse_update(update)
        self.assertEqual(chat_id, 123)
        self.assertEqual(text, "hello")
        self.assertIsNone(callback)

    def test_callback_query(self):
        update = {
            "callback_query": {
                "id": "abc123",
                "data": "done:todo:1",
                "message": {"chat": {"id": 123}, "message_id": 42},
            }
        }
        chat_id, text, callback = parse_update(update)
        self.assertEqual(chat_id, 123)
        self.assertIsNone(text)
        self.assertEqual(callback["id"], "abc123")
        self.assertEqual(callback["data"], "done:todo:1")
        self.assertEqual(callback["message_id"], 42)

    def test_empty_update(self):
        chat_id, text, callback = parse_update({})
        self.assertIsNone(chat_id)
        self.assertEqual(text, "")
        self.assertIsNone(callback)

    def test_message_no_text(self):
        update = {"message": {"chat": {"id": 123}}}
        chat_id, text, callback = parse_update(update)
        self.assertEqual(chat_id, 123)
        self.assertEqual(text, "")


class TestMakeKeyboard(unittest.TestCase):
    def test_single_button(self):
        buttons = [[("Click me", "action:1")]]
        kb = make_keyboard(buttons)
        self.assertEqual(kb, {
            "inline_keyboard": [[{"text": "Click me", "callback_data": "action:1"}]]
        })

    def test_multiple_rows(self):
        buttons = [[("A", "a:1")], [("B", "b:2")]]
        kb = make_keyboard(buttons)
        self.assertEqual(len(kb["inline_keyboard"]), 2)

    def test_multiple_buttons_per_row(self):
        buttons = [[("A", "a:1"), ("B", "b:2")]]
        kb = make_keyboard(buttons)
        self.assertEqual(len(kb["inline_keyboard"][0]), 2)


class TestSendMessage(unittest.TestCase):
    @patch("telegram.requests.post")
    def test_basic_send(self, mock_post):
        mock_post.return_value = MagicMock(
            json=lambda: {"ok": True, "result": {"message_id": 1}}
        )
        result = send_message(123, "hello")
        self.assertTrue(result["ok"])
        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["chat_id"], 123)
        self.assertEqual(payload["text"], "hello")

    @patch("telegram.requests.post")
    def test_send_with_keyboard(self, mock_post):
        mock_post.return_value = MagicMock(json=lambda: {"ok": True})
        keyboard = {"inline_keyboard": [[{"text": "A", "callback_data": "a"}]]}
        send_message(123, "pick", reply_markup=keyboard)
        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["reply_markup"], keyboard)


class TestEditMessage(unittest.TestCase):
    @patch("telegram.requests.post")
    def test_edit(self, mock_post):
        mock_post.return_value = MagicMock(json=lambda: {"ok": True})
        edit_message(123, 42, "updated")
        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["message_id"], 42)
        self.assertEqual(payload["text"], "updated")


class TestAnswerCallback(unittest.TestCase):
    @patch("telegram.requests.post")
    def test_answer_with_text(self, mock_post):
        mock_post.return_value = MagicMock(json=lambda: {"ok": True})
        answer_callback("cb123", "Done!")
        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["callback_query_id"], "cb123")
        self.assertEqual(payload["text"], "Done!")

    @patch("telegram.requests.post")
    def test_answer_no_text(self, mock_post):
        mock_post.return_value = MagicMock(json=lambda: {"ok": True})
        answer_callback("cb123")
        payload = mock_post.call_args[1]["json"]
        self.assertNotIn("text", payload)


if __name__ == "__main__":
    unittest.main()
