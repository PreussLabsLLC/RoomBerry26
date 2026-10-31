// @(#)CompassPacket.swift 3.1.compass.1 2026/10/31 12:10:00
import Foundation
import simd

/// North-referenced bearings increase clockwise; these are not odometry yaw.
struct CompassPacket {
    var session: UInt64 = 1
    var calibration: UInt64 = 0
    var sequence: UInt32 = 0
    var flags: UInt16 = 0
    // 0 unsupported, 1 acquiring, 2 usable, 3 unreliable, 4 stale, 5 error.
    var state: UInt8 = 1
    var sendUS: UInt64 = 0
    var sampleUS: UInt64 = 0
    var sampleEpochUS: UInt64 = 0
    // Phone/robot magnetic bearing, accuracy, device field X/Y/Z (µT),
    // field magnitude (µT), mount yaw (radians).
    var values: [Float] = [0,0,-1,0,0,0,0,0]
    private var headingMeasured = false
    private var fieldMeasured = false
    static func bearing(_ degrees: Double) -> Double {
        let wrapped = degrees.truncatingRemainder(dividingBy: 360)
        return (wrapped < 0 ? wrapped+360 : wrapped) * .pi/180
    }
    mutating func update(magneticDegrees: Double, accuracyDegrees: Double,
                         field: SIMD3<Double>, sampleUS: UInt64, epochUS: UInt64,
                         mountYawDegrees: Double) {
        self.sampleUS = sampleUS; self.sampleEpochUS = epochUS
        headingMeasured = magneticDegrees.isFinite && (0..<360).contains(magneticDegrees)
            && accuracyDegrees.isFinite && accuracyDegrees >= 0 && accuracyDegrees <= 20
            && mountYawDegrees.isFinite && abs(mountYawDegrees) <= 360
        fieldMeasured = [field.x,field.y,field.z].allSatisfy { $0.isFinite && abs($0) < 1e6 }
        values[0] = magneticDegrees.isFinite && (0..<360).contains(magneticDegrees) ? Float(Self.bearing(magneticDegrees)) : 0
        values[1] = headingMeasured ? Float(Self.bearing(magneticDegrees+mountYawDegrees)) : 0
        values[2] = accuracyDegrees.isFinite && abs(accuracyDegrees) < 1e6 ? Float(accuracyDegrees * .pi/180) : -1
        values[3] = fieldMeasured ? Float(field.x) : 0; values[4] = fieldMeasured ? Float(field.y) : 0
        values[5] = fieldMeasured ? Float(field.z) : 0; values[6] = fieldMeasured ? Float(simd_length(field)) : 0
        values[7] = mountYawDegrees.isFinite && abs(mountYawDegrees) <= 360 ? Float(mountYawDegrees * .pi/180) : 0
    }
    mutating func prepare(nowUS: UInt64) {
        sendUS = nowUS; flags = 0
        guard sampleUS > 0 else { return }
        guard sampleUS <= nowUS, nowUS-sampleUS <= 1_000_000 else { state = 4; return }
        state = headingMeasured ? 2 : 3
        if fieldMeasured { flags |= 2 }
        if headingMeasured { flags |= 5 } // phone heading + calibrated robot bearing
    }
    mutating func fail() { sampleUS = 0; sampleEpochUS = 0; flags = 0; state = 5 }
    func encoded() -> Data {
        precondition(values.count == 8 && values.allSatisfy { $0.isFinite })
        var d = Data("NVLK".utf8)
        func put<T: FixedWidthInteger>(_ n: T) {
            var v = n.littleEndian
            withUnsafeBytes(of: &v) { d.append(contentsOf: $0) }
        }
        put(UInt8(1)); put(UInt8(4)); put(UInt16(128))
        put(session); put(calibration); put(sequence); put(flags); put(state); put(UInt8(0))
        put(sendUS); put(sampleUS); values.forEach { put($0.bitPattern) }; put(sampleEpochUS)
        d.append(contentsOf: repeatElement(UInt8(0),count: 40))
        precondition(d.count == 128)
        return d
    }
}
