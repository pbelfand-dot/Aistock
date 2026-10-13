"""Google Classroom on the Today screen: signing in once (in your own browser), reading your classes, assignments
and turned-in state, today's calendar, and saying plainly when your school blocks it. Google is pretend here."""
import base64
import hashlib
import io
import json
import os
import stat
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from aitrader import app_api, google_school, school
from aitrader.config import data_path

NY = ZoneInfo("America/New_York")
# made-up keys, put together at run time so they never look like real ones in the code
CLIENT_ID = "123456789012-" + "k" * 32 + ".apps.googleusercontent.com"
SECRET = "GOCSPX" + "-" + "s" * 28


def id_token(email):
    part = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{part({'alg': 'RS256'})}.{part({'email': email})}.signature"


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeGoogle:
    """Answers like Google's sign-in server, Classroom and Calendar. routes: {url prefix: body, or (code, body)}."""
    def __init__(self):
        self.calls, self.routes = [], {}

    def __call__(self, request, timeout=None):
        url = request.full_url
        self.calls.append((request.get_method(), url, request.data.decode() if request.data else "",
                           request.get_header("Authorization")))
        for prefix in sorted(self.routes, key=len, reverse=True):
            if url.startswith(prefix):
                answer = self.routes[prefix]
                code, body = answer if isinstance(answer, tuple) else (200, answer)
                if code >= 400:
                    raise urllib.error.HTTPError(url, code, "error", {}, io.BytesIO(json.dumps(body).encode()))
                return Resp(json.dumps(body).encode())
        raise AssertionError(f"unexpected call to {url}")


@pytest.fixture
def google(cfg, monkeypatch):
    cfg["secrets"].update(google_client_id=CLIENT_ID, google_client_secret=SECRET)
    fake = FakeGoogle()
    fake.routes[google_school.TOKEN_URL] = {"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3599,
                                            "id_token": id_token("paul@school.org"), "scope": " ".join(google_school.SCOPES)}
    monkeypatch.setattr(google_school, "urlopen", fake)
    return fake


def classroom(fake, today=date(2026, 10, 13)):
    C = google_school.CLASSROOM
    fake.routes[f"{C}/courses?"] = {"courses": [
        {"id": "111", "name": "AP US History", "section": "Period 2", "alternateLink": "https://classroom.google.com/c/111"},
        {"id": "222", "name": "Chemistry", "alternateLink": "https://classroom.google.com/c/222"}]}
    fake.routes[f"{C}/courses/111/courseWork?"] = {"courseWork": [
        # due Friday 11:59pm New York time = Saturday 03:59 in UTC (Classroom gives UTC)
        {"id": "w1", "title": "Unit 3 Progress Check: MCQ", "dueDate": {"year": 2026, "month": 10, "day": 17},
         "dueTime": {"hours": 3, "minutes": 59}, "alternateLink": "https://classroom.google.com/w1",
         "creationTime": "2026-10-10T12:00:00Z"},
        {"id": "w2", "title": "DBQ outline", "dueDate": {"year": 2026, "month": 10, "day": 9},
         "dueTime": {"hours": 3, "minutes": 59}, "creationTime": "2026-10-01T12:00:00Z"},
        {"id": "w3", "title": "Chapter 4 reading", "dueDate": {"year": 2026, "month": 10, "day": 12},
         "dueTime": {"hours": 3, "minutes": 59}, "creationTime": "2026-10-05T12:00:00Z"},
        {"id": "w4", "title": "Unit 1 essay", "dueDate": {"year": 2026, "month": 8, "day": 20},
         "dueTime": {"hours": 3, "minutes": 59}, "creationTime": "2026-08-10T12:00:00Z"}]}
    fake.routes[f"{C}/courses/111/courseWork/-/studentSubmissions?"] = {"studentSubmissions": [
        {"courseWorkId": "w1", "state": "CREATED", "alternateLink": "https://classroom.google.com/s1"},
        {"courseWorkId": "w2", "state": "CREATED", "late": True},                        # missing
        {"courseWorkId": "w3", "state": "TURNED_IN", "updateTime": "2026-10-12T20:00:00Z"},   # done yesterday
        {"courseWorkId": "w4", "state": "RETURNED", "updateTime": "2026-08-25T20:00:00Z"}]}   # long ago: off the list
    fake.routes[f"{C}/courses/222/courseWork?"] = (500, {"error": {"code": 500, "message": "Backend Error"}})
    fake.routes[f"{google_school.CALENDAR}/calendars/primary/events?"] = {"items": [
        {"summary": "Math test", "start": {"dateTime": "2026-10-13T09:30:00-04:00"}, "htmlLink": "https://cal/1"},
        {"summary": "Cancelled club", "status": "cancelled", "start": {"dateTime": "2026-10-13T15:00:00-04:00"}},
        {"summary": "School holiday", "start": {"date": "2026-10-13"}}]}


