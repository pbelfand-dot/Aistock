"""
google_school.py: your Google Classroom and today's calendar on the Today screen (docs/DASHBOARD-PLAN.md, step 2).

You sign in ONCE, with Google, in your own browser (Safari or Chrome). Kestrel never sees your password, and it
can't sign you in inside its own window: Google blocks sign-ins in apps' built-in browsers. Google then gives
Kestrel a key that can only READ these things (saved on this Mac only, data/google_token.json), and Kestrel
checks Classroom by itself from then on. Sign out in Setup → School; that also tells Google to cancel the key.

What it may read (Google's read-only permissions, nothing else):
  classroom.courses.readonly         your active classes
  classroom.coursework.me.readonly   their assignments and due dates, and whether you turned each one in
  calendar.events.owned.readonly     today's events on your own calendar
  openid, email                      which account signed in

How the sign-in works: a "Desktop app" OAuth client from your own free Google Cloud project (Setup → School has
the steps), with Google's loopback flow and PKCE (RFC 8252): the browser comes back to http://127.0.0.1:<port>,
which only this Mac can reach, where a small helper waits up to 5 minutes for it.

If your school blocks it, Google shows "Access blocked" (admin_policy_enforced) in the browser: school accounts
of students under 18 can't use apps the school hasn't approved (support.google.com/a/answer/13288950). Then it's
the "Request access" button there, your school's IT, or the quick-add list.
"""
import base64
import hashlib
import html
import http.server
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

from .config import ROOT, data_path

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
CLASSROOM = "https://classroom.googleapis.com/v1"
CALENDAR = "https://www.googleapis.com/calendar/v3"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events.owned.readonly"
SCOPES = ["openid", "email",
          "https://www.googleapis.com/auth/classroom.courses.readonly",
          "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
          CALENDAR_SCOPE]
TOKEN_FILE, LOGIN_FILE, CACHE_FILE = "google_token.json", "google_login.json", "classroom.json"
CLIENT_ID_PATTERN = r"\d{5,}-[a-z0-9]{8,}\.apps\.googleusercontent\.com"
SECRET_PATTERN = r"[A-Za-z0-9_-]{20,80}"
LOGIN_MINUTES = 5                    # how long the helper waits for the browser to come back
STALE_MINUTES = 15                   # the Today screen asks for fresh Classroom data after this
KEEP_DAYS_BACK, KEEP_DAYS_AHEAD = 21, 60
TIMEOUT = 20
urlopen = urllib.request.urlopen     # tests replace this


class GoogleError(Exception):
    """A problem with Google, in plain words. kind: signed_out, school_blocked, api_off, offline or other."""
    def __init__(self, message: str, kind: str = "other"):
        super().__init__(message)
        self.kind = kind


# ------------------------------------------------------------------ files (this Mac only)
def _path(cfg, name):
    return data_path(cfg, name)


def _read(path) -> dict:
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except (OSError, ValueError):
        return {}


def _write_private(path, data: dict):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def has_keys(cfg) -> bool:
    s = cfg.get("secrets") or {}
    return bool(s.get("google_client_id") and s.get("google_client_secret"))


def load_token(cfg) -> dict:
    return _read(_path(cfg, TOKEN_FILE))


def signed_in(cfg) -> bool:
    return bool(load_token(cfg).get("refresh_token"))


def load_cache(cfg) -> dict:
    return _read(_path(cfg, CACHE_FILE))


# ------------------------------------------------------------------ talking to Google
def _explain(code: int, text: str) -> GoogleError:
    try:
        body = json.loads(text)
    except ValueError:
        body = {}
    err = body.get("error")
    if isinstance(err, str):                                   # the sign-in server: {"error": "invalid_grant", ...}
        if err == "invalid_grant":
            return GoogleError("Google signed Kestrel out (the sign-in expired or was cancelled). Sign in again in "
                               "Setup → School.", "signed_out")
        if err in ("invalid_client", "unauthorized_client"):
            return GoogleError("Google didn't accept the Client ID and secret. Copy both again from your Google Cloud "
                               "project (Clients → your Desktop client).", "other")
        return GoogleError(f"Google said: {body.get('error_description') or err}", "other")
    err = err or {}
    message = str(err.get("message") or text[:200])
    if "ClassroomApiDisabled" in text or "not permitted to access the Classroom API" in text:
        return GoogleError("Your school has turned off outside access to Classroom for your account. Ask your "
                           "school's IT, or keep using quick add.", "school_blocked")
    if "SERVICE_DISABLED" in text or "accessNotConfigured" in text or "has not been used in project" in text:
        which = "Calendar" if "calendar" in text.lower() else "Classroom"
        return GoogleError(f"The Google {which} API isn't switched on in your Google Cloud project: APIs & Services "
                           f"→ Library → Google {which} API → Enable. Then press Refresh.", "api_off")
    if code == 401:
        return GoogleError("Google didn't accept Kestrel's key. Sign in again in Setup → School.", "signed_out")
    if code == 403 and "insufficient" in text.lower():
        return GoogleError("Google didn't give Kestrel permission for this. Sign in again and allow everything on "
                           "Google's page.", "signed_out")
    return GoogleError(f"Google said {code}: {message}", "other")


