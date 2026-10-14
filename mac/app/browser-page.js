// browser-page.js: Kestrel's browser (browser.swift) keeps a copy of the data (JSON) a page downloads to draw itself, so
// the bot (school_web.py) can read assignments from it even when the page lays them out in a way it doesn't know.
// The copy stays in the page (window.__kestrelData) until Kestrel reads the page; nothing is sent anywhere.
// Sign-in pages are left exactly as they are (their security checks look for changes like this one).
(() => {
  if (window.__kestrelData || /^accounts\.|log-?in|sign-?in|auth|idp|sso|okta/i.test(location.host + location.pathname)) return;
  const kept = [];
  let total = 0;
  Object.defineProperty(window, "__kestrelData", { value: kept });
  const keep = (url, body) => {
    if (typeof body !== "string" || body.length < 2 || body.length > 3000000 || total > 8000000) return;
    if (!/^\s*([[{]|\)\]\}')/.test(body.slice(0, 20))) return;
    kept.push({ url: String(url || "").slice(0, 300), body });
    total += body.length;
    while (kept.length > 60) total -= kept.shift().body.length;
  };
  const json = (type) => /json|javascript|text\/plain/i.test(type || "");
  const realFetch = window.fetch;
  if (realFetch) {
    window.fetch = function (...args) {
      const answer = realFetch.apply(this, args);
      answer.then((r) => {
        try { if (json(r.headers.get("content-type"))) r.clone().text().then((t) => keep(r.url, t), () => {}); } catch (e) {}
      }, () => {});
      return answer;
    };
  }
  const open = XMLHttpRequest.prototype.open, send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.__kestrelUrl = url;
    return open.call(this, method, url, ...rest);
  };
  XMLHttpRequest.prototype.send = function (...args) {
    this.addEventListener("load", () => {
      try {
        const where = this.responseURL || this.__kestrelUrl;
        if ((this.responseType === "" || this.responseType === "text") && json(this.getResponseHeader("content-type"))) keep(where, this.responseText);
        else if (this.responseType === "json" && this.response) keep(where, JSON.stringify(this.response));
      } catch (e) {}
    });
    return send.apply(this, args);
  };
})();