def test_the_client_id_and_secret_are_checked_before_saving(cfg, monkeypatch, tmp_path):
    assert google_school.valid_keys(f" {CLIENT_ID} ", SECRET) == (CLIENT_ID, SECRET)
    with pytest.raises(ValueError, match="apps.googleusercontent.com"):
        google_school.valid_keys("my-client", SECRET)
    with pytest.raises(ValueError, match="GOCSPX-"):
        google_school.valid_keys(CLIENT_ID, "short")
    env = tmp_path / ".env"
    monkeypatch.setattr(app_api, "env_file", lambda: env)
    out = app_api.handle("google-keys", cfg, payload={"client_id": CLIENT_ID, "client_secret": SECRET})
    assert "Sign in with Google" in out["message"]
    assert f"GOOGLE_CLIENT_ID={CLIENT_ID}" in env.read_text() and stat.S_IMODE(os.stat(env).st_mode) == 0o600


def test_the_sign_in_page_asks_only_for_read_only_classroom_and_calendar(cfg, google):
    url = google_school.start_login(cfg, now=datetime(2026, 10, 13, 8, 0), spawn=False)
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    login = json.loads(data_path(cfg, google_school.LOGIN_FILE).read_text())
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert q["redirect_uri"] == [f"http://127.0.0.1:{login['port']}"] and q["client_id"] == [CLIENT_ID]
    assert q["scope"][0].split() == ["openid", "email", "https://www.googleapis.com/auth/classroom.courses.readonly",
                                     "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
                                     "https://www.googleapis.com/auth/calendar.events.owned.readonly"]
    assert all("readonly" in s for s in q["scope"][0].split()[2:])                    # it can only read
    challenge = base64.urlsafe_b64encode(hashlib.sha256(login["verifier"].encode()).digest()).rstrip(b"=").decode()
    assert q["code_challenge"] == [challenge] and q["code_challenge_method"] == ["S256"]   # PKCE
    assert q["state"] == [login["state"]] and q["access_type"] == ["offline"]
    assert stat.S_IMODE(os.stat(data_path(cfg, google_school.LOGIN_FILE)).st_mode) == 0o600
    cfg["secrets"]["google_client_id"] = ""
    with pytest.raises(google_school.GoogleError, match="Client ID"):
        google_school.start_login(cfg, spawn=False)


def run_sign_in(cfg, query_for):
    """Starts a sign-in, runs the real helper, and comes back to it the way the browser does."""
    google_school.start_login(cfg, spawn=False)
    login = json.loads(data_path(cfg, google_school.LOGIN_FILE).read_text())
    ready = threading.Event()
    helper = threading.Thread(target=google_school.wait, args=(cfg, ready.set), daemon=True)
    helper.start()
    assert ready.wait(10)
    pages, browser = [], urllib.request.build_opener(urllib.request.ProxyHandler({}))    # straight to this Mac
    for query in query_for(login):
        with browser.open(f"{login['redirect']}/?{urllib.parse.urlencode(query)}", timeout=10) as r:
            pages.append(r.read().decode())
    helper.join(15)
    assert not helper.is_alive()
    return login, pages


