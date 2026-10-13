// apclassroom.swift: AP Classroom in a Kestrel window (the bot's side is aitrader/ap_classroom.py).
//
// College Board offers no way for other apps to read AP Classroom, so Kestrel does what you'd do yourself: it
// opens AP Classroom in a window of its own. You sign in to College Board once (this window remembers you, like
// Safari), open a page that lists your AP assignments, and press "Use this page for Today". Kestrel hands that
// page's visible text to the bot, which finds each assignment, its due date and its status. Later Kestrel
// re-reads the same pages by itself, out of sight, when the Today screen asks (at most every 2 hours).
// It only reads text: it never clicks, starts or submits anything in AP Classroom.
// A College Board account you sign in to with Google won't work here: Google blocks sign-ins in apps' built-in
// browsers. A College Board username and password does.
import Cocoa
import WebKit

let apHome = URL(string: "https://myap.collegeboard.org/")!

/// A page's visible text once it has rendered (AP Classroom builds its pages with JavaScript after they load):
/// it waits until the text mentions a due date, or stops changing, for up to about 18 seconds.
func readPageText(_ web: WKWebView, tries: Int = 12, last: Int = -1, done: @escaping (String) -> Void) {
    web.evaluateJavaScript("document.body ? document.body.innerText : ''") { value, _ in
        let text = value as? String ?? ""
        let ready = text.contains("Due") || text.contains("Now Open") || (text.count > 200 && text.count == last)
        if ready || tries <= 1 {
            done(text)
            return
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            readPageText(web, tries: tries - 1, last: text.count, done: done)
        }
    }
}

/// Hands a page's text to the bot (`app_api ap-save`), which finds the assignments. Call off the main thread.
func saveAPPage(url: String, title: String, text: String, auto: Bool) -> [String: Any] {
    let payload: [String: Any] = ["url": url, "title": title, "text": text, "auto": auto]
    guard let data = try? JSONSerialization.data(withJSONObject: payload),
          let input = String(data: data, encoding: .utf8) else {
        return ["error": "The page couldn't be handed to the bot."]
    }
    let answer = askBot(["ap-save"], input: input)
    return (try? JSONSerialization.jsonObject(with: Data(answer.utf8))) as? [String: Any] ?? ["error": answer]
}

final class APClassroom: NSObject, WKNavigationDelegate, WKUIDelegate {
    let onSaved: () -> Void                 // tells the Today screen to show what's new
    var window: NSWindow?
    var web: WKWebView!
    var status: NSTextField!
    var reader: WKWebView?                  // re-reads the chosen pages out of sight
    var readerWindow: NSWindow?
    var queue: [String] = []
    var reading = false
    var readingURL: String?
    var generation = 0                      // which page the reader is on (late answers about an earlier one are ignored)

    init(onSaved: @escaping () -> Void) {
        self.onSaved = onSaved
        super.init()
    }

