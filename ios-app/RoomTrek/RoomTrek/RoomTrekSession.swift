// @(#)RoomTrekSession.swift 3.2.imu.1 2026/11/12 15:12:06
import ARKit
import CoreMotion
import Foundation

/// ARSession engine for both modes. The view controller owns the ARSCNView
/// and passes its session in; this object is the ARSessionDelegate and
/// builds the pose, relocalization state, and NavLink packet stream.
/// Pose validity follows StarLock: normal tracking, no interruption or
/// failure, capture age 0-250 ms, usable heading projection. In Navigator
/// mode a pose is only valid once relocalization has reached `.localized`
/// (sustained normal tracking for >= 1 s after relocalizing). A valid
/// camera transform alone is never treated as proof of localization.
final class RoomTrekSession: NSObject, ARSessionDelegate {
    enum Mode { case survey, navigate }

    var mode: Mode = .survey
    var mapID: UUID?                       // selected map (Navigator); nil in Surveyor
    var poseLogInterval: TimeInterval = 0.5 // 2 Hz default; never per-frame
    var navLinkEnabled: Bool = false {
        didSet {
            if navLinkEnabled { startLink() } else { link.stop() }
        }
    }
    private(set) var running = false
    private(set) var operationError = ""
    var navigationCompletion: ((String, String) -> Void)?
    private var relocTimedOut = false
    private var navigationDeadline: TimeInterval?
    let control = TrekControl(key: TrekControl.loadKey())

    private var requiresRelocalization: Bool { mode == .navigate || mapID != nil }
    var canAmendSurvey: Bool {
        guard mode == .survey, running, !interrupted, !failed, let pose = latestPose else { return false }
        return MapRevisionPolicy.canAmend(localized: !requiresRelocalization || relocState == .localized,
            trackingNormal: pose.isValid && pose.tracking == 2,
            frameAge: ProcessInfo.processInfo.systemUptime - pose.timestamp,
            mapping: pose.worldMappingStatus, operationError: operationError)
    }

    func operationSnapshot() -> [String: Any] {
        UIDevice.current.isBatteryMonitoringEnabled = true
        let level = UIDevice.current.batteryLevel
        return ["running": running, "mode": mode == .survey ? "survey" : "navigate",
                "session": String(sessionID), "map_id": mapID?.uuidString ?? "",
                "tracking": lastTracking, "interrupted": interrupted, "failed": failed,
                "relocalization": String(describing: relocState), "error": operationError,
                "can_amend": canAmendSurvey, "mapping": lastMapping,
                "battery_percent": level < 0 ? -1 : Int((level * 100).rounded()),
                "battery_state": UIDevice.current.batteryState.rawValue]
    }

    func failOperation(_ detail: String) {
        operationError = detail
        logger.logEvent("operation_error", detail)
        navigationResult("failed", detail)
    }

    private func navigationResult(_ state: String, _ detail: String) {
        let callback = navigationCompletion; navigationCompletion = nil
        callback?(state, detail)
    }
    private var lastTracking = ""
    private var lastMapping = ""
    private var observedRelocalizing = false
    var onPose: ((TrekPose, Bool, String, String) -> Void)? // pose, valid, trackingLabel, relocLabel
    var onStatus: ((String) -> Void)?

    private weak var arSession: ARSession?
    private var sessionID: UInt64 = 0
    private var sequence: UInt32 = 0
    private var interrupted = false
    private var failed = false
    private var latestPose: TrekPose?
    private var previous: (time: TimeInterval, position: SIMD3<Float>)?
    private var lastLogged: TimeInterval = 0
    private var normalSince: TimeInterval?      // start of current normal streak
    private var relocStarted: TimeInterval?      // when relocalizing began
    private var relocState: TrekPose.RelocState = .notNeeded
    private var timer: Timer?
    private var batteryPercent: UInt8 = 255
    private var batteryState: UInt8 = 0
    private var batteryReadAt: TimeInterval = -1

    private let motion = TrekMotion()
    private var motionSequence: UInt32 = 0
    private var lastMotionLog: TimeInterval = -1

    let logger = TrekLogger()
    let link = TrekLink()

    override init() {
        super.init()
        control.send = { [weak self] data in self?.link.sendControl(data) }
        control.snapshot = { [weak self] in self?.operationSnapshot() ?? [:] }
        link.onReceive = { [weak self] data in self?.control.receive(data) }
        link.onHeartbeat = { [weak self] in self?.control.heartbeat() }
    }

    // MARK: - Session control