def test_signing_in_once_saves_a_key_and_reads_classroom(cfg, google):
    classroom(google)
    login, pages = run_sign_in(cfg, lambda login: [{"code": "the-code", "state": "someone-else"},   # not ours: ignored
                                                   {"code": "the-code", "state": login["state"]}])
    assert "doesn't match" in pages[0] and "Kestrel is connected to Google Classroom" in pages[1]
    method, url, form, _ = next(c for c in google.calls if c[1] == google_school.TOKEN_URL)
    sent = urllib.parse.parse_qs(form)
    assert sent["code"] == ["the-code"] and sent["code_verifier"] == [login["verifier"]]
    assert sent["redirect_uri"] == [login["redirect"]] and sent["grant_type"] == ["authorization_code"]
    token_file = data_path(cfg, google_school.TOKEN_FILE)
    token = json.loads(token_file.read_text())
    assert token["refresh_token"] == "rt-1" and token["email"] == "paul@school.org"
    assert stat.S_IMODE(os.stat(token_file).st_mode) == 0o600                         # this Mac's user only
    status = google_school.status(cfg)
    assert status["signed_in"] and status["login"]["status"] == "connected" and status["classes"] == 2
    assert status["problems"] == ["Chemistry: Google said 500: Backend Error"]          # one class failing isn't all
    assert any(c[3] == "Bearer at-1" for c in google.calls if "classroom.googleapis.com" in c[1])


def test_classroom_work_shows_with_its_own_due_time_turned_in_and_missing_state(cfg, google):
    classroom(google)
    run_sign_in(cfg, lambda login: [{"code": "c", "state": login["state"]}])
    cache = google_school.refresh(cfg, now=datetime(2026, 10, 13, 7, 30, tzinfo=NY))
    by_id = {i["id"].split("-")[-1]: i for i in cache["items"]}
    assert set(by_id) == {"w1", "w2", "w3"}                                             # w4: finished in August
    w1 = by_id["w1"]
    assert (w1["due"], w1["due_time"], w1["ap"], w1["course"]) == ("2026-10-16", "11:59pm", True, "AP US History")
    assert w1["link"] == "https://classroom.google.com/s1" and w1["source"] == "classroom" and not w1["done"]
    assert by_id["w2"]["status"] == "missing" and by_id["w3"]["status"] == "turned in" and by_id["w3"]["done"]
    assert cache["events"]["items"] == [{"title": "Math test", "time": "9:30am", "location": "", "link": "https://cal/1"},
                                        {"title": "School holiday", "time": "all day", "location": "", "link": ""}]
    s = school.summary(cfg, date(2026, 10, 13))
    g = {k: [r["title"] for r in rows] for k, rows in s["groups"].items()}
    assert g["overdue"] == ["DBQ outline"] and g["week"] == ["Unit 3 Progress Check: MCQ"]
    assert g["done"] == ["Chapter 4 reading"] and s["missing"] == 1 and s["ap_open"] == 2
    assert [e["title"] for e in s["events"]] == ["Math test", "School holiday"]
    assert school.summary(cfg, date(2026, 10, 14))["events"] == []                       # yesterday's calendar isn't today's


def test_a_school_that_blocks_outside_apps_gets_a_plain_answer(cfg, google):
    login, pages = run_sign_in(cfg, lambda login: [{"error": "admin_policy_enforced", "state": login["state"]}])
    assert "Your school doesn't allow outside apps" in pages[0]
    st = google_school.status(cfg)
    assert st["login"]["status"] == "error" and "Request access" in st["login"]["message"] and not st["signed_in"]
    # signed in, but the school turned the Classroom API off for students
    run_sign_in(cfg, lambda login: [{"code": "c", "state": login["state"]}])
    google.routes[f"{google_school.CLASSROOM}/courses?"] = (403, {"error": {
        "code": 403, "message": "@ClassroomApiDisabled The user is not permitted to access the Classroom API.",
        "status": "PERMISSION_DENIED"}})
    with pytest.raises(google_school.GoogleError) as e:
        google_school.refresh(cfg)
    assert e.value.kind == "school_blocked" and "turned off outside access" in str(e.value)
    assert "turned off outside access" in google_school.status(cfg)["error"]              # the Today screen can say so
    out = app_api.handle("school-refresh", cfg)
    assert out["ok"] is False and "turned off outside access" in out["message"]


