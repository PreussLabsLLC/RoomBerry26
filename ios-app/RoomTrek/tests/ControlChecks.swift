// @(#)ControlChecks.swift 3.2.maps.1 2026/11/10 10:15:00
import Foundation
import CryptoKit

@main struct ControlChecks {
    static func main() {
        dispatchPrecondition(condition: .onQueue(.main))
        let key = Data(repeating: 65, count: 32)
        let control = TrekControl(key: key)
        var responses: [[String: Any]] = []
        var executions = 0
        var complete: ((String, String) -> Void)?
        control.send = { responses.append(control.decode($0)!) }
        control.execute = { _, finish in executions += 1; complete = finish }
        let id = UUID().uuidString
        let body: [String: Any] = ["kind": "command", "target": control.target, "id": id, "command": "NAV_START"]
        let data = control.encode(body)!
        control.receive(data)
        assert(executions == 1 && responses.last?["status"] as? String == "accepted")
        control.receive(data)
        assert(executions == 1 && responses.last?["status"] as? String == "accepted")
        complete?("failed", "relocalization_timeout")
        control.receive(data)
        assert(executions == 1 && responses.last?["detail"] as? String == "relocalization_timeout")
        var altered = body; altered["command"] = "SESSION_STOP"
        let count = responses.count
        control.receive(control.encode(altered)!)
        assert(responses.count == count && executions == 1)
        altered = body; altered["target"] = UUID().uuidString
        control.receive(control.encode(altered)!)
        assert(responses.count == count)
        let wrongKey = TrekControl(key: Data(repeating: 66, count: 32))
        control.receive(wrongKey.encode(body)!)
        control.receive(Data("invalid".utf8))
        assert(responses.count == count)
        var outer = try! JSONSerialization.jsonObject(with: data) as! [String: String]
        var payload = try! JSONSerialization.jsonObject(with: Data(base64Encoded: outer["payload"]!)!) as! [String: Any]
        payload["command"] = "SESSION_STOP"
        outer["payload"] = (try! JSONSerialization.data(withJSONObject: payload)).base64EncodedString()
        control.receive(try! JSONSerialization.data(withJSONObject: outer))
        assert(responses.count == count)
        // Even a correctly signed envelope with an old timestamp is rejected.
        var stale = body; stale["v"] = 1; stale["ts"] = Date().timeIntervalSince1970 - 60
        let stalePayload = try! JSONSerialization.data(withJSONObject: stale)
        let staleMAC = Data(HMAC<SHA256>.authenticationCode(for: stalePayload, using: SymmetricKey(data: key)))
        let staleEnvelope = try! JSONSerialization.data(withJSONObject: ["payload": stalePayload.base64EncodedString(), "mac": staleMAC.base64EncodedString()])
        control.receive(staleEnvelope)
        assert(responses.count == count)
        for name in ["STATUS", "SURVEY_START", "SURVEY_SAVE", "NAV_START", "NAV_RETRY", "SESSION_STOP", "SPEAK", "MAP_LIST", "MAP_RENAME", "MAP_DELETE"] {
            var command = body; command["id"] = UUID().uuidString; command["command"] = name
            control.receive(control.encode(command)!)
            assert(responses.last?["status"] as? String == "accepted")
            complete?("completed", name)
            assert(responses.last?["status"] as? String == "completed")
        }
        var unknown = body; unknown["id"] = UUID().uuidString; unknown["command"] = "INVALID"
        let oldExecutions = executions
        control.receive(control.encode(unknown)!)
        assert(executions == oldExecutions && responses.last?["status"] as? String == "failed")
        let shortKey = TrekControl(key: Data("1701".utf8))
        assert(shortKey.decode(shortKey.encode(["kind": "hello"])!)?["kind"] as? String == "hello")
        if let shortFixture = ProcessInfo.processInfo.environment["TREK_SHORT_KEY_FIXTURE"] {
            assert(shortKey.decode(Data(shortFixture.utf8))?["kind"] as? String == "hello")
        }
        assert(TrekControl(key: Data()).encode(body) == nil)
        let disabled = TrekControl(key: nil)
        assert(disabled.encode(body) == nil && disabled.decode(data) == nil)
        // Protocol fixture from Python: byte-exact HMAC compatibility.
        let fixture = ProcessInfo.processInfo.environment["TREK_CONTROL_FIXTURE"]
        if let fixture = fixture { assert(control.decode(Data(fixture.utf8))?["kind"] as? String == "hello") }
        if ProcessInfo.processInfo.environment["TREK_CONTROL_EMIT_FIXTURE"] != nil {
            print(String(data: control.encode(["kind": "hello", "target": control.target])!, encoding: .utf8)!)
        }
        print("RoomTrek control checks passed")
    }
}
