// browser.swift: Kestrel's own web browser (Window → Browser, or the browser buttons on Today and in Setup → School).
//
// A small Safari: tabs, an address bar, bookmarks, downloads and uploads. It stays signed in to your accounts, as many
// as you like: your school Google and your personal Gmail (Google's own "Add another account"), College Board, any
// school site. When you sign in it offers to save the password (logins.swift keeps them, sealed, on this Mac) and fills
// it in next time. Pages are told it's Safari (it is Safari's engine, WebKit), so Google lets you sign in.
//
// "Add to Today": the page you're on (AP Classroom's assignments, Google Classroom's To-do for each account, any school
// page that lists your work) goes to the bot (school_web.py), which finds the assignments, due dates and status on it.
// Kestrel re-reads those pages by itself, out of sight: soon after it opens, every few hours, after the Mac wakes, and
// when the Today screen asks. When a site has signed it out, it signs back in with your saved password. It only reads:
// it never clicks, starts or turns in anything (signing in aside).
//
// Its helpers run inside each page: browser.js (reads the page; fills and saves passwords) and browser-page.js (keeps
// a copy of the data the page downloads, for the bot).
import Cocoa
import WebKit

let apHome = URL(string: "https://myap.collegeboard.org/")!
let classroomHome = URL(string: "https://classroom.google.com/")!
let defaultBookmarks: [[String]] = [["Google Classroom", "https://classroom.google.com/"],
                                    ["AP Classroom", "https://myap.collegeboard.org/"],
                                    ["Gmail", "https://mail.google.com/"], ["Calendar", "https://calendar.google.com/"]]

/// "Version/18.4 Safari/605.1.15" for this Mac's Safari: pages (Google's sign-in above all) see the browser it is.
let safariName: String = {
    let info = NSDictionary(contentsOfFile: "/Applications/Safari.app/Contents/Info.plist")
    let version = info?["CFBundleShortVersionString"] as? String ?? "18.0"
    return "Version/\(version) Safari/605.1.15"
}()

func bundledScript(_ name: String) -> String {
    guard let url = Bundle.main.url(forResource: name, withExtension: "js"),
          let text = try? String(contentsOf: url, encoding: .utf8) else { return "" }
    return text
}

func jsonText(_ value: Any) -> String {
    guard let data = try? JSONSerialization.data(withJSONObject: value) else { return "{}" }
    return String(data: data, encoding: .utf8) ?? "{}"
}

func jsonObject(_ text: String) -> [String: Any] {
    (try? JSONSerialization.jsonObject(with: Data(text.utf8))) as? [String: Any] ?? [:]
}

/// A web address from what you typed: an address, or else a Google search.
func addressURL(_ typed: String) -> URL? {
    let text = typed.trimmingCharacters(in: .whitespacesAndNewlines)
    if text.isEmpty { return nil }
    if let url = URL(string: text), let scheme = url.scheme?.lowercased(), ["http", "https", "about"].contains(scheme) {
        return url
    }
    if !text.contains(" "), text.contains("."), let url = URL(string: "https://" + text), url.host != nil { return url }
    var search = URLComponents(string: "https://www.google.com/search")!
    search.queryItems = [URLQueryItem(name: "q", value: text)]
    return search.url
}

struct ChosenPage {
    let url: URL
    let account: String                        // the Google account it belongs to, when the bot knows it
}

final class Browser: NSObject, WKScriptMessageHandlerWithReply, WKNavigationDelegate, WKUIDelegate {
    let onSaved: () -> Void                    // the Today screen shows what's new
    var showSetup: (String) -> Void = { _ in } // opens Setup on that pane (main.swift)
    let controller = WKUserContentController()
    var tabs: [BrowserTab] = []
    var lastUser: [String: String] = [:]       // the username you typed on a site's first sign-in step
    var asking = false                         // a "Save this password?" question is showing
    // the reader: re-reads the chosen pages out of sight
    var reader: WKWebView?
    var readerWindow: NSWindow?
    var queue: [ChosenPage] = []
    var current: ChosenPage?
    var reading = false
    var generation = 0                         // which page the reader is on (late answers about an earlier one are ignored)
    var signIns = 0
    var lastLength = -1
    var lastRead: Date?
    var timer: Timer?
    var wakeWatch: NSObjectProtocol?

