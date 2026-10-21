#!/usr/bin/env python3
"""mail — local e-mail reader for AI_OS.

A network-free mail store and reader. Messages live in a JSON file
(default /ai/state/mail.json, override with AIOS_MAIL_FILE or --file).
Nothing here opens sockets; fetching is done by importing an mbox file
with `mail import` (e.g. from a local spool or a file you provide).

Commands:
  mail import MBOX            Import messages from an mbox file.
  mail list [--folder F] [--all]
                              List messages with R/U flags (default: INBOX).
  mail show ID                Print one full message.
  mail read ID                Mark a message as read.
  mail unread ID              Mark a message as unread.
  mail delete ID              Delete a message.
  mail folders                List folders with unread/total counts.
  mail search PATTERN         Case-insensitive search of from/subject/body.
  mail compose TO SUBJECT [BODY]
                              Append a message to the Outbox folder.
  mail stats                  One-line summary: unread/total in INBOX.

Message fields: id, folder, from, to, subject, date, body, read.
"""
from __future__ import annotations

import argparse
import datetime
import email
import email.utils
import json
import mailbox
import os
import re
import sys
import tempfile

AI_ROOT = os.environ.get("AIOS_ROOT", "/ai")
DEFAULT_FILE = os.path.join(AI_ROOT, "state", "mail.json")

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2


def die(msg, code=EXIT_ERROR):
    print(f"mail: {msg}", file=sys.stderr)
    return code


def store_path(args) -> str:
    return args.file or os.environ.get("AIOS_MAIL_FILE") or DEFAULT_FILE


