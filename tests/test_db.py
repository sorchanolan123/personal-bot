"""Tests for database operations in db.py."""

import datetime as dt
import json
import unittest
from unittest.mock import patch

from conftest import BotTestCase
import db


class TestListOperations(BotTestCase):
    def test_create_list(self):
        ok, reason = db.create_list("todo", "Things to do")
        self.assertTrue(ok)
        self.assertTrue(db.list_exists("todo"))

    def test_create_list_duplicate(self):
        db.create_list("todo")
        ok, reason = db.create_list("todo")
        self.assertFalse(ok)
        self.assertEqual(reason, "exists")

    def test_create_list_reserved(self):
        ok, reason = db.create_list("help")
        self.assertFalse(ok)
        self.assertEqual(reason, "reserved")

    def test_create_list_case_insensitive(self):
        db.create_list("Todo")
        self.assertTrue(db.list_exists("todo"))

    def test_delete_list(self):
        db.create_list("todo")
        db.add_item("todo", "test item")
        self.assertTrue(db.delete_list("todo"))
        self.assertFalse(db.list_exists("todo"))

    def test_delete_list_nonexistent(self):
        self.assertFalse(db.delete_list("nope"))

    def test_rename_list(self):
        db.create_list("old")
        db.add_item("old", "item")
        ok, _ = db.rename_list("old", "new")
        self.assertTrue(ok)
        self.assertFalse(db.list_exists("old"))
        self.assertTrue(db.list_exists("new"))
        self.assertEqual(len(db.get_items("new")), 1)

    def test_rename_list_reserved(self):
        db.create_list("old")
        ok, reason = db.rename_list("old", "help")
        self.assertFalse(ok)
        self.assertEqual(reason, "reserved")

    def test_rename_list_conflict(self):
        db.create_list("a")
        db.create_list("b")
        ok, reason = db.rename_list("a", "b")
        self.assertFalse(ok)
        self.assertEqual(reason, "exists")

    def test_get_lists_pending_count(self):
        self.populate_db()
        lists = db.get_lists()
        todo = [l for l in lists if l["name"] == "todo"][0]
        self.assertEqual(todo["pending"], 3)


