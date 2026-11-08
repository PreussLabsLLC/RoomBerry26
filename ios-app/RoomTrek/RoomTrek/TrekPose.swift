// @(#)TrekPose.swift 3.1.roomtrek.2 2026/11/08 12:00:00
import Foundation
import simd

/// RoomTrek camera pose in mapped ARKit world coordinates.
/// Coordinates (documented conversions):
/// - ARKit world is right-handed with +Y up (gravity alignment).
/// - We store positions in metres using StarLock's mapped convention:
///   mapped = (AR.x, -AR.z, AR.y), so the mapped Z axis is up.
/// - Camera forward is the optical axis, `-column2` of the ARCamera transform.
///   Yaw is `atan2(forwardMapped.y, forwardMapped.x)` in the mapped XY plane:
///   0 rad faces mapped +X, +pi/2 faces mapped +Y.
/// - The orientation quaternion is authoritative; yaw/roll/pitch are derived
///   for display and NavLink diagnostics.
/// - Camera pose is the source. Robot body pose is derived as
///   PoseRobot = PoseCamera * inverse(MountTransform), where MountTransform
///   describes the camera in robot body axes.
///   It is identity until calibrated from measured mount values; the
///   architecture keeps the two frames distinct.
struct TrekPose {
    var position: SIMD3<Float> = .zero          // metres, mapped AR world
    var orientation: SIMD4<Float> = SIMD4(0, 0, 0, 1) // quaternion x,y,z,w
    var yaw: Float = 0                            // rad, atan2 in mapped XY
    var timestamp: TimeInterval = 0               // ARFrame.timestamp (uptime)
    var tracking: UInt8 = 0                       // 0 unavailable, 1 limited, 2 normal, 3 interrupted
    var reason: UInt8 = 0                         // 0 none, 1 initializing, 2 excessiveMotion, 3 insufficientFeatures, 4 relocalizing, 5 interrupted, 6 sessionError, 7 other
    var worldMappingStatus: String = "unknown"    // notAvailable / limited / extending / mapped / unknown
    var mapID: UUID?                              // selected map; nil in Surveyor
    var session: UInt64 = 0
    var features: UInt16 = 0
    var relocalization: RelocState = .notNeeded
    var isValid: Bool = false                     // derived; never set from a bare camera transform alone

    enum RelocState: String, Codable {
        case notNeeded        // Surveyor
        case relocalizing     // Navigator: limited(relocalizing) or awaiting stable normal
        case localized        // Navigator: sustained normal >= 1s after relocalizing
        case lost             // Navigator: unavailable / failed
    }
}

/// T_B_C describes the camera mount relative to the robot body, in metres.
/// Given T_M_C, robot pose is T_M_B = T_M_C * inverse(T_B_C).
/// The output is kept separate from the camera pose sent/logged by v1.
struct MountTransform {
    var translation: SIMD3<Float> = .zero // camera origin in robot body axes
    var quaternion: SIMD4<Float> = SIMD4(0, 0, 0, 1) // camera axes in body axes
    static let identity = MountTransform()

    func robotTransform(cameraTransform: simd_float4x4) -> simd_float4x4 {
        let q = simd_normalize(simd_quatf(vector: quaternion))
        var bodyFromCamera = simd_float4x4(q)
        bodyFromCamera.columns.3 = SIMD4(translation, 1)
        return cameraTransform * simd_inverse(bodyFromCamera)
    }
}

enum TrekPoseMath {
    /// StarLock mapped conversion: (x, -z, y). Input is an AR column vector.
    static func mapped(_ v: SIMD3<Float>) -> SIMD3<Float> {
        SIMD3(v.x, -v.z, v.y)
    }

    /// Yaw from a mapped forward vector. Returns 0 for a near-vertical forward
    /// (projection too small to define a heading), matching NavLink validity.
    static func yaw(fromForwardMapped forward: SIMD3<Float>) -> Float {
        let h = hypot(forward.x, forward.y)
        guard h > 0.0001 else { return 0 }
        return atan2(forward.y, forward.x)
    }

    static func horizontalProjection(_ forwardMapped: SIMD3<Float>) -> Float {
        hypot(forwardMapped.x, forwardMapped.y)
    }

    /// Validity mirrors StarLock NavLinkTelemetry: normal tracking, no
    /// interruption/failure, capture age 0-250 ms, usable heading projection.
    /// Map-dependent validity (Navigator relocalization) is applied by the
    /// session, not here; call this the lower bound.
    static func isValid(tracking: UInt8, interrupted: Bool, failed: Bool, frameAge: Double, forwardMapped: SIMD3<Float>) -> Bool {
        tracking == 2 && !interrupted && !failed && frameAge >= 0 && frameAge <= 0.25 && horizontalProjection(forwardMapped) > 0.1
    }

    /// Nonzero stable token derived from a map UUID for the NavLink
    /// alignment field (offset 16). Same UUID always gives the same token.
    static func token(for uuid: UUID) -> UInt64 {
        var u = uuid.uuid
        var token: UInt64 = 0
        withUnsafeBytes(of: &u) { raw in
            for (i, byte) in raw.prefix(8).enumerated() { token |= UInt64(byte) << (i * 8) }
        }
        if token == 0 { token = 1 }
        return token
    }

    static func microseconds(_ seconds: TimeInterval) -> UInt64 {
        guard seconds.isFinite, seconds > 0 else { return 0 }
        return UInt64(min(seconds * 1_000_000, Double(UInt64.max / 2)))
    }

    /// Quaternion from an ARCamera transform rotation.
    static func quaternion(from rotation: simd_float3x3) -> SIMD4<Float> {
        let q = simd_quatf(rotation)
        return SIMD4(q.vector.x, q.vector.y, q.vector.z, q.vector.w)
    }

    static func rotation(from transform: simd_float4x4) -> simd_float3x3 {
        simd_float3x3(SIMD3(transform.columns.0.x, transform.columns.0.y, transform.columns.0.z), SIMD3(transform.columns.1.x, transform.columns.1.y, transform.columns.1.z), SIMD3(transform.columns.2.x, transform.columns.2.y, transform.columns.2.z))
    }
}
