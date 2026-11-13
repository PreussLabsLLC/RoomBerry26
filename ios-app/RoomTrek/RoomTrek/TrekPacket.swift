// @(#)TrekPacket.swift 3.2.imu.1 2026/11/12 15:12:06
import Foundation

/// Experimental NavLink v1/type 6; see NAVLINK.md. Existing receivers
/// reject this type until upgraded. Camera pose, never robot-center pose.
struct TrekPacket {
    var session: UInt64 = 1
    var mapID: UUID?
    var sequence: UInt32 = 0
    var flags: UInt16 = 0
    var tracking: UInt8 = 0
    var reason: UInt8 = 0
    var relocalization: UInt8 = 0
    var frameUS: UInt64 = 0
    var sendUS: UInt64 = 0
    var position = SIMD3<Float>.zero
    var quaternion = SIMD4<Float>(0, 0, 0, 1)
    var yaw: Float = 0
    var features: UInt16 = 0
    var frameAgeUS: UInt32 = .max

    func encoded() -> Data {
        var data = Data("NVLK".utf8)
        func append<T: FixedWidthInteger>(_ number: T) {
            var value = number.littleEndian
            withUnsafeBytes(of: &value) { data.append(contentsOf: $0) }
        }
        append(UInt8(1)); append(UInt8(6)); append(UInt16(128))
        append(session); append(sequence); append(flags)
        append(tracking); append(reason)
        append(frameUS); append(sendUS)
        var uuid = mapID?.uuid ?? UUID(uuidString: "00000000-0000-0000-0000-000000000000")!.uuid
        withUnsafeBytes(of: &uuid) { data.append(contentsOf: $0) }
        for value in [position.x, position.y, position.z, quaternion.x, quaternion.y, quaternion.z, quaternion.w, yaw] {
            precondition(value.isFinite)
            append(value.bitPattern)
        }
        append(frameAgeUS); append(features); append(relocalization); append(UInt8(0))
        data.append(contentsOf: repeatElement(UInt8(0), count: 32))
        precondition(data.count == 128)
        return data
    }
}

/// Type 7: Core Motion diagnostics, independent of AR tracking validity.
struct TrekMotionPacket {
    var session: UInt64 = 1
    var sequence: UInt32 = 0
    var flags: UInt16 = 0
    var state: UInt8 = 0 // unavailable, starting, valid, error
    var sampleUS: UInt64 = 0
    var sendUS: UInt64 = 0
    var quaternion = SIMD4<Float>(0, 0, 0, 1)
    var gyro = SIMD3<Float>.zero // device axes, rad/s, bias corrected
    var acceleration = SIMD3<Float>.zero // device axes, gravity removed, m/s²
    var gravity = SIMD3<Float>(0, 0, -1) // device axes, g
    var integratedYaw: Float = 0 // radians about gravity-up, unwrapped
    var sampleAgeUS: UInt32 = .max
    var generation: UInt32 = 0

    func encoded() -> Data {
        var data = Data("NVLK".utf8)
        func append<T: FixedWidthInteger>(_ number: T) {
            var value = number.littleEndian
            withUnsafeBytes(of: &value) { data.append(contentsOf: $0) }
        }
        append(UInt8(1)); append(UInt8(7)); append(UInt16(128))
        append(session); append(sequence); append(flags); append(state); append(UInt8(0))
        append(sampleUS); append(sendUS)
        for v in [quaternion.x, quaternion.y, quaternion.z, quaternion.w,
                  gyro.x, gyro.y, gyro.z, acceleration.x, acceleration.y, acceleration.z,
                  gravity.x, gravity.y, gravity.z, integratedYaw] {
            precondition(v.isFinite); append(v.bitPattern)
        }
        append(sampleAgeUS); append(generation)
        data.append(contentsOf: repeatElement(UInt8(0), count: 24))
        precondition(data.count == 128)
        return data
    }
}

/// Trapezoidal gyro integration; a missing interval begins a new baseline.
struct TrekGyroIntegrator {
    private var previous: (Double, Double)?
    private(set) var yaw: Double = 0
    mutating func add(time: Double, rate: SIMD3<Double>, gravity: SIMD3<Double>) -> Bool {
        let norm = sqrt(gravity.x*gravity.x + gravity.y*gravity.y + gravity.z*gravity.z)
        let vertical = -(rate.x*gravity.x + rate.y*gravity.y + rate.z*gravity.z)/norm
        guard time.isFinite, norm.isFinite, norm > 0.8, norm < 1.2, vertical.isFinite else {
            previous = nil; yaw = 0; return false
        }
        var continuous = true
        if let (lastTime, lastRate) = previous {
            let dt = time-lastTime
            if dt > 0 && dt <= 0.1 { yaw += (lastRate+vertical)*0.5*dt }
            else { yaw = 0; continuous = false }
        }
        previous = (time, vertical)
        return continuous
    }
}
