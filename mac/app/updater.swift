// updater.swift: AI Trader keeps itself up to date from its GitHub download page.
//
// The build machine publishes, next to AITrader-mac.zip, a small latest.json:
//     {"version": "1.0.12", "zip": "AITrader-mac.zip", "sha256": "<fingerprint of the zip>"}
// The app reads it when it opens and once a day. If there's a newer version it downloads the zip,
// checks the fingerprint, checks the new app (right version, valid signature), then swaps it in
// and restarts. Your keys and data in ~/AITrader are never touched by this; the new app's
// install.sh copies the new bot code in when it opens, as with any update.
//
// Paper trading only: it updates automatically. Real money involved (switched on, a desk LIVE, or
// real shares owned): it asks you first, so new code never takes over real money unannounced.
import Cocoa
import CryptoKit

let updateFeed = URL(string: ProcessInfo.processInfo.environment["AITRADER_UPDATE_FEED"]
                     ?? "https://github.com/pbelfand-dot/Aistock/releases/download/mac-app/latest.json")!

struct UpdateInfo {
    let version: String
    let zip: URL
    let sha256: String
}

struct UpdateError: LocalizedError {
    let errorDescription: String?
    init(_ message: String) { errorDescription = message }
}

func currentVersion() -> String {
    Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "dev"
}

func versionNumbers(_ version: String) -> [Int]? {
    let parts = version.split(separator: ".").map { Int($0) }
    guard !parts.isEmpty, !parts.contains(where: { $0 == nil }) else { return nil }
    return parts.compactMap { $0 }
}

/// "1.0.12" is newer than "1.0.9". Anything that isn't plain numbers is never "newer".
func isNewer(_ candidate: String, than current: String) -> Bool {
    guard let a = versionNumbers(candidate), let b = versionNumbers(current) else { return false }
    for i in 0..<max(a.count, b.count) {
        let x = i < a.count ? a[i] : 0, y = i < b.count ? b[i] : 0
        if x != y { return x > y }
    }
    return false
}

func logUpdate(_ line: String) {
    let log = logFile()
    let stamp = ISO8601DateFormatter().string(from: Date())
    log.write("[\(stamp)] update: \(line)\n".data(using: .utf8)!)
    if log !== FileHandle.nullDevice { log.closeFile() }
}

/// Holds the download's answer until the waiting thread reads it.
final class Answer: @unchecked Sendable {
    var result: Result<Data, Error>
    init(_ result: Result<Data, Error>) { self.result = result }
}

/// Downloads a URL (https, or file:// for the build machine's test). Call off the main thread.
func fetch(_ url: URL) throws -> Data {
    let answer = Answer(.failure(UpdateError("No answer from \(url.host ?? url.path).")))
    let done = DispatchSemaphore(value: 0)
    var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 120)
    request.setValue("AITrader/\(currentVersion())", forHTTPHeaderField: "User-Agent")
    URLSession.shared.dataTask(with: request) { data, response, error in
        if let error = error {
            answer.result = .failure(error)
        } else if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            answer.result = .failure(UpdateError("\(url.lastPathComponent): the server answered \(http.statusCode)."))
        } else {
            answer.result = .success(data ?? Data())
        }
        done.signal()
    }.resume()
    done.wait()
    return try answer.result.get()
}

/// Runs a system tool and fails with its message if it fails.
@discardableResult
func runTool(_ path: String, _ args: [String]) throws -> String {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: path)
    process.arguments = args
    let output = Pipe()
    process.standardOutput = output
    process.standardError = output
    try process.run()
    let data = output.fileHandleForReading.readDataToEndOfFile()
    process.waitUntilExit()
    let text = String(data: data, encoding: .utf8) ?? ""
    guard process.terminationStatus == 0 else {
        throw UpdateError("\((path as NSString).lastPathComponent) failed: \(text.trimmingCharacters(in: .whitespacesAndNewlines))")
    }
    return text
}

/// Why this copy of the app can't replace itself, or nil if it can.
func cannotReplace(_ app: URL) -> String? {
    if app.pathExtension != "app" { return "It isn't running as an app." }
    if versionNumbers(currentVersion()) == nil { return "This is a test build (version \(currentVersion()))." }
    if app.path.contains("/AppTranslocation/") {
        return "macOS is running it from a temporary copy. Drag AI Trader into your Applications folder and open it from there."
    }
    if !FileManager.default.isWritableFile(atPath: app.deletingLastPathComponent().path) {
        return "It can't write to the folder it's in (\(app.deletingLastPathComponent().path)). Move it to your Applications folder."
    }
    return nil
}

