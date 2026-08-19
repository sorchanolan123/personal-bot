"""Tests for message routing and command handlers."""

import json
import unittest
from unittest.mock import patch

from conftest import BotTestCase
import db
from handlers import handle_message, handle_callback, format_items, format_all_lists


class TestMessageRouting(BotTestCase):
    def test_slash_command(self):
        self.populate_db()
        handle_message(123, "/lists")
        self.assertIn("Your lists", self.sent[0]["text"])

    def test_command_without_slash(self):
        self.populate_db()
        handle_message(123, "lists")
        self.assertIn("Your lists", self.sent[0]["text"])

    def test_list_name_shows_items(self):
        self.populate_db()
        handle_message(123, "/todo")
        self.assertIn("todo", self.sent[0]["text"])

    def test_list_name_adds_item(self):
        self.populate_db()
        handle_message(123, "/todo new task")
        self.assertIn("Added", self.sent[0]["text"])
        self.assertIn("new task", self.sent[0]["text"])

    def test_unknown_goes_to_freeform(self):
        self.populate_db()
        with patch("handlers.handle_freeform") as mock_ff:
            handle_message(123, "I feel great today")
            mock_ff.assert_called_once()

    def test_review_intercept(self):
        self.populate_db()
        wins = {"completed": [], "habits": [], "tracking": []}
        db.start_weekly_review(wins)
        handle_message(123, "things went well")
        self.assertTrue(any("?" in s["text"] for s in self.sent))

    def test_bot_username_stripped(self):
        self.populate_db()
        handle_message(123, "/lists@MyBot")
        self.assertIn("Your lists", self.sent[0]["text"])

    def test_help_command(self):
        handle_message(123, "/help")
        self.assertIn("Commands", self.sent[0]["text"])

    def test_start_command(self):
        handle_message(123, "/start")
        self.assertIn("Hey", self.sent[0]["text"])


class TestCommandHandlers(BotTestCase):
    def test_newlist(self):
        handle_message(123, "/newlist mylist A test list")
        self.assertTrue(db.list_exists("mylist"))
        self.assertIn("Created", self.sent[0]["text"])

    def test_newlist_reserved(self):
        handle_message(123, "/newlist help")
        self.assertIn("reserved", self.sent[0]["text"])

    def test_deletelist(self):
        self.populate_db()
        handle_message(123, "/deletelist todo")
        self.assertFalse(db.list_exists("todo"))

    def test_done(self):
        self.populate_db()
        handle_message(123, "/done todo 1")
        self.assertIn("Done", self.sent[0]["text"])

    def test_done_invalid(self):
        self.populate_db()
        handle_message(123, "/done todo 99")
        self.assertIn("not found", self.sent[0]["text"])

    def test_undo(self):
        self.populate_db()
        db.mark_done("todo", 1)
        handle_message(123, "/undo todo 1")
        self.assertIn("Restored", self.sent[0]["text"])

    def test_move(self):
        self.populate_db()
        handle_message(123, "/move todo 1 shopping")
        self.assertIn("Moved", self.sent[0]["text"])
        self.assertEqual(len(db.get_items("todo")), 2)

    def test_remove(self):
        self.populate_db()
        handle_message(123, "/remove todo 1")
        self.assertIn("Removed", self.sent[0]["text"])

    def test_edit(self):
        self.populate_db()
        handle_message(123, "/edit todo 1 updated text")
        self.assertIn("Updated", self.sent[0]["text"])

    def test_due(self):
        self.populate_db()
        import datetime as dt
        with patch("handlers.datetime") as mock_dt:
            mock_dt.now.return_value = dt.datetime(2025, 3, 12)
            mock_dt.strptime.side_effect = dt.datetime.strptime
            handle_message(123, "/due todo 2 tomorrow")
            self.assertIn("Due date set", self.sent[0]["text"])

    def test_undue(self):
        self.populate_db()
        handle_message(123, "/undue todo 1")
        self.assertIn("Due date removed", self.sent[0]["text"])

    def test_clear(self):
        self.populate_db()
        db.mark_done("todo", 1)
        handle_message(123, "/clear todo")
        self.assertIn("Cleared", self.sent[0]["text"])

    def test_all(self):
        self.populate_db()
        handle_message(123, "/all")
        self.assertIn("Everything pending", self.sent[0]["text"])

    def test_all_empty(self):
        handle_message(123, "/all")
        self.assertIn("caught up", self.sent[0]["text"])

    def test_focus(self):
        self.populate_db()
        import datetime as dt
        with patch("db.datetime") as mock_dt:
            mock_dt.now.return_value = dt.datetime(2025, 3, 12)
            mock_dt.strptime.side_effect = dt.datetime.strptime
            handle_message(123, "/focus")
            self.assertIn("Today", self.sent[0]["text"])

    def test_track(self):
        handle_message(123, "/track mood 7 feeling good")
        self.assertIn("Logged", self.sent[0]["text"])
        self.assertIn("mood", self.sent[0]["text"])

    def test_track_no_args(self):
        handle_message(123, "/track")
        self.assertIn("Usage", self.sent[0]["text"])


