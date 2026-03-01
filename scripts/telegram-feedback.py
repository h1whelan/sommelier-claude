#!/usr/bin/env python3
"""
telegram-feedback.py — Poll Telegram for wine feedback messages from Henry.

Runs on a cron (every 15 min). Checks for messages starting with "/wine" or
"wine feedback" and saves them to the feedback/ directory.

Usage:
    python3 scripts/telegram-feedback.py          # poll and save
    python3 scripts/telegram-feedback.py --check   # show pending feedback without saving

Messages from Henry like:
    /wine The Barolo was excellent, really opened up after 2 hours
    /wine March picks: loved the Rioja, the white was too acidic

Get saved to feedback/YYYY-MM.md (appended if the file already exists).
"""

import json
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).parent.parent
FEEDBACK_DIR = PROJECT / "feedback"
STATE_FILE = PROJECT / ".telegram-feedback-offset"
TRIGGER_PREFIXES = ["/wine ", "/wine\n", "wine feedback"]

# Reuse clawdbot's Telegram credentials
CONFIG = Path.home() / ".clawdbot" / "clawdbot.json"
ALLOW_FROM = Path.home() / ".clawdbot" / "credentials" / "telegram-allowFrom.json"


def load_bot_token():
    with open(CONFIG) as f:
        data = json.load(f)
    return data["channels"]["telegram"]["botToken"]


def load_allowed_users():
    with open(ALLOW_FROM) as f:
        data = json.load(f)
    return set(data["allowFrom"])


def get_last_offset():
    if STATE_FILE.exists():
        return int(STATE_FILE.read_text().strip())
    return 0


def save_offset(offset):
    STATE_FILE.write_text(str(offset))


def get_updates(token, offset=0):
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = f"?timeout=5&allowed_updates=[\"message\"]"
    if offset:
        params += f"&offset={offset}"

    req = urllib.request.Request(url + params)
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        if data.get("ok"):
            return data.get("result", [])
    except Exception as e:
        print(f"Error polling Telegram: {e}", file=sys.stderr)
    return []


def is_wine_feedback(text):
    lower = text.lower().strip()
    for prefix in TRIGGER_PREFIXES:
        if lower.startswith(prefix):
            return True
    return False


def extract_feedback(text):
    """Remove the trigger prefix and return the feedback content."""
    lower = text.lower().strip()
    for prefix in TRIGGER_PREFIXES:
        if lower.startswith(prefix):
            return text[len(prefix):].strip()
    return text.strip()


def save_feedback(feedback_text, timestamp):
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    dt = datetime.fromtimestamp(timestamp)
    month_file = FEEDBACK_DIR / f"{dt.strftime('%Y-%m')}.md"

    entry = f"\n### {dt.strftime('%Y-%m-%d %H:%M')}\n\n{feedback_text}\n"

    if month_file.exists():
        with open(month_file, "a") as f:
            f.write(entry)
    else:
        with open(month_file, "w") as f:
            f.write(f"# Wine Feedback — {dt.strftime('%B %Y')}\n")
            f.write(entry)

    print(f"  Saved to {month_file}")


def send_confirmation(token, chat_id, feedback_text):
    """Send a confirmation reply."""
    preview = feedback_text[:100] + ("..." if len(feedback_text) > 100 else "")
    msg = f"Noted! Your feedback has been saved and will be reviewed next month.\n\n_{preview}_"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "Markdown",
    }).encode()

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"  Warning: couldn't send confirmation: {e}", file=sys.stderr)


def main():
    check_only = "--check" in sys.argv

    token = load_bot_token()
    allowed = load_allowed_users()
    offset = get_last_offset()

    print(f"Polling from offset {offset}...")
    updates = get_updates(token, offset)

    if not updates:
        print("No new messages")
        return

    feedback_count = 0
    max_update_id = offset

    for update in updates:
        update_id = update["update_id"]
        max_update_id = max(max_update_id, update_id)

        msg = update.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        user_id = str(msg.get("from", {}).get("id", ""))
        text = msg.get("text", "")
        timestamp = msg.get("date", int(time.time()))

        # Only process messages from Henry
        if user_id not in allowed:
            continue

        if not text or not is_wine_feedback(text):
            continue

        feedback = extract_feedback(text)
        if not feedback:
            continue

        dt = datetime.fromtimestamp(timestamp)
        print(f"\nFeedback ({dt.strftime('%Y-%m-%d %H:%M')}):")
        print(f"  {feedback}")

        if not check_only:
            save_feedback(feedback, timestamp)
            send_confirmation(token, chat_id, feedback)
            feedback_count += 1

    # Save offset (update_id + 1 to mark as processed)
    if not check_only and max_update_id > offset:
        save_offset(max_update_id + 1)

    print(f"\nProcessed {feedback_count} feedback message(s)")


if __name__ == "__main__":
    main()