def _http(url: str, form: dict = None, token: str = None) -> dict:
    """JSON from Google. form: fields to POST (the sign-in server); otherwise a GET with the access token."""
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    request = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
    request.add_header("Accept", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urlopen(request, timeout=TIMEOUT) as resp:
            text = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise _explain(e.code, e.read().decode("utf-8", "replace")) from None
    except (urllib.error.URLError, OSError) as e:
        raise GoogleError(f"Couldn't reach Google ({getattr(e, 'reason', e)}). Is the Mac online?", "offline") from None
    return json.loads(text) if text.strip() else {}


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _email_in(id_token: str) -> str:
    """The signed-in account, from the ID token Google's own server just sent (over TLS: read, not re-checked)."""
    try:
        part = id_token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))).get("email", "")
    except (IndexError, ValueError, AttributeError):
        return ""


def _save_token(cfg, answer: dict, now: datetime) -> dict:
    old = load_token(cfg)
    token = {"access_token": answer.get("access_token", ""),
             "refresh_token": answer.get("refresh_token") or old.get("refresh_token", ""),
             "expires_at": (now + timedelta(seconds=int(answer.get("expires_in") or 3600) - 60)).isoformat(),
             "scope": answer.get("scope") or old.get("scope", ""),
             "email": _email_in(answer.get("id_token", "")) or old.get("email", ""),
             "signed_in": old.get("signed_in") or now.isoformat(timespec="seconds")}
    _write_private(_path(cfg, TOKEN_FILE), token)
    return token


def access_token(cfg, now: datetime = None) -> str:
    """A working access token: the saved one, or a fresh one from the refresh token (they last an hour)."""
    now = now or datetime.now()
    token = load_token(cfg)
    if not token.get("refresh_token"):
        raise GoogleError("Not signed in to Google yet (Setup → School).", "signed_out")
    if token.get("access_token") and datetime.fromisoformat(token["expires_at"]) > now:
        return token["access_token"]
    s = cfg["secrets"]
    try:
        answer = _http(TOKEN_URL, {"client_id": s.get("google_client_id", ""), "client_secret": s.get("google_client_secret", ""),
                                   "refresh_token": token["refresh_token"], "grant_type": "refresh_token"})
    except GoogleError as e:
        if e.kind == "signed_out":
            _path(cfg, TOKEN_FILE).unlink(missing_ok=True)
        raise
    return _save_token(cfg, answer, now)["access_token"]


# ------------------------------------------------------------------ signing in (once)
def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_login(cfg, now: datetime = None, spawn: bool = True) -> str:
    """Begins a sign-in: the address of Google's page to open in your browser. A helper process waits for the
    browser to come back (wait()); the Setup screen follows along with login_status()."""
    if not has_keys(cfg):
        raise GoogleError("Paste your Google Client ID and Client secret first (Setup → School).")
    now = now or datetime.now()
    verifier = _b64(secrets.token_bytes(48))
    state, port = secrets.token_urlsafe(24), _free_port()
    login = {"status": "waiting", "state": state, "verifier": verifier, "port": port,
             "redirect": f"http://127.0.0.1:{port}", "started": now.isoformat(timespec="seconds"),
             "until": (now + timedelta(minutes=LOGIN_MINUTES)).isoformat(timespec="seconds")}
    _write_private(_path(cfg, LOGIN_FILE), login)
    if spawn:
        log = open(_path(cfg, "google_login.log"), "a")
        subprocess.Popen([sys.executable, "-m", "aitrader.google_school", "wait"], cwd=str(ROOT), start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log)
    params = {"client_id": cfg["secrets"]["google_client_id"], "redirect_uri": login["redirect"], "response_type": "code",
              "scope": " ".join(SCOPES), "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()),
              "code_challenge_method": "S256", "state": state, "access_type": "offline", "prompt": "consent"}
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


