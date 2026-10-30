// @(#)NavLinkPacket.swift 2.3.navlink.1 2026/10/30 09:51:08
import Foundation

/// NavLink v1. Explicit little-endian fields; no Swift ABI padding on the wire.
struct NavLinkPacket {
    var session: UInt64 = 1
    var sequence: UInt32 = 0
    var flags: UInt16 = 0
    var tracking: UInt8 = 0
    var reason: UInt8 = 0
    var frameUS: UInt64 = 0
    var sendUS: UInt64 = 0
    var imuUS: UInt64 = 0
    // x, y, z, heading, roll, pitch, forward speed, left speed, yaw rate,
    // acceleration x/y/z, interval acceleration peak and RMS.
    var measurements = [Float](repeating: 0, count: 14)
    var features: UInt16 = 0
    var imuSamples: UInt16 = 0
    var frameAgeUS: UInt32 = .max
    var batteryPercent: UInt8 = 255
    var batteryState: UInt8 = 0

    static func microseconds(_ seconds: TimeInterval) -> UInt64 {
        guard seconds.isFinite, seconds > 0 else { return 0 }
        return UInt64(min(seconds * 1_000_000, Double(UInt64.max / 2)))
    }

    func encoded() -> Data {
        precondition(measurements.count == 14 && measurements.allSatisfy { $0.isFinite })
        var data = Data("NVLK".utf8)
        func append<T: FixedWidthInteger>(_ number: T) {
            var value = number.littleEndian
            withUnsafeBytes(of: &value) { data.append(contentsOf: $0) }
        }
        append(UInt8(1)) // protocol version
        append(UInt8(1)) // observation packet
        append(UInt16(128))
        append(session)
        append(UInt64(0)) // no surveyed room/mount alignment in this milestone
        append(sequence)
        append(flags)
        append(tracking)
        append(reason)
        append(frameUS)
        append(sendUS)
        append(imuUS)
        for value in measurements { append(value.bitPattern) }
        append(features)
        append(imuSamples)
        append(frameAgeUS)
        append(batteryPercent)
        append(batteryState)
        data.append(contentsOf: repeatElement(UInt8(0), count: 6))
        precondition(data.count == 128)
        return data
    }
}
