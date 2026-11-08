// @(#)GridLine.swift 3.1.tiles.6 2026/11/06 20:30:00
import Foundation
import simd

struct GridConfiguration: Codable {
    var heightMM = 85.0
    var yawDegrees = 180.0
    var forwardMM = -200.0
    // Re-measured from run residuals: config was 26, the stripe held at
    // 15 mm offset (tracking error -10.6 mm, constant). Physical ≈ 15.
    var leftMM = 15.0
    var gain = 2.0
    var limit = 0.25
    var direction: Int8 = -1
    var identity: UInt64 = 1
    var mount: MountCalibration {
        MountCalibration(heightMM: heightMM, yawDegrees: yawDegrees,
                         lensForwardMM: forwardMM, lensLeftMM: leftMM, identity: identity)
    }
    var valid: Bool {
        mount.valid && gain.isFinite && limit.isFinite && (0.1...8).contains(gain)
            && (0.01...0.35).contains(limit) && [-1,1].contains(Int(direction))
    }
}

struct GridDetection {
    var valid = false
    var first = SIMD2(0.5,0.25)
    var second = SIMD2(0.5,0.75)
    var targetFirst = SIMD2(0.5,0.25)
    var targetSecond = SIMD2(0.5,0.75)
    var offset = 0.0
    var angle = 0.0
    var confidence = 0.0
    var correction = 0.0
}

