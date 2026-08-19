"""Tests for date parsing in handlers.py."""

import datetime as dt
import unittest
from unittest.mock import patch

from handlers import parse_due_date, _resolve_date_word, _resolve_ordinal_day

# Fix "now" to Wednesday 2025-03-12 for predictable tests
FIXED_NOW = dt.datetime(2025, 3, 12, 10, 0, 0)


def mock_datetime():
    """Return a patch context manager that freezes handlers.datetime.now()."""
    p = patch("handlers.datetime")
    mock_dt = p.start()
    mock_dt.now.return_value = FIXED_NOW
    mock_dt.strptime.side_effect = dt.datetime.strptime
    return p, mock_dt


class TestResolveDateWord(unittest.TestCase):
    def setUp(self):
        self._patch, _ = mock_datetime()

    def tearDown(self):
        self._patch.stop()

    def test_today(self):
        self.assertEqual(_resolve_date_word("today"), "2025-03-12")

    def test_tonight(self):
        self.assertEqual(_resolve_date_word("tonight"), "2025-03-12")

    def test_tomorrow(self):
        self.assertEqual(_resolve_date_word("tomorrow"), "2025-03-13")

    def test_day_name_future(self):
        # Wednesday now, friday = 2 days ahead
        self.assertEqual(_resolve_date_word("friday"), "2025-03-14")

    def test_day_name_same_day(self):
        # Wednesday now, wednesday = next week
        self.assertEqual(_resolve_date_word("wednesday"), "2025-03-19")

    def test_day_name_past_in_week(self):
        # Wednesday now, monday = next monday (5 days)
        self.assertEqual(_resolve_date_word("monday"), "2025-03-17")

    def test_iso_date(self):
        self.assertEqual(_resolve_date_word("2025-06-15"), "2025-06-15")

    def test_invalid(self):
        self.assertIsNone(_resolve_date_word("banana"))

    def test_case_insensitive(self):
        self.assertEqual(_resolve_date_word("TODAY"), "2025-03-12")
        self.assertEqual(_resolve_date_word("Friday"), "2025-03-14")


class TestResolveOrdinalDay(unittest.TestCase):
    def setUp(self):
        self._patch, _ = mock_datetime()

    def tearDown(self):
        self._patch.stop()

    def test_future_day_this_month(self):
        self.assertEqual(_resolve_ordinal_day(20), "2025-03-20")

    def test_today_same_day(self):
        self.assertEqual(_resolve_ordinal_day(12), "2025-03-12")

    def test_past_day_rolls_to_next_month(self):
        self.assertEqual(_resolve_ordinal_day(5), "2025-04-05")

    def test_day_31_this_month(self):
        self.assertEqual(_resolve_ordinal_day(31), "2025-03-31")

    def test_invalid_day_for_next_month(self):
        # Jan 31, asking for 30th → Feb doesn't have 30 → None
        self._patch.stop()
        with patch("handlers.datetime") as mock_dt:
            mock_dt.now.return_value = dt.datetime(2025, 1, 31, 10, 0, 0)
            mock_dt.strptime.side_effect = dt.datetime.strptime
            self.assertIsNone(_resolve_ordinal_day(30))
        self._patch, _ = mock_datetime()  # Restore for tearDown


class TestParseDueDate(unittest.TestCase):
    def setUp(self):
        self._patch, _ = mock_datetime()

    def tearDown(self):
        self._patch.stop()

    # Explicit due: prefix
    def test_due_prefix_today(self):
        self.assertEqual(parse_due_date("call mom due:today"), ("call mom", "2025-03-12"))

    def test_due_prefix_tomorrow(self):
        self.assertEqual(parse_due_date("call mom due:tomorrow"), ("call mom", "2025-03-13"))

    def test_due_prefix_day_name(self):
        self.assertEqual(parse_due_date("call mom due:friday"), ("call mom", "2025-03-14"))

    def test_due_prefix_iso(self):
        self.assertEqual(parse_due_date("call mom due:2025-06-15"), ("call mom", "2025-06-15"))

    def test_due_prefix_middle_of_text(self):
        self.assertEqual(parse_due_date("submit due:friday report"), ("submit report", "2025-03-14"))

    def test_due_prefix_invalid_falls_through(self):
        _, date = parse_due_date("call mom due:banana")
        self.assertIsNone(date)

    # Trailing natural words
    def test_trailing_today(self):
        self.assertEqual(parse_due_date("ring dad today"), ("ring dad", "2025-03-12"))

    def test_trailing_tomorrow(self):
        self.assertEqual(parse_due_date("buy milk tomorrow"), ("buy milk", "2025-03-13"))

    def test_trailing_tonight(self):
        self.assertEqual(parse_due_date("laundry tonight"), ("laundry", "2025-03-12"))

    def test_trailing_day_name(self):
        self.assertEqual(parse_due_date("submit report friday"), ("submit report", "2025-03-14"))

    def test_trailing_iso(self):
        self.assertEqual(parse_due_date("meeting 2025-03-15"), ("meeting", "2025-03-15"))

    # Ordinal patterns
    def test_on_the_5th(self):
        self.assertEqual(parse_due_date("dentist on the 5th"), ("dentist", "2025-04-05"))

    def test_on_the_20th(self):
        self.assertEqual(parse_due_date("submit report on the 20th"), ("submit report", "2025-03-20"))

    def test_on_the_1st(self):
        self.assertEqual(parse_due_date("rent on the 1st"), ("rent", "2025-04-01"))

    def test_on_the_23rd(self):
        self.assertEqual(parse_due_date("deadline on the 23rd"), ("deadline", "2025-03-23"))

    # No date
    def test_no_date(self):
        self.assertEqual(parse_due_date("buy oat milk"), ("buy oat milk", None))

    def test_single_word(self):
        self.assertEqual(parse_due_date("milk"), ("milk", None))

    # False positives
    def test_no_false_positive_possessive(self):
        _, date = parse_due_date("buy today's newspaper")
        self.assertIsNone(date)

    def test_no_false_positive_everyday(self):
        _, date = parse_due_date("buy everyday shampoo")
        self.assertIsNone(date)

    # Punctuation stripping
    def test_trailing_with_period(self):
        self.assertEqual(parse_due_date("ring dad today."), ("ring dad", "2025-03-12"))

    def test_trailing_with_exclamation(self):
        self.assertEqual(parse_due_date("ring dad tomorrow!"), ("ring dad", "2025-03-13"))

    # Priority
    def test_due_prefix_takes_priority(self):
        _, date = parse_due_date("ring dad due:friday today")
        self.assertEqual(date, "2025-03-14")


if __name__ == "__main__":
    unittest.main()
