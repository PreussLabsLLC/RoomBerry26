// @(#)RoomTrekSession.swift 3.1.roomtrek.2 2026/11/08 12:00:00
import ARKit
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
            if navLinkEnabled && running { startLink() } else { link.stop() }
        }
    }
    private var running = false
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

    let logger = TrekLogger()
    let link = TrekLink()

    override init() {
        super.init()
    }

    // MARK: - Session control

    func startSurveyor(arSession: ARSession) {
        mode = .survey; mapID = nil; relocState = .notNeeded
        begin(arSession: arSession)
        logger.logEvent("session_start", "Surveyor")
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
        catch { report("Reset failed: \(error.localizedDescription)"); return }
        startNavigator(arSession: arSession, map: map, mapID: mapID)
        logger.logEvent("relocalization_retry", "map=\(mapID.uuidString)")
    }

    func stop() {
        timer?.invalidate(); timer = nil
        link.stop()
        logger.logEvent("session_stop", mode == .survey ? "Surveyor" : "Navigator")
        if mode == .navigate && relocState != .localized {
            logger.logEvent("relocalization_outcome", "stopped_without_candidate")
        }
        logger.flush()
        running = false; latestPose = nil; previous = nil
        arSession?.pause()
    }

    private var arSessionRef: ARSession? { arSession }

    private func begin(arSession: ARSession, initialWorldMap: ARWorldMap? = nil) {
        latestPose = nil; previous = nil
        observedRelocalizing = false
        lastTracking = ""; lastMapping = ""
        running = true
        self.arSession = arSession
        arSession.delegate = self
        arSession.delegateQueue = .main
        guard ARWorldTrackingConfiguration.isSupported else {
            report("ARKit world tracking is not supported on this device.")
            logger.logEvent("session_error", "unsupported")
            return
        }
        let config = ARWorldTrackingConfiguration()
        config.worldAlignment = .gravity
        if mode == .navigate, let map = initialWorldMap {
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
        if mode == .navigate {
            relocState = .relocalizing
            relocStarted = ProcessInfo.processInfo.systemUptime
        } else {
            relocState = .notNeeded
        }
        UIDevice.current.isBatteryMonitoringEnabled = true
        batteryReadAt = -1
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
        if mode == .navigate {
            let relocalizingNow = (tracking == 1 && reason == 4)
            if relocalizingNow {
                if relocState != .relocalizing { relocStarted = now }
                relocState = .relocalizing
                observedRelocalizing = true
                normalSince = nil
            } else if observedRelocalizing, tracking == 2, let since = normalSince, now - since >= 1.0 {
                if relocState != .localized {
                    relocState = .localized
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
        let valid = baseValid && (mode == .survey || relocState == .localized)
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
        if mode == .navigate { relocState = .relocalizing; observedRelocalizing = false }
        logger.logEvent("interrupted", "")
    }

    func sessionInterruptionEnded(_ session: ARSession) {
        interrupted = false
        sessionID = UInt64.random(in: 1...UInt64.max)
        sequence = 0; previous = nil; normalSince = nil
        if mode == .navigate { relocState = .relocalizing; relocStarted = ProcessInfo.processInfo.systemUptime }
        if navLinkEnabled { startLink() }
        logger.logEvent("interruption_ended", "new session=\(sessionID)")
    }

    func session(_ session: ARSession, didFailWithError error: Error) {
        failed = true; latestPose = nil; previous = nil; normalSince = nil
        logger.logEvent("session_error", error.localizedDescription)
        report("TRACKING error: \(error.localizedDescription)")
    }

    // MARK: - NavLink tick (10 Hz)

    private func tick() {
        guard running else { return }
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
        // Only Navigator observations can be valid map-relative measurements.
        if mode == .navigate && pose.mapID != nil && pose.isValid && age >= 0 && age <= 0.25 && !interrupted && !failed {
            packet.flags = 1
        }
        if navLinkEnabled { link.send(packet.encoded(), session: sessionID) }
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
