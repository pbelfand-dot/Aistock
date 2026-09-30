// Kestrel.app (formerly "AI Trader"): a real Mac app window for the bot.
//
// The window shows the dashboard (aitrader/web/dashboard.html) with Apple's WebKit, the same engine
// as Safari, but inside this app: no browser and no web server. When the page needs data or a button
// is pressed, it sends a message to this app, which runs the bot's helper
// (`python -m aitrader.app_api ...` in ~/AITrader) and hands back its answer.
//
// First launch (or after an update that needs new libraries): the Setup menu opens in Terminal to
// install Python and the bot's libraries, and this window waits until that's done.
// Updates: the app updates itself from its download page (updater.swift).
import Cocoa
import WebKit

let env = ProcessInfo.processInfo.environment
let appHome = URL(fileURLWithPath: env["AITRADER_HOME"] ?? NSHomeDirectory() + "/AITrader")
let python = URL(fileURLWithPath: env["AITRADER_PYTHON"] ?? appHome.path + "/.venv/bin/python")
let selfTest = CommandLine.arguments.contains("--self-test")      // the build machine's check
let bridgeActions: Set<String> = ["snapshot", "pause", "kill", "demo-build", "setup-status", "save-keys",
                                   "check-keys", "autopilot-on", "autopilot-off", "resume"]

/// Python and the bot's libraries are installed, and match this version of the app.
func botIsReady() -> Bool {
    guard FileManager.default.isExecutableFile(atPath: python.path) else { return false }
    if selfTest { return true }
    let wanted = try? Data(contentsOf: appHome.appendingPathComponent("requirements.txt"))
    let installed = try? Data(contentsOf: appHome.appendingPathComponent(".venv/.installed-requirements"))
    return wanted != nil && wanted == installed
}

func jsonError(_ message: String) -> String {
    let data = try? JSONSerialization.data(withJSONObject: ["error": message])
    return data.flatMap { String(data: $0, encoding: .utf8) } ?? "{\"error\": \"failed\"}"
}

/// The bot's own messages go to ~/AITrader/data/app.log.
func logFile() -> FileHandle {
    let url = appHome.appendingPathComponent("data/app.log")
    try? FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
    if !FileManager.default.fileExists(atPath: url.path) {
        FileManager.default.createFile(atPath: url.path, contents: nil)
    }
    guard let handle = try? FileHandle(forWritingTo: url) else { return FileHandle.nullDevice }
    handle.seekToEndOfFile()
    return handle
}

/// Asks the bot: runs `python -m aitrader.app_api <args>` and returns the JSON it prints.
/// `input` goes to the bot's standard input (used for keys, so they never appear in a process list).
func askBot(_ args: [String], input: String? = nil) -> String {
    let process = Process()
    process.executableURL = python
    process.arguments = ["-m", "aitrader.app_api"] + args
    process.currentDirectoryURL = appHome
    let output = Pipe()
    let inputPipe = Pipe()
    let log = logFile()
    process.standardOutput = output
    process.standardInput = inputPipe
    process.standardError = log
    defer { if log !== FileHandle.nullDevice { log.closeFile() } }
    do { try process.run() } catch {
        return jsonError("Couldn't start the bot: \(error.localizedDescription)")
    }
    if let input = input, let data = input.data(using: .utf8) { inputPipe.fileHandleForWriting.write(data) }
    try? inputPipe.fileHandleForWriting.close()
    let data = output.fileHandleForReading.readDataToEndOfFile()
    process.waitUntilExit()
    let text = String(data: data, encoding: .utf8) ?? ""
    return text.isEmpty ? jsonError("The bot stopped unexpectedly. Details: AITrader/data/app.log") : text
}