def test_unticking_classroom_on_googles_page_is_explained(cfg, google):
    google.routes[google_school.TOKEN_URL] = {"access_token": "a", "refresh_token": "r", "expires_in": 3599,
                                              "scope": "openid email " + google_school.CALENDAR_SCOPE}
    _, pages = run_sign_in(cfg, lambda login: [{"code": "c", "state": login["state"]}])
    assert "didn't share your classes" in pages[0] and google_school.status(cfg)["login"]["status"] == "error"


def test_the_key_is_renewed_and_a_cancelled_one_signs_out_cleanly(cfg, google):
    run_sign_in(cfg, lambda login: [{"code": "c", "state": login["state"]}])
    later = datetime.now() + timedelta(hours=2)
    google.routes[google_school.TOKEN_URL] = {"access_token": "at-2", "expires_in": 3599}       # no new refresh token
    assert google_school.access_token(cfg, later) == "at-2"
    assert json.loads(data_path(cfg, google_school.TOKEN_FILE).read_text())["refresh_token"] == "rt-1"   # kept
    google.routes[google_school.TOKEN_URL] = (400, {"error": "invalid_grant", "error_description": "Token has been expired or revoked."})
    with pytest.raises(google_school.GoogleError) as e:
        google_school.access_token(cfg, later + timedelta(hours=2))
    assert e.value.kind == "signed_out" and "Sign in again" in str(e.value)
    assert not google_school.signed_in(cfg)


def test_signing_out_cancels_the_key_at_google_and_forgets_everything(cfg, google):
    classroom(google)
    run_sign_in(cfg, lambda login: [{"code": "c", "state": login["state"]}])
    google.routes[google_school.REVOKE_URL] = {}
    assert "cancel" in app_api.handle("google-signout", cfg)["message"]
    assert ("POST", google_school.REVOKE_URL, "token=rt-1", None) in google.calls
    assert not any(data_path(cfg, f).exists() for f in (google_school.TOKEN_FILE, google_school.CACHE_FILE))
    assert school.summary(cfg)["groups"]["week"] == []


def test_an_unanswered_sign_in_expires_with_a_hint(cfg, google):
    google_school.start_login(cfg, now=datetime.now() - timedelta(minutes=10), spawn=False)
    st = google_school.login_status(cfg)
    assert st["status"] == "expired" and "Sign in with Google again" in st["message"]
    assert app_api.handle("google-status", cfg)["login"]["status"] == "expired"


def test_due_times_without_a_time_keep_their_date():
    assert google_school.due_local({"dueDate": {"year": 2026, "month": 10, "day": 17}}, NY) == (date(2026, 10, 17), "")
    assert google_school.due_local({}, NY) == (None, "")
    utc_noon = {"dueDate": {"year": 2026, "month": 10, "day": 17}, "dueTime": {"hours": 16}}
    assert google_school.due_local(utc_noon, NY) == (date(2026, 10, 17), "12:00pm")


def test_setup_and_the_phone_see_the_google_sign_in(cfg, google):
    from aitrader import phone_screen
    status = app_api.handle("setup-status", cfg)["google"]
    assert status["keys"] and not status["signed_in"] and status["login"]["status"] is None
    assert "school-refresh" in phone_screen.ALLOWED and "google-login" not in phone_screen.ALLOWED   # sign-in: Mac only
    assert {"google-keys", "google-login", "google-status", "google-signout", "school-refresh"} <= set(app_api.ACTIONS)
