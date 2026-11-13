// @(#)TrekControl.swift 3.2.maps.1 2026/11/10 10:15:00
import Foundation
import CryptoKit

/// ARKit-independent authentication, replay protection and operation acknowledgments.
/// All access is on main; transport receive callbacks explicitly dispatch here.
final class TrekControl {
    let target = UUID().uuidString
    var execute: (([String: Any], @escaping (String, String) -> Void) -> Void)?
    var snapshot: (() -> [String: Any])?
    var send: ((Data) -> Void)?
    private var replies: [String: [String: Any]] = [:]
    private var requests: [String: Data] = [:]
    private let key: Data?

    init(key: Data?) { self.key = key.flatMap { $0.isEmpty ? nil : $0 } }

    static func loadKey() -> Data? {
        let url = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("NavLink.key")
        guard let text = try? String(contentsOf: url, encoding: .utf8) else { return nil }
        return text.trimmingCharacters(in: .whitespacesAndNewlines).data(using: .utf8)
    }

    func encode(_ body: [String: Any]) -> Data? {
        guard let key = key else { return nil }
        var body = body
        body["v"] = 1; body["ts"] = Date().timeIntervalSince1970
        guard let payload = try? JSONSerialization.data(withJSONObject: body, options: [.sortedKeys]) else { return nil }
        let mac = Data(HMAC<SHA256>.authenticationCode(for: payload, using: SymmetricKey(data: key))).base64EncodedString()
        return try? JSONSerialization.data(withJSONObject: ["payload": payload.base64EncodedString(), "mac": mac])
    }

    func decode(_ data: Data) -> [String: Any]? {
        guard data.count <= 8192, let key = key,
              let outer = (try? JSONSerialization.jsonObject(with: data)) as? [String: String],
              let p = outer["payload"], let payload = Data(base64Encoded: p),
              let m = outer["mac"], let mac = Data(base64Encoded: m),
              HMAC<SHA256>.isValidAuthenticationCode(mac, authenticating: payload, using: SymmetricKey(data: key)),
              let body = (try? JSONSerialization.jsonObject(with: payload)) as? [String: Any],
              body["v"] as? Int == 1, let ts = body["ts"] as? Double,
              abs(ts - Date().timeIntervalSince1970) <= 30 else { return nil }
        return body
    }

    func heartbeat() {
        if let data = encode(["kind": "hello", "target": target, "operation": snapshot?() ?? [:]]) { send?(data) }
    }

    func receive(_ data: Data) {
        dispatchPrecondition(condition: .onQueue(.main))
        guard let body = decode(data), body["target"] as? String == target else { return }
        if body["kind"] as? String == "challenge", let nonce = body["nonce"] as? String {
            if let reply = encode(["kind": "peer", "target": target, "nonce": nonce]) { send?(reply) }
            return
        }
        guard body["kind"] as? String == "command", let id = body["id"] as? String,
              UUID(uuidString: id) != nil, let command = body["command"] as? String else { return }
        // Retain IDs for this target's entire lifetime. Refuse work at capacity
        // instead of evicting an ID that could execute again on a late retry.
        var identity = body; identity.removeValue(forKey: "ts")
        guard let fingerprint = try? JSONSerialization.data(withJSONObject: identity, options: [.sortedKeys]) else { return }
        if let reply = replies[id] {
            guard requests[id] == fingerprint else { return }
            transmit(reply); return
        }
        guard replies.count < 10000 else {
            transmit(["kind": "response", "target": target, "id": id, "command": command,
                      "status": "failed", "detail": "Command cache full; relaunch app for a new target"])
            return
        }
        requests[id] = fingerprint
        func finish(_ state: String, _ detail: String) {
            var reply: [String: Any] = ["kind": "response", "target": self.target, "id": id,
                                       "command": command, "status": state, "detail": detail]
            reply["operation"] = self.snapshot?() ?? [:]
            self.replies[id] = reply; self.transmit(reply)
        }
        finish("accepted", "Command authenticated")
        guard ["STATUS", "SURVEY_START", "SURVEY_SAVE", "NAV_START", "NAV_RETRY", "SESSION_STOP", "SPEAK", "MAP_LIST", "MAP_RENAME", "MAP_DELETE"].contains(command) else {
            finish("failed", "Unknown command"); return
        }
        guard let execute = execute else { finish("failed", "Controller unavailable"); return }
        execute(body, finish)
    }

    private func transmit(_ body: [String: Any]) {
        if let data = encode(body) { send?(data) }
    }
}