let setupPage = """
<!doctype html><html><head><meta charset="utf-8"><style>
body { font: 15px/1.5 -apple-system, system-ui, sans-serif; margin: 0; display: grid; place-items: center;
       height: 100vh; background: #0b2a4a; color: #fff; text-align: center; }
p { color: #b9c8da; max-width: 460px; }
</style></head><body><div><h2>Setting up Kestrel</h2>
<p>The first time (and after some updates), the Setup window in Terminal installs Python and the bot's
libraries. It takes about 2 minutes. This window opens your dashboard as soon as it's done.</p></div>
</body></html>
"""

final class AppController: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKScriptMessageHandlerWithReply {
    var window: NSWindow!
    var web: WKWebView!
    var demoItem: NSMenuItem!
    var demo = false
    var waiting: Timer?
    var autoUpdateItem: NSMenuItem!
    var updateTimer: Timer?
    var updating = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        buildMenus()
        let config = WKWebViewConfiguration()
        config.userContentController.addScriptMessageHandler(self, contentWorld: .page, name: "aitrader")
        if selfTest {                                     // the build machine's check: no first-run Setup popup
            config.userContentController.addUserScript(WKUserScript(source: "window.aitraderTesting = true;",
                                                                    injectionTime: .atDocumentStart,
                                                                    forMainFrameOnly: true))
        }
        web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = self
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1280, height: 860),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "Kestrel"
        window.minSize = NSSize(width: 420, height: 560)
        window.contentView = web
        window.center()
        window.setFrameAutosaveName("AITraderMainWindow")
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        if selfTest {
            DispatchQueue.main.asyncAfter(deadline: .now() + 300) { print("SELF-TEST FAILED: timed out"); exit(1) }
        } else {
            installOrUpdate()
            startUpdateChecks()
        }
        if botIsReady() {
            loadDashboard()
        } else {
            web.loadHTMLString(setupPage, baseURL: nil)
            openSetupMenu()
            waiting = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] timer in
                if botIsReady() { timer.invalidate(); self?.loadDashboard() }
            }
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    /// Copies this version of the bot into ~/AITrader (your keys and data stay). Quick.
    func installOrUpdate() {
        guard let script = Bundle.main.url(forResource: "install", withExtension: "sh") else { return }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/bash")
        process.arguments = [script.path]
        try? process.run()
        process.waitUntilExit()
    }

    func loadDashboard() {
        let page = appHome.appendingPathComponent("aitrader/web/dashboard.html")
        web.loadFileURL(page, allowingReadAccessTo: page.deletingLastPathComponent())
    }

    // MARK: the page asks, the bot answers
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage,
                               replyHandler: @escaping (Any?, String?) -> Void) {
        guard let body = message.body as? [String: Any], let action = body["action"] as? String else {
            replyHandler(nil, "bad message"); return
        }
        if action == "open-menu" { openSetupMenu(); replyHandler("{}", nil); return }
        if action == "app-version" { replyHandler("{\"version\": \"\(currentVersion())\"}", nil); return }
        if action == "check-updates" { checkForUpdates(userAsked: true); replyHandler("{}", nil); return }
        guard bridgeActions.contains(action) else { replyHandler(nil, "unknown action"); return }
        var args = [action]
        if body["demo"] as? Bool == true { args.append("--demo") }
        if let confirm = body["confirm"] as? String { args += ["--confirm", confirm] }
        let input = body["input"] as? String
        DispatchQueue.global(qos: .userInitiated).async {
            let answer = askBot(args, input: input)
            DispatchQueue.main.async { replyHandler(answer, nil) }
        }
    }

    // Links to websites open in your browser; the app window only ever shows the dashboard.
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let url = navigationAction.request.url, url.scheme == "http" || url.scheme == "https" {
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
        } else {
            decisionHandler(.allow)
        }
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        guard selfTest, webView.url?.isFileURL == true else { return }
        webView.callAsyncJavaScript("return await window.aitraderSelfTest();", arguments: [:], in: nil, in: .page) { result in
            switch result {
            case .success(let value):
                let summary = "\(value)"
                print("SELF-TEST: \(summary)")
                self.saveScreenshot { exit(summary.hasPrefix("OK") ? 0 : 1) }
            case .failure(let error):
                print("SELF-TEST FAILED: \(error)")
                exit(1)
            }
        }
    }

    func saveScreenshot(then done: @escaping () -> Void) {
        guard let path = env["AITRADER_SCREENSHOT"] else { done(); return }
        web.takeSnapshot(with: nil) { image, _ in
            if let tiff = image?.tiffRepresentation, let bitmap = NSBitmapImageRep(data: tiff),
               let png = bitmap.representation(using: .png, properties: [:]) {
                try? png.write(to: URL(fileURLWithPath: path))
            }
            done()
        }
    }

    // MARK: menus
    @objc func openSetupMenu() {
        if selfTest { return }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        process.arguments = ["-a", "Terminal", appHome.appendingPathComponent("Kestrel Menu.command").path]
        try? process.run()
    }

    @objc func refresh() {
        web.evaluateJavaScript("window.aitraderRefresh && window.aitraderRefresh(); 0", completionHandler: nil)
    }

    @objc func toggleDemo() {
        demo.toggle()
        demoItem.state = demo ? .on : .off
        web.evaluateJavaScript("window.aitraderSetDemo && window.aitraderSetDemo(\(demo)); 0", completionHandler: nil)
    }

    func buildMenus() {
        let main = NSMenu()

        let app = NSMenu(title: "Kestrel")
        app.addItem(withTitle: "About Kestrel",
                    action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        app.addItem(withTitle: "Check for Updates…", action: #selector(checkForUpdatesNow), keyEquivalent: "").target = self
        autoUpdateItem = app.addItem(withTitle: "Update Automatically (asks first when real money is on)",
                                     action: #selector(toggleAutomaticUpdates), keyEquivalent: "")
        autoUpdateItem.target = self
        autoUpdateItem.state = updatesAutomatically ? .on : .off
        app.addItem(.separator())
        app.addItem(withTitle: "Setup Menu (keys, plans, autopilot)…",
                    action: #selector(openSetupMenu), keyEquivalent: ",").target = self
        app.addItem(.separator())
        app.addItem(withTitle: "Hide Kestrel", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        app.addItem(withTitle: "Quit Kestrel", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        main.addItem(withTitle: "Kestrel", action: nil, keyEquivalent: "").submenu = app

        let edit = NSMenu(title: "Edit")                     // so copy and paste work in the window
        edit.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z")
        edit.addItem(withTitle: "Redo", action: Selector(("redo:")), keyEquivalent: "Z")
        edit.addItem(.separator())
        edit.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        main.addItem(withTitle: "Edit", action: nil, keyEquivalent: "").submenu = edit

        let view = NSMenu(title: "View")
        view.addItem(withTitle: "Refresh", action: #selector(refresh), keyEquivalent: "r").target = self
        demoItem = view.addItem(withTitle: "Show Demo Data (made-up prices)", action: #selector(toggleDemo),
                                keyEquivalent: "d")
        demoItem.target = self
        view.addItem(.separator())
        let fullScreen = view.addItem(withTitle: "Enter Full Screen",
                                      action: #selector(NSWindow.toggleFullScreen(_:)), keyEquivalent: "f")
        fullScreen.keyEquivalentModifierMask = [.command, .control]
        main.addItem(withTitle: "View", action: nil, keyEquivalent: "").submenu = view

        let windowMenu = NSMenu(title: "Window")
        windowMenu.addItem(withTitle: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        windowMenu.addItem(withTitle: "Zoom", action: #selector(NSWindow.performZoom(_:)), keyEquivalent: "")
        main.addItem(withTitle: "Window", action: nil, keyEquivalent: "").submenu = windowMenu

        NSApp.mainMenu = main
        NSApp.windowsMenu = windowMenu
    }
}

if CommandLine.arguments.contains("--update-test") {      // the build machine's check (updater.swift)
    exit(runUpdateTest())
}

let application = NSApplication.shared
let controller = AppController()
application.delegate = controller
application.setActivationPolicy(.regular)
application.run()
