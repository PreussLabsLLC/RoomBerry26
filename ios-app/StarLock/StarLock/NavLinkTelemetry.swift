// @(#)NavLinkTelemetry.swift 2.3.navlink.1 2026/10/30 09:51:08
import ARKit
import CoreMotion
import Network
import UIKit

/// Foreground observation stream. Main-thread sampling, one in-flight UDP send.
final class NavLinkTelemetry: NSObject, ARSessionDelegate {
    private let session: ARSession
    private let motion = CMMotionManager()
    private let queue = DispatchQueue(label: "StarLock.NavLink")
    private var timer: Timer?
    private var connection: NWConnection?
    private var ready = false
    private var inFlight = false
    private var running = false
    private var attemptStarted: TimeInterval = 0
    private var useAvahi = false
    private var epoch = UInt64.random(in: 1...UInt64.max)
    private var sequence: UInt32 = 0
    private var interrupted = false
    private var failed = false
    private var previous: (time: TimeInterval, position: SIMD3<Float>)?
    private var imu: CMDeviceMotion?
    private var peak: Double = 0
    private var squares: Double = 0
    private var samples: UInt16 = 0
    private var batteryPercent: UInt8 = 255
    private var batteryState: UInt8 = 0
    private var batteryReadAt: TimeInterval = -1
    private var sent: UInt64 = 0
    var onStatus: ((String) -> Void)?

    init(session: ARSession) {
        self.session = session
        super.init()
        session.delegate = self
        session.delegateQueue = .main
    }

    func start() {
        guard timer == nil else { return }
        epoch = UInt64.random(in: 1...UInt64.max)
        sequence = 0
        interrupted = false
        failed = false
        previous = nil
        imu = nil
        peak = 0; squares = 0; samples = 0
        UIDevice.current.isBatteryMonitoringEnabled = true
        batteryReadAt = -1
        motion.deviceMotionUpdateInterval = 0.02
        if motion.isDeviceMotionAvailable {
            motion.startDeviceMotionUpdates(to: .main) { [weak self] value, _ in
                guard let self = self, let value = value else { return }
                self.imu = value
                let a = value.userAcceleration
                let magnitude = sqrt(a.x * a.x + a.y * a.y + a.z * a.z) * 9806.65
                self.peak = max(self.peak, magnitude)
                self.squares += magnitude * magnitude
                if self.samples < .max { self.samples += 1 }
            }
        }
        queue.async {
            self.running = true
            self.sent = 0
            self.connect()
        }
        timer = Timer(timeInterval: 0.1, repeats: true) { [weak self] _ in self?.tick() }
        RunLoop.main.add(timer!, forMode: .common)
    }

    func stop() {
        timer?.invalidate()
        timer = nil
        motion.stopDeviceMotionUpdates()
        UIDevice.current.isBatteryMonitoringEnabled = false
        previous = nil
        imu = nil
        queue.async {
            self.running = false
            self.connection?.cancel()
            self.connection = nil
            self.ready = false
            self.inFlight = false
        }
    }

    // Called only on the network queue. Try the configured DNS name first,
    // then its explicit Avahi spelling; retry without queueing stale packets.
    private func connect() {
        connection?.cancel()
        ready = false
        inFlight = false
        attemptStarted = ProcessInfo.processInfo.systemUptime
        let host = useAvahi ? "pi.local" : "pi"
        let parameters = NWParameters.udp
        (parameters.defaultProtocolStack.internetProtocol as? NWProtocolIP.Options)?.version = .v4
        let current = NWConnection(host: NWEndpoint.Host(host), port: 5010, using: parameters)
        connection = current
        report("NAVLINK resolving \(host):5010")
        current.stateUpdateHandler = { [weak self, weak current] state in
            guard let self = self, let current = current, self.connection === current else { return }
            switch state {
            case .ready:
                self.ready = true
            case .failed(let error), .waiting(let error):
                self.ready = false
                self.report("NAVLINK \(host): \(error.localizedDescription)")
            default:
                self.ready = false
            }
        }
        current.start(queue: queue)
    }

    private func report(_ text: String) {
        DispatchQueue.main.async { [weak self] in self?.onStatus?(text) }
    }

    private func send(_ data: Data) {
        queue.async {
            guard self.running else { return }
            let now = ProcessInfo.processInfo.systemUptime
            if (!self.ready || self.inFlight) && now - self.attemptStarted > 5 {
                self.useAvahi.toggle()
                self.connect()
            }
            guard self.ready, !self.inFlight, let current = self.connection else { return }
            self.inFlight = true
            self.attemptStarted = now
            current.send(content: data, completion: .contentProcessed { [weak self, weak current] error in
                guard let self = self, let current = current, self.connection === current else { return }
                self.inFlight = false
                if let error = error {
                    self.ready = false
                    self.report("NAVLINK send: \(error.localizedDescription)")
                } else {
                    self.sent += 1
                    if self.sent % 10 == 0 {
                        self.report("NAVLINK UDP sent \(self.sent) · 10 Hz\npi:5010 · receipt unconfirmed")
                    }
                }
            })
        }
    }

