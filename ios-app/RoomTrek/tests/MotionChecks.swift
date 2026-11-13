// @(#)MotionChecks.swift 3.2.imu.1 2026/11/12 15:05:56
import Foundation
@main struct MotionChecks {
    static func main() throws {
        // Same physical vertical rotation in upright and rolled device axes.
        for gravity in [SIMD3<Double>(0,0,-1), SIMD3<Double>(-1,0,0), SIMD3<Double>(0,1,0)] {
            var i = TrekGyroIntegrator()
            for n in 0...100 {
                assert(i.add(time: Double(n)*0.02+1, rate: -gravity, gravity: gravity))
            }
            assert(abs(i.yaw-2) < 1e-9)
            assert(!i.add(time: 4, rate: -gravity, gravity: gravity))
            assert(i.yaw == 0)
        }
        var i = TrekGyroIntegrator()
        assert(i.add(time: 1, rate: SIMD3(1,0,0), gravity: SIMD3(0,0,-1)))
        assert(i.add(time: 1.02, rate: SIMD3(1,0,0), gravity: SIMD3(0,0,-1)))
        assert(i.yaw == 0, "roll must not become yaw")
        assert(!i.add(time: 1.03, rate: .zero, gravity: .zero))
        var p = TrekMotionPacket()
        p.session=42; p.sequence=5; p.state=2; p.flags=1
        p.sampleUS=1_000_000; p.sendUS=1_010_000; p.sampleAgeUS=10_000; p.generation=3
        p.gyro=SIMD3(0,0,0.5); p.integratedYaw=1.25
        let data=p.encoded(); assert(data.count==128 && data[5]==7)
        try data.write(to: URL(fileURLWithPath: "/tmp/roomtrek-motion-fixture.bin"))
        print("Motion integration and type7 checks passed")
    }
}
