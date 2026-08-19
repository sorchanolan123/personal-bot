"""Tests for LLM wrapper."""

import json
import unittest
from unittest.mock import patch, MagicMock

from llm import parse_freeform, generate_review_summary, call_haiku


class TestCallHaiku(unittest.TestCase):
    @patch("llm.requests.post")
    def test_successful_call(self, mock_post):
        mock_post.return_value = MagicMock(
            json=lambda: {"content": [{"text": "hello"}]},
        )
        mock_post.return_value.raise_for_status = MagicMock()
        result = call_haiku("system", "user msg")
        self.assertEqual(result, "hello")

    @patch("llm.requests.post")
    def test_failed_call(self, mock_post):
        mock_post.side_effect = Exception("network error")
        result = call_haiku("system", "user msg")
        self.assertIsNone(result)

    @patch("llm.requests.post")
    def test_timeout(self, mock_post):
        from requests.exceptions import Timeout
        mock_post.side_effect = Timeout("timed out")
        result = call_haiku("system", "user msg")
        self.assertIsNone(result)


class TestParseFreeform(unittest.TestCase):
    @patch("llm.call_haiku")
    def test_list_item(self, mock_haiku):
        mock_haiku.return_value = json.dumps([
            {"action": "list_item", "list": "todo", "text": "buy milk", "due_date": None}
        ])
        actions = parse_freeform("buy milk", ["todo", "shopping"])
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["action"], "list_item")
        self.assertEqual(actions[0]["text"], "buy milk")

    @patch("llm.call_haiku")
    def test_tracking(self, mock_haiku):
        mock_haiku.return_value = json.dumps([
            {"action": "tracking", "type": "mood", "value": 7, "notes": "great day"}
        ])
        actions = parse_freeform("mood 7 great day", ["todo"])
        self.assertEqual(actions[0]["action"], "tracking")
        self.assertEqual(actions[0]["value"], 7)

    @patch("llm.call_haiku")
    def test_multiple_actions(self, mock_haiku):
        mock_haiku.return_value = json.dumps([
            {"action": "list_item", "list": "shopping", "text": "eggs", "due_date": None},
            {"action": "tracking", "type": "mood", "value": 8, "notes": "good"},
        ])
        actions = parse_freeform("buy eggs and feeling 8/10", ["todo", "shopping"])
        self.assertEqual(len(actions), 2)

    @patch("llm.call_haiku")
    def test_markdown_fences_stripped(self, mock_haiku):
        mock_haiku.return_value = (
            '```json\n[{"action": "list_item", "list": "todo", '
            '"text": "test", "due_date": null}]\n```'
        )
        actions = parse_freeform("test", ["todo"])
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["text"], "test")

    @patch("llm.call_haiku")
    def test_remove_item(self, mock_haiku):
        mock_haiku.return_value = json.dumps([
            {"action": "remove_item", "list": "todo", "text": "buy milk"}
        ])
        actions = parse_freeform("remove buy milk from todo", ["todo"])
        self.assertEqual(actions[0]["action"], "remove_item")

    @patch("llm.call_haiku")
    def test_mark_done(self, mock_haiku):
        mock_haiku.return_value = json.dumps([
            {"action": "mark_done", "list": "todo", "text": "buy milk"}
        ])
        actions = parse_freeform("I bought milk", ["todo"])
        self.assertEqual(actions[0]["action"], "mark_done")

    @patch("llm.call_haiku")
    def test_query(self, mock_haiku):
        mock_haiku.return_value = json.dumps([
            {"action": "query", "type": "show_all", "list": None}
        ])
        actions = parse_freeform("what do I need to do", ["todo"])
        self.assertEqual(actions[0]["action"], "query")

    @patch("llm.call_haiku")
    def test_invalid_json(self, mock_haiku):
        mock_haiku.return_value = "this is not json"
        actions = parse_freeform("hello", ["todo"])
        self.assertIsNone(actions)

    @patch("llm.call_haiku")
    def test_llm_returns_none(self, mock_haiku):
        mock_haiku.return_value = None
        actions = parse_freeform("hello", ["todo"])
        self.assertIsNone(actions)


class TestGenerateReviewSummary(unittest.TestCase):
    @patch("llm.call_haiku")
    def test_successful_summary(self, mock_haiku):
        mock_haiku.return_value = "Great week!"
        wins = {"completed": [{"list": "todo", "text": "thing"}]}
        answers = {"q1": "well", "q2": "nothing", "q3": "exercise"}
        result = generate_review_summary(wins, answers)
        self.assertEqual(result, "Great week!")

    @patch("llm.call_haiku")
    def test_failed_summary(self, mock_haiku):
        mock_haiku.return_value = None
        result = generate_review_summary({}, {})
        self.assertIn("keep going", result)


if __name__ == "__main__":
    unittest.main()