    private func tick() {
        let now = ProcessInfo.processInfo.systemUptime
        if now - batteryReadAt >= 1 || batteryReadAt < 0 {
            let device = UIDevice.current
            let level = device.batteryLevel
            batteryPercent = level < 0 ? 255 : UInt8(min(100, max(0, (level * 100).rounded())))
            switch device.batteryState {
            case .unplugged: batteryState = 1
            case .charging: batteryState = 2
            case .full: batteryState = 3
            default: batteryState = 0
            }
            batteryReadAt = now
        }
        if sequence == .max {
            epoch = UInt64.random(in: 1...UInt64.max)
            sequence = 0
            previous = nil
        }
        var packet = NavLinkPacket()
        packet.session = epoch
        packet.sequence = sequence
        sequence += 1
        packet.sendUS = NavLinkPacket.microseconds(now)
        packet.batteryPercent = batteryPercent
        packet.batteryState = batteryState
        packet.flags = 0x20 // camera pose, not surveyed robot-axle pose

        if let frame = session.currentFrame {
            packet.frameUS = NavLinkPacket.microseconds(frame.timestamp)
            let age = now - frame.timestamp
            packet.frameAgeUS = age >= 0 ? UInt32(clamping: packet.sendUS - min(packet.sendUS, packet.frameUS)) : .max
            switch frame.camera.trackingState {
            case .normal: packet.tracking = 2
            case .notAvailable: packet.tracking = 0
            case .limited(let reason):
                packet.tracking = 1
                switch reason {
                case .initializing: packet.reason = 1
                case .excessiveMotion: packet.reason = 2
                case .insufficientFeatures: packet.reason = 3
                case .relocalizing: packet.reason = 4
                @unknown default: packet.reason = 7
                }
            }
            packet.features = UInt16(clamping: frame.rawFeaturePoints?.points.count ?? 0)
            let transform = frame.camera.transform
            // Gravity-aligned session coordinates: X=AR.x, Y=-AR.z, Z=AR.y.
            func mapped(_ column: SIMD4<Float>) -> SIMD3<Float> {
                SIMD3(column.x, -column.z, column.y)
            }
            let position = mapped(transform.columns.3) * 1000
            let forward = mapped(transform.columns.1)
            let left = mapped(transform.columns.0)
            let up = -mapped(transform.columns.2)
            let horizontal = hypot(forward.x, forward.y)
            packet.measurements[0] = position.x
            packet.measurements[1] = position.y
            packet.measurements[2] = position.z
            packet.measurements[3] = atan2(forward.y, forward.x)
            packet.measurements[4] = atan2(left.z, up.z)
            packet.measurements[5] = atan2(-forward.z, horizontal)
            let valid = packet.tracking == 2 && !interrupted && !failed && age >= 0 && age <= 0.25 && horizontal > 0.1
            if valid {
                packet.flags |= 1
                if let old = previous {
                    let dt = frame.timestamp - old.time
                    if dt > 0 && dt <= 0.5 {
                        let velocity = (position - old.position) / Float(dt)
                        packet.measurements[6] = (velocity.x * forward.x + velocity.y * forward.y) / horizontal
                        packet.measurements[7] = (-velocity.x * forward.y + velocity.y * forward.x) / horizontal
                        packet.flags |= 2
                    }
                }
                // Repeated ARFrames retain their capture time and have no velocity validity.
                previous = (frame.timestamp, position)
            } else {
                previous = nil
            }
        }
        if interrupted { packet.tracking = 3; packet.reason = 5 }
        if failed { packet.tracking = 0; packet.reason = 6 }
        if let value = imu, now - value.timestamp >= 0, now - value.timestamp <= 0.1 {
            packet.imuUS = NavLinkPacket.microseconds(value.timestamp)
            let a = value.userAcceleration
            let g = value.gravity
            let w = value.rotationRate
            packet.measurements[8] = Float(-(w.x * g.x + w.y * g.y + w.z * g.z))
            // Native Core Motion device axes, explicitly flagged; no assumed mount.
            packet.measurements[9] = Float(a.x * 9806.65)
            packet.measurements[10] = Float(a.y * 9806.65)
            packet.measurements[11] = Float(a.z * 9806.65)
            packet.flags |= 0x44 // IMU valid + native-device acceleration
        }
        if samples > 0 {
            packet.measurements[12] = Float(peak)
            packet.measurements[13] = Float(sqrt(squares / Double(samples)))
            packet.imuSamples = samples
            packet.flags |= 8
        }
        peak = 0; squares = 0; samples = 0
        // Never crash the foreground app on an invalid sensor value.
        guard packet.measurements.allSatisfy({ $0.isFinite }), packet.frameUS <= packet.sendUS,
              packet.imuUS <= packet.sendUS else { return }
        send(packet.encoded())
    }

    func sessionWasInterrupted(_ session: ARSession) { interrupted = true; previous = nil }
    func sessionInterruptionEnded(_ session: ARSession) {
        interrupted = false
        epoch = UInt64.random(in: 1...UInt64.max)
        sequence = 0
        previous = nil
    }
    func session(_ session: ARSession, didFailWithError error: Error) {
        failed = true
        previous = nil
        onStatus?("TRACKING error: \(error.localizedDescription)")
    }
}
