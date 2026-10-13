// logins.swift: the passwords Kestrel's browser saves (browser.swift), so it can fill them in for you and sign back in
// by itself when it re-reads your pages for Today.
//
// They stay on this Mac: ~/Library/Application Support/Kestrel/logins.sealed, sealed (AES-GCM) with a random key kept
// in your Mac's keychain as "Kestrel saved logins". Never in the bot's folder (~/AITrader), never sent anywhere; the
// bot itself never sees them.
//
// The keychain key is readable without a question each time: Kestrel has no paid Apple developer ID, so each update
// would otherwise make macOS ask for your Mac password again, and the sign-ins Kestrel does by itself, out of sight,
// would wait on that question.
import CryptoKit
import Foundation

struct SavedLogin: Codable {
    var host: String
    var username: String
    var password: String
    var saved: Date
}

private struct LoginFile: Codable {
    var logins: [SavedLogin] = []
    var never: [String] = []                       // sites you said "Never for This Site" to
}

extension Data {
    init?(hexString: String) {
        let chars = Array(hexString.utf8)
        guard chars.count % 2 == 0 else { return nil }
        var bytes: [UInt8] = []
        var i = 0
        while i < chars.count {
            guard let pair = String(bytes: chars[i..<i + 2], encoding: .utf8), let byte = UInt8(pair, radix: 16) else {
                return nil
            }
            bytes.append(byte)
            i += 2
        }
        self.init(bytes)
    }
}

final class Logins {
    static let shared = Logins()
    private var store: LoginFile?
    let file = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Application Support/Kestrel/logins.sealed")
    let service = "Kestrel saved logins"

    /// Runs Apple's `security` tool (the keychain's own command): (exit status, what it printed).
    private func security(_ args: [String]) -> (Int32, String) {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/security")
        process.arguments = args
        let output = Pipe()
        process.standardOutput = output
        process.standardError = FileHandle.nullDevice
        do { try process.run() } catch { return (-1, "") }
        let data = output.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        let text = String(data: data, encoding: .utf8) ?? ""
        return (process.terminationStatus, text.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    /// The sealing key from the keychain; made (once) when create is true and there's none yet.
    private func key(create: Bool) -> SymmetricKey? {
        let (found, hex) = security(["find-generic-password", "-a", "Kestrel", "-s", service, "-w"])
        if found == 0, let data = Data(hexString: hex), data.count == 32 { return SymmetricKey(data: data) }
        guard create else { return nil }
        let fresh = SymmetricKey(size: .bits256)
        let text = fresh.withUnsafeBytes { Data($0) }.map { String(format: "%02x", $0) }.joined()
        let (added, _) = security(["add-generic-password", "-a", "Kestrel", "-s", service, "-w", text, "-A", "-U",
                                   "-j", "Kestrel's browser: seals the passwords it saved"])
        return added == 0 ? fresh : nil
    }

    private func load() -> LoginFile {
        if let store = store { return store }
        guard let sealed = try? Data(contentsOf: file) else {
            store = LoginFile()
            return store!
        }
        guard let key = key(create: false) else { return LoginFile() }     // the keychain didn't answer: ask again later
        if let box = try? AES.GCM.SealedBox(combined: sealed), let plain = try? AES.GCM.open(box, using: key),
           let decoded = try? JSONDecoder().decode(LoginFile.self, from: plain) {
            store = decoded
        } else {                                       // sealed with a key that's gone: set it aside, start a new list
            try? FileManager.default.moveItem(at: file, to: file.appendingPathExtension("unreadable"))
            store = LoginFile()
        }
        return store!
    }

    private func write(_ updated: LoginFile) {
        store = updated
        guard let key = key(create: true), let plain = try? JSONEncoder().encode(updated),
              let sealed = try? AES.GCM.seal(plain, using: key).combined else { return }
        try? FileManager.default.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
        try? sealed.write(to: file, options: [.atomic])
        try? FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: file.path)
    }

    // MARK: what the browser asks
    func matching(host: String) -> [SavedLogin] {
        let site = host.lowercased()
        return load().logins.filter { $0.host == site }
    }

    func find(host: String, username: String) -> SavedLogin? {
        matching(host: host).first { $0.username.caseInsensitiveCompare(username) == .orderedSame }
    }

    /// The login to use on a site: the one for the account the page names (hint), else the only one saved there.
    /// Google's sign-in names the account it's signing in: never another account's password there.
    func pick(host: String, hint: String) -> SavedLogin? {
        let saved = matching(host: host)
        if !hint.isEmpty, let match = saved.first(where: { $0.username.caseInsensitiveCompare(hint) == .orderedSame }) {
            return match
        }
        if !hint.isEmpty && hint.contains("@") && host.lowercased() == "accounts.google.com" { return nil }
        return saved.count == 1 ? saved[0] : nil
    }

    func save(host: String, username: String, password: String) {
        var updated = load()
        let site = host.lowercased()
        updated.logins.removeAll { $0.host == site && $0.username.caseInsensitiveCompare(username) == .orderedSame }
        updated.logins.append(SavedLogin(host: site, username: username, password: password, saved: Date()))
        updated.never.removeAll { $0 == site }
        write(updated)
    }

    func remove(host: String, username: String) {
        var updated = load()
        let site = host.lowercased()
        updated.logins.removeAll { $0.host == site && $0.username.caseInsensitiveCompare(username) == .orderedSame }
        write(updated)
    }

    func never(_ host: String) {
        var updated = load()
        if !updated.never.contains(host.lowercased()) { updated.never.append(host.lowercased()) }
        write(updated)
    }

    func isNever(_ host: String) -> Bool { load().never.contains(host.lowercased()) }

    /// For Setup → School: each saved login without its password.
    func list() -> [[String: String]] {
        let stamp = ISO8601DateFormatter()
        return load().logins.sorted { ($0.host, $0.username) < ($1.host, $1.username) }
            .map { ["host": $0.host, "username": $0.username, "saved": stamp.string(from: $0.saved)] }
    }
}