/// The newest version on the download page, or nil if this one is already the newest.
func checkLatest() throws -> UpdateInfo? {
    let data = try fetch(updateFeed)
    guard let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
          let version = json["version"] as? String, let zipName = json["zip"] as? String,
          let sha = json["sha256"] as? String, let zip = URL(string: zipName, relativeTo: updateFeed)?.absoluteURL
    else { throw UpdateError("The update information (latest.json) is unreadable.") }
    return isNewer(version, than: currentVersion()) ? UpdateInfo(version: version, zip: zip, sha256: sha) : nil
}

/// Downloads the new app next to this one and checks it thoroughly. Returns where it is.
func downloadAndVerify(_ update: UpdateInfo, replacing app: URL) throws -> URL {
    let staging = app.deletingLastPathComponent().appendingPathComponent(".AI Trader update \(update.version)")
    let files = FileManager.default
    try? files.removeItem(at: staging)
    try files.createDirectory(at: staging, withIntermediateDirectories: true)
    let zipData = try fetch(update.zip)
    let digest = SHA256.hash(data: zipData).map { String(format: "%02x", $0) }.joined()
    guard digest == update.sha256.lowercased() else {
        try? files.removeItem(at: staging)
        throw UpdateError("The download didn't match its fingerprint (sha256), so it wasn't installed.")
    }
    let zipFile = staging.appendingPathComponent("AITrader-mac.zip")
    try zipData.write(to: zipFile)
    try runTool("/usr/bin/ditto", ["-x", "-k", zipFile.path, staging.path])
    try? files.removeItem(at: zipFile)
    let newApp = staging.appendingPathComponent("AI Trader.app")
    let info = NSDictionary(contentsOf: newApp.appendingPathComponent("Contents/Info.plist"))
    guard info?["CFBundleShortVersionString"] as? String == update.version,
          info?["CFBundleIdentifier"] as? String == Bundle.main.bundleIdentifier else {
        try? files.removeItem(at: staging)
        throw UpdateError("The downloaded app isn't the expected AI Trader \(update.version).")
    }
    try runTool("/usr/bin/codesign", ["--verify", "--strict", newApp.path])
    _ = try? runTool("/usr/bin/xattr", ["-dr", "com.apple.quarantine", newApp.path])
    return newApp
}

/// Puts the new app in place of the old one once the old one has quit (pid), then opens it.
/// pid 0 = don't wait (the build machine's test); wait = run it now and return when done.
func swapIn(_ newApp: URL, replacing app: URL, afterQuit pid: Int32, relaunch: Bool, wait: Bool) throws {
    let script = """
    #!/bin/bash
    # AI Trader update: wait for the old app to quit, put the new one in its place, open it.
    OLD="$1"; NEW="$2"; PID="$3"; RELAUNCH="$4"
    while [ "$PID" != "0" ] && kill -0 "$PID" 2>/dev/null; do sleep 0.2; done
    rm -rf "$OLD.previous"
    if mv "$OLD" "$OLD.previous" && mv "$NEW" "$OLD"; then
      rm -rf "$OLD.previous" "$(dirname "$NEW")"
    elif [ ! -d "$OLD" ] && [ -d "$OLD.previous" ]; then
      mv "$OLD.previous" "$OLD"
    fi
    if [ "$RELAUNCH" = "yes" ]; then open -g "$OLD"; fi
    exit 0
    """
    let scriptURL = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("aitrader-update.sh")
    try script.write(to: scriptURL, atomically: true, encoding: .utf8)
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/bin/bash")
    process.arguments = [scriptURL.path, app.path, newApp.path, String(pid), relaunch ? "yes" : "no"]
    try process.run()
    if wait { process.waitUntilExit() }
}

/// What the bot says about real money. Anything unclear counts as "ask first".
func realMoneyReasons() -> [String] {
    guard botIsReady() else { return [] }                         // not set up yet: nothing is trading
    guard let data = askBot(["update-policy"]).data(using: .utf8),
          let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
          let realMoney = json["real_money"] as? Bool else {
        return ["the bot couldn't confirm that no real money is involved"]
    }
    return realMoney ? (json["reasons"] as? [String] ?? ["real money is involved"]) : []
}