    init(onSaved: @escaping () -> Void) {
        self.onSaved = onSaved
        super.init()
        controller.addUserScript(WKUserScript(source: bundledScript("browser-page"), injectionTime: .atDocumentStart,
                                              forMainFrameOnly: true, in: .page))
        controller.addUserScript(WKUserScript(source: bundledScript("browser"), injectionTime: .atDocumentEnd,
                                              forMainFrameOnly: true, in: .defaultClient))
        controller.addScriptMessageHandler(self, contentWorld: .defaultClient, name: "kestrelLogin")
    }

    /// Every tab and the reader share Safari-like storage (your sign-ins) and the helpers.
    func configuration(hidden: Bool = false) -> WKWebViewConfiguration {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()
        config.userContentController = controller
        config.applicationNameForUserAgent = safariName
        if hidden {
            if #available(macOS 14.0, *) {
                config.preferences.inactiveSchedulingPolicy = .none  // the reader isn't paused while out of sight
            }
        }
        return config
    }

    // MARK: windows and tabs
    /// Opens the browser: a new tab with that address, or the browser as you left it (Google Classroom the first time).
    func open(_ url: URL? = nil) {
        if url == nil, let tab = tabs.last, let window = tab.window {
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        newTab(url ?? classroomHome)
    }

    @discardableResult
    func newTab(_ url: URL?, configuration: WKWebViewConfiguration? = nil, newWindow: Bool = false,
                behind: Bool = false) -> BrowserTab {
        let key = NSApp.keyWindow
        let front = key?.tabbingIdentifier == BrowserTab.group ? key : tabs.last(where: { $0.window?.isVisible == true })?.window
        let tab = BrowserTab(browser: self, configuration: configuration ?? self.configuration())
        tabs.append(tab)
        guard let window = tab.window else { return tab }
        if let front = front, !newWindow {
            front.addTabbedWindow(window, ordered: .above)
        } else if let front = front {
            window.setFrame(front.frame.offsetBy(dx: 24, dy: -24), display: false)
        } else {
            window.center()
            window.setFrameAutosaveName("KestrelBrowser")
        }
        if behind, let front = front {
            front.makeKeyAndOrderFront(nil)
        } else {
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
        }
        if let url = url {
            tab.web.load(URLRequest(url: url))
        } else if configuration == nil {
            tab.focusAddress()
        }
        return tab
    }

    func closed(_ tab: BrowserTab) {
        tabs.removeAll { $0 === tab }
    }

    @objc func newTabFromMenu() { newTab(nil) }
    @objc func newWindowFromMenu() { newTab(nil, newWindow: true) }
    @objc func openFromMenu() { open() }
    @objc func openAPFromMenu() { open(apHome) }

    // MARK: bookmarks (the bar under the address)
    var bookmarks: [[String]] {
        get { UserDefaults.standard.array(forKey: "browserBookmarks") as? [[String]] ?? defaultBookmarks }
        set {
            UserDefaults.standard.set(newValue, forKey: "browserBookmarks")
            tabs.forEach { $0.fillBookmarks() }
        }
    }

    // MARK: saved passwords
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage,
                               replyHandler: @escaping (Any?, String?) -> Void) {
        let origin = message.frameInfo.securityOrigin
        guard message.frameInfo.isMainFrame, origin.protocol == "https", let body = message.body as? [String: Any],
              let kind = body["kind"] as? String else {
            replyHandler(nil, nil)
            return
        }
        let host = origin.host.lowercased()                          // where the page really is, not what it says
        let username = (body["username"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let fromReader = message.webView != nil && message.webView === reader
        switch kind {
        case "user":
            if !username.isEmpty { lastUser[host] = username }
            replyHandler(nil, nil)
        case "need":
            let wanted = fromReader ? (current?.account ?? "") : ""
            let hint = wanted.isEmpty ? (body["hint"] as? String ?? "") : wanted
            if let login = Logins.shared.pick(host: host, hint: hint) {
                replyHandler(["username": login.username, "password": login.password], nil)
            } else {
                replyHandler(nil, nil)
            }
        case "save":
            replyHandler(nil, nil)
            guard !fromReader, let password = body["password"] as? String, !password.isEmpty else { return }
            offerToSave(host: host, username: username.isEmpty ? (lastUser[host] ?? "") : username,
                        password: password, window: message.webView?.window)
        default:
            replyHandler(nil, nil)
        }
    }

    func offerToSave(host: String, username: String, password: String, window: NSWindow?) {
        let logins = Logins.shared
        if asking || logins.isNever(host) { return }
        let known = logins.find(host: host, username: username)
        if known?.password == password { return }
        let alert = NSAlert()
        alert.messageText = known != nil ? "Update your saved password for \(host)?" : "Save this password in Kestrel?"
        alert.informativeText = (username.isEmpty ? "" : "\(username) on ") + "\(host). Kestrel fills it in for you, "
            + "and uses it to sign back in by itself when it re-reads your pages for Today. It stays on this Mac, sealed "
            + "with a key in your Mac's keychain."
        alert.addButton(withTitle: known != nil ? "Update Password" : "Save Password")
        alert.addButton(withTitle: "Not Now")
        if known == nil { alert.addButton(withTitle: "Never for This Site") }
        asking = true
        let done: (NSApplication.ModalResponse) -> Void = { answer in
            self.asking = false
            if answer == .alertFirstButtonReturn {
                logins.save(host: host, username: username, password: password)
            } else if answer == .alertThirdButtonReturn {
                logins.never(host)
            }
        }
        if let window = window {
            alert.beginSheetModal(for: window, completionHandler: done)
        } else {
            done(alert.runModal())
        }
    }

    // MARK: reading a page for Today
    /// What a web view shows, handed to the bot: "web-save" adds it to Today (auto = a re-read of a chosen page), and
    /// "web-report" only describes it ("Copy What Kestrel Saw").
    func capture(_ web: WKWebView, page: ChosenPage?, auto: Bool, action: String = "web-save",
                 done: @escaping ([String: Any]) -> Void) {
        web.evaluateJavaScript("JSON.stringify(window.kestrel ? kestrel.snapshot() : null)", in: nil,
                               in: .defaultClient) { result in
            var payload: [String: Any] = [:]
            if case .success(let value) = result, let text = value as? String { payload = jsonObject(text) }
            web.evaluateJavaScript("JSON.stringify({data: window.__kestrelData || [], text: document.body ? "
                                   + "document.body.innerText : '', title: document.title, url: location.href})",
                                   in: nil, in: .page) { more in
                if case .success(let value) = more, let text = value as? String {
                    let shown = jsonObject(text)
                    payload["data"] = shown["data"] ?? [Any]()
                    for key in ["text", "title", "url"] where payload[key] == nil { payload[key] = shown[key] }
                }
                if let page = page {
                    payload["page"] = page.url.absoluteString
                    if (payload["account"] as? String ?? "").isEmpty { payload["account"] = page.account }
                }
                payload["auto"] = auto
                let input = jsonText(payload)
                DispatchQueue.global(qos: .utility).async {
                    let answer = jsonObject(askBot([action], input: input))
                    DispatchQueue.main.async {
                        done(answer)
                        if action == "web-save" { self.onSaved() }
                    }
                }
            }
        }
    }

    // MARK: re-reading the chosen pages, out of sight
    /// Starts the schedule: soon after Kestrel opens, then whenever 3 hours have passed (checked every 30 minutes),
    /// and a minute and a half after the Mac wakes up.
    func startSchedule() {
        DispatchQueue.main.asyncAfter(deadline: .now() + 20) { [weak self] in self?.readSaved() }
        timer = Timer.scheduledTimer(withTimeInterval: 1800, repeats: true) { [weak self] _ in
            guard let self = self else { return }
            if self.lastRead.map({ Date().timeIntervalSince($0) > 3 * 3600 }) ?? true { self.readSaved() }
        }
        wakeWatch = NSWorkspace.shared.notificationCenter.addObserver(forName: NSWorkspace.didWakeNotification,
                                                                      object: nil, queue: .main) { [weak self] _ in
            DispatchQueue.main.asyncAfter(deadline: .now() + 90) { self?.readSaved() }
        }
    }

    /// Asks the bot which pages were chosen, then reads them one at a time. Not again within 10 minutes unless forced.
    func readSaved(force: Bool = false) {
        if reading { return }
        if !force, let last = lastRead, Date().timeIntervalSince(last) < 600 { return }
        reading = true
        DispatchQueue.global(qos: .utility).async {
            let answer = jsonObject(askBot(["web-pages"]))
            var pages: [ChosenPage] = []
            for item in answer["pages"] as? [[String: Any]] ?? [] {
                if let text = item["url"] as? String, let url = URL(string: text), url.scheme == "https" {
                    pages.append(ChosenPage(url: url, account: item["account"] as? String ?? ""))
                }
            }
            DispatchQueue.main.async {
                self.queue = pages
                self.readNext()
            }
        }
    }

    func readNext() {
        guard !queue.isEmpty else {
            reading = false
            current = nil
            lastRead = Date()
            reader?.stopLoading()
            reader = nil
            readerWindow?.close()
            readerWindow = nil
            onSaved()
            return
        }
        let page = queue.removeFirst()
        current = page
        signIns = 0
        lastLength = -1
        generation += 1
        let mine = generation
        if reader == nil {
            let view = WKWebView(frame: NSRect(x: 0, y: 0, width: 1280, height: 900), configuration: configuration(hidden: true))
            view.navigationDelegate = self
            view.uiDelegate = self
            let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1280, height: 900), styleMask: [.borderless],
                             backing: .buffered, defer: false)
            w.contentView = view                               // never shown: it only gives the page a size
            w.isReleasedWhenClosed = false
            reader = view
            readerWindow = w
        }
        reader?.load(URLRequest(url: page.url))
        let started = Date()
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) { [weak self] in self?.check(mine, started: started) }
    }

    /// Every 2 seconds: a sign-in page? sign in (at most 3 tries). Settled (it shows due dates, or its text stopped
    /// changing)? read it. Never more than about a minute and a half per page.
    func check(_ mine: Int, started: Date) {
        guard reading, mine == generation, let web = reader, let page = current else { return }
        web.evaluateJavaScript("JSON.stringify(window.kestrel ? kestrel.state() : null)", in: nil,
                               in: .defaultClient) { [weak self] result in
            guard let self = self, mine == self.generation else { return }
            var state: [String: Any] = [:]
            if case .success(let value) = result, let text = value as? String { state = jsonObject(text) }
            let waited = Date().timeIntervalSince(started)
            let step = state["step"] as? String ?? ""
            if !step.isEmpty, self.signIns < 3, waited < 75, self.signIn(web, step: step, state: state, page: page) {
                self.signIns += 1
                self.lastLength = -1
                DispatchQueue.main.asyncAfter(deadline: .now() + 4) { [weak self] in self?.check(mine, started: started) }
                return
            }
            let length = state["text"] as? Int ?? 0
            let settled = !web.isLoading && ((state["due"] as? Bool == true && waited >= 5)
                                             || (length > 150 && length == self.lastLength))
            self.lastLength = length
            if !settled && waited < 45 {
                DispatchQueue.main.asyncAfter(deadline: .now() + 2) { [weak self] in self?.check(mine, started: started) }
                return
            }
            self.generation += 1                               // this page is done: later answers about it don't count
            self.capture(web, page: page, auto: true) { [weak self] _ in self?.readNext() }
        }
    }

    /// Signs back in on a sign-in page with the saved password (or picks the account on Google's account chooser).
    func signIn(_ web: WKWebView, step: String, state: [String: Any], page: ChosenPage) -> Bool {
        let host = (state["host"] as? String ?? web.url?.host ?? "").lowercased()
        if step == "choose" {
            let accounts = state["accounts"] as? [String] ?? []
            let want = !page.account.isEmpty ? page.account : (accounts.count == 1 ? accounts[0] : "")
            guard !want.isEmpty, accounts.contains(where: { $0.caseInsensitiveCompare(want) == .orderedSame }) else {
                return false
            }
            web.callAsyncJavaScript("return kestrel.choose(email)", arguments: ["email": want], in: nil,
                                    in: .defaultClient, completionHandler: nil)
            return true
        }
        let hint = !page.account.isEmpty ? page.account : (state["shown"] as? String ?? "")
        guard let login = Logins.shared.pick(host: host, hint: hint) else { return false }
        web.callAsyncJavaScript("return kestrel.fill(user, password, true)",
                                arguments: ["user": login.username, "password": login.password], in: nil,
                                in: .defaultClient, completionHandler: nil)
        return true
    }

    // The reader answers pages' questions by itself: no pop-up windows, no downloads, OK to alerts.
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if navigationAction.targetFrame == nil { webView.load(navigationAction.request) }
        return nil
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        let scheme = navigationAction.request.url?.scheme?.lowercased() ?? ""
        decisionHandler(["http", "https", "about", "blob", "data"].contains(scheme) && !navigationAction.shouldPerformDownload
                        ? .allow : .cancel)
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        decisionHandler(navigationResponse.canShowMIMEType ? .allow : .cancel)
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        completionHandler()
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        completionHandler(false)
    }
}