    func startSurveyor(arSession: ARSession, map: ARWorldMap? = nil, mapID: UUID? = nil) {
        mode = .survey; self.mapID = mapID; relocState = mapID == nil ? .notNeeded : .relocalizing
        begin(arSession: arSession, initialWorldMap: map)
        if let mapID = mapID {
            logger.logEvent("map_load", mapID.uuidString)
            logger.logEvent("relocalization_attempt", "amend map=\(mapID.uuidString)")
        }
        logger.logEvent("session_start", mapID == nil ? "Surveyor fresh" : "Surveyor amend map=\(mapID!.uuidString)")
    }

    func startNavigator(arSession: ARSession, map: ARWorldMap, mapID: UUID) {
        mode = .navigate; self.mapID = mapID; relocState = .relocalizing
        relocStarted = ProcessInfo.processInfo.systemUptime
        normalSince = nil
        begin(arSession: arSession, initialWorldMap: map)
        logger.logEvent("map_load", mapID.uuidString)
        logger.logEvent("relocalization_attempt", mapID.uuidString)
        logger.logEvent("session_start", "Navigator map=\(mapID.uuidString)")
    }

    func resetNavigator() {
        guard mode == .navigate, let arSession, let mapID else { return }
        // Explicit operator reset: new session identity, same stored map.
        // The coordinates are never silently reinterpreted; a new sessionID
        // is the marker that the Pi must rebind.
        let map: ARWorldMap
        do { map = try MapStore().loadWorldMap(for: mapID) }
        catch { failOperation("map_load: \(error.localizedDescription)"); report(operationError); return }
        startNavigator(arSession: arSession, map: map, mapID: mapID)
        logger.logEvent("relocalization_retry", "map=\(mapID.uuidString)")
    }

    func stop() {
        running = false; navigationDeadline = nil
        motion.stop()
        sendMotion()
        timer?.invalidate(); timer = nil
        if !navLinkEnabled { link.stop() }
        navigationResult("failed", "Session stopped")
        logger.logEvent("session_stop", mode == .survey ? "Surveyor" : "Navigator")
        if requiresRelocalization && relocState != .localized {
            logger.logEvent("relocalization_outcome", "stopped_without_candidate")
        }
        logger.flush()
        running = false; latestPose = nil; previous = nil
        arSession?.pause()
    }

    private var arSessionRef: ARSession? { arSession }

    private func begin(arSession: ARSession, initialWorldMap: ARWorldMap? = nil) {
        operationError = ""; relocTimedOut = false
        latestPose = nil; previous = nil
        observedRelocalizing = false
        lastTracking = ""; lastMapping = ""
        running = true
        self.arSession = arSession
        arSession.delegate = self
        arSession.delegateQueue = .main
        guard ARWorldTrackingConfiguration.isSupported else {
            running = false; failed = true; operationError = "ARKit world tracking unsupported"
            navigationResult("failed", operationError)
            report("ARKit world tracking is not supported on this device.")
            logger.logEvent("session_error", "unsupported")
            return
        }
        let config = ARWorldTrackingConfiguration()
        config.worldAlignment = .gravity
        if let map = initialWorldMap {
            config.initialWorldMap = map
        }
        // Same power profile as StarLock: lowest 30 fps video format.
        let formats = ARWorldTrackingConfiguration.supportedVideoFormats
        if let format = formats.filter({ $0.framesPerSecond == 30 }).min(by: { $0.imageResolution.width * $0.imageResolution.height < $1.imageResolution.width * $1.imageResolution.height }) {
            config.videoFormat = format
        }
        config.isLightEstimationEnabled = false
        arSession.run(config, options: [.resetTracking, .removeExistingAnchors])
        sessionID = UInt64.random(in: 1...UInt64.max)
        sequence = 0
        interrupted = false; failed = false
        previous = nil; lastLogged = 0; normalSince = nil
        if requiresRelocalization {
            relocState = .relocalizing
            relocStarted = ProcessInfo.processInfo.systemUptime
            navigationDeadline = ProcessInfo.processInfo.systemUptime + 30
        } else {
            navigationDeadline = nil
            relocState = .notNeeded
        }
        UIDevice.current.isBatteryMonitoringEnabled = true
        batteryReadAt = -1
        motionSequence = 0; lastMotionLog = -1
        motion.start()
        startLink()
        if timer == nil {
            timer = Timer(timeInterval: 0.1, repeats: true) { [weak self] _ in self?.tick() }
            RunLoop.main.add(timer!, forMode: .common)
        }
        logger.logEvent("tracking_start", "video=\(config.videoFormat.framesPerSecond)fps ; session=\(sessionID)")
    }

