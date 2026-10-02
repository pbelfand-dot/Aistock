"""
pushover.py: Kestrel's alerts as push notifications through Pushover (pushover.net), alongside or
instead of Telegram (phone.py). One-way: Pushover delivers alerts; commands stay on Telegram.

What you need (Setup -> Your phone -> Pushover):
  User Key    on your Pushover dashboard after you sign up (pushover.net), 30 letters and digits
  API Token   from "Create an Application/API Token" (pushover.net/apps/build), name it Kestrel
The Pushover app is free for 30 days, then a one-time $4.99 per platform (iPhone/iPad, Android,
Desktop). Sending is free up to 10,000 messages a month.

How loud each alert is (Pushover's priorities):
   2  emergency  a real-money kill switch or emergency stop: repeats every minute until you open it
   1  high       anything urgent (!!!, kill switch, emergency, a pause): sounds even in quiet hours
   0  normal     every buy and sell, the after-market report
  -1  quiet      everything else it forwards (daily results, lessons learned): no sound

It keeps count of what it sent each month, and near the 10,000 limit it only sends urgent alerts. A
failed send never stops trading. The keys live in ~/AITrader/.env, readable only by you.
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from .config import data_path

API = "https://api.pushover.net/1"
KEY_PATTERN = r"[A-Za-z0-9]{30}"
MAX_MESSAGE, MAX_TITLE, MAX_URL = 1024, 250, 512       # Pushover's limits
MONTHLY_LIMIT = 10_000
URGENT_ONLY_AFTER = 9_500                               # keep the last 500 of the month for urgent alerts
COUNT_FILE = "pushover_count.json"


def has_keys(cfg) -> bool:
    s = cfg["secrets"]
    return bool(s.get("pushover_user") and s.get("pushover_token"))


def call(cfg, endpoint: str, wait: float = 20, **fields) -> dict:
    """One Pushover API call (form fields, as Pushover's API wants). Raises with Pushover's own words."""
    s = cfg["secrets"]
    data = urllib.parse.urlencode({"token": s.get("pushover_token", ""), "user": s.get("pushover_user", ""),
                                   **{k: v for k, v in fields.items() if v is not None}}).encode()
    request = urllib.request.Request(f"{API}/{endpoint}.json", data=data, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=wait) as resp:
            answer = json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:                 # 4xx: Pushover refused it (don't retry the same thing)
        try:
            answer = json.loads(e.read() or b"{}")
        except ValueError:
            answer = {}
        raise RuntimeError("; ".join(answer.get("errors") or []) or f"Pushover said no (HTTP {e.code})") from None
    if answer.get("status") != 1:
        raise RuntimeError("; ".join(answer.get("errors") or []) or "Pushover said no")
    return answer


def validate(cfg) -> dict:
    """Checks the User Key and API Token with Pushover; the answer lists your devices."""
    return call(cfg, "users/validate")


# ---------------------------------------------------------------- the monthly count
def _count(cfg) -> dict:
    path = data_path(cfg, COUNT_FILE)
    month = datetime.now().strftime("%Y-%m")
    try:
        saved = json.loads(path.read_text()) if path.exists() else {}
    except ValueError:
        saved = {}
    return saved if saved.get("month") == month else {"month": month, "sent": 0}


def sent_this_month(cfg) -> int:
    return _count(cfg)["sent"]


def _add_one(cfg):
    state = _count(cfg)
    state["sent"] += 1
    path = data_path(cfg, COUNT_FILE)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(path)


# ---------------------------------------------------------------- sending
def priority_of(message: str) -> int:
    urgent = any(m in message for m in ("!!!", "KILL SWITCH", "EMERGENCY", "PAUSED by"))
    if urgent and "[live-" in message and any(m in message for m in ("KILL SWITCH", "EMERGENCY")):
        return 2
    if urgent:
        return 1
    if any(m in message for m in ("] BUY ", "] SELL ", "PHASE CHANGE", "WARNING:", "CHALLENGER ")) or \
            message.startswith("After-market report"):
        return 0
    return -1


def send(cfg, message: str, title: str = "Kestrel", priority: int = None, url: str = None,
         url_title: str = None) -> bool:
    """Sends one push notification. Never raises: a phone alert must never stop trading."""
    if not has_keys(cfg) or not message.strip():
        return False
    priority = priority_of(message) if priority is None else priority
    if sent_this_month(cfg) >= URGENT_ONLY_AFTER and priority < 1:
        return False                                    # near the monthly limit: urgent alerts only
    fields = {"message": message[:MAX_MESSAGE], "title": title[:MAX_TITLE], "priority": priority}
    if priority == 2:
        fields.update(retry=60, expire=3600)            # every minute, for up to an hour, until you open it
    if url:
        fields.update(url=url[:MAX_URL], url_title=(url_title or "Open")[:100])
    try:
        call(cfg, "messages", **fields)
    except Exception:
        return False
    _add_one(cfg)
    return True


_queue = None


def send_later(cfg, message: str, **kw):
    """Queues the alert for a background sender (in order), so trading never waits on Pushover."""
    import queue
    import threading
    global _queue
    if _queue is None:
        _queue = queue.Queue()

        def work():
            while True:
                args, kwargs = _queue.get()
                send(*args, **kwargs)
        threading.Thread(target=work, daemon=True, name="pushover").start()
    _queue.put(((cfg, message), kw))


def report_alert(cfg, day: str) -> str:
    """The after-market report squeezed into one notification: its plain-English summary when the local
    AI wrote one, otherwise the first lines (the full report is in the app, and on Telegram)."""
    path = data_path(cfg, f"reports/after-market-{day}.md")
    if not path.exists():
        return ""
    text = path.read_text()
    match = re.search(r"## In plain English\n\n(.+?)(\n## |\Z)", text, re.S)
    body = match.group(1).strip() if match else "\n".join(
        line for line in text.splitlines()[1:] if line.strip() and not line.startswith("#"))
    return body[:MAX_MESSAGE]