/// The build machine's test: an older copy of the app updates itself to the new build.
func runUpdateTest() -> Int32 {
    let app = Bundle.main.bundleURL
    do {
        if let problem = cannotReplace(app) { throw UpdateError(problem) }
        guard let update = try checkLatest() else { throw UpdateError("no version newer than \(currentVersion())") }
        print("real money involved: \(realMoneyReasons())")
        let newApp = try downloadAndVerify(update, replacing: app)
        try swapIn(newApp, replacing: app, afterQuit: 0, relaunch: false, wait: true)
        let installed = NSDictionary(contentsOf: app.appendingPathComponent("Contents/Info.plist"))?["CFBundleShortVersionString"]
        guard installed as? String == update.version else { throw UpdateError("found \(installed ?? "nothing") after the swap") }
        print("UPDATE-TEST: OK \(currentVersion()) -> \(update.version)")
        return 0
    } catch {
        print("UPDATE-TEST FAILED: \(error.localizedDescription)")
        return 1
    }
}

extension AppController {
    var updatesAutomatically: Bool {
        UserDefaults.standard.object(forKey: "autoUpdate") as? Bool ?? true
    }

    func startUpdateChecks() {
        DispatchQueue.main.asyncAfter(deadline: .now() + 20) { [weak self] in self?.checkForUpdates(userAsked: false) }
        updateTimer = Timer.scheduledTimer(withTimeInterval: 24 * 3600, repeats: true) { [weak self] _ in
            self?.checkForUpdates(userAsked: false)
        }
    }

    @objc func checkForUpdatesNow() { checkForUpdates(userAsked: true) }

    @objc func toggleAutomaticUpdates() {
        UserDefaults.standard.set(!updatesAutomatically, forKey: "autoUpdate")
        autoUpdateItem.state = updatesAutomatically ? .on : .off
    }

    func tell(_ title: String, _ text: String) {
        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = text
        alert.runModal()
    }

    func checkForUpdates(userAsked: Bool) {
        if updating { return }
        let app = Bundle.main.bundleURL
        if let problem = cannotReplace(app) {
            logUpdate("can't update itself: \(problem)")
            if userAsked { tell("AI Trader can't update itself from here", problem) }
            return
        }
        updating = true
        DispatchQueue.global(qos: .utility).async {
            do {
                guard let update = try checkLatest() else {
                    DispatchQueue.main.async {
                        self.updating = false
                        if userAsked { self.tell("You're up to date", "AI Trader \(currentVersion()) is the newest version.") }
                    }
                    return
                }
                let reasons = realMoneyReasons()
                DispatchQueue.main.async {
                    let mustAsk = userAsked || !self.updatesAutomatically || !reasons.isEmpty
                    if mustAsk && !self.confirm(update, reasons) {
                        logUpdate("\(update.version) is available; you chose Later")
                        self.updating = false
                        return
                    }
                    self.install(update, app, userAsked: userAsked)
                }
            } catch {
                logUpdate("check failed: \(error.localizedDescription)")
                DispatchQueue.main.async {
                    self.updating = false
                    if userAsked { self.tell("Couldn't check for updates", error.localizedDescription) }
                }
            }
        }
    }

    func confirm(_ update: UpdateInfo, _ reasons: [String]) -> Bool {
        let alert = NSAlert()
        alert.messageText = "AI Trader \(update.version) is available (you have \(currentVersion()))"
        var text = "Installing takes a few seconds. AI Trader restarts, and the bot switches to the new version."
        if !reasons.isEmpty {
            text += "\n\nReal money is involved: " + reasons.joined(separator: "; ")
                + ". That's why it's asking instead of updating by itself."
        }
        alert.informativeText = text
        alert.addButton(withTitle: "Install and Restart")
        alert.addButton(withTitle: "Later")
        return alert.runModal() == .alertFirstButtonReturn
    }

    func install(_ update: UpdateInfo, _ app: URL, userAsked: Bool) {
        DispatchQueue.global(qos: .utility).async {
            do {
                let newApp = try downloadAndVerify(update, replacing: app)
                try swapIn(newApp, replacing: app, afterQuit: getpid(), relaunch: true, wait: false)
                logUpdate("installing \(update.version) (was \(currentVersion())); restarting")
                DispatchQueue.main.async { NSApp.terminate(nil) }
            } catch {
                logUpdate("install of \(update.version) failed: \(error.localizedDescription)")
                DispatchQueue.main.async {
                    self.updating = false
                    if userAsked {
                        self.tell("The update didn't install",
                                  "\(error.localizedDescription) AI Trader keeps running version \(currentVersion()).")
                    }
                }
            }
        }
    }
}
