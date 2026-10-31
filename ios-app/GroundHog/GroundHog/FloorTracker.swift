// @(#)FloorTracker.swift 3.1.compass.1 2026/10/31 12:10:00
import AVFoundation
import CoreMotion
import Vision
import simd

final class FloorTracker: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    let capture = AVCaptureSession()
    let health = PhoneTelemetry()
    private let queue = DispatchQueue(label: "GroundHog.capture", qos: .userInitiated)
    private let motion = CMMotionManager()
    private let motionQueue: OperationQueue = { let q = OperationQueue(); q.maxConcurrentOperationCount = 1; return q }()
    private let lock = NSLock()
    private struct IMU { var time: Double; var yaw: Double; var rate: Double; var gravity: SIMD3<Double> }
    private var samples: [IMU] = []
    private struct Frame { var image: CVPixelBuffer; var time: Double; var imu: IMU; var k: simd_double3x3 }
    private var previous: Frame?
    private var mount = MountCalibration()
    private var packet = GroundPacket()
    private var tally = PlanarTransform()
    private var path: Double = 0
    private var duration: Double = 0
    private var running = false
    private var configured = false
    private var focusReadyAt: Double = 0
    private var camera: AVCaptureDevice?
    private var timer: DispatchSourceTimer?
    private var battery: (UInt8, UInt8) = (255, 0)
    var onPacket: ((GroundPacket) -> Void)? // capture queue
    var onStatus: ((String) -> Void)? // delivered on main

    override init() {
        super.init()
        NotificationCenter.default.addObserver(self, selector: #selector(interrupted), name: .AVCaptureSessionWasInterrupted, object: capture)
        NotificationCenter.default.addObserver(self, selector: #selector(interrupted), name: .AVCaptureSessionRuntimeError, object: capture)
    }
    deinit { NotificationCenter.default.removeObserver(self) }
    private func status(_ text: String) { DispatchQueue.main.async { self.onStatus?(text) } }
    @objc private func interrupted() { queue.async { self.breakTracking(5, countFrame: false); self.previous = nil } }
    func setBattery(_ percent: UInt8, _ state: UInt8) {
        health.setBattery(percent,state)
        queue.async { self.battery = (percent,state) }
    }

    func start(_ calibration: MountCalibration) {
        queue.async {
            guard !self.running, calibration.valid else { return }
            self.mount = calibration
            self.packet = GroundPacket(); self.packet.session = UInt64.random(in: 1...UInt64.max)
            self.packet.calibration = calibration.identity
            self.packet.flags = 2; self.packet.values[7] = Float(calibration.heightMM)
            self.tally = PlanarTransform(); self.path = 0; self.duration = 0; self.previous = nil
            self.lock.lock(); self.samples = []; self.lock.unlock()
            do {
                if !self.configured { try self.configure() }
                guard self.motion.isDeviceMotionAvailable else { throw TrackerError.message("Device motion unavailable") }
                self.running = true
                let epoch = self.packet.session
                self.health.start(session: epoch,calibration: calibration.identity,mountYawDegrees: calibration.yawDegrees)
                self.motion.deviceMotionUpdateInterval = 0.01
                self.motion.startDeviceMotionUpdates(using: .xArbitraryZVertical, to: self.motionQueue) { [weak self] value, _ in
                    guard let self = self, let m = value else { return }
                    self.health.record(m,session: epoch)
                    let g = SIMD3(m.gravity.x, m.gravity.y, m.gravity.z)
                    let w = SIMD3(m.rotationRate.x, m.rotationRate.y, m.rotationRate.z)
                    let rate = -simd_dot(w,g)
                    guard rate.isFinite, simd_length(g) > 0.9 else { return }
                    self.lock.lock(); defer { self.lock.unlock() }
                    let old = self.samples.last
                    let dt = old.map { m.timestamp - $0.time } ?? 0
                    let yaw = (old?.yaw ?? 0) + (dt > 0 && dt < 0.1 ? dt * (rate + (old?.rate ?? rate)) / 2 : 0)
                    self.samples.append(IMU(time: m.timestamp, yaw: yaw, rate: rate, gravity: g))
                    if self.samples.count > 400 { self.samples.removeFirst(self.samples.count - 400) }
                }
                self.focusReadyAt = ProcessInfo.processInfo.systemUptime + 1
                if let camera = self.camera {
                    try camera.lockForConfiguration()
                    if camera.isFocusModeSupported(.autoFocus) { camera.focusMode = .autoFocus }
                    camera.unlockForConfiguration()
                }
                self.capture.startRunning()
                let timer = DispatchSource.makeTimerSource(queue: self.queue)
                timer.schedule(deadline: .now(), repeating: .milliseconds(100))
                timer.setEventHandler { [weak self] in self?.emit() }
                self.timer = timer; timer.resume()
                self.status("Acquiring floor texture…")
            } catch {
                self.running = false; self.motion.stopDeviceMotionUpdates(); self.health.stop()
                self.capture.stopRunning(); self.status(error.localizedDescription)
            }
        }
    }
    func stop() {
        health.stop()
        queue.async {
            self.running = false; self.timer?.cancel(); self.timer = nil
            self.health.stop(); self.motion.stopDeviceMotionUpdates(); self.capture.stopRunning(); self.previous = nil
            self.status("Stopped")
        }
    }
    enum TrackerError: LocalizedError {
        case message(String)
        var errorDescription: String? { if case .message(let s) = self { return s }; return nil }
    }
    private func configure() throws {
        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back) else {
            throw TrackerError.message("Rear camera unavailable")
        }
        let input = try AVCaptureDeviceInput(device: device)
        capture.beginConfiguration(); defer { capture.commitConfiguration() }
        capture.sessionPreset = .vga640x480
        guard capture.canAddInput(input) else { throw TrackerError.message("Camera input unavailable") }
        capture.addInput(input)
        let output = AVCaptureVideoDataOutput()
        output.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_420YpCbCr8BiPlanarFullRange]
        output.alwaysDiscardsLateVideoFrames = true
        output.setSampleBufferDelegate(self, queue: queue)
        guard capture.canAddOutput(output) else { capture.removeInput(input); throw TrackerError.message("Video output unavailable") }
        capture.addOutput(output)
        if let connection = output.connection(with: .video) {
            connection.videoOrientation = .portrait
            if connection.isVideoStabilizationSupported { connection.preferredVideoStabilizationMode = .off }
            if connection.isCameraIntrinsicMatrixDeliverySupported {
                connection.isCameraIntrinsicMatrixDeliveryEnabled = true
            }
        }
        try device.lockForConfiguration(); defer { device.unlockForConfiguration() }
        device.videoZoomFactor = 1
        if device.activeFormat.videoSupportedFrameRateRanges.contains(where: { $0.minFrameRate <= 30 && $0.maxFrameRate >= 30 }) {
            device.activeVideoMinFrameDuration = CMTime(value: 1, timescale: 30)
            device.activeVideoMaxFrameDuration = CMTime(value: 1, timescale: 30)
        }
        // One-shot autofocus settles at each start, then stays fixed. Reject
        // frames during focus adjustment. No continuous focus breathing.
        if device.isAutoFocusRangeRestrictionSupported { device.autoFocusRangeRestriction = .near }
        camera = device
        configured = true
    }
    private func imu(at t: Double) -> IMU? {
        lock.lock(); let values = samples; lock.unlock()
        guard let nearest = values.min(by: { abs($0.time-t) < abs($1.time-t) }), abs(nearest.time-t) <= 0.025 else { return nil }
        // Require uninterrupted IMU coverage throughout the image interval.
        let from = previous?.time ?? t
        let interval = values.filter { $0.time >= from - 0.02 && $0.time <= t + 0.02 }
        guard zip(interval, interval.dropFirst()).allSatisfy({ $1.time - $0.time <= 0.03 }) else { return nil }
        return IMU(time: t, yaw: nearest.yaw + nearest.rate * (t-nearest.time), rate: nearest.rate, gravity: nearest.gravity)
    }
    private func newSession() {
        packet.session = UInt64.random(in: 1...UInt64.max)
        packet.sequence = 0; packet.continuity = 0
        packet.accepted = 0; packet.rejected = 0
    }
    private func breakTracking(_ reason: UInt8, countFrame: Bool = true) {
        if packet.flags & 4 != 0 {
            if packet.continuity == .max { newSession() }
            else { packet.continuity += 1 }
        }
        packet.flags = 2; packet.state = 1; packet.reason = reason
        if countFrame { packet.rejected = packet.rejected == .max ? .max : packet.rejected + 1 }
        tally = PlanarTransform(); path = 0; duration = 0
        for i in 0..<12 where i != 7 { packet.values[i] = 0 }
        packet.inliers = 0; packet.candidates = 0
    }
    private func emit() {
        guard running else { return }
        let now = ProcessInfo.processInfo.systemUptime
        if packet.endUS == 0 || now - Double(packet.endUS)/1e6 > 0.25 {
            breakTracking(4, countFrame: false); previous = nil
        }
        if packet.sequence == .max {
            newSession(); packet.flags = 2
            breakTracking(1, countFrame: false); previous = nil
        }
        packet.sendUS = GroundPacket.us(now); packet.sequence += 1
        packet.battery = battery.0; packet.batteryState = battery.1
        onPacket?(packet)
        let p = tally.position
        status(String(format: "%@  X %.1f  Y %.1f mm\nYaw %.1f° · segment %u\nAccepted %u · lost %u · residual %.2f mm",
                      packet.flags & 1 != 0 ? "TRACKING" : "NO LOCK (reason \(packet.reason))",
                      p.x, p.y, tally.yaw * 180 / .pi, packet.continuity, packet.accepted, packet.rejected, packet.values[6]))
    }
    func captureOutput(_ output: AVCaptureOutput, didOutput sample: CMSampleBuffer, from connection: AVCaptureConnection) {
        guard running, let buffer = CMSampleBufferGetImageBuffer(sample) else { return }
        health.setDimensions(width: CVPixelBufferGetWidth(buffer),height: CVPixelBufferGetHeight(buffer))
        autoreleasepool { [self] in
            let began = ProcessInfo.processInfo.systemUptime
            guard began >= focusReadyAt, camera?.isAdjustingFocus == false else {
                breakTracking(1); previous = nil; return
            }
            let time = CMTimeGetSeconds(CMSampleBufferGetPresentationTimeStamp(sample))
            guard time.isFinite, time > 0, time <= began, began-time <= 0.15, let imu = imu(at: time), -imu.gravity.z > cos(10 * .pi/180) else {
                breakTracking(3); previous = nil; return
            }
            let width = CVPixelBufferGetWidth(buffer), height = CVPixelBufferGetHeight(buffer)
            // Native landscape FOV -> portrait delivered pixels, fixed zoom=1.
            let fieldOfView = Double(camera?.activeFormat.videoFieldOfView ?? 0)
            guard fieldOfView > 0, fieldOfView < 180 else { breakTracking(6); return }
            let f = Double(height) / (2 * tan(fieldOfView * .pi / 360))
            var k = simd_double3x3(columns: (SIMD3(f,0,0), SIMD3(0,f,0), SIMD3(Double(width)/2,Double(height)/2,1)))
            if let data = CMGetAttachment(sample, key: kCMSampleBufferAttachmentKey_CameraIntrinsicMatrix, attachmentModeOut: nil) as? Data,
               data.count == MemoryLayout<simd_float3x3>.size {
                var matrix = matrix_identity_float3x3
                _ = withUnsafeMutableBytes(of: &matrix) { data.copyBytes(to: $0) }
                let m = simd_double3x3(columns: (SIMD3<Double>(matrix.columns.0), SIMD3<Double>(matrix.columns.1), SIMD3<Double>(matrix.columns.2)))
                // Intrinsics are expressed in the delivered frame, upper left
                // origin. Reject an inconsistent principal point or focal length.
                if m[0][0] > 0, m[1][1] > 0,
                   abs(m[2][0]-Double(width)/2) < Double(width)*0.15,
                   abs(m[2][1]-Double(height)/2) < Double(height)*0.15 {
                    k = m
                }
            }
            let current = Frame(image: buffer, time: time, imu: imu, k: k)
            guard let old = previous else { previous = current; return }
            previous = current
            let dt = time - old.time
            guard dt > 0, dt <= 0.15 else { breakTracking(4); return }
            let yaw = imu.yaw - old.imu.yaw
            guard abs(yaw) < 0.25 else { breakTracking(2); return }
            do {
                // Empirically verified with synthetic +8/+4 pixel translation:
                // handler(previous) -> targeted(current), row coordinates down.
                // Pin classical revision 1 for iOS15.
                let request = VNGenerateOpticalFlowRequest(targetedCVPixelBuffer: buffer, options: [:])
                request.revision = VNGenerateOpticalFlowRequestRevision1
                request.computationAccuracy = .low
                request.outputPixelFormat = kCVPixelFormatType_TwoComponent32Float
                try VNImageRequestHandler(cvPixelBuffer: old.image, orientation: .up, options: [:]).perform([request])
                guard let flow = request.results?.first?.pixelBuffer else { breakTracking(6); return }
                let candidates = translations(flow: flow, old: old, current: current, yaw: yaw)
                guard let fit = FloorGeometry.fit(candidates) else { breakTracking(7); return }
                let camera = mount.robot(fit.delta)
                let center = PlanarTransform.centerDelta(camera: camera, yaw: yaw, mount: mount)
                guard simd_length(center)/dt <= 1000, abs(yaw)/dt <= 4 else { breakTracking(2); return }
                guard ProcessInfo.processInfo.systemUptime-time <= 0.25 else { breakTracking(4); previous = nil; return }
                tally.append(center, yaw: yaw); path += simd_length(center); duration += dt
                packet.flags = 7; packet.state = 2; packet.reason = 0
                packet.accepted = packet.accepted == .max ? .max : packet.accepted + 1
                packet.startUS = GroundPacket.us(old.time); packet.endUS = GroundPacket.us(time)
                packet.values = [Float(tally.position.x),Float(tally.position.y),Float(tally.yaw),Float(center.x),Float(center.y),Float(yaw),Float(fit.rms),Float(mount.heightMM),Float(path),Float(duration),Float(center.x/dt),Float(center.y/dt)]
                packet.inliers = UInt16(clamping: fit.inliers); packet.candidates = UInt16(clamping: candidates.count)
                packet.processingUS = UInt32(clamping: GroundPacket.us(ProcessInfo.processInfo.systemUptime-began))
            } catch { breakTracking(6) }
        }
    }
    private func translations(flow: CVPixelBuffer, old: Frame, current: Frame, yaw: Double) -> [SIMD2<Double>] {
        guard CVPixelBufferGetWidth(flow) == CVPixelBufferGetWidth(old.image),
              CVPixelBufferGetHeight(flow) == CVPixelBufferGetHeight(old.image),
              CVPixelBufferGetPixelFormatType(flow) == kCVPixelFormatType_TwoComponent32Float else { return [] }
        CVPixelBufferLockBaseAddress(flow, .readOnly)
        CVPixelBufferLockBaseAddress(old.image, .readOnly)
        CVPixelBufferLockBaseAddress(current.image, .readOnly)
        defer {
            CVPixelBufferUnlockBaseAddress(flow, .readOnly); CVPixelBufferUnlockBaseAddress(old.image, .readOnly)
            CVPixelBufferUnlockBaseAddress(current.image, .readOnly)
        }
        guard let base = CVPixelBufferGetBaseAddress(flow),
              let oldBase = CVPixelBufferGetBaseAddressOfPlane(old.image,0),
              let newBase = CVPixelBufferGetBaseAddressOfPlane(current.image,0) else { return [] }
        let w = CVPixelBufferGetWidth(flow), h = CVPixelBufferGetHeight(flow)
        let strideOld = CVPixelBufferGetBytesPerRowOfPlane(old.image,0), strideNew = CVPixelBufferGetBytesPerRowOfPlane(current.image,0)
        let oldY = oldBase.assumingMemoryBound(to: UInt8.self), newY = newBase.assumingMemoryBound(to: UInt8.self)
        var candidates: [SIMD2<Double>] = []
        var cells = Set<Int>()
        for y in stride(from: h/8, to: 7*h/8, by: 16) {
            let row = base.advanced(by: y * CVPixelBufferGetBytesPerRow(flow)).assumingMemoryBound(to: Float.self)
            for x in stride(from: w/8, to: 7*w/8, by: 16) {
                let gradient = abs(Int(oldY[y*strideOld+x+2])-Int(oldY[y*strideOld+x-2])) + abs(Int(oldY[(y+2)*strideOld+x])-Int(oldY[(y-2)*strideOld+x]))
                guard gradient >= 12 else { continue }
                let dx = Double(row[2*x]), dy = Double(row[2*x+1])
                guard dx.isFinite, dy.isFinite, abs(dx) < Double(w)/4, abs(dy) < Double(h)/4 else { continue }
                let nx = Double(x)+dx, ny = Double(y)+dy
                guard nx >= 2, nx < Double(w-2), ny >= 2, ny < Double(h-2),
                      abs(Int(oldY[y*strideOld+x])-Int(newY[Int(ny.rounded())*strideNew+Int(nx.rounded())])) <= 35,
                      let a = FloorGeometry.point(pixel: SIMD2(Double(x),Double(y)), intrinsics: old.k, gravity: old.imu.gravity, height: mount.heightMM),
                      let b = FloorGeometry.point(pixel: SIMD2(nx,ny), intrinsics: current.k, gravity: current.imu.gravity, height: mount.heightMM) else { continue }
                candidates.append(a - PlanarTransform.rotate(b,yaw))
                cells.insert((y >= h/2 ? 2 : 0) + (x >= w/2 ? 1 : 0))
            }
        }
        return cells.count == 4 ? candidates : []
    }
}
