"""Shared base class for all tests — uses unittest (no pytest needed)."""

import sys
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import db
import telegram
import handlers


class BotTestCase(unittest.TestCase):
    """Base class that sets up a fresh temp database and Telegram mocks."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = os.path.join(self._tmpdir, "test.db")
        self._db_patch = patch.object(db, "DB_PATH", self._db_path)
        self._db_patch.start()
        db.init_db()

        # Telegram mocks — must patch in handlers module too since it uses
        # `from telegram import send_message` (binds its own reference)
        self.sent = []
        self.edits = []
        self.answers = []

        def fake_send(chat_id, text, parse_mode="Markdown", reply_markup=None):
            self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
            return {"ok": True, "result": {"message_id": len(self.sent)}}

        def fake_edit(chat_id, message_id, text, parse_mode="Markdown", reply_markup=None):
            self.edits.append({"chat_id": chat_id, "message_id": message_id,
                               "text": text, "reply_markup": reply_markup})
            return {"ok": True}

        def fake_answer(callback_query_id, text=None):
            self.answers.append({"id": callback_query_id, "text": text})
            return {"ok": True}

        # Patch in both telegram and handlers modules
        self._patches = [
            patch.object(telegram, "send_message", side_effect=fake_send),
            patch.object(telegram, "edit_message", side_effect=fake_edit),
            patch.object(telegram, "answer_callback", side_effect=fake_answer),
            patch.object(handlers, "send_message", side_effect=fake_send),
            patch.object(handlers, "edit_message", side_effect=fake_edit),
            patch.object(handlers, "answer_callback", side_effect=fake_answer),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        self._db_patch.stop()
        for p in self._patches:
            p.stop()
        if os.path.exists(self._db_path):
            os.remove(self._db_path)
        os.rmdir(self._tmpdir)

    def populate_db(self):
        """Add standard test data."""
        db.create_list("todo", "Things to do")
        db.create_list("shopping", "Groceries")
        db.add_item("todo", "buy oat milk", due_date="2025-03-12")
        db.add_item("todo", "call dentist")
        db.add_item("todo", "fix bike", due_date="2025-03-10")
        db.add_item("shopping", "eggs")
        db.add_item("shopping", "bread")