    private func startLink() {
        link.onStatus = { [weak self] text in self?.report("NAVLINK \(text)"); self?.logger.logEvent("navlink_status", text) }
        if navLinkEnabled { link.start(session: sessionID) }
    }

    private func report(_ text: String) { DispatchQueue.main.async { self.onStatus?(text) } }

    // MARK: - ARSessionDelegate

    func session(_ session: ARSession, didUpdate frame: ARFrame) {
        guard running else { return }
        let now = ProcessInfo.processInfo.systemUptime
        let age = now - frame.timestamp
        var tracking: UInt8 = 0
        var reason: UInt8 = 0
        switch frame.camera.trackingState {
        case .normal:
            tracking = 2; reason = 0
            if normalSince == nil { normalSince = now }
        case .notAvailable:
            tracking = 0; reason = 0; normalSince = nil
        case .limited(let r):
            tracking = 1; normalSince = nil
            switch r {
            case .initializing: reason = 1
            case .excessiveMotion: reason = 2
            case .insufficientFeatures: reason = 3
            case .relocalizing: reason = 4
            @unknown default: reason = 7
            }
        }
        if interrupted { tracking = 3; reason = 5 }
        if failed { tracking = 0; reason = 6 }

        let transform = frame.camera.transform
        let positionM = TrekPoseMath.mapped(SIMD3(transform.columns.3.x, transform.columns.3.y, transform.columns.3.z))
        let forwardAR = -SIMD3(transform.columns.2.x, transform.columns.2.y, transform.columns.2.z) // optical forward
        let forwardMapped = TrekPoseMath.mapped(forwardAR)
        let rotation = TrekPoseMath.rotation(from: transform)
        let basis = simd_float3x3(SIMD3(1, 0, 0), SIMD3(0, 0, 1), SIMD3(0, -1, 0))
        let quat = TrekPoseMath.quaternion(from: basis * rotation)
        let yaw = TrekPoseMath.yaw(fromForwardMapped: forwardMapped)
        let horizontal = TrekPoseMath.horizontalProjection(forwardMapped)
        let baseValid = TrekPoseMath.isValid(tracking: tracking, interrupted: interrupted, failed: failed, frameAge: age, forwardMapped: forwardMapped)
        _ = horizontal

        // Relocalization state machine (Navigator only).
        if requiresRelocalization && !relocTimedOut {
            if tracking != 2 && navigationDeadline == nil { navigationDeadline = now + 30 }
            let relocalizingNow = (tracking == 1 && reason == 4)
            if relocalizingNow {
                if relocState != .relocalizing { relocStarted = now }
                relocState = .relocalizing
                observedRelocalizing = true
                normalSince = nil
            } else if observedRelocalizing, tracking == 2, let since = normalSince, now - since >= 1.0 {
                if relocState != .localized {
                    relocState = .localized
                    navigationDeadline = nil
                    operationError = ""
                    navigationResult("completed", "Localized candidate; accuracy unverified")
                    let elapsed = relocStarted.map { now - $0 } ?? 0
                    logger.logEvent("relocalization_outcome", String(format: "localized_candidate after %.1fs", elapsed))
                    report(String(format: "RELOCALIZED (candidate) after %.1fs · valid pose", elapsed))
                }
            } else if tracking == 0 {
                relocState = .lost
            } else if tracking != 2 {
                relocState = .relocalizing
            }
        }

        let trackingKey = "\(tracking):\(reason)"
        if trackingKey != lastTracking {
            logger.logEvent("tracking_state", trackingKey); lastTracking = trackingKey
        }
        let mappingKey = Self.mappingLabel(frame.worldMappingStatus)
        if mappingKey != lastMapping {
            logger.logEvent("mapping_status", mappingKey); lastMapping = mappingKey
        }
        let valid = baseValid && !relocTimedOut && (!requiresRelocalization || relocState == .localized)
        var pose = TrekPose()
        pose.position = positionM
        pose.orientation = quat
        pose.yaw = yaw
        pose.timestamp = frame.timestamp
        pose.tracking = tracking
        pose.reason = reason
        pose.worldMappingStatus = Self.mappingLabel(frame.worldMappingStatus)
        pose.mapID = mapID
        pose.session = sessionID
        pose.features = UInt16(clamping: frame.rawFeaturePoints?.points.count ?? 0)
        pose.relocalization = relocState
        pose.isValid = valid
        latestPose = pose

        // Throttled pose log (default 2 Hz). Never per-frame.
        if pose.timestamp - lastLogged >= poseLogInterval {
            lastLogged = pose.timestamp
            logger.logPose(pose, Double(yaw) * 180 / .pi, valid)
        }

        let trackingLabel: String
        switch tracking {
        case 2: trackingLabel = "NORMAL"
        case 1: trackingLabel = "LIMITED — \(Self.trackingReasonLabel(reason))"
        case 3: trackingLabel = "INTERRUPTED"
        default: trackingLabel = "UNAVAILABLE"
        }
        let relocLabel: String
        switch relocState {
        case .notNeeded: relocLabel = "—"
        case .relocalizing: relocLabel = "RELOCALIZING"
        case .localized: relocLabel = "LOCALIZED (candidate)"
        case .lost: relocLabel = "LOST"
        }
        DispatchQueue.main.async { self.onPose?(pose, valid, trackingLabel, relocLabel) }
    }