struct GridLine {
    struct Hit { var x: Double; var y: Double; var confidence: Double }
    static func correction(offset: Double, angle: Double, config: GridConfiguration) -> Double {
        max(-config.limit,min(config.limit,config.gain*((offset-config.leftMM)/600+Double(config.direction)*angle)))
    }
    static func robotPoint(_ pixel: SIMD2<Double>, k: simd_double3x3,
                           gravity: SIMD3<Double>, config: GridConfiguration) -> SIMD2<Double>? {
        guard let floor = FloorGeometry.point(pixel: pixel,intrinsics: k,gravity: gravity,height: config.heightMM) else { return nil }
        return config.mount.robot(floor)+SIMD2(config.forwardMM,config.leftMM)
    }
    static func hits(luma: UnsafePointer<UInt8>, width: Int, height: Int, stride: Int, nominal: Double) -> [Hit] {
        // Widened to width/16..15*width/16 (was width/8..7*width/8): after
        // turnaround the stripe rides near the left search edge and flickers
        // in/out, which the 1 s degraded timer turned into a tag handoff.
        let x0 = width/16, x1 = 15*width/16
        var hits: [Hit] = []
        // Still two horizontal scanlines. Nearby alternatives avoid placing a
        // scanline directly along a transverse dark grout stripe. No counting.
        for shift in [-24,0,24] {
            let y = min(height-2,max(1,Int(Double(height)*nominal)+shift))
            var profile = [Double](repeating: 0,count: x1-x0)
            for x in x0..<x1 {
                var sum = 0.0
                for yy in (y-1)...(y+1) {
                    for xx in max(0,x-1)...min(width-1,x+1) { sum += Double(luma[yy*stride+xx]) }
                }
                profile[x-x0] = sum/9
            }
            let sorted = profile.sorted()
            let light = sorted[sorted.count*3/4]
            guard let dark = sorted.first, light-dark >= 30 else { continue }
            let threshold = light-max(22,(light-dark)*0.45)
            var i = 0
            while i < profile.count {
                if profile[i] >= threshold { i += 1; continue }
                let begin = i
                while i < profile.count && profile[i] < threshold { i += 1 }
                let count = i-begin
                guard count >= 2, count <= min(60,width/6), begin > 0, i < profile.count else { continue }
                let weight = profile[begin..<i].map { light-$0 }
                let total = weight.reduce(0,+)
                let center = zip(begin..<i,weight).reduce(0.0) { $0+Double($1.0)*$1.1 }/total+Double(x0)
                let contrast = total/Double(count)
                let confidence = min(1,contrast/80)*min(1,Double(count)/3)
                if confidence >= 0.45 { hits.append(Hit(x: center,y: Double(y),confidence: confidence)) }
            }
        }
        return hits
    }
    static func targetX(y: Double, width: Int, k: simd_double3x3,
                        gravity: SIMD3<Double>, config: GridConfiguration) -> Double {
        var lo = 0.0, hi = Double(width-1)
        guard let p0 = robotPoint(SIMD2(lo,y),k:k,gravity:gravity,config:config),
              let p1 = robotPoint(SIMD2(hi,y),k:k,gravity:gravity,config:config) else { return Double(width)/2 }
        let target = config.leftMM
        if (p0.y-target)*(p1.y-target) > 0 { return abs(p0.y-target)<abs(p1.y-target) ? lo : hi }
        for _ in 0..<20 {
            let mid = (lo+hi)/2
            guard let p = robotPoint(SIMD2(mid,y),k:k,gravity:gravity,config:config) else { break }
            if (p.y-target)*(p0.y-target) > 0 { lo = mid } else { hi = mid }
        }
        return (lo+hi)/2
    }
    static func detect(luma: UnsafePointer<UInt8>, width: Int, height: Int, stride: Int,
                       k: simd_double3x3, gravity: SIMD3<Double>, config: GridConfiguration) -> GridDetection {
        var empty = GridDetection()
        // Scanlines at 25%/75% (were 35%/65%): the LED corona near the
        // image centre was degrading contrast at the scanline rows and
        // contributing to intermittent lost-line status.
        for (nominal,first) in [(0.25,true),(0.75,false)] {
            let y = nominal*Double(height)
            let p = SIMD2(targetX(y:y,width:width,k:k,gravity:gravity,config:config)/Double(width),nominal)
            if first { empty.targetFirst = p } else { empty.targetSecond = p }
        }
        let top = hits(luma:luma,width:width,height:height,stride:stride,nominal:0.25)
        let bottom = hits(luma:luma,width:width,height:height,stride:stride,nominal:0.75)
        var candidates: [(Double,GridDetection)] = []
        for a in top { for b in bottom {
            guard let p = robotPoint(SIMD2(a.x,a.y),k:k,gravity:gravity,config:config),
                  let q = robotPoint(SIMD2(b.x,b.y),k:k,gravity:gravity,config:config), abs(q.x-p.x)>15 else { continue }
            let slope = (q.y-p.y)/(q.x-p.x)
            let angle = atan(slope), offset = p.y-slope*p.x
            guard abs(angle)<=0.35, abs(offset)<=200 else { continue }
            let confidence = min(a.confidence,b.confidence)*(1-abs(angle)/1.0)
            guard confidence >= 0.45 else { continue }
            var result = empty
            result.valid = true; result.first = SIMD2(a.x/Double(width),a.y/Double(height))
            result.second = SIMD2(b.x/Double(width),b.y/Double(height))
            result.targetFirst = SIMD2(targetX(y:a.y,width:width,k:k,gravity:gravity,config:config)/Double(width),a.y/Double(height))
            result.targetSecond = SIMD2(targetX(y:b.y,width:width,k:k,gravity:gravity,config:config)/Double(width),b.y/Double(height))
            result.offset = offset; result.angle = angle; result.confidence = confidence
            result.correction = correction(offset:offset,angle:angle,config:config)
            candidates.append((confidence-abs(offset-config.leftMM)*0.001,result))
        } }
        candidates.sort { $0.0 > $1.0 }
        guard let best = candidates.first else {
            if !top.isEmpty || !bottom.isEmpty {
                NSLog("GridRunner no-stripe: topHits=%d bottomHits=%d", top.count, bottom.count)
            }
            return empty
        }
        if candidates.dropFirst().contains(where: {
            best.0-$0.0<0.1 && (abs(best.1.offset-$0.1.offset)>8 || abs(best.1.angle-$0.1.angle)>0.1)
        }) { return empty }
        return best.1
    }
}