/// One browser tab: its own window, which macOS shows as a tab next to the others.
final class BrowserTab: NSObject, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    static let group = "KestrelBrowser"
    unowned let browser: Browser
    let web: WKWebView
    var window: NSWindow?
    let address = NSTextField()
    let status = NSTextField(labelWithString: "")
    let bookmarkBar = NSStackView()
    var back: NSButton!
    var forward: NSButton!
    var watchers: [NSKeyValueObservation] = []
    var downloads: [ObjectIdentifier: URL] = [:]
    var statusTimer: Timer?

    init(browser: Browser, configuration: WKWebViewConfiguration) {
        self.browser = browser
        web = WKWebView(frame: .zero, configuration: configuration)
        super.init()
        web.navigationDelegate = self
        web.uiDelegate = self
        web.allowsBackForwardNavigationGestures = true
        web.allowsMagnification = true
        build()
    }

    func button(_ symbol: String, _ tip: String, _ action: Selector) -> NSButton {
        let image = NSImage(systemSymbolName: symbol, accessibilityDescription: tip) ?? NSImage()
        let b = NSButton(image: image, target: self, action: action)
        b.toolTip = tip
        return b
    }

    func build() {
        back = button("chevron.left", "Back", #selector(goBack))
        forward = button("chevron.right", "Forward", #selector(goForward))
        let reload = button("arrow.clockwise", "Reload this page", #selector(refresh))
        address.placeholderString = "Search Google or type a web address"
        address.target = self
        address.action = #selector(go)
        address.cell?.isScrollable = true
        address.cell?.wraps = false
        address.cell?.usesSingleLineMode = true
        address.setContentHuggingPriority(.defaultLow, for: .horizontal)
        let add = NSButton(title: "Add to Today", target: self, action: #selector(addToToday))
        add.toolTip = "Kestrel reads the assignments on this page onto Today, and re-reads it by itself every few hours"
        let key = button("key.fill", "Saved passwords for this site", #selector(showLogins))
        let top = NSStackView(views: [back, forward, reload, address, add, key])
        top.orientation = .horizontal
        top.spacing = 6
        top.edgeInsets = NSEdgeInsets(top: 6, left: 10, bottom: 4, right: 10)
        bookmarkBar.orientation = .horizontal
        bookmarkBar.spacing = 2
        bookmarkBar.alignment = .centerY
        bookmarkBar.edgeInsets = NSEdgeInsets(top: 0, left: 8, bottom: 4, right: 8)
        fillBookmarks()
        status.textColor = .secondaryLabelColor
        status.font = .systemFont(ofSize: 12)
        status.lineBreakMode = .byTruncatingTail
        status.isHidden = true
        let line = NSBox()
        line.boxType = .separator
        let content = NSView()
        for view in [top, bookmarkBar, line, web, status] as [NSView] {
            view.translatesAutoresizingMaskIntoConstraints = false
            content.addSubview(view)
        }
        NSLayoutConstraint.activate([
            top.topAnchor.constraint(equalTo: content.topAnchor),
            top.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            top.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            bookmarkBar.topAnchor.constraint(equalTo: top.bottomAnchor),
            bookmarkBar.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            bookmarkBar.trailingAnchor.constraint(lessThanOrEqualTo: content.trailingAnchor),
            line.topAnchor.constraint(equalTo: bookmarkBar.bottomAnchor),
            line.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            line.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            web.topAnchor.constraint(equalTo: line.bottomAnchor),
            web.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            web.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            web.bottomAnchor.constraint(equalTo: content.bottomAnchor),
            status.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 12),
            status.trailingAnchor.constraint(lessThanOrEqualTo: content.trailingAnchor, constant: -12),
            status.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -6),
        ])
        status.wantsLayer = true
        status.drawsBackground = true
        status.backgroundColor = .windowBackgroundColor

        let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1200, height: 860),
                         styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        w.title = "Kestrel Browser"
        w.contentView = content
        w.tabbingIdentifier = BrowserTab.group
        w.tabbingMode = .automatic
        w.isReleasedWhenClosed = false
        w.minSize = NSSize(width: 600, height: 420)
        w.delegate = self
        window = w

        watchers = [
            web.observe(\.url, options: [.initial, .new]) { [weak self] _, _ in self?.showAddress() },
            web.observe(\.title, options: [.new]) { [weak self] web, _ in
                let title = web.title ?? ""
                self?.window?.title = title.isEmpty ? "Kestrel Browser" : title
            },
            web.observe(\.canGoBack, options: [.initial, .new]) { [weak self] web, _ in self?.back.isEnabled = web.canGoBack },
            web.observe(\.canGoForward, options: [.initial, .new]) { [weak self] web, _ in
                self?.forward.isEnabled = web.canGoForward
            },
        ]
    }

    func fillBookmarks() {
        bookmarkBar.arrangedSubviews.forEach { $0.removeFromSuperview() }
        for (index, mark) in browser.bookmarks.enumerated() where mark.count == 2 {
            let b = NSButton(title: mark[0], target: self, action: #selector(openBookmark(_:)))
            b.bezelStyle = .recessed
            b.showsBorderOnlyWhileMouseInside = true
            b.tag = index
            b.toolTip = mark[1]
            let menu = NSMenu()
            let remove = NSMenuItem(title: "Remove Bookmark", action: #selector(removeBookmark(_:)), keyEquivalent: "")
            remove.target = self
            remove.tag = index
            menu.addItem(remove)
            b.menu = menu
            bookmarkBar.addArrangedSubview(b)
        }
    }

    func showAddress() {
        guard address.currentEditor() == nil else { return }     // you're typing in it
        let url = web.url?.absoluteString ?? ""
        address.stringValue = url == "about:blank" ? "" : url
    }

    func focusAddress() {
        window?.makeFirstResponder(address)
        address.selectText(nil)
    }

    /// A short message at the bottom of the window, for 15 seconds.
    func say(_ text: String) {
        status.stringValue = " \(text) "
        status.isHidden = false
        statusTimer?.invalidate()
        statusTimer = Timer.scheduledTimer(withTimeInterval: 15, repeats: false) { [weak self] _ in
            self?.status.isHidden = true
        }
    }

    // MARK: buttons and menus (the menus reach the front tab through the responder chain)
    @objc func go() {
        guard let url = addressURL(address.stringValue) else { return }
        web.load(URLRequest(url: url))
        window?.makeFirstResponder(web)
    }

    @objc func goBack() { web.goBack() }
    @objc func goForward() { web.goForward() }
    @objc func refresh() { web.reload() }
    @objc func openLocation() { focusAddress() }
    @objc func zoomIn() { web.pageZoom = min(3, web.pageZoom + 0.1) }
    @objc func zoomOut() { web.pageZoom = max(0.5, web.pageZoom - 0.1) }
    @objc func actualSize() { web.pageZoom = 1 }
    @objc func newWindowForTab(_ sender: Any?) { browser.newTab(nil) }       // the + in the tab bar

    @objc func openBookmark(_ sender: NSButton) {
        let marks = browser.bookmarks
        guard sender.tag < marks.count, let url = URL(string: marks[sender.tag][1]) else { return }
        if NSEvent.modifierFlags.contains(.command) {
            browser.newTab(url, behind: true)
        } else {
            web.load(URLRequest(url: url))
        }
    }

    @objc func removeBookmark(_ sender: NSMenuItem) {
        var marks = browser.bookmarks
        guard sender.tag < marks.count else { return }
        marks.remove(at: sender.tag)
        browser.bookmarks = marks
    }

    @objc func bookmarkPage() {
        guard let url = web.url?.absoluteString, url.hasPrefix("http") else { return }
        var marks = browser.bookmarks
        if marks.contains(where: { $0.count == 2 && $0[1] == url }) { say("It's already in your bookmarks."); return }
        var name = (web.title ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if name.isEmpty { name = web.url?.host ?? url }
        if name.count > 28 { name = String(name.prefix(27)) + "…" }
        marks.append([name, url])
        browser.bookmarks = marks
        say("Bookmarked: \(name). Right-click a bookmark to remove it.")
    }

    @objc func addToToday() {
        guard web.url?.scheme == "https" else { say("Open the page that lists your work first."); return }
        say("Reading this page…")
        browser.capture(web, page: nil, auto: false) { [weak self] answer in
            self?.say(answer["message"] as? String ?? answer["error"] as? String ?? "Done.")
        }
    }

    @objc func copyWhatKestrelSaw() {
        guard web.url?.scheme == "https" else { say("Open a web page first."); return }
        browser.capture(web, page: nil, auto: false, action: "web-report") { [weak self] answer in
            guard let text = answer["text"] as? String else {
                self?.say(answer["error"] as? String ?? "Kestrel couldn't read this page.")
                return
            }
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(text, forType: .string)
            self?.say("Copied what Kestrel saw on this page: paste it into your chat with Claude.")
        }
    }

    @objc func showLogins() {
        let menu = NSMenu()
        let host = web.url?.host ?? ""
        let saved = Logins.shared.matching(host: host)
        if saved.isEmpty {
            menu.addItem(withTitle: host.isEmpty ? "No saved passwords here" : "No saved passwords for \(host)",
                         action: nil, keyEquivalent: "")
        }
        for login in saved {
            let item = NSMenuItem(title: "Fill in \(login.username.isEmpty ? "the password" : login.username)",
                                  action: #selector(fillLogin(_:)), keyEquivalent: "")
            item.target = self
            item.representedObject = login.username
            menu.addItem(item)
        }
        menu.addItem(.separator())
        let all = NSMenuItem(title: "Saved Passwords…", action: #selector(savedPasswords), keyEquivalent: "")
        all.target = self
        menu.addItem(all)
        _ = menu.popUp(positioning: nil, at: NSEvent.mouseLocation, in: nil)
    }

    @objc func fillLogin(_ item: NSMenuItem) {
        guard let user = item.representedObject as? String, let host = web.url?.host,
              let login = Logins.shared.find(host: host, username: user) else { return }
        web.callAsyncJavaScript("return window.kestrel ? kestrel.fill(user, password, false) : ''",
                                arguments: ["user": login.username, "password": login.password], in: nil,
                                in: .defaultClient, completionHandler: nil)
    }

    @objc func savedPasswords() { browser.showSetup("school") }

    // MARK: the window
    func windowWillClose(_ notification: Notification) {
        watchers.forEach { $0.invalidate() }
        watchers = []
        statusTimer?.invalidate()
        web.stopLoading()
        browser.closed(self)
    }

    // MARK: pages
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        let scheme = url.scheme?.lowercased() ?? ""
        if !["http", "https", "about", "blob", "data"].contains(scheme) {    // mailto:, zoommtg:… go to their apps
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
            return
        }
        if navigationAction.shouldPerformDownload {
            decisionHandler(.download)
            return
        }
        if navigationAction.navigationType == .linkActivated, navigationAction.modifierFlags.contains(.command) {
            browser.newTab(url, behind: true)                          // ⌘-click: a new tab behind this one
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        decisionHandler(navigationResponse.canShowMIMEType ? .allow : .download)
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        let code = (error as NSError).code
        if code == NSURLErrorCancelled || code == 102 { return }       // you went elsewhere, or it became a download
        say("Couldn't open the page: \(error.localizedDescription)")
    }

    // pop-ups and links that open a new window: a new tab (sign-in pop-ups keep working)
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        browser.newTab(nil, configuration: configuration).web
    }

    func webViewDidClose(_ webView: WKWebView) {
        window?.close()
    }

    // uploads (turning work in, attaching a file)
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.canChooseDirectories = parameters.allowsDirectories
        panel.canChooseFiles = true
        if let window = window {
            panel.beginSheetModal(for: window) { answer in completionHandler(answer == .OK ? panel.urls : nil) }
        } else {
            completionHandler(panel.runModal() == .OK ? panel.urls : nil)
        }
    }

    // the page's own questions
    func ask(_ alert: NSAlert, done: @escaping (NSApplication.ModalResponse) -> Void) {
        if let window = window {
            alert.beginSheetModal(for: window, completionHandler: done)
        } else {
            done(alert.runModal())
        }
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = NSAlert()
        alert.messageText = frame.securityOrigin.host
        alert.informativeText = message
        alert.addButton(withTitle: "OK")
        ask(alert) { _ in completionHandler() }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = NSAlert()
        alert.messageText = frame.securityOrigin.host
        alert.informativeText = message
        alert.addButton(withTitle: "OK")
        alert.addButton(withTitle: "Cancel")
        ask(alert) { answer in completionHandler(answer == .alertFirstButtonReturn) }
    }

    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
        let alert = NSAlert()
        alert.messageText = frame.securityOrigin.host
        alert.informativeText = prompt
        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 300, height: 24))
        field.stringValue = defaultText ?? ""
        alert.accessoryView = field
        alert.addButton(withTitle: "OK")
        alert.addButton(withTitle: "Cancel")
        ask(alert) { answer in completionHandler(answer == .alertFirstButtonReturn ? field.stringValue : nil) }
    }

    // downloads go to your Downloads folder
    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = self
    }

    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
        download.delegate = self
    }

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String,
                  completionHandler: @escaping (URL?) -> Void) {
        let folder = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask)[0]
        let name = suggestedFilename.isEmpty ? "download" : suggestedFilename
        let base = (name as NSString).deletingPathExtension, ext = (name as NSString).pathExtension
        var target = folder.appendingPathComponent(name)
        var n = 1
        while FileManager.default.fileExists(atPath: target.path) {
            n += 1
            target = folder.appendingPathComponent(ext.isEmpty ? "\(base) \(n)" : "\(base) \(n).\(ext)")
        }
        downloads[ObjectIdentifier(download)] = target
        say("Downloading \(target.lastPathComponent)…")
        completionHandler(target)
    }

    func downloadDidFinish(_ download: WKDownload) {
        let target = downloads.removeValue(forKey: ObjectIdentifier(download))
        say("Downloaded \(target?.lastPathComponent ?? "the file") to your Downloads folder.")
    }

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        downloads.removeValue(forKey: ObjectIdentifier(download))
        say("The download didn't finish: \(error.localizedDescription)")
    }
}