class TestItemOperations(BotTestCase):
    def test_add_item(self):
        db.create_list("todo")
        item_id = db.add_item("todo", "test item")
        self.assertGreater(item_id, 0)
        items = db.get_items("todo")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["text"], "test item")

    def test_add_item_with_due_date(self):
        db.create_list("todo")
        db.add_item("todo", "deadline thing", due_date="2025-03-15")
        items = db.get_items("todo")
        self.assertEqual(items[0]["due_date"], "2025-03-15")

    def test_add_item_with_metadata(self):
        db.create_list("watch")
        db.add_item("watch", "Inception", metadata={"category": "film"})
        items = db.get_items("watch")
        meta = json.loads(items[0]["metadata"])
        self.assertEqual(meta["category"], "film")

    def test_get_items_pending_only(self):
        self.populate_db()
        items = db.get_items("todo")
        self.assertTrue(all(not i["done"] for i in items))

    def test_get_items_include_done_recent(self):
        self.populate_db()
        db.mark_done("todo", 1)
        items = db.get_items("todo", include_done=True)
        self.assertTrue(any(i["done"] for i in items))

    def test_get_items_old_done_excluded(self):
        db.create_list("todo")
        db.add_item("todo", "old item")
        db.mark_done("todo", 1)
        conn = db.get_db()
        conn.execute("UPDATE items SET completed_at = '2020-01-01 00:00:00' WHERE done = 1")
        conn.commit()
        conn.close()
        items = db.get_items("todo", include_done=True)
        self.assertEqual(len(items), 0)

    def test_mark_done(self):
        self.populate_db()
        self.assertTrue(db.mark_done("todo", 1))
        self.assertEqual(len(db.get_items("todo")), 2)

    def test_mark_done_invalid(self):
        self.populate_db()
        self.assertFalse(db.mark_done("todo", 99))

    def test_mark_undone(self):
        self.populate_db()
        db.mark_done("todo", 1)
        self.assertTrue(db.mark_undone("todo", 1))
        self.assertEqual(len(db.get_items("todo")), 3)

    def test_move_item(self):
        self.populate_db()
        self.assertTrue(db.move_item("todo", 1, "shopping"))
        self.assertEqual(len(db.get_items("todo")), 2)
        self.assertEqual(len(db.get_items("shopping")), 3)

    def test_move_item_invalid(self):
        self.populate_db()
        self.assertFalse(db.move_item("todo", 99, "shopping"))

    def test_delete_item(self):
        self.populate_db()
        text = db.delete_item("todo", 1)
        self.assertEqual(text, "buy oat milk")
        self.assertEqual(len(db.get_items("todo")), 2)

    def test_delete_item_invalid(self):
        self.populate_db()
        self.assertIsNone(db.delete_item("todo", 99))

    def test_edit_item(self):
        self.populate_db()
        self.assertTrue(db.edit_item("todo", 1, "buy almond milk"))
        items = db.get_items("todo")
        self.assertEqual(items[0]["text"], "buy almond milk")

    def test_set_due_date(self):
        self.populate_db()
        self.assertTrue(db.set_due_date("todo", 2, "2025-04-01"))
        items = db.get_items("todo")
        item = [i for i in items if i["text"] == "call dentist"][0]
        self.assertEqual(item["due_date"], "2025-04-01")

    def test_clear_due_date(self):
        self.populate_db()
        self.assertTrue(db.set_due_date("todo", 1, None))
        items = db.get_items("todo")
        self.assertIsNone(items[0]["due_date"])

    def test_find_item_by_text(self):
        self.populate_db()
        pos, item = db.find_item_by_text("todo", "dentist")
        self.assertEqual(pos, 2)
        self.assertIn("dentist", item["text"])

    def test_find_item_not_found(self):
        self.populate_db()
        pos, item = db.find_item_by_text("todo", "nonexistent")
        self.assertIsNone(pos)

    def test_clear_done(self):
        self.populate_db()
        db.mark_done("todo", 1)
        db.mark_done("todo", 1)
        count = db.clear_done("todo")
        self.assertEqual(count, 2)

    def test_mark_done_by_id(self):
        db.create_list("todo")
        item_id = db.add_item("todo", "test")
        db.mark_done_by_id(item_id)
        self.assertEqual(len(db.get_items("todo")), 0)


class TestBriefingHelpers(BotTestCase):
    def test_get_all_pending(self):
        self.populate_db()
        items = db.get_all_pending()
        self.assertEqual(len(items), 5)

    def test_get_due_today(self):
        self.populate_db()
        with patch("db.datetime") as mock_dt:
            mock_dt.now.return_value = dt.datetime(2025, 3, 12)
            mock_dt.strptime.side_effect = dt.datetime.strptime
            items = db.get_due_today()
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["text"], "buy oat milk")

    def test_get_overdue(self):
        self.populate_db()
        with patch("db.datetime") as mock_dt:
            mock_dt.now.return_value = dt.datetime(2025, 3, 12)
            mock_dt.strptime.side_effect = dt.datetime.strptime
            items = db.get_overdue()
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["text"], "fix bike")

    def test_get_due_tomorrow(self):
        self.populate_db()
        with patch("db.datetime") as mock_dt:
            mock_dt.now.return_value = dt.datetime(2025, 3, 11)
            mock_dt.strptime.side_effect = dt.datetime.strptime
            items = db.get_due_tomorrow()
            self.assertEqual(len(items), 1)

    def test_get_completed_since(self):
        self.populate_db()
        db.mark_done("todo", 1)
        items = db.get_completed_since(days=1)
        self.assertEqual(len(items), 1)

    def test_get_stale_items(self):
        db.create_list("todo")
        db.add_item("todo", "old thing")
        conn = db.get_db()
        conn.execute("UPDATE items SET created_at = '2020-01-01 00:00:00'")
        conn.commit()
        conn.close()
        stale = db.get_stale_items(days=7)
        self.assertEqual(len(stale), 1)

    def test_get_focus_today(self):
        self.populate_db()
        with patch("db.datetime") as mock_dt:
            mock_dt.now.return_value = dt.datetime(2025, 3, 12)
            mock_dt.strptime.side_effect = dt.datetime.strptime
            items = db.get_focus_today()
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["text"], "buy oat milk")


