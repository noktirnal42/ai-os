#!/bin/sh
# mail acceptance test runner.
set -eu
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
export AIOS_MAIL_FILE="$WORK/mail.json"
FIXTURE="$WORK/mail.mbox"
cat > "$FIXTURE" <<'EOF'
From alice@example.com  Mon Oct 19 09:00:00 2026
From: alice@example.com
To: you@ai-os.local
Subject: Welcome to AI_OS

Hello from the acceptance fixture.

From bob@example.com  Mon Oct 19 10:00:00 2026
From: bob@example.com
To: you@ai-os.local
Subject: Lunch?

Are you free at noon?

From carol@example.com  Mon Oct 19 11:00:00 2026
From: carol@example.com
To: you@ai-os.local
Subject: Report attached

See the attached quarterly numbers.
EOF

# 1. Import: three messages land in INBOX.
OUT=$(/ai/bin/mail import "$FIXTURE")
[ "$OUT" = "imported 3 message(s) into INBOX" ] || { echo "import failed: $OUT"; exit 1; }

# 2. Stats: 3 unread / 3 total.
OUT=$(/ai/bin/mail stats)
[ "$OUT" = "INBOX: 3 unread / 3 total" ] || { echo "stats failed: $OUT"; exit 1; }

# 3. List shows all three INBOX messages, all unread (U flags).
LIST=$(/ai/bin/mail list)
echo "$LIST" | grep -q "alice@example.com" || { echo "list missing alice"; exit 1; }
echo "$LIST" | grep -q "Welcome to AI_OS" || { echo "list missing subject"; exit 1; }
[ "$(echo "$LIST" | grep -c '  \[U\]  INBOX')" = "3" ] || { echo "list count failed"; exit 1; }

# 4. Show message 1: full headers and body.
SHOW=$(/ai/bin/mail show 1)
echo "$SHOW" | grep -q "From:    alice@example.com" || { echo "show From failed"; exit 1; }
echo "$SHOW" | grep -q "Subject: Welcome to AI_OS" || { echo "show Subject failed"; exit 1; }
echo "$SHOW" | grep -q "Hello from the acceptance fixture." || { echo "show body failed"; exit 1; }

# 5. Read/unread round-trip.
OUT=$(/ai/bin/mail read 1)
[ "$OUT" = "message 1 marked read" ] || { echo "read failed: $OUT"; exit 1; }
OUT=$(/ai/bin/mail stats)
[ "$OUT" = "INBOX: 2 unread / 3 total" ] || { echo "stats after read failed: $OUT"; exit 1; }
OUT=$(/ai/bin/mail unread 1)
[ "$OUT" = "message 1 marked unread" ] || { echo "unread failed: $OUT"; exit 1; }
OUT=$(/ai/bin/mail stats)
[ "$OUT" = "INBOX: 3 unread / 3 total" ] || { echo "stats after unread failed: $OUT"; exit 1; }

# 6. Folders.
OUT=$(/ai/bin/mail folders)
echo "$OUT" | grep -q "INBOX" || { echo "folders missing INBOX"; exit 1; }

# 7. Search finds by body and by subject.
OUT=$(/ai/bin/mail search "quarterly")
echo "$OUT" | grep -q "Report attached" || { echo "search body failed"; exit 1; }
OUT=$(/ai/bin/mail search "lunch")
echo "$OUT" | grep -q "bob@example.com" || { echo "search subject failed"; exit 1; }
OUT=$(/ai/bin/mail search "zzz-no-match")
echo "$OUT" | grep -q -- "-- 0 match(es)" || { echo "search no-match failed"; exit 1; }

# 8. Compose goes to Outbox and does not disturb INBOX counts.
OUT=$(/ai/bin/mail compose "dave@example.com" "Ping" "Just checking in.")
echo "$OUT" | grep -q "queued message 4 in Outbox" || { echo "compose failed: $OUT"; exit 1; }
OUT=$(/ai/bin/mail stats)
[ "$OUT" = "INBOX: 3 unread / 3 total" ] || { echo "stats after compose failed: $OUT"; exit 1; }
OUT=$(/ai/bin/mail list --folder Outbox)
echo "$OUT" | grep -q "Ping" || { echo "outbox list failed"; exit 1; }
OUT=$(/ai/bin/mail folders)
echo "$OUT" | grep -q "Outbox" || { echo "folders missing Outbox"; exit 1; }

# 9. Delete removes the message.
OUT=$(/ai/bin/mail delete 4)
[ "$OUT" = "deleted message 4" ] || { echo "delete failed: $OUT"; exit 1; }
if /ai/bin/mail show 4 >/dev/null 2>&1; then
    echo "show of deleted message should have failed"
    exit 1
fi

# 10. Unknown id fails with nonzero exit.
if /ai/bin/mail show 999 >/dev/null 2>&1; then
    echo "show of unknown id should have failed"
    exit 1
fi

rm -f "$AIOS_MAIL_FILE" "$FIXTURE"
echo "MAIL_ALL_PASS"