ERRORS = {
    "access_denied": "You (or Google) said no on Google's page, so nothing was shared. Press Sign in with Google to try "
                     "again. If Google said the app is only for testers, add your school email as a Test user in your "
                     "Google Cloud project (Google Auth Platform → Audience), or publish the app there.",
    "admin_policy_enforced": "Your school doesn't allow outside apps for your account, so Google blocked the sign-in. "
                             "Use \"Request access\" on Google's page if it offers it, or ask your school's IT. Quick add "
                             "keeps working meanwhile.",
}


def _page(title: str, text: str, ok: bool) -> bytes:
    color = "#0b7a0b" if ok else "#b42318"
    return (f"<!doctype html><meta charset='utf-8'><title>Kestrel</title><body style='font:16px/1.5 -apple-system,"
            f"system-ui,sans-serif;max-width:560px;margin:12vh auto;padding:0 20px'><h2 style='color:{color}'>"
            f"{html.escape(title, quote=False)}</h2><p>{html.escape(text, quote=False)}</p><p style='color:#666'>You can close this tab and go back "
            f"to Kestrel.</p></body>").encode()


def finish_login(cfg, query: dict, login: dict, now: datetime = None) -> tuple:
    """The browser came back with ?code=..&state=.. (or ?error=..). Returns (ok, the message) and writes the outcome."""
    now = now or datetime.now()
    state = (query.get("state") or [""])[0]
    if state != login.get("state"):
        return False, "This sign-in doesn't match the one Kestrel started. Press Sign in with Google again."
    error = (query.get("error") or [""])[0]
    if error:
        message = ERRORS.get(error, f"Google said: {error}.")
    else:
        try:
            s = cfg["secrets"]
            answer = _http(TOKEN_URL, {"code": (query.get("code") or [""])[0], "client_id": s["google_client_id"],
                                       "client_secret": s["google_client_secret"], "redirect_uri": login["redirect"],
                                       "grant_type": "authorization_code", "code_verifier": login["verifier"]})
            token = _save_token(cfg, answer, now)
            granted = set(str(token.get("scope", "")).split())
            missing = [scope for scope in SCOPES[2:4] if scope not in granted]
            if missing:
                message = ("Signed in, but Google's page didn't share your classes and assignments (a box was left "
                           "unticked). Press Sign in with Google again and allow both Classroom items.")
                _write_private(_path(cfg, LOGIN_FILE), {"status": "error", "message": message})
                return False, message
            message = f"Connected as {token.get('email') or 'your Google account'}."
            _write_private(_path(cfg, LOGIN_FILE), {"status": "connected", "message": message,
                                                    "at": now.isoformat(timespec="seconds")})
            return True, message
        except GoogleError as e:
            message = str(e)
    _write_private(_path(cfg, LOGIN_FILE), {"status": "error", "message": message, "error": error})
    return False, message


def wait(cfg, ready=None):
    """The helper: answers the browser's return to http://127.0.0.1:<port> (this Mac only), then reads Classroom
    once. Stops after LOGIN_MINUTES, or when a newer sign-in replaced this one."""
    login = _read(_path(cfg, LOGIN_FILE))
    if login.get("status") != "waiting":
        return
    until, done = datetime.fromisoformat(login["until"]), {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if not ({"code", "error"} & set(query)):
                self.send_response(404)
                self.end_headers()
                return
            ok, message = finish_login(cfg, query, login)
            if (query.get("state") or [""])[0] == login["state"]:    # anything else isn't Google's answer: keep waiting
                done["ok"] = ok
            body = _page("Kestrel is connected to Google Classroom" if ok else "Kestrel isn't connected", message, ok)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    try:
        server = http.server.HTTPServer(("127.0.0.1", int(login["port"])), Handler)
    except OSError as e:
        _write_private(_path(cfg, LOGIN_FILE), {"status": "error", "message": f"Kestrel couldn't wait for Google ({e}). "
                                                                             "Press Sign in with Google again."})
        return
    server.timeout = 1
    if ready:
        ready()
    try:
        while not done and datetime.now() < until:
            if _read(_path(cfg, LOGIN_FILE)).get("state") != login["state"]:
                return                                           # a newer sign-in took over
            server.handle_request()
    finally:
        server.server_close()
    if not done:
        _write_private(_path(cfg, LOGIN_FILE), {"status": "expired", "message": (
            "No answer from Google in 5 minutes. If Google said \"Access blocked\" or admin_policy_enforced, your "
            "school doesn't allow outside apps for your account. Otherwise press Sign in with Google again.")})
    elif done.get("ok"):
        try:
            refresh(cfg)
        except Exception:                                        # the Today screen shows a problem when it asks next
            pass


def login_status(cfg, now: datetime = None) -> dict:
    now = now or datetime.now()
    login = _read(_path(cfg, LOGIN_FILE))
    if login.get("status") == "waiting" and datetime.fromisoformat(login["until"]) < now - timedelta(seconds=30):
        login = {"status": "expired", "message": "No answer from Google in 5 minutes. Press Sign in with Google again."}
    return {k: login.get(k) for k in ("status", "message", "started")}


def sign_out(cfg) -> str:
    """Forgets the key here and asks Google to cancel it (Google's own list of your connected apps drops Kestrel)."""
    token = load_token(cfg)
    if token.get("refresh_token"):
        try:
            _http(REVOKE_URL, {"token": token["refresh_token"]})
        except GoogleError:
            pass
    for name in (TOKEN_FILE, CACHE_FILE, LOGIN_FILE):
        _path(cfg, name).unlink(missing_ok=True)
    return "Signed out of Google: Kestrel forgot its key and asked Google to cancel it."


# ------------------------------------------------------------------ reading Classroom and the calendar
def _list(url: str, params: dict, key: str, token: str, pages: int) -> list:
    out, params = [], dict(params)
    for _ in range(pages):
        answer = _http(f"{url}?{urllib.parse.urlencode(params)}", token=token)
        out += answer.get(key) or []
        if not answer.get("nextPageToken"):
            break
        params["pageToken"] = answer["nextPageToken"]
    return out


def _when(stamp: str, tz):
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).astimezone(tz)
    except (TypeError, ValueError):
        return None