class TestTracking(BotTestCase):
    def test_add_and_get_tracking(self):
        db.add_tracking("mood", 7, "feeling good")
        rows = db.get_tracking_since(days=1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["type"], "mood")
        self.assertEqual(rows[0]["value"], 7.0)

    def test_tracking_by_type(self):
        db.add_tracking("mood", 7)
        db.add_tracking("sleep", 8)
        db.add_tracking("mood", 6)
        rows = db.get_tracking_by_type("mood")
        self.assertEqual(len(rows), 2)


class TestHabits(BotTestCase):
    def test_create_habit(self):
        self.assertTrue(db.create_habit("meditate"))
        self.assertEqual(len(db.get_habits()), 1)

    def test_create_habit_duplicate(self):
        db.create_habit("meditate")
        self.assertFalse(db.create_habit("meditate"))

    def test_delete_habit(self):
        db.create_habit("meditate")
        db.log_habit("meditate")
        self.assertTrue(db.delete_habit("meditate"))
        self.assertEqual(len(db.get_habits()), 0)

    def test_log_habit(self):
        db.create_habit("meditate")
        db.log_habit("meditate")
        self.assertIn("meditate", db.get_habits_logged_today())

    def test_habit_streak_one_day(self):
        db.create_habit("meditate")
        db.log_habit("meditate")
        self.assertEqual(db.get_habit_streak("meditate"), 1)

    def test_habit_streak_consecutive(self):
        db.create_habit("meditate")
        db.log_habit("meditate")
        conn = db.get_db()
        yesterday = (dt.datetime.now() - dt.timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO habit_logs (habit_name, done, created_at) VALUES (?, 1, ?)",
            ("meditate", yesterday)
        )
        conn.commit()
        conn.close()
        self.assertEqual(db.get_habit_streak("meditate"), 2)

    def test_habit_streak_broken(self):
        db.create_habit("meditate")
        db.log_habit("meditate")
        conn = db.get_db()
        old = (dt.datetime.now() - dt.timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO habit_logs (habit_name, done, created_at) VALUES (?, 1, ?)",
            ("meditate", old)
        )
        conn.commit()
        conn.close()
        self.assertEqual(db.get_habit_streak("meditate"), 1)


class TestWeeklyReview(BotTestCase):
    def test_review_lifecycle(self):
        wins = {"completed": [], "habits": [], "tracking": []}
        review_id = db.start_weekly_review(wins)
        self.assertGreater(review_id, 0)
        self.assertIsNotNone(db.get_active_review())

        db.advance_review(review_id, "went well")
        db.advance_review(review_id, "nothing bad")
        db.advance_review(review_id, "focus on health")

        self.assertIsNone(db.get_active_review())
        past = db.get_past_reviews(limit=1)
        self.assertEqual(len(past), 1)
        self.assertEqual(past[0]["q1_answer"], "went well")

    def test_save_review_summary(self):
        wins = {"completed": [], "habits": [], "tracking": []}
        review_id = db.start_weekly_review(wins)
        db.advance_review(review_id, "a")
        db.advance_review(review_id, "b")
        db.advance_review(review_id, "c")
        db.save_review_summary(review_id, "Great week!")
        past = db.get_past_reviews(limit=1)
        self.assertEqual(past[0]["summary"], "Great week!")

    def test_stale_review_expired(self):
        wins = {"completed": [], "habits": [], "tracking": []}
        db.start_weekly_review(wins)
        db.start_weekly_review(wins)
        # First review should be auto-completed
        past = db.get_past_reviews()
        self.assertTrue(any(r["completed_at"] for r in past))


if __name__ == "__main__":
    unittest.main()