    func sessionShouldAttemptRelocalization(_ session: ARSession) -> Bool { running }

    func sessionWasInterrupted(_ session: ARSession) {
        interrupted = true; latestPose = nil; previous = nil; normalSince = nil
        if requiresRelocalization {
            relocState = .relocalizing; observedRelocalizing = false
            if navigationDeadline == nil { navigationDeadline = ProcessInfo.processInfo.systemUptime + 30 }
        }
        logger.logEvent("interrupted", "")
    }

    func sessionInterruptionEnded(_ session: ARSession) {
        interrupted = false
        sessionID = UInt64.random(in: 1...UInt64.max)
        sequence = 0; previous = nil; normalSince = nil
        if requiresRelocalization { relocState = .relocalizing; relocStarted = ProcessInfo.processInfo.systemUptime }
        if navLinkEnabled { startLink() }
        logger.logEvent("interruption_ended", "new session=\(sessionID)")
    }

    func session(_ session: ARSession, didFailWithError error: Error) {
        failed = true; latestPose = nil; previous = nil; normalSince = nil
        logger.logEvent("session_error", error.localizedDescription)
        operationError = "tracking_failure: \(error.localizedDescription)"
        navigationResult("failed", operationError)
        report("TRACKING error: \(error.localizedDescription)")
    }

    // MARK: - NavLink tick (10 Hz)

    private func tick() {
        guard running else { return }
        let now = ProcessInfo.processInfo.systemUptime
        if requiresRelocalization, !failed, !relocTimedOut, relocState != .localized,
           let deadline = navigationDeadline, now >= deadline {
            relocTimedOut = true; relocState = .lost
            operationError = "relocalization_timeout: no localized candidate within 30 seconds; retry required"
            navigationResult("failed", operationError)
            logger.logEvent("relocalization_outcome", operationError); report(operationError)
        }
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
        sendMotion()
        guard let pose = latestPose else { return }
        let age = now - pose.timestamp
        var packet = TrekPacket()
        packet.session = sessionID
        packet.sequence = sequence; sequence &+= 1
        packet.mapID = pose.mapID
        packet.frameUS = TrekPoseMath.microseconds(pose.timestamp)
        packet.sendUS = TrekPoseMath.microseconds(now)
        packet.frameAgeUS = age >= 0 ? UInt32(clamping: TrekPoseMath.microseconds(age)) : .max
        packet.tracking = interrupted ? 3 : (failed ? 0 : pose.tracking)
        packet.reason = interrupted ? 5 : (failed ? 6 : pose.reason)
        packet.relocalization = [.notNeeded: 0, .relocalizing: 1, .localized: 2, .lost: 3][pose.relocalization] ?? 3
        packet.position = pose.position
        packet.quaternion = pose.orientation
        packet.yaw = pose.yaw
        packet.features = pose.features
        // Loaded-map Surveyor and Navigator observations share validity rules.
        if pose.mapID != nil && pose.isValid && age >= 0 && age <= 0.25 && !interrupted && !failed && !relocTimedOut {
            packet.flags = 1
        }
        if navLinkEnabled { link.send(packet.encoded(), session: sessionID) }
    }