    /// Both web views share Safari-like storage (your sign-in), and keep working while out of sight.
    func configuration() -> WKWebViewConfiguration {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()
        if #available(macOS 14.0, *) {
            config.preferences.inactiveSchedulingPolicy = .none     // a hidden page isn't paused while it's read
        }
        return config
    }

    // MARK: the window where you sign in and choose pages
    func open() {
        if let window = window {
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        web = WKWebView(frame: .zero, configuration: configuration())   // keeps your College Board sign-in
        web.navigationDelegate = self
        web.uiDelegate = self

        let back = NSButton(title: "Back", target: self, action: #selector(goBack))
        let home = NSButton(title: "My AP", target: self, action: #selector(goHome))
        let use = NSButton(title: "Use this page for Today", target: self, action: #selector(useThisPage))
        use.keyEquivalent = "\r"
        let label = NSTextField(labelWithString: "Sign in to College Board, open a page that lists your AP "
                                                 + "assignments, then press Use this page for Today.")
        label.textColor = .secondaryLabelColor
        label.lineBreakMode = .byTruncatingTail
        label.setContentHuggingPriority(.defaultLow, for: .horizontal)
        label.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        status = label
        let bar = NSStackView(views: [back, home, label, use])
        bar.orientation = .horizontal
        bar.spacing = 8
        bar.edgeInsets = NSEdgeInsets(top: 8, left: 12, bottom: 8, right: 12)

        let content = NSView()
        for view in [bar, web!] as [NSView] {
            view.translatesAutoresizingMaskIntoConstraints = false
            content.addSubview(view)
        }
        NSLayoutConstraint.activate([
            bar.topAnchor.constraint(equalTo: content.topAnchor),
            bar.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            bar.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            web.topAnchor.constraint(equalTo: bar.bottomAnchor),
            web.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            web.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            web.bottomAnchor.constraint(equalTo: content.bottomAnchor),
        ])

        let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1100, height: 800),
                         styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        w.title = "AP Classroom (Kestrel)"
        w.contentView = content
        w.isReleasedWhenClosed = false
        w.minSize = NSSize(width: 640, height: 480)
        w.center()
        w.setFrameAutosaveName("KestrelAPClassroom")
        window = w
        web.load(URLRequest(url: apHome))
        w.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc func goBack() {
        if web.canGoBack { web.goBack() }
    }

    @objc func goHome() {
        web.load(URLRequest(url: apHome))
    }

    @objc func useThisPage() {
        guard let url = web.url?.absoluteString else { return }
        let title = web.title ?? ""
        status.stringValue = "Reading this page…"
        readPageText(web, tries: 4) { text in
            DispatchQueue.global(qos: .userInitiated).async {
                let answer = saveAPPage(url: url, title: title, text: text, auto: false)
                DispatchQueue.main.async {
                    self.status.stringValue = (answer["message"] as? String) ?? (answer["error"] as? String) ?? "Done."
                    self.onSaved()
                }
            }
        }
    }

    // Links that open a new window open here instead; mail and other apps' links go to their apps.
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if navigationAction.targetFrame == nil { webView.load(navigationAction.request) }
        return nil
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let url = navigationAction.request.url, let scheme = url.scheme,
           !["http", "https", "about", "blob", "data"].contains(scheme) {
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.allow)
    }

    // MARK: re-reading the chosen pages, out of sight
    /// Asks the bot which pages were chosen, then reads them one at a time and saves what's on them.
    func readSaved() {
        if reading { return }
        reading = true
        DispatchQueue.global(qos: .utility).async {
            let answer = askBot(["ap-pages"])
            let json = (try? JSONSerialization.jsonObject(with: Data(answer.utf8))) as? [String: Any]
            let pages = json?["pages"] as? [String] ?? []
            DispatchQueue.main.async {
                self.queue = pages
                self.readNext()
            }
        }
    }

    func readNext() {
        while !queue.isEmpty {
            let next = queue.removeFirst()
            if let url = URL(string: next), url.scheme == "https" {
                load(url)
                return
            }
        }
        reading = false
        readingURL = nil
        reader = nil
        readerWindow?.close()
        readerWindow = nil
        onSaved()
    }

    func load(_ url: URL) {
        if reader == nil {
            let view = WKWebView(frame: NSRect(x: 0, y: 0, width: 1200, height: 900), configuration: configuration())
            view.navigationDelegate = self
            let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1200, height: 900), styleMask: [.borderless],
                             backing: .buffered, defer: false)
            w.contentView = view                               // never shown: it only gives the page a size
            w.isReleasedWhenClosed = false
            reader = view
            readerWindow = w
        }
        generation += 1
        let mine = generation
        readingURL = url.absoluteString
        reader?.load(URLRequest(url: url))
        DispatchQueue.main.asyncAfter(deadline: .now() + 60) { [weak self] in   // a page that never finishes: skip it
            guard let self = self, self.reading, self.generation == mine else { return }
            self.generation += 1
            self.readNext()
        }
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        guard webView === reader, let wanted = readingURL else { return }
        let mine = generation
        readPageText(webView) { text in
            guard self.generation == mine else { return }      // already read (or given up on)
            self.generation += 1
            let title = webView.title ?? ""
            DispatchQueue.global(qos: .utility).async {
                _ = saveAPPage(url: wanted, title: title, text: text, auto: true)
                DispatchQueue.main.async { self.readNext() }
            }
        }
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        readerFailed(webView)
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        readerFailed(webView)
    }

    func readerFailed(_ webView: WKWebView) {
        guard webView === reader, reading else { return }
        generation += 1
        readNext()
    }
}