class TestCategoryCommands(BotTestCase):
    def test_category_add(self):
        db.create_list("watch")
        handle_message(123, "/watch film Inception")
        items = db.get_items("watch")
        self.assertEqual(items[0]["text"], "Inception")
        meta = json.loads(items[0]["metadata"])
        self.assertEqual(meta["category"], "film")

    def test_category_filter(self):
        db.create_list("watch")
        db.add_item("watch", "Inception", metadata={"category": "film"})
        db.add_item("watch", "Breaking Bad", metadata={"category": "show"})
        handle_message(123, "/watch films")
        # Should only show films
        self.assertEqual(len(self.sent), 1)


class TestHabitHandlers(BotTestCase):
    def test_newhabit(self):
        handle_message(123, "/newhabit meditate")
        self.assertIn("created", self.sent[0]["text"].lower())

    def test_log_habit(self):
        db.create_habit("meditate")
        handle_message(123, "/log meditate")
        self.assertIn("Logged", self.sent[0]["text"])

    def test_habits_display_with_buttons(self):
        db.create_habit("meditate")
        handle_message(123, "/habits")
        self.assertIn("meditate", self.sent[0]["text"])
        self.assertIsNotNone(self.sent[0]["reply_markup"])

    def test_deletehabit(self):
        db.create_habit("meditate")
        handle_message(123, "/deletehabit meditate")
        self.assertIn("Deleted", self.sent[0]["text"])


class TestCallbackHandler(BotTestCase):
    def test_done_callback(self):
        self.populate_db()
        callback = {"id": "cb1", "data": "done:todo:1", "message_id": 42}
        handle_callback(123, callback)
        self.assertEqual(self.answers[0]["text"], "✅ Done!")
        self.assertEqual(len(self.edits), 1)

    def test_focusdone_callback(self):
        self.populate_db()
        items = db.get_items("todo")
        item_id = items[0]["id"]
        callback = {"id": "cb1", "data": f"focusdone:{item_id}", "message_id": 42}
        handle_callback(123, callback)
        self.assertIn("Done", self.answers[0]["text"])

    def test_habit_callback(self):
        db.create_habit("meditate")
        callback = {"id": "cb1", "data": "habit:meditate", "message_id": 42}
        handle_callback(123, callback)
        self.assertIn("Logged", self.answers[0]["text"])
        self.assertIn("meditate", db.get_habits_logged_today())

    def test_unknown_callback(self):
        callback = {"id": "cb1", "data": "unknown:foo", "message_id": 42}
        handle_callback(123, callback)
        self.assertEqual(len(self.answers), 1)


class TestFormatters(BotTestCase):
    def test_format_items_empty(self):
        text = format_items([], "todo")
        self.assertIn("empty", text)

    def test_format_all_lists_empty(self):
        text = format_all_lists([])
        self.assertIn("No lists", text)

    def test_format_items_with_buttons(self):
        self.populate_db()
        items = db.get_items("todo")
        text, keyboard = format_items(items, "todo", with_buttons=True)
        self.assertIsNotNone(keyboard)
        self.assertIn("todo", text)


class TestDateParsingInAdd(BotTestCase):
    def test_add_item_with_trailing_date(self):
        db.create_list("todo")
        import datetime as dt
        with patch("handlers.datetime") as mock_dt:
            mock_dt.now.return_value = dt.datetime(2025, 3, 12)
            mock_dt.strptime.side_effect = dt.datetime.strptime
            handle_message(123, "/todo ring dad today")
            items = db.get_items("todo")
            self.assertEqual(items[0]["text"], "ring dad")
            self.assertEqual(items[0]["due_date"], "2025-03-12")
            self.assertIn("due 2025-03-12", self.sent[0]["text"])


if __name__ == "__main__":
    unittest.main()
