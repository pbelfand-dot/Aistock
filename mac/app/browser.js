// browser.js: Kestrel's helper inside each page of its browser (browser.swift). It runs in a "world" of its own:
// the page's own scripts can't see it, and can't reach Kestrel (or your saved passwords) through it.
//   kestrel.snapshot()                what the page shows: its text, its rows (tables, lists, cards), the Google account
//                                     it's signed in as, and whether a sign-in form is showing
//   kestrel.state()                   is this a sign-in step ("password", "username", or Google's "choose" an account)?
//   kestrel.fill(user, password, go)  fills a sign-in form, and submits it when the browser signs back in by itself
//   kestrel.choose(email)             picks that account on Google's "Choose an account" page
// It also offers your saved password when a sign-in form shows, and tells Kestrel when you sign in with a new one
// (Kestrel then asks whether to save it). It never sends anything anywhere else.
(() => {
  if (window.kestrel) return;
  const EMAIL = /[\w.+'-]+@[\w-]+(\.[\w-]+)+/;
  const USER = /user|email|e-mail|login|identifier|account|sign.?in/i;
  const GO = /^(next|sign in|log in|login|log on|sign on|continue|submit|verify)$/i;
  const LOGIN_PAGE = /log-?in|sign-?in|signin|auth|account|idp|sso|identifier|oauth|saml/i;
  const DATEISH = /\bdue\b|now open|\b\d{1,2}\/\d{1,2}\b|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d|\b(mon|tue|wed|thu|fri|sat|sun)[a-z]*\b|tomorrow|today/i;

  const handler = () => window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.kestrelLogin;
  const post = (message) => {
    const h = handler();
    if (!h) return Promise.resolve(null);
    try { return Promise.resolve(h.postMessage(message)); } catch (e) { return Promise.resolve(null); }
  };
  const visible = (el) => {
    if (!el || !el.getBoundingClientRect) return false;
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const st = getComputedStyle(el);
    return st.visibility !== "hidden" && st.display !== "none" && st.opacity !== "0";
  };
  const text = () => (document.body ? document.body.innerText || "" : "");
  const clean = (s) => String(s || "").replace(/\s+/g, " ").trim();
  const loginPage = () => LOGIN_PAGE.test(location.host + location.pathname);

  // ---------------------------------------------------------------- sign-in forms
  const passwords = () => [...document.querySelectorAll("input[type=password]")].filter(visible);
  const userFields = () => [...document.querySelectorAll("input")].filter((i) => {
    const kind = (i.getAttribute("type") || "text").toLowerCase();
    if (!["text", "email", "tel"].includes(kind) || i.readOnly || i.disabled || !visible(i)) return false;
    if (kind === "email") return true;
    return USER.test([i.name, i.id, i.getAttribute("autocomplete"), i.getAttribute("aria-label"), i.placeholder].join(" "));
  });
  const shownEmail = () => {                                // Google's password step shows whose account it is
    const tagged = [...document.querySelectorAll("[data-email], [data-identifier]")].find(visible);
    if (tagged) return tagged.getAttribute("data-email") || tagged.getAttribute("data-identifier") || "";
    const found = text().slice(0, 4000).match(EMAIL);
    return found ? found[0] : "";
  };
  const userFor = (pw) => {                                 // the username box that goes with a password box
    const pool = userFields().filter((u) => !pw.form || u.form === pw.form);
    const before = pool.filter((u) => u.compareDocumentPosition(pw) & Node.DOCUMENT_POSITION_FOLLOWING);
    return before[before.length - 1] || pool[0] || null;
  };
  const type = (input, value) => {                          // as if typed: pages built with React notice it too
    input.focus();
    input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  };
  const words = (b) => clean(b.innerText || b.value || b.getAttribute("aria-label") || "");
  const isGo = (b) => GO.test(words(b)) || (b.getAttribute("type") || "").toLowerCase() === "submit"
    || !!(b.closest && b.closest("#passwordNext, #identifierNext"));
  const goButton = (field) => {
    const scope = (field && field.form) || document;
    const buttons = [...scope.querySelectorAll("button, input[type=submit], [role=button]")].filter(visible);
    return buttons.find((b) => GO.test(words(b)))
      || buttons.find((b) => (b.getAttribute("type") || "").toLowerCase() === "submit")
      || document.querySelector("#passwordNext button, #identifierNext button");
  };
  const submit = (field) => {
    const button = goButton(field);
    if (button) { button.click(); return true; }
    if (field && field.form) {
      try { field.form.requestSubmit(); } catch (e) { field.form.submit(); }
      return true;
    }
    return false;
  };
  const accounts = () => [...document.querySelectorAll("[data-identifier], [data-email]")].filter(visible)
    .map((e) => e.getAttribute("data-identifier") || e.getAttribute("data-email")).filter((x) => EMAIL.test(x || ""));

  const state = () => {
    const pw = passwords().length > 0;
    const user = !pw && loginPage() && userFields().length > 0;
    const chooser = !pw && !user && loginPage() && accounts().length > 0;
    const all = text();
    return { step: pw ? "password" : user ? "username" : chooser ? "choose" : "", host: location.host,
             url: location.href, shown: shownEmail(), accounts: chooser ? accounts() : [], text: all.length,
             due: /\bdue\b|now open/i.test(all) };
  };
  const fill = (user, password, go) => {
    const pw = passwords()[0];
    if (pw) {
      const u = userFor(pw);
      if (u && user && u.value !== user) type(u, user);
      type(pw, password);
      if (go) setTimeout(() => submit(pw), 150);
      return "password";
    }
    const u = userFields()[0];
    if (u && user) {
      type(u, user);
      if (go) setTimeout(() => submit(u), 150);
      return "username";
    }
    return "";
  };
  const choose = (email) => {
    const pick = [...document.querySelectorAll("[data-identifier], [data-email]")].filter(visible).find((e) =>
      (e.getAttribute("data-identifier") || e.getAttribute("data-email") || "").toLowerCase() === String(email).toLowerCase());
    if (!pick) return false;
    pick.click();
    return true;
  };

  // ---------------------------------------------------------------- what the page shows
  const account = () => {                                   // the Google account the page is signed in as
    for (const el of document.querySelectorAll("a[aria-label], button[aria-label], [data-email]")) {
      const label = el.getAttribute("data-email") || el.getAttribute("aria-label") || "";
      if (!el.hasAttribute("data-email") && !/account|signed in/i.test(label)) continue;
      const found = label.match(EMAIL);
      if (found) return found[0];
    }
    return "";
  };
  const cellsOf = (el) => (el.innerText || "").split("\n").map(clean).filter(Boolean).slice(0, 15).map((c) => c.slice(0, 200));
  const linkOf = (el) => {
    const a = el.matches && el.matches("a[href]") ? el : el.querySelector && el.querySelector("a[href]");
    return a && /^https:/.test(a.href) ? a.href : "";
  };
  const signature = (el) => el.tagName + "." + (typeof el.className === "string" ? el.className.trim().split(/\s+/).sort().join(".") : "");
  const rows = () => {
    const out = [], taken = new Set();
    const add = (cells, link) => { if (cells.length >= 2 && out.length < 400) out.push({ cells, link }); };
    for (const row of document.querySelectorAll("tr, [role=row]")) {         // tables and grids
      if (!visible(row)) continue;
      const parts = [...row.children].filter((c) => /^(TD|TH)$/.test(c.tagName) || /cell|header/.test(c.getAttribute("role") || ""));
      const cells = (parts.length ? parts.map((c) => clean(c.innerText).slice(0, 200)) : cellsOf(row)).filter(Boolean).slice(0, 15);
      add(cells, linkOf(row));
      taken.add(row);
    }
    let looked = 0;                                                           // lists and cards: look-alike siblings
    for (const parent of document.querySelectorAll("ul, ol, div, section, main, [role=list], [role=feed]")) {
      if (++looked > 4000 || out.length >= 400) break;
      const kids = [...parent.children];
      if (kids.length < 2 || kids.length > 300) continue;
      const counts = new Map();
      for (const k of kids) counts.set(signature(k), (counts.get(signature(k)) || 0) + 1);
      let best = "", most = 0;
      for (const [sig, n] of counts) if (n > most) { best = sig; most = n; }
      if (most < 2) continue;
      const same = kids.filter((k) => signature(k) === best && !taken.has(k) && visible(k))
        .map((k) => [k, cellsOf(k)]).filter(([, c]) => c.length >= 2 && c.length <= 15);
      if (same.length < 2 || !same.some(([, c]) => DATEISH.test(c.join(" ")))) continue;
      for (const [k, c] of same) add(c, linkOf(k));
    }
    return out;
  };
  const snapshot = () => ({ url: location.href, title: document.title, text: text().slice(0, 200000), rows: rows(),
                            account: account(), login: passwords().length > 0 });

  // ---------------------------------------------------------------- saving and offering passwords
  let lastUser = "", offered = "";
  const capture = () => {
    const pw = passwords().find((p) => p.value);
    if (pw) {
      const u = userFor(pw);
      post({ kind: "save", username: clean(u && u.value) || lastUser || shownEmail(), password: pw.value });
      return;
    }
    const u = userFields().find((i) => clean(i.value).length >= 3);
    if (u && loginPage()) {
      lastUser = clean(u.value);
      post({ kind: "user", username: lastUser });
    }
  };
  document.addEventListener("submit", capture, true);
  document.addEventListener("click", (e) => {
    const b = e.target && e.target.closest && e.target.closest("button, input[type=submit], [role=button]");
    if (b && isGo(b)) capture();
  }, true);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target && e.target.tagName === "INPUT") capture();
  }, true);

  const offer = async () => {
    const pw = passwords()[0];
    const user = pw ? null : userFields()[0];
    if (!pw && !(user && loginPage())) return;
    const key = location.href.split("#")[0] + (pw ? "|password" : "|username");
    if (offered === key) return;
    offered = key;
    const login = await post({ kind: "need", hint: shownEmail() || clean(user && user.value), step: pw ? "password" : "username" });
    if (!login) return;
    if (pw) {
      if (pw.value || !login.password) return;
      const u = userFor(pw);
      if (u && !u.value && login.username) type(u, login.username);
      type(pw, login.password);
    } else if (user && !user.value && login.username) {
      type(user, login.username);
    }
  };
  let timer = 0;
  const later = () => { clearTimeout(timer); timer = setTimeout(offer, 400); };
  if (document.documentElement) new MutationObserver(later).observe(document.documentElement, { childList: true, subtree: true });
  later();

  window.kestrel = { snapshot, state, fill, choose, rows, account };
})();
