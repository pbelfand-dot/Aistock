# Plan: Kestrel becomes your daily dashboard

Written Oct 13, 2026. Status: **step 1 is built** (the Today tab, homework quick add, AP Classroom button,
open at login); the rest is planned. Facts that came from the web have their source linked; where sources
disagreed, it says so.

**Step 2 (Google Classroom) is built too**, through Google's own sign-in (one account, needs a Google Cloud key).

**Update, Oct 13 evening: Kestrel's own browser.** The AP Classroom window signed in fine but found no assignments:
its reader only knew AP Classroom's older layouts. You asked for a browser like Claude's that keeps several accounts
signed in, saves passwords and signs in daily. Built (`mac/app/browser.swift`, `logins.swift`, `browser.js`,
`aitrader/school_web.py`):
- tabs, bookmarks, downloads and uploads; it tells pages it's Safari (it is Safari's engine), which is how
  WebKit-based browsers like Orion and DuckDuckGo's Mac browser sign in to Google;
- any number of accounts (Google's own "Add another account"), and saved passwords: sealed with AES-GCM in
  ~/Library/Application Support/Kestrel, with the key in the keychain. The bot (and Claude) never sees them;
- "Add to Today" on any page that lists your work; the chosen pages are re-read every 3 hours and after the Mac wakes,
  signing back in with the saved password when a site signed Kestrel out;
- a sturdier reader: the page's own data (JSON it downloaded), then its rows (tables, lists, cards), then its text,
  then the local AI (only titles that really are on the page count). "Copy what Kestrel saw" turns a page it can't
  read yet into text to paste to Claude, so the reader can learn it.

What could still go wrong, honestly:
- **Google may still refuse.** Its "This browser or app may not be secure" check looks at more than the browser's
  name, and Google changes it without notice. If it refuses, Google Classroom still works through Google's own
  sign-in (step 2), and AP Classroom doesn't need Google at all.
- **Signing back in stops at a phone code or a "verify it's you" check**: then Today says "Sign in", and you do it
  once in the browser. Google sessions usually last weeks; College Board's are shorter, which is what the saved
  password is for.
- **The keychain key has no question in front of it.** Kestrel has no paid Apple developer ID, so a normal keychain
  item would make macOS ask for your Mac password after every update (and the out-of-sight sign-ins would wait on
  it). The cost: another app running as you could read the key. Cookies in any browser have the same exposure.
- **I couldn't see AP Classroom's or Google Classroom's current pages** (they need your sign-in), so the first real
  read is the real test. That's what "Copy what Kestrel saw" is for.
- **College Board's terms** (automated reading of your own pages) still couldn't be checked from here.

**Your answers (Oct 13):** Classroom is on a school account, so the sign-in test comes before building the
Google part. AP work comes both ways (in Google Classroom and only in AP Classroom), so both paths stay. The
Mac goes to school, and a desktop at home is coming: that's where the autopilot should run.

## The goal

You log in to your Mac and Kestrel opens by itself on a **Today** screen with three parts:

1. **School:** what's due today, tomorrow and this week; anything missing or late, in red; AP Classroom
   work next to your Google Classroom work.
2. **Your day:** today's calendar events.
3. **Trading:** the account value vs. the S&P 500, today's gain or loss, what each desk did or plans,
   whether the autopilot ran all day, the next big economic news (e.g. CPI on Wed Oct 14), and the
   after-market report's summary.

The trading tabs (Summary, Thinking, Trades, Journal, Research) stay as they are. Today becomes the
first tab.

---

## Pass 1: how it works when everything goes right

**Opening at login.** Kestrel already keeps its autopilot alive with a macOS LaunchAgent
(`mac_service.py`). A second, smaller one (`com.aitrader.open-at-login`) would run
`open -a Kestrel` once each time you log in. The app opens on the Today tab. It's a switch in
Setup → Settings ("Open Kestrel when I log in").
- Why not Apple's built-in login-item API (`SMAppService.mainApp`)? It needs macOS 13+, but Kestrel
  supports macOS 12, and developers report it sometimes failing to register (Kestrel is only ad-hoc
  signed, not notarized) ([Apple docs](https://developer.apple.com/documentation/servicemanagement/smappservice/mainapp),
  [forum report](https://developer.apple.com/forums/thread/726826)). A LaunchAgent works on every version,
  and it's the same mechanism the autopilot already uses.

**Google Classroom (the best source).** The Classroom API lets a student read their own classes,
assignments, due dates, and whether each one is turned in, late or missing. The scopes are
`classroom.courses.readonly` and `classroom.coursework.me.readonly`
([Google: studentSubmissions.list](https://developers.google.cn/workspace/classroom/reference/rest/v1/courses.courseWork.studentSubmissions/list)).
It's free; Google's published limits are quotas, not prices: 4,000,000 requests a day per app
([Google: usage limits](https://developers.google.com/classroom/limits)). Kestrel would check every
30 minutes and save a copy, so the Today screen opens instantly, even offline.
Setup: a free Google Cloud project, the Classroom API switched on, a "Desktop app" OAuth client, then
**Connect Google Classroom** in Setup opens Google's sign-in page once. Keys stay on the Mac like the
others.

**Google Calendar.** Classroom gives each class a calendar with every assignment that has a due date
([Google Classroom Help](https://support.google.com/edu/classroom/answer/6272985)). The same sign-in
can read your calendar for today's events. As a backup, it can also read class due dates from there.

**AP Classroom.** Students sign in through My AP at myap.collegeboard.org
([College Board](https://apstudents.collegeboard.org/join-your-class-online)). College Board doesn't publish an API, a calendar feed, or a sync with Google Classroom.
I searched and found none
([AP Classroom student guide](https://leonapecongov.weebly.com/uploads/1/2/1/3/121328859/ap_student_guide_to_ap_classroom.pdf):
assignments live on its own Assignments page). So AP work reaches the dashboard three ways:
1. **When your teacher also posts it in Google Classroom** (many do, as an assignment with a due date),
   it shows up automatically, tagged "AP" when the title or class says AP.
2. **Quick add:** type "APUSH Unit 3 progress check, Friday" on the Today screen. It shows next to the
   rest and drops off when you tick it.
3. **An "AP Classroom" button** on the School card (it opens My AP), so checking it is one click.

**The trading part** reuses what Kestrel already computes (`dashboard.snapshot`, the report, the uptime
check), so it needs no new data.

**How it's built (the shape, not the code).**
- `aitrader/school.py`: Classroom + Calendar: sign in, fetch, cache in `data/school.json`, quick-add items.
- `app_api.py`: `today` (everything on the Today screen), `school-connect`, `school-add`, `school-done`,
  `login-open-on` / `login-open-off`.
- `dashboard.html`: the Today tab first; phone screen too.
- `mac_service.py`: the open-at-login LaunchAgent.
- The autopilot refreshes school data every 30 minutes (school data never touches trading).

**Build order (each step is useful on its own):**
1. **Done:** open at login + a Today tab with the trading summary, quick-add homework, and an AP Classroom
   button. No Google needed. (`aitrader/today.py`, `aitrader/school.py`, `mac_service.open_at_login_on`.)
2. **Built (Oct 13):** Google Classroom + today's calendar, with one sign-in in your own browser
   (`aitrader/google_school.py`, Setup → School). Read-only permissions: classroom.courses.readonly,
   classroom.coursework.me.readonly and calendar.events.owned.readonly. Checked against Google's own API description
   (the discovery documents, revision 20261011 for Classroom). Whether your school allows it is the first real test.
   Google blocks its sign-in inside apps' embedded web views (since 2019, and OAuth in them since 2021), which is
   why this step signs in through your own browser.
   **Built (Oct 13, evening): Kestrel's own browser** (see the update at the top): every account, saved passwords,
   signing back in by itself, and any school page on Today.
3. Polish: the phone screen, a morning push alert ("3 things due today, the autopilot ran all day
   yesterday"), and colors for overdue work.

---

## Pass 2: what won't work, or what we're not accounting for

**1. Your school may block Kestrel from reading Classroom. This is the biggest risk.**
Google lets school admins block outside apps, and for students marked under 18 an app the school hasn't
reviewed is **blocked by default**. The student sees a block message with a "request access" option
that goes to the admin ([Google Workspace Admin Help](https://support.google.com/a/answer/13288950)).
Apps from big companies hit the same wall ("Access blocked: your institution's admin needs to review";
see e.g. [Cengage](https://help.cengage.com/explore/teacher/nglsync/tbs-nglsync-admin-review.html)).
Kestrel would be a brand-new, unreviewed app. So:
- First test (5 minutes, before building anything): try the sign-in with your school account. If it's
  blocked, the options are to ask your school's IT to allow it (they might say no), or to use the
  fallbacks below.
- The fallbacks still work without Google: quick add, and the AP Classroom button. Another option is
  macOS's own Calendar app: if your school account is added in System Settings → Internet Accounts,
  Kestrel can read the class calendars from the Mac. That's Apple's sign-in, which many schools allow,
  but not all. Due dates only, no turned-in status.

**2. Google's "testing" sign-ins expire after 7 days.** A personal Google Cloud app in "Testing" mode
gets sign-ins that expire in 7 days. Switching it to "In production" fixes that, but sensitive scopes
then show an "unverified app" warning you click through once
([Google](https://developers.google.com/health/setup)). Not a blocker; it's one extra step in Setup.

**3. The calendar doesn't know what you've finished.** Class calendars show due dates, not whether
you turned something in. Work your teacher assigns to just you (not the whole class) doesn't appear in
Google Calendar at all ([Google](https://support.google.com/edu/classroom/answer/7184151)). Only the
Classroom API knows about missing work.

**4. I checked the Google account you connected to Claude.** I only looked; nothing was changed.
pbelfand@gmail.com has one Classroom calendar, "Paul", which **you own** (you created that class) and
which has no events Aug–Dec 2026. So your school classes are on a different (school) account, and
that's the one Kestrel needs.

**5. Opening at login doesn't keep the autopilot running, and that's the real problem in your reports.**
In the four reports you sent (Oct 7–12), the autopilot was off for 1–3 hours **every school day**, at
times like 9:45–10:50 and 13:15–14:35. On Oct 12 it **missed the swing desk's 3:45 decision**, and three
stop-losses sold at about -9% instead of -7% (either the price jumped past the stop, or the Mac was asleep
when it crossed; the report can't tell which). The pattern looks like a laptop asleep in a backpack. No dashboard fixes that. Options:
- an always-on computer at home runs the autopilot (an old laptop, a used Mac mini), and your laptop's
  Kestrel window shows it over Tailscale (Kestrel already has the phone screen for this);
- a free cloud server (Oracle Cloud's Always Free tier: sources disagree on whether it's 4 CPUs/24 GB
  or now 2/12, and free capacity is often "out of capacity" in busy regions;
  [Oracle docs](https://docs.oracle.com/en-us/iaas/Content/FreeTier/resourceref.htm),
  [report of the change](https://terminalbytes.com/oracle-cloud-free-tier-changes-2026));
- accept the gaps while it's pretend money, and fix it before real money.

**6. Real money has an age rule.** Alpaca's individual accounts require you to be 18
([Alpaca](https://alpaca.markets/support/requirements-alpaca-brokerage-account)). Under 18, the account
has to be a custodial one an adult controls, and the minor can't trade in it
([Alpaca custodial accounts](https://docs.alpaca.markets/us/docs/custodial-accounts)). Paper trading
isn't affected. (The $25,000 day-trading rule is gone at Alpaca since June 4, 2026
([Alpaca](https://alpaca.markets/blog/finra-retires-the-pdt-rule-introducing-alpacas-new-intraday-margin-framework/)),
so that one isn't a problem; other brokers may phase it in until Oct 2027.)

**7. Privacy and safety.** Your school data would sit on your Mac only, like your broker keys. The school
sign-in would be read-only: it can't post, submit or change anything in Classroom.

**8. Things I'm not sure of yet:** whether your teachers post AP Classroom work in Google Classroom
(you'd know), and whether your school blocks outside apps (one sign-in attempt tells us).

---

## Pass 3: is it worth it? Money, competitors, alternatives

**What it costs to build and run.**
- Google Classroom/Calendar API: $0 (quotas only).
- Open at login, Today screen: $0.
- Keeping the autopilot running all day: the real cost question. An old computer at home: $0. A free
  cloud tier: $0, but capacity and setup are hassles. A paid server: about $5/month. A new Mac mini:
  sources disagree on the price ($599 or $799 in 2026,
  [macprices.net](https://www.macprices.net/macmini.shtml)).
- **The finance lens:** Kestrel's real money is capped at $1,000. $5 a month is $60 a year, which is 6% of
  that capital. The bot would have to beat the market by 6% a year just to pay for its server. A real
  momentum fund beat the market by about 1–2 points a year (`research/history/RESULTS-methods.md`). A Mac mini would be the price of most of the
  trading money. So: **don't pay for hardware for this.** Use a computer you already have at home, a free
  tier, or accept the gaps while it's pretend money.

**Competitors (things that already do the school part).**
- **Google Classroom's own to-do page** (classroom.google.com → To-do): free, exact, shows assigned,
  missing and done. Its weakness: it's one more page to open, and it doesn't show AP Classroom.
- **Study Central** (Google Workspace Marketplace, paid): imports Classroom classes, assignments and
  due dates into one planner ([listing](https://workspace.google.com/marketplace/app/study_central/1069799160687)).
  It hits the same school-admin wall.
- **Planner apps** (myHomework, Notion, Todoist): manual entry, or sync through the calendar.

**Where Kestrel's version is different:** one screen at login with school, calendar and your bot
together, on your Mac, free. None of these does the trading part, and none does AP Classroom
automatically either (no one can: College Board has no API).

**My opinion.** Build step 1 first: open at login, the Today screen, trading summary, quick add, and the
AP button. It's cheap, works whatever your school allows, and you'll use it every day. Then do the
5-minute school sign-in test before building the Google part, so we don't build something your school
blocks. And treat the uptime problem as more important than the dashboard: a bot that's asleep at
3:45 can't make its decision, however nice the screen is.

---

## Questions for you

1. Is your Google Classroom on a school account (like name@yourschool.org)? Is your school strict about
   apps (do other apps ask your admin for access)?
2. Do your AP teachers post AP Classroom assignments in Google Classroom too, or only in AP Classroom?
3. Does your Mac go to school with you? Is there a computer at home that stays on?
4. What's your budget for this (including $0)?
5. What else should Today show: weather, sports or club schedules, a to-do list, grades?
6. **AP Classroom in-app login** (you said build it: built Oct 13, `mac/app/apclassroom.swift` and
   `aitrader/ap_classroom.py`): you'd sign in to College Board once in a Kestrel window, it remembers you, and
   reads your AP Classroom assignments page. Technically possible, and the only way to automate AP Classroom. But I
   couldn't load College Board's terms to check whether they allow automated reading, and it breaks whenever they
   change the page. The reader knows two layouts: a table with a Due column, and cards with "Due <date>" lines.
   Your real page is the test; if it finds nothing, a screenshot of the page lets it learn the layout.

---

## The trader's thinking: what the Oct 7–12 reports taught (done in this update)

1. **Leveraged and inverse funds are off the lists.** It bought MUU and MULL (2x Micron funds) while
   owning MU. That's one bet three times, and a 2x fund's 12-month rise tops a momentum ranking by
   construction. GraniteShares itself says not to expect 2x over more than a day
   ([fact sheet](https://www.graniteshares.com/media/x5skovpx/graniteshares-2x-long-mu-daily-etf.pdf)).
   The evening scan now leaves 2x/3x and inverse funds out (they also leave the stocks-in-play and
   pre-market pools, which come from the scan). It takes effect from the next evening scan.
2. **Count bets, not tickers.** The Risk agent groups stocks that move together (60-day correlation
   0.85+) into one bet, and holds at most 2 stocks in one bet (on by default; `agents.max_same_bet`). The
   Scout says how many separate bets the desk really holds. On Oct 12, MUU, MULL and SNDK hit their
   stops on the same day: -$15.30 of the desk's -$25.84.
3. **A "half size" lesson no longer sells winners.** On Oct 12 the desk learned "half size" for momentum
   and then trimmed MRNA (+13.8%) and BWET (+10.2%) down to the halved limit. Now the lesson only makes
   new buys smaller.

**Next ideas (not built; each would be shadow-tested before it changes trades):**
- **Think in R:** each trade's result in units of what it risked (its stop distance), plus expectancy
  (average win × win rate − average loss × loss rate).
- **How far each trade went for and against it** before it closed (MFE/MAE), to see if the stops are too
  tight or exits too early.
- **Market weather:** momentum has crashed after bear markets in jumpy markets (Daniel & Moskowitz,
  "Momentum Crashes", 2016), and momentum profits came mostly after up markets (Cooper, Gutierrez &
  Hameed, 2004). A flag for those conditions, tagged on every buy so the mistake memory learns from it.
- **Don't over-learn from one day:** 4 stop-outs from one bet on one day count as roughly one piece of
  evidence, not four.
- **A missed 3:45 decision:** decide at the next morning's check instead of skipping the day (this
  changes the tested timing, so it needs its own test first).
- **Stocks in play:** some picks were bond or country funds (LQD 11.6x, EMB, EWZ). Their volume comes
  from fund flows, not company news; worth testing stocks-only.
