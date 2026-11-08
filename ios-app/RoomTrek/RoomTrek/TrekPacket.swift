// @(#)TrekPacket.swift 3.1.roomtrek.2 2026/11/08 12:00:00
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
