"""Logic tests for the mail window. Run in the guest: MAILWINDOW_DIR=/ai/bin python3 mailwindow_test.py
These do not need a display. They use a private mail store in a temp directory."""
import json
import os
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
os.environ.setdefault("AIOS_MAIL_SOURCE", "/ai/apps/mail/mail.py")
import importlib.machinery  # noqa: E402
import importlib.util  # noqa: E402

# The window script has no .py suffix (it is installed as an executable), so load it by path.
_dir = os.environ.get("MAILWINDOW_DIR", str(HERE.parent / "bin"))
_loader = importlib.machinery.SourceFileLoader("mailwindow", os.path.join(_dir, "mailwindow"))
mailwindow = importlib.util.module_from_spec(importlib.util.spec_from_loader("mailwindow", _loader))
_loader.exec_module(mailwindow)


class MailWindowLogic(unittest.TestCase):
    def setUp(self):
        self.mail = mailwindow.load_mail()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "mail.json")
        self.store = {"messages": [
            {"id": 1, "folder": "INBOX", "from": "alice@example.com", "subject": "Welcome", "read": False, "body": "hi"},
            {"id": 2, "folder": "INBOX", "from": "bob@example.com", "subject": "Lunch", "read": True, "body": "noon?"},
            {"id": 3, "folder": "Outbox", "from": "you@ai-os.local", "subject": "Draft", "read": True, "body": ""},
        ], "next_id": 4}

    def tearDown(self):
        self.tmp.cleanup()

    def test_inbox_excludes_other_folders(self):
        self.assertEqual([m["id"] for m in mailwindow.inbox(self.store)], [1, 2])

    def test_row_marks_unread_messages(self):
        self.assertTrue(mailwindow.row_text(self.store["messages"][0]).startswith("● "))
        self.assertTrue(mailwindow.row_text(self.store["messages"][1]).startswith("  "))

    def test_detail_shows_headers_and_body(self):
        text = mailwindow.detail_text(self.store["messages"][0])
        self.assertIn("From:    alice@example.com", text)
        self.assertIn("Subject: Welcome", text)
        self.assertTrue(text.endswith("hi"))

    def test_set_read_changes_only_the_selected_message(self):
        self.assertTrue(mailwindow.set_read(self.store, 1, True))
        self.assertTrue(self.store["messages"][0]["read"])
        self.assertTrue(self.store["messages"][1]["read"])
        self.assertFalse(mailwindow.set_read(self.store, 99, True))

    def test_queue_message_lands_in_outbox_and_persists(self):
        msg = mailwindow.queue_message(self.store, "carol@example.com", "Report", "numbers", "Mon, 19 Oct 2026 09:00:00 +0000")
        self.assertEqual(msg["folder"], "Outbox")
        self.assertEqual(msg["id"], 4)
        self.assertEqual(self.store["next_id"], 5)
        self.mail.save_store(self.path, self.store)
        reloaded = self.mail.load_store(self.path)
        self.assertEqual(reloaded["messages"][-1]["subject"], "Report")

    def test_window_store_round_trip_keeps_read_state(self):
        mailwindow.set_read(self.store, 1, True)
        self.mail.save_store(self.path, self.store)
        again = self.mail.load_store(self.path)
        self.assertTrue(again["messages"][0]["read"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
