// @(#)PhoneTelemetry.swift 3.1.compass.1 2026/10/31 12:10:00
import Foundation
import CoreMotion
import simd

/// Dedicated queue/timer: a slow optical-flow request cannot block impact reports.
final class PhoneTelemetry {
    private let queue = DispatchQueue(label: "GroundHog.health", qos: .userInitiated)
    private var timer: DispatchSourceTimer?
    private var packet = HealthPacket()
    private var detector = BumpDetector()
    private var metrics = ProcessMetrics()
    private var resourceReadAt: Double = 0
    private var peak: Double = 0
    private var samples: UInt16 = 0
    private var running = false
    private var compass: CompassTelemetry? // accessed only on main queue
    var onPacket: ((HealthPacket) -> Void)?
    var onCompassPacket: ((CompassPacket) -> Void)?
    var onCompassStatus: ((String) -> Void)?
    var onStatus: ((String) -> Void)? // main queue
    func start(session: UInt64, calibration: UInt64, mountYawDegrees: Double) {
        queue.async {
            self.timer?.cancel()
            self.packet = HealthPacket(); self.packet.session = session; self.packet.calibration = calibration
            self.detector = BumpDetector(); self.metrics = ProcessMetrics(); self.resourceReadAt = 0
            self.peak = 0; self.samples = 0; self.running = true
            DispatchQueue.main.async {
                if self.compass == nil { self.compass = CompassTelemetry() }
                self.compass?.onPacket = { [weak self] in self?.onCompassPacket?($0) }
                self.compass?.onStatus = { [weak self] in self?.onCompassStatus?($0) }
                self.compass?.start(session: session,calibration: calibration,mountYawDegrees: mountYawDegrees)
            }
            let t = DispatchSource.makeTimerSource(queue: self.queue)
            t.schedule(deadline: .now(), repeating: .milliseconds(100))
            t.setEventHandler { [weak self] in self?.emit() }; self.timer = t; t.resume()
        }
    }
    func stop() {
        queue.async {
            self.running = false; self.timer?.cancel(); self.timer = nil
            DispatchQueue.main.async { self.compass?.stop() }
        }
    }
    func setBattery(_ percent: UInt8, _ state: UInt8) {
        queue.async { self.packet.battery = percent; self.packet.batteryState = state }
    }
    func setDimensions(width: Int, height: Int) {
        queue.async { self.packet.width = UInt16(clamping: width); self.packet.height = UInt16(clamping: height) }
    }
    func record(_ motion: CMDeviceMotion, session: UInt64) {
        // CMDeviceMotion is immutable; copy its scalar readings before dispatch.
        let time = motion.timestamp
        let a = SIMD3(motion.userAcceleration.x,motion.userAcceleration.y,motion.userAcceleration.z)
        let w = SIMD3(motion.rotationRate.x,motion.rotationRate.y,motion.rotationRate.z)
        let g = SIMD3(motion.gravity.x,motion.gravity.y,motion.gravity.z)
        queue.async {
            guard self.running, self.packet.session == session,
                  time > Double(self.packet.imuUS)/1e6,
                  [a.x,a.y,a.z,w.x,w.y,w.z,g.x,g.y,g.z].allSatisfy({ $0.isFinite }) else { return }
            let now = ProcessInfo.processInfo.systemUptime
            guard time <= now, now-time <= 0.1 else { return }
            self.packet.imuUS = GroundPacket.us(time)
            self.packet.values[0] = Float(a.x*9806.65); self.packet.values[1] = Float(a.y*9806.65); self.packet.values[2] = Float(a.z*9806.65)
            self.packet.values[3] = Float(w.x); self.packet.values[4] = Float(w.y); self.packet.values[5] = Float(w.z)
            self.packet.values[6] = Float(g.x); self.packet.values[7] = Float(g.y); self.packet.values[8] = Float(g.z)
            self.peak = max(self.peak,simd_length(a)*9806.65)
            self.samples = self.samples == .max ? .max : self.samples+1
            let hit = self.detector.sample(time: time,acceleration: a)
            self.packet.bumps = self.detector.count
            self.packet.bumpUS = GroundPacket.us(self.detector.lastTime)
            self.packet.values[10] = Float(self.detector.lastPeakG*9806.65)
            if hit { self.emit() } // immediate best-effort event; repeated by heartbeat
        }
    }
    private func emit() {
        guard running else { return }
        let now = ProcessInfo.processInfo.systemUptime
        if packet.sequence == .max { return } // start a new tracking session before exhaustion
        packet.sequence += 1; packet.sendUS = GroundPacket.us(now)
        // Bits 2/3 retained only until the next resource query.
        packet.flags &= 0x0c
        if packet.imuUS > 0, packet.sendUS >= packet.imuUS, packet.sendUS-packet.imuUS <= 100000 { packet.flags |= 1 }
        if samples > 0 { packet.flags |= 2 }
        if packet.bumpUS > 0 { packet.flags |= 16 }
        if packet.battery <= 100 { packet.flags |= 32 }
        if packet.width > 0, packet.height > 0 { packet.flags |= 64 }
        packet.samples = samples; packet.values[9] = Float(peak)
        if now-resourceReadAt >= 1 {
            let resource = metrics.read()
            packet.flags &= ~UInt16(12)
            packet.values[11] = resource.cpu ?? 0; packet.footprintBytes = resource.footprint ?? 0
            if resource.cpu != nil { packet.flags |= 4 }
            if resource.footprint != nil { packet.flags |= 8 }
            resourceReadAt = now
        }
        packet.resourceAgeMS = UInt32(clamping: GroundPacket.us(max(0,now-resourceReadAt))/1000)
        switch ProcessInfo.processInfo.thermalState {
        case .nominal: packet.thermal = 0
        case .fair: packet.thermal = 1
        case .serious: packet.thermal = 2
        case .critical: packet.thermal = 3
        @unknown default: packet.thermal = 255
        }
        onPacket?(packet)
        let cpu = packet.flags & 4 != 0 ? String(format: "%.0f%%",packet.values[11]) : "—"
        let memory = packet.flags & 8 != 0 ? String(format: "%.1f MiB",Double(packet.footprintBytes)/1048576) : "—"
        let dimensions = packet.width > 0 ? "\(packet.width)×\(packet.height) · target 30 fps" : "VGA · target 30 fps"
        let text = "\(dimensions)\nBattery \(packet.battery <= 100 ? "\(packet.battery)%" : "—") · bumps \(packet.bumps)\nCPU \(cpu) · memory \(memory) · thermal \(packet.thermal)"
        DispatchQueue.main.async { self.onStatus?(text) }
        peak = 0; samples = 0
    }
}