def due_local(work: dict, tz) -> tuple:
    """(the due date, "11:59pm" or "") where you are. Classroom gives the due date and time in UTC."""
    d = work.get("dueDate")
    if not d or not d.get("year"):
        return None, ""
    t = work.get("dueTime")
    if not t:
        return date(d["year"], d["month"], d["day"]), ""
    utc = datetime(d["year"], d["month"], d["day"], tzinfo=timezone.utc) + timedelta(
        hours=t.get("hours", 0), minutes=t.get("minutes", 0))
    local = utc.astimezone(tz)
    return local.date(), local.strftime("%-I:%M%p").lower()


def classroom_item(course: dict, work: dict, submission: dict, today: date, tz):
    """One assignment for the Today list, or None when it's too old, far off, or finished long ago."""
    from .school import is_ap
    due, at = due_local(work, tz)
    sub = submission or {}
    state = sub.get("state") or ""
    done = state in ("TURNED_IN", "RETURNED")
    done_when = _when(sub.get("updateTime"), tz) if done else None
    if done and (done_when is None or done_when.date() < today - timedelta(days=3)):
        return None                                              # finished a while ago: off the list
    if due and not (today - timedelta(days=KEEP_DAYS_BACK) <= due <= today + timedelta(days=KEEP_DAYS_AHEAD)):
        return None
    created = _when(work.get("creationTime"), tz)
    if not due and not done and (created is None or created.date() < today - timedelta(days=KEEP_DAYS_BACK)):
        return None
    name = course.get("name") or ""
    status = ("turned in" if state == "TURNED_IN" else "returned" if state == "RETURNED"
              else "missing" if due and due < today else "")
    return {"id": f"gc-{course.get('id')}-{work.get('id')}", "title": work.get("title") or "(untitled)",
            "course": name, "due": due.isoformat() if due else None, "due_time": at,
            "ap": is_ap(f"{work.get('title', '')} {name}"), "done": done,
            "done_on": done_when.date().isoformat() if done_when else None,
            "added": work.get("creationTime") or "", "source": "classroom", "status": status, "late": bool(sub.get("late")),
            "link": sub.get("alternateLink") or work.get("alternateLink") or ""}


def today_events(token: str, now: datetime) -> list:
    """Today's events on your own calendar (cancelled ones and working-location markers left out)."""
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    params = {"timeMin": start.isoformat(), "timeMax": (start + timedelta(days=1)).isoformat(),
              "singleEvents": "true", "orderBy": "startTime", "maxResults": 25}
    items = _http(f"{CALENDAR}/calendars/primary/events?{urllib.parse.urlencode(params)}", token=token).get("items") or []
    out = []
    for e in items:
        if e.get("status") == "cancelled" or e.get("eventType") in ("workingLocation", "outOfOffice", "focusTime"):
            continue
        begin = (e.get("start") or {}).get("dateTime")
        when = _when(begin, now.tzinfo) if begin else None
        out.append({"title": e.get("summary") or "(busy)", "time": when.strftime("%-I:%M%p").lower() if when else "all day",
                    "location": e.get("location") or "", "link": e.get("htmlLink") or ""})
    return out