def load_store(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {"messages": [], "next_id": 1}
    except (OSError, json.JSONDecodeError) as exc:
        raise MailError(f"cannot read {path}: {exc}")
    if not isinstance(data, dict):
        raise MailError(f"{path}: unexpected store format")
    messages = data.get("messages", [])
    if not isinstance(messages, list):
        raise MailError(f"{path}: 'messages' must be a list")
    try:
        next_id = int(data.get("next_id", 1))
    except (TypeError, ValueError):
        raise MailError(f"{path}: 'next_id' must be an integer")
    return {"messages": messages, "next_id": next_id}


def save_store(path, store):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory or ".", prefix=".mail-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(store, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


class MailError(Exception):
    pass


def find_message(store, msg_id):
    for message in store["messages"]:
        if message.get("id") == msg_id:
            return message
    return None


def require_message(store, msg_id):
    message = find_message(store, msg_id)
    if message is None:
        raise MailError(f"no such message: {msg_id}")
    return message


def message_date(item):
    """Date header, or the mbox envelope date when the header is missing."""
    header = str(item.get("Date", "")).strip()
    if header:
        return header
    envelope = (item.get_from() or "").split(None, 1)
    if len(envelope) < 2:
        return ""
    try:
        parsed = datetime.datetime.strptime(envelope[1], "%a %b %d %H:%M:%S %Y")
    except ValueError:
        return envelope[1]
    return email.utils.format_datetime(parsed.replace(tzinfo=datetime.timezone.utc))


def parse_mbox(path):
    """Yield normalized message dicts from an mbox file."""
    if not os.path.isfile(path):
        raise MailError(f"no such file: {path}")
    box = mailbox.mbox(path, create=False)
    parsed = []
    try:
        for item in box:
            body = ""
            if item.is_multipart():
                parts = []
                for part in item.walk():
                    if part.get_content_type() == "text/plain" and not part.is_multipart():
                        try:
                            parts.append(part.get_payload(decode=True).decode(
                                part.get_content_charset() or "utf-8", "replace"))
                        except Exception:
                            continue
                body = "\n".join(parts)
            else:
                try:
                    payload = item.get_payload(decode=True)
                    body = payload.decode(
                        item.get_content_charset() or "utf-8", "replace") if payload else ""
                except Exception:
                    body = ""
            parsed.append({
                "folder": "INBOX",
                "from": str(item.get("From", "")).strip(),
                "to": str(item.get("To", "")).strip(),
                "subject": str(item.get("Subject", "")).strip(),
                "date": message_date(item),
                "body": body,
                "read": False,
            })
    finally:
        box.close()
    return parsed


def cmd_import(args):
    path = store_path(args)
    store = load_store(path)
    incoming = parse_mbox(args.mbox)
    added = 0
    for msg in incoming:
        msg["id"] = store["next_id"]
        store["next_id"] += 1
        store["messages"].append(msg)
        added += 1
    save_store(path, store)
    print(f"imported {added} message(s) into INBOX")
    return EXIT_OK


def matches_folder(message, folder, all_folders):
    return all_folders or message.get("folder", "INBOX") == folder


def cmd_list(args):
    store = load_store(store_path(args))
    shown = 0
    for message in store["messages"]:
        if not matches_folder(message, args.folder, args.all):
            continue
        flags = "R" if message.get("read") else "U"
        subject = message.get("subject", "") or "(no subject)"
        sender = message.get("from", "") or "(unknown sender)"
        print(f"{message['id']:>4}  [{flags}]  {message.get('folder', 'INBOX'):<8}  "
              f"{sender:<24}  {subject}")
        shown += 1
    print(f"-- {shown} message(s) shown")
    return EXIT_OK


def cmd_show(args):
    store = load_store(store_path(args))
    message = require_message(store, args.id)
    print(f"From:    {message.get('from', '')}")
    print(f"To:      {message.get('to', '')}")
    print(f"Subject: {message.get('subject', '')}")
    print(f"Date:    {message.get('date', '')}")
    print(f"Folder:  {message.get('folder', 'INBOX')}")
    print(f"Status:  {'read' if message.get('read') else 'unread'}")
    print()
    print(message.get("body", ""))
    return EXIT_OK


def _set_read(args, value):
    path = store_path(args)
    store = load_store(path)
    message = require_message(store, args.id)
    message["read"] = value
    save_store(path, store)
    print(f"message {args.id} marked {'read' if value else 'unread'}")
    return EXIT_OK


def cmd_read(args):
    return _set_read(args, True)


def cmd_unread(args):
    return _set_read(args, False)


def cmd_delete(args):
    path = store_path(args)
    store = load_store(path)
    require_message(store, args.id)
    store["messages"] = [m for m in store["messages"] if m.get("id") != args.id]
    save_store(path, store)
    print(f"deleted message {args.id}")
    return EXIT_OK


def cmd_folders(args):
    store = load_store(store_path(args))
    counts = {}
    for message in store["messages"]:
        folder = message.get("folder", "INBOX")
        total, unread = counts.get(folder, (0, 0))
        counts[folder] = (total + 1, unread + (0 if message.get("read") else 1))
    if not counts:
        print("(no folders)")
        return EXIT_OK
    for folder in sorted(counts):
        total, unread = counts[folder]
        print(f"{folder:<12} {unread} unread / {total} total")
    return EXIT_OK


def cmd_search(args):
    store = load_store(store_path(args))
    pattern = args.pattern.lower()
    hits = 0
    for message in store["messages"]:
        haystack = " ".join([
            str(message.get("from", "")),
            str(message.get("subject", "")),
            str(message.get("body", "")),
        ]).lower()
        if pattern in haystack:
            flags = "R" if message.get("read") else "U"
            print(f"{message['id']:>4}  [{flags}]  {message.get('folder', 'INBOX'):<8}  "
                  f"{message.get('from', ''):<24}  {message.get('subject', '')}")
            hits += 1
    print(f"-- {hits} match(es)")
    return EXIT_OK


def cmd_compose(args):
    path = store_path(args)
    store = load_store(path)
    message = {
        "id": store["next_id"],
        "folder": "Outbox",
        "from": "you@ai-os.local",
        "to": args.to,
        "subject": args.subject,
        "date": email.utils.formatdate(localtime=True),
        "body": args.body or "",
        "read": True,
    }
    store["next_id"] += 1
    store["messages"].append(message)
    save_store(path, store)
    print(f"queued message {message['id']} in Outbox")
    return EXIT_OK


def cmd_stats(args):
    store = load_store(store_path(args))
    inbox = [m for m in store["messages"] if m.get("folder", "INBOX") == "INBOX"]
    unread = sum(1 for m in inbox if not m.get("read"))
    print(f"INBOX: {unread} unread / {len(inbox)} total")
    return EXIT_OK


def build_parser():
    parser = argparse.ArgumentParser(prog="mail", add_help=True,
                                     description="Local e-mail reader for AI_OS")
    parser.add_argument("--file", help="mail store path (default /ai/state/mail.json)")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("import")
    p.add_argument("mbox")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("list")
    p.add_argument("--folder", default="INBOX")
    p.add_argument("--all", action="store_true")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show")
    p.add_argument("id", type=int)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("read")
    p.add_argument("id", type=int)
    p.set_defaults(func=cmd_read)

    p = sub.add_parser("unread")
    p.add_argument("id", type=int)
    p.set_defaults(func=cmd_unread)

    p = sub.add_parser("delete")
    p.add_argument("id", type=int)
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("folders")
    p.set_defaults(func=cmd_folders)

    p = sub.add_parser("search")
    p.add_argument("pattern")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("compose")
    p.add_argument("to")
    p.add_argument("subject")
    p.add_argument("body", nargs="?")
    p.set_defaults(func=cmd_compose)

    p = sub.add_parser("stats")
    p.set_defaults(func=cmd_stats)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return EXIT_USAGE
    try:
        return args.func(args)
    except MailError as exc:
        return die(str(exc))


if __name__ == "__main__":
    sys.exit(main())
