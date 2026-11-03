// @(#)ReportingCheck.swift 3.1.threading.1 2026/10/31 14:30:00
import Foundation

@main struct ReportingCheck {
    static func main() {
        let snapshot = GroundPacketSnapshot()
        var p = GroundPacket()
        p.session = 11; p.calibration = 22; p.continuity = 3
        p.flags = 7; p.state = 2; p.reason = 0
        p.startUS = 9_966_667; p.endUS = 10_000_000
        p.accepted = 42; p.values[0] = 123; p.values[7] = 85; p.values[9] = 0.033333
        p.inliers = 30; p.candidates = 40
        snapshot.activate(p)
        p.values[0] = 999
        assert(snapshot.load()!.values[0] == 123) // independent value snapshot
        let fresh = snapshot.load()!.reportingCopy(now: 10.1, sequence: 1, battery: (88,1))
        assert(fresh.flags == 7 && fresh.values[0] == 123 && fresh.sequence == 1)
        let stale = snapshot.load()!.reportingCopy(now: 10.3, sequence: 2, battery: (87,1))
        assert(stale.flags == 2 && stale.state == 1 && stale.reason == 4)
        assert(stale.values[0] == 0 && stale.values[7] == 85 && stale.inliers == 0)
        assert(stale.continuity == 3 && stale.accepted == 42 && stale.battery == 87)
        assert(snapshot.load()!.flags == 7 && snapshot.load()!.values[0] == 123)
        // A blocked camera queue cannot block periodic snapshot reporting.
        let capture = DispatchQueue(label: "check.capture")
        let reporting = DispatchQueue(label: "check.reporting")
        let blocked = DispatchSemaphore(value: 0), release = DispatchSemaphore(value: 0)
        capture.async { blocked.signal(); release.wait() }
        assert(blocked.wait(timeout: .now()+1) == .success)
        let ticks = DispatchSemaphore(value: 0)
        let timer = DispatchSource.makeTimerSource(queue: reporting)
        timer.schedule(deadline: .now(), repeating: .milliseconds(100))
        timer.setEventHandler {
            assert(snapshot.load()!.reportingCopy(now: 11, sequence: 3, battery: (88,1)).flags == 2)
            ticks.signal()
        }
        timer.resume()
        for _ in 0..<6 { assert(ticks.wait(timeout: .now()+0.5) == .success) }
        timer.cancel(); reporting.sync {}; release.signal(); capture.sync {}
        // Concurrent reads must never see a partially updated packet.
        let group = DispatchGroup()
        for writer in 0..<2 {
            group.enter()
            DispatchQueue.global().async {
                for i in 1...5000 {
                    var value = GroundPacket()
                    value.accepted = UInt32(i+writer*5000)
                    value.values[0] = Float(value.accepted)
                    snapshot.store(value)
                    let read = snapshot.load()!
                    assert(read.values[0] == Float(read.accepted))
                }
                group.leave()
            }
        }
        assert(group.wait(timeout: .now()+5) == .success)
        snapshot.store(nil); assert(snapshot.load() == nil)
        snapshot.store(p); assert(snapshot.load() == nil) // late camera callback after Stop
        snapshot.activate(p); assert(snapshot.load() != nil)
        snapshot.store(nil)
        for packet in [fresh, stale] {
            print(packet.encoded().map { String(format: "%02x", $0) }.joined())
        }
        print("Reporting isolation, freshness and concurrent snapshots verified")
    }
}