def refresh(cfg, now: datetime = None) -> dict:
    """Reads your active classes, their assignments and your submissions, and today's calendar, and saves them
    (data/classroom.json). A problem with one class doesn't stop the others; a problem with all of them (signed
    out, blocked, offline) is saved too, so the Today screen can say what's wrong."""
    now = now or datetime.now()
    now = now if now.tzinfo else now.astimezone()             # the Mac's own time zone, unless one was given
    try:
        return _refresh(cfg, now)
    except GoogleError as e:
        _write_private(_path(cfg, CACHE_FILE), {**load_cache(cfg), "error": str(e), "error_kind": e.kind,
                                                "tried": now.isoformat(timespec="seconds")})
        raise


def _refresh(cfg, now: datetime) -> dict:
    tz, today = now.tzinfo, now.date()
    token = access_token(cfg, now.replace(tzinfo=None))
    courses = _list(f"{CLASSROOM}/courses", {"studentId": "me", "courseStates": "ACTIVE", "pageSize": 50},
                    "courses", token, pages=3)
    items, problems = [], []
    for course in courses[:30]:
        cid = urllib.parse.quote(str(course.get("id")), safe="")
        try:
            work = _list(f"{CLASSROOM}/courses/{cid}/courseWork", {"orderBy": "updateTime desc", "pageSize": 50},
                         "courseWork", token, pages=2)
            subs = _list(f"{CLASSROOM}/courses/{cid}/courseWork/-/studentSubmissions", {"userId": "me", "pageSize": 100},
                         "studentSubmissions", token, pages=3)
        except GoogleError as e:
            if e.kind in ("signed_out", "school_blocked", "api_off", "offline"):
                raise
            problems.append(f"{course.get('name')}: {e}")
            continue
        mine = {s.get("courseWorkId"): s for s in subs}
        items += [i for w in work for i in [classroom_item(course, w, mine.get(w.get("id")), today, tz)] if i]
    events, calendar_error = [], ""
    if CALENDAR_SCOPE in str(load_token(cfg).get("scope", "")):
        try:
            events = today_events(token, now)
        except GoogleError as e:
            calendar_error = str(e)
    cache = {"updated": now.isoformat(timespec="seconds"), "email": load_token(cfg).get("email", ""),
             "courses": [{"id": c.get("id"), "name": c.get("name"), "section": c.get("section") or "",
                          "link": c.get("alternateLink") or ""} for c in courses],
             "items": items, "events": {"date": today.isoformat(), "items": events}, "calendar_error": calendar_error,
             "problems": problems, "error": "", "error_kind": ""}
    _write_private(_path(cfg, CACHE_FILE), cache)
    return cache


def status(cfg, now: datetime = None) -> dict:
    """For Setup and the Today screen: keys, sign-in, the last read and whether it's due for a fresh one."""
    now = now or datetime.now()
    token, cache = load_token(cfg), load_cache(cfg)
    updated = cache.get("updated")
    age = (now.astimezone() - datetime.fromisoformat(updated)).total_seconds() / 60 if updated else None
    return {"keys": has_keys(cfg), "signed_in": bool(token.get("refresh_token")), "email": token.get("email", ""),
            "login": login_status(cfg, now), "updated": updated, "minutes_ago": round(age) if age is not None else None,
            "stale": bool(token.get("refresh_token")) and (age is None or age >= STALE_MINUTES),
            "classes": len(cache.get("courses") or []), "error": cache.get("error", ""),
            "error_kind": cache.get("error_kind", ""), "problems": cache.get("problems") or [],
            "calendar_error": cache.get("calendar_error", "")}


def valid_keys(client_id: str, secret: str) -> tuple:
    client_id, secret = str(client_id or "").strip(), str(secret or "").strip()
    if not re.fullmatch(CLIENT_ID_PATTERN, client_id):
        raise ValueError("That Client ID doesn't look right: it ends with .apps.googleusercontent.com. Copy it from "
                         "your Google Cloud project (Google Auth Platform → Clients → your Desktop client).")
    if not re.fullmatch(SECRET_PATTERN, secret):
        raise ValueError("That Client secret doesn't look right (it usually starts with GOCSPX-). Copy it from the same "
                         "Desktop client.")
    return client_id, secret


if __name__ == "__main__":                                       # the sign-in helper (start_login starts it)
    if sys.argv[1:] == ["wait"]:
        from .config import load_config
        wait(load_config())
