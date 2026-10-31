// @(#)HealthPacket.swift 3.1.health.1 2026/10/31 12:00:00
import Foundation
import simd

/// Impact-like episodes, not a contact/proximity sensor. Acceleration in g.
struct BumpDetector {
    var count: UInt32 = 0
    var lastTime: Double = 0
    var lastPeakG: Double = 0
    private var previous: (time: Double, acceleration: SIMD3<Double>)?
    private var began: Double?
    private var quietSince: Double?
    private var armed = true
    mutating func sample(time: Double, acceleration a: SIMD3<Double>) -> Bool {
        guard time.isFinite, time > 0, a.x.isFinite, a.y.isFinite, a.z.isFinite else { return false }
        if let old = previous, time <= old.time { return false }
        let magnitude = simd_length(a)
        if lastTime > 0, time-lastTime <= 0.15 { lastPeakG = max(lastPeakG,magnitude) }
        let old = previous
        previous = (time,a)
        guard let old = old, time-old.time <= 0.03 else {
            began = time; quietSince = nil; return false
        }
        if began == nil { began = old.time }
        let jerk = simd_length(a-old.acceleration)/(time-old.time)
        if magnitude < 0.15 {
            if quietSince == nil { quietSince = time }
            if time-(quietSince ?? time) >= 0.08, time-lastTime >= 0.3 { armed = true }
        } else { quietSince = nil }
        guard time-(began ?? time) >= 0.3, armed else { return false }
        let impulse = (magnitude >= 0.6 && jerk >= 15) || magnitude >= 1.2
            || (magnitude >= 0.25 && jerk >= 40)
        guard impulse else { return false }
        count = count == .max ? .max : count+1
        lastTime = time; lastPeakG = magnitude; armed = false; quietSince = nil
        return true
    }
}

/// NavLink v1/type 3: sensor/health heartbeat independent of Vision processing.
struct HealthPacket {
    var session: UInt64 = 1
    var calibration: UInt64 = 0
    var sequence: UInt32 = 0
    var flags: UInt16 = 0
    var thermal: UInt8 = 255
    var batteryState: UInt8 = 0
    var sendUS: UInt64 = 0
    var imuUS: UInt64 = 0
    var bumpUS: UInt64 = 0
    var bumps: UInt32 = 0
    var samples: UInt16 = 0
    var battery: UInt8 = 255
    // Native device axes: user acceleration mm/s², rotation rad/s, gravity g;
    // interval peak user acceleration, last impact peak mm/s², app CPU percent.
    var values = [Float](repeating: 0, count: 12)
    var footprintBytes: UInt64 = 0
    var width: UInt16 = 0
    var height: UInt16 = 0
    var resourceAgeMS: UInt32 = .max
    func encoded() -> Data {
        precondition(values.count == 12 && values.allSatisfy { $0.isFinite })
        var d = Data("NVLK".utf8)
        func put<T: FixedWidthInteger>(_ n: T) {
            var v = n.littleEndian
            withUnsafeBytes(of: &v) { d.append(contentsOf: $0) }
        }
        put(UInt8(1)); put(UInt8(3)); put(UInt16(128))
        put(session); put(calibration); put(sequence); put(flags); put(thermal); put(batteryState)
        put(sendUS); put(imuUS); put(bumpUS); put(bumps); put(samples); put(battery); put(UInt8(0))
        values.forEach { put($0.bitPattern) }
        put(footprintBytes); put(width); put(height); put(resourceAgeMS)
        precondition(d.count == 128)
        return d
    }
}
