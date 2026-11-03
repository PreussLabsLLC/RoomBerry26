// @(#)GroundMotion.swift 3.1.floor.5 2026/11/02 22:00:00
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
    static func fit(_ candidates: [SIMD2<Double>], failure: ((String) -> Void)? = nil) -> (delta: SIMD2<Double>, rms: Double, inliers: Int, indices: [Int])? {
        guard candidates.count >= 24 else { failure?("too few candidates=\(candidates.count)"); return nil }
        let median = SIMD2(Self.median(candidates.map(\.x)), Self.median(candidates.map(\.y)))
        let distances = candidates.map { simd_length($0 - median) }
        let limit = min(5.0, max(0.5, 3 * Self.median(distances)))
        let indices = candidates.indices.filter { simd_length(candidates[$0] - median) <= limit }
        let good = indices.map { candidates[$0] }
        guard good.count >= 24, Double(good.count) / Double(candidates.count) >= 0.65 else {
            failure?("inlier agreement candidates=\(candidates.count) inliers=\(good.count)"); return nil
        }
        let mean = good.reduce(SIMD2<Double>(repeating: 0), +) / Double(good.count)
        let rms = sqrt(good.map { simd_length_squared($0 - mean) }.reduce(0,+) / Double(good.count))
        guard rms <= 2 else { failure?("residual rms=\(rms) inliers=\(good.count)"); return nil }
        return (mean, rms, good.count, indices)
    }
    // Normalized full-frame pixel locations of robust inliers, not raw matches.
    // Accept a missing quadrant, but reject small patches and nearly collinear
    // support. Central-75% sampling remains unchanged.
    static func spatialCoverage(_ points: [SIMD2<Double>]) -> (valid: Bool, detail: String) {
        guard points.count >= 24 else { return (false, "coverage: fewer than 24 inliers") }
        guard points.allSatisfy({ $0.x.isFinite && $0.y.isFinite && (0...1).contains($0.x) && (0...1).contains($0.y) }) else {
            return (false, "coverage: invalid pixel positions")
        }
        let xs = points.map(\.x), ys = points.map(\.y)
        let spanX = xs.max()! - xs.min()!, spanY = ys.max()! - ys.min()!
        let cells = Set(points.map { min(3, max(0, Int($0.x*4))) + 4*min(3, max(0, Int($0.y*4))) })
        let quadrants = Set(points.map { ($0.x >= 0.5 ? 1 : 0) + ($0.y >= 0.5 ? 2 : 0) }).count
        let mean = points.reduce(SIMD2<Double>(repeating: 0), +) / Double(points.count)
        var xx = 0.0, yy = 0.0, xy = 0.0
        for point in points {
            let d = point-mean; xx += d.x*d.x; yy += d.y*d.y; xy += d.x*d.y
        }
        let areaRatio = xx*yy > 0 ? max(0, 1-xy*xy/(xx*yy)) : 0
        let valid = spanX >= 0.30 && spanY >= 0.30 && cells.count >= 4 && areaRatio >= 0.10
        return (valid, String(format: "coverage quadrants=%d cells=%d span=%.2f/%.2f area=%.2f", quadrants, cells.count, spanX, spanY, areaRatio))
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

/// One immutable snapshot between capture and reporting; never hold this lock
/// across Vision, dispatch, callbacks, or network operations.
final class GroundPacketSnapshot {
    private let lock = NSLock()
    private var latest: GroundPacket?
    private var active = false
    func activate(_ packet: GroundPacket) {
        lock.lock(); latest = packet; active = true; lock.unlock()
    }
    func store(_ packet: GroundPacket?) {
        lock.lock(); defer { lock.unlock() }
        if packet == nil { active = false; latest = nil }
        else if active { latest = packet }
    }
    func load() -> GroundPacket? {
        lock.lock(); defer { lock.unlock() }
        return latest
    }
}

extension GroundPacket {
    func reportingCopy(now: Double, sequence: UInt32, battery: (UInt8, UInt8)) -> GroundPacket {
        var result = self
        if endUS == 0 || now - Double(endUS)/1e6 > 0.25 {
            // Staleness affects only this report. Capture owns continuity and
            // resets its live segment when the next frame reveals a gap.
            result.flags = 2; result.state = 1; result.reason = 4
            for i in 0..<12 where i != 7 { result.values[i] = 0 }
            result.inliers = 0; result.candidates = 0
        }
        result.sequence = sequence; result.sendUS = Self.us(now)
        result.battery = battery.0; result.batteryState = battery.1
        return result
    }
}