    private func sendMotion() {
        guard sessionID != 0 else { return }
        let now = ProcessInfo.processInfo.systemUptime
        var packet = motion.packet
        packet.session = sessionID
        packet.sequence = motionSequence; motionSequence &+= 1
        packet.sendUS = TrekPoseMath.microseconds(now)
        let age = now-Double(packet.sampleUS)/1_000_000
        packet.sampleAgeUS = age >= 0 ? UInt32(clamping: TrekPoseMath.microseconds(age)) : .max
        packet.flags = packet.state == 2 && age >= 0 && age <= 0.25 ? 1 : 0
        if navLinkEnabled { link.send(packet.encoded(), session: sessionID) }
        if now-lastMotionLog >= 0.5 {
            let fields: [String: Any] = ["session": String(sessionID), "sample_us": packet.sampleUS,
                "generation": packet.generation, "state": packet.state, "valid": packet.flags == 1,
                "gyro_rad_s": [packet.gyro.x, packet.gyro.y, packet.gyro.z],
                "user_acceleration_ms2": [packet.acceleration.x, packet.acceleration.y, packet.acceleration.z],
                "gravity_g": [packet.gravity.x, packet.gravity.y, packet.gravity.z],
                "quaternion": [packet.quaternion.x, packet.quaternion.y, packet.quaternion.z, packet.quaternion.w],
                "integrated_yaw_rad": packet.integratedYaw]
            if let data = try? JSONSerialization.data(withJSONObject: fields, options: [.sortedKeys]),
               let text = String(data: data, encoding: .utf8) { logger.logEvent("motion_sample", text) }
            lastMotionLog = now
        }
    }

    // MARK: - Helpers

    static func mappingLabel(_ status: ARFrame.WorldMappingStatus) -> String {
        switch status {
        case .notAvailable: return "notAvailable"
        case .limited: return "limited"
        case .extending: return "extending"
        case .mapped: return "mapped"
        @unknown default: return "unknown"
        }
    }

    static func trackingReasonLabel(_ reason: UInt8) -> String {
        switch reason {
        case 1: return "initializing"
        case 2: return "excessive motion"
        case 3: return "insufficient features"
        case 4: return "relocalizing"
        case 5: return "interrupted"
        case 6: return "session error"
        default: return "other"
        }
    }
}


/// Main-queue sensor state; independent of ARSession pose and tracking state.
private final class TrekMotion {
    private let manager = CMMotionManager()
    private var integrator = TrekGyroIntegrator()
    private var token: UInt32 = 0
    private(set) var packet = TrekMotionPacket()

    func stop() {
        token &+= 1
        manager.stopDeviceMotionUpdates()
        packet.state = 0; packet.flags = 0
    }

    func start() {
        stop()
        integrator = TrekGyroIntegrator()
        packet.generation &+= 1
        packet.sampleUS = 0; packet.integratedYaw = 0
        guard manager.isDeviceMotionAvailable,
              CMMotionManager.availableAttitudeReferenceFrames().contains(.xArbitraryZVertical) else { return }
        packet.state = 1
        manager.deviceMotionUpdateInterval = 0.02
        let current = token
        manager.startDeviceMotionUpdates(using: .xArbitraryZVertical, to: .main) { [weak self] sample, error in
            guard let self = self, self.token == current else { return }
            guard error == nil, let sample = sample else {
                self.packet.state = 3; self.packet.flags = 0
                self.packet.generation &+= 1; self.integrator = TrekGyroIntegrator(); return
            }
            let r = sample.rotationRate, g = sample.gravity, a = sample.userAcceleration
            let q = sample.attitude.quaternion
            let values = [sample.timestamp, r.x, r.y, r.z, g.x, g.y, g.z, a.x, a.y, a.z, q.x, q.y, q.z, q.w]
            guard values.allSatisfy({ $0.isFinite }),
                  (g.x*g.x+g.y*g.y+g.z*g.z) > 0.64,
                  (g.x*g.x+g.y*g.y+g.z*g.z) < 1.44 else {
                self.packet.state = 3; self.packet.generation &+= 1
                self.integrator = TrekGyroIntegrator(); return
            }
            if !self.integrator.add(time: sample.timestamp, rate: SIMD3(r.x,r.y,r.z), gravity: SIMD3(g.x,g.y,g.z)) {
                self.packet.generation &+= 1
            }
            self.packet.state = 2
            self.packet.sampleUS = TrekPoseMath.microseconds(sample.timestamp)
            self.packet.quaternion = SIMD4(Float(q.x), Float(q.y), Float(q.z), Float(q.w))
            self.packet.gyro = SIMD3(Float(r.x), Float(r.y), Float(r.z))
            self.packet.gravity = SIMD3(Float(g.x), Float(g.y), Float(g.z))
            self.packet.acceleration = SIMD3(Float(a.x*9.80665), Float(a.y*9.80665), Float(a.z*9.80665))
            self.packet.integratedYaw = Float(self.integrator.yaw)
        }
    }
}
