// @(#)GroundMotion.swift 3.1 2026/10/31 11:30:00
import Foundation
import simd

struct MountCalibration: Codable {
    var heightMM: Double = 0
    // Angle of phone portrait +Y (top edge) from robot forward, positive left.
    var yawDegrees: Double = 0
    var lensForwardMM: Double = 0
    var lensLeftMM: Double = 0
    var identity: UInt64 = 0
    var valid: Bool {
        [heightMM, yawDegrees, lensForwardMM, lensLeftMM].allSatisfy { $0.isFinite }
            && (50...1500).contains(heightMM) && abs(yawDegrees) <= 360
            && abs(lensForwardMM) <= 1000 && abs(lensLeftMM) <= 1000 && identity != 0
    }
    func robot(_ phone: SIMD2<Double>) -> SIMD2<Double> {
        let a = yawDegrees * .pi / 180
        return SIMD2(cos(a)*phone.y + sin(a)*phone.x, sin(a)*phone.y - cos(a)*phone.x)
    }
}

struct PlanarTransform {
    var position = SIMD2<Double>(repeating: 0)
    var yaw: Double = 0
    static func rotate(_ p: SIMD2<Double>, _ a: Double) -> SIMD2<Double> {
        SIMD2(cos(a)*p.x - sin(a)*p.y, sin(a)*p.x + cos(a)*p.y)
    }
    mutating func append(_ delta: SIMD2<Double>, yaw increment: Double) {
        position += Self.rotate(delta, yaw)
        yaw += increment
    }
    static func centerDelta(camera: SIMD2<Double>, yaw: Double, mount: MountCalibration) -> SIMD2<Double> {
        let r = SIMD2(mount.lensForwardMM, mount.lensLeftMM)
        return camera - (rotate(r, yaw) - r)
    }
}

struct FloorGeometry {
    // Portrait pixel axes: right/down. Rear-camera rays: device +X/-Y/-Z.
    static func point(pixel: SIMD2<Double>, intrinsics k: simd_double3x3,
                      gravity: SIMD3<Double>, height: Double) -> SIMD2<Double>? {
        let up = -simd_normalize(gravity)
        guard up.z > cos(10 * .pi / 180) else { return nil }
        let right = simd_normalize(SIMD3<Double>(1,0,0) - up * up.x)
        let top = simd_cross(up, right)
        let rayCV = k.inverse * SIMD3(pixel.x, pixel.y, 1)
        let ray = SIMD3(rayCV.x, -rayCV.y, -rayCV.z)
        let down = -simd_dot(ray, up)
        guard down > 0.1 else { return nil }
        let p = ray * (height / down)
        return SIMD2(simd_dot(p, right), simd_dot(p, top))
    }
    static func median(_ values: [Double]) -> Double {
        let v = values.sorted(); return v[v.count / 2]
    }
    static func fit(_ candidates: [SIMD2<Double>]) -> (delta: SIMD2<Double>, rms: Double, inliers: Int)? {
        guard candidates.count >= 24 else { return nil }
        let median = SIMD2(Self.median(candidates.map(\.x)), Self.median(candidates.map(\.y)))
        let distances = candidates.map { simd_length($0 - median) }
        let limit = min(5.0, max(0.5, 3 * Self.median(distances)))
        let good = candidates.filter { simd_length($0 - median) <= limit }
        guard good.count >= 24, Double(good.count) / Double(candidates.count) >= 0.65 else { return nil }
        let mean = good.reduce(SIMD2<Double>(repeating: 0), +) / Double(good.count)
        let rms = sqrt(good.map { simd_length_squared($0 - mean) }.reduce(0,+) / Double(good.count))
        guard rms <= 2 else { return nil }
        return (mean, rms, good.count)
    }
}

/// NavLink v1/type 2. Tallies describe a continuous segment, never room position.
struct GroundPacket {
    var session: UInt64 = 1
    var calibration: UInt64 = 0
    var sequence: UInt32 = 0
    var flags: UInt16 = 0
    var state: UInt8 = 0
    var reason: UInt8 = 1
    var startUS: UInt64 = 0
    var endUS: UInt64 = 0
    var sendUS: UInt64 = 0
    var continuity: UInt32 = 0
    var accepted: UInt32 = 0
    var rejected: UInt32 = 0
    // segment X/Y/yaw; last frame forward/left/yaw; residual; height;
    // segment path length, valid duration; last frame forward/left speed.
    var values = [Float](repeating: 0, count: 12)
    var inliers: UInt16 = 0
    var candidates: UInt16 = 0
    var battery: UInt8 = 255
    var batteryState: UInt8 = 0
    var processingUS: UInt32 = 0
    static func us(_ t: Double) -> UInt64 { UInt64(max(0, min(t * 1e6, Double(UInt64.max / 2)))) }
    func encoded() -> Data {
        precondition(values.count == 12 && values.allSatisfy { $0.isFinite })
        var d = Data("NVLK".utf8)
        func put<T: FixedWidthInteger>(_ n: T) {
            var v = n.littleEndian
            withUnsafeBytes(of: &v) { d.append(contentsOf: $0) }
        }
        put(UInt8(1)); put(UInt8(2)); put(UInt16(128))
        put(session); put(calibration); put(sequence); put(flags); put(state); put(reason)
        put(startUS); put(endUS); put(sendUS); put(continuity); put(accepted); put(rejected)
        values.forEach { put($0.bitPattern) }
        put(inliers); put(candidates); put(battery); put(batteryState); put(UInt16(0)); put(processingUS)
        precondition(d.count == 128)
        return d
    }
}
