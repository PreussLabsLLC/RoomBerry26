// @(#)GridCamera.swift 3.1.tiles.1 2026/11/05 16:00:00
import AVFoundation
import CoreMotion
import simd

final class GridCamera: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    let capture = AVCaptureSession()
    let health = PhoneTelemetry()
    private let queue = DispatchQueue(label:"GridRunner.capture",qos:.userInitiated)
    private let reporting = DispatchQueue(label:"GridRunner.reporting",qos:.userInitiated)
    private let imuQueue: OperationQueue = { let q = OperationQueue(); q.maxConcurrentOperationCount = 1; return q }()
    private let motion = CMMotionManager()
    private let lock = NSLock()
    private var activeSession: UInt64 = 0
    private var packet = GridPacket()
    private var sequence: UInt32 = 0
    private var gravity = SIMD3<Double>(0,0,-1)
    private var gravityTime = 0.0
    private var config = GridConfiguration()
    private var crossingTracker = GridCrossingTracker()
    private var crossingState = GridCrossingState()
    private var timer: DispatchSourceTimer?
    private var camera: AVCaptureDevice?
    private var configured = false
    private var captureSession: UInt64 = 0 // capture queue only
    private var focusReadyAt = 0.0
    private var torch = false
    var onPacket: ((GridPacket)->Void)?
    var onOverlay: ((GridPacket)->Void)? // main queue, <=10 Hz
    var onError: ((String)->Void)? // main queue
    override init() {
        super.init()
        NotificationCenter.default.addObserver(self,selector:#selector(interrupted),name:.AVCaptureSessionWasInterrupted,object:capture)
        NotificationCenter.default.addObserver(self,selector:#selector(interrupted),name:.AVCaptureSessionRuntimeError,object:capture)
    }
    deinit { NotificationCenter.default.removeObserver(self) }
    @objc private func interrupted() {
        stop()
        DispatchQueue.main.async { self.onError?("Camera interrupted. Stop and start explicitly.") }
    }
    private func isActive(_ session: UInt64) -> Bool {
        lock.lock(); defer { lock.unlock() }; return activeSession == session && session != 0
    }
    func setTorch(_ enabled: Bool) {
        queue.async { self.torch = enabled; self.applyTorch() }
    }
    private func applyTorch() {
        guard let device = camera, device.hasTorch else { return }
        do {
            try device.lockForConfiguration(); defer { device.unlockForConfiguration() }
            if torch && capture.isRunning { try device.setTorchModeOn(level:AVCaptureDevice.maxAvailableTorchLevel) }
            else { device.torchMode = .off }
        } catch { DispatchQueue.main.async { self.onError?("LED: "+error.localizedDescription) } }
    }
    func start(config: GridConfiguration, session: UInt64) {
        guard config.valid else { return }
        lock.lock()
        activeSession = session; sequence = 0; gravityTime = 0
        packet = GridPacket(); packet.session = session; packet.calibration = config.identity
        packet.config = config; packet.direction = config.direction
        crossingState = GridCrossingState()
        lock.unlock()
        queue.async {
            guard self.isActive(session) else { return }
            self.config = config; self.captureSession = session
            self.crossingTracker.reset()
            do {
                if !self.configured { try self.configure() }
                guard self.motion.isDeviceMotionAvailable else { throw Failure.message("Device motion unavailable") }
                self.health.start(session:session,calibration:config.identity,mountYawDegrees:config.yawDegrees)
                self.motion.deviceMotionUpdateInterval = 0.01
                self.motion.startDeviceMotionUpdates(using:.xArbitraryZVertical,to:self.imuQueue) { [weak self] value,_ in
                    guard let self = self, let m = value, self.isActive(session) else { return }
                    self.health.record(m,session:session)
                    self.lock.lock(); self.gravity = SIMD3(m.gravity.x,m.gravity.y,m.gravity.z)
                    self.gravityTime = m.timestamp; self.lock.unlock()
                }
                self.capture.startRunning(); self.applyTorch()
                self.focusReadyAt = ProcessInfo.processInfo.systemUptime+1
                if let camera = self.camera {
                    try camera.lockForConfiguration()
                    if camera.isFocusModeSupported(.autoFocus) { camera.focusMode = .autoFocus }
                    camera.unlockForConfiguration()
                }
                self.reporting.async {
                    self.timer?.cancel()
                    let t = DispatchSource.makeTimerSource(queue:self.reporting)
                    t.schedule(deadline:.now(),repeating:.milliseconds(100))
                    t.setEventHandler { [weak self] in self?.emit(session:session) }
                    self.timer = t; t.resume()
                }
            } catch {
                self.stop()
                DispatchQueue.main.async { self.onError?(error.localizedDescription) }
            }
        }
    }
    func stop() {
        lock.lock()
        let session = activeSession
        activeSession = 0
        var stopped = packet
        sequence &+= 1; stopped.sequence = sequence; stopped.flags = 0; stopped.reason = 3
        stopped.sendUS = GroundPacket.us(ProcessInfo.processInfo.systemUptime)
        stopped.detection.correction = 0
        stopped.crossing = crossingState
        lock.unlock()
        if session != 0 { onPacket?(stopped) }
        health.stop()
        reporting.async { self.timer?.cancel(); self.timer = nil }
        queue.async {
            self.torch = false; self.applyTorch()
            self.motion.stopDeviceMotionUpdates(); self.capture.stopRunning()
        }
    }
    private func emit(session: UInt64) {
        lock.lock()
        guard activeSession == session else { lock.unlock(); return }
        var p = packet
        sequence &+= 1; p.sequence = sequence
        p.sendUS = GroundPacket.us(ProcessInfo.processInfo.systemUptime)
        if p.frameUS == 0 || p.frameUS > p.sendUS || p.sendUS-p.frameUS > 250000 {
            p.flags = 2; p.reason = 2; p.detection.valid = false; p.detection.correction = 0
        }
        lock.unlock()
        onPacket?(p)
        NSLog("GridRunner seq=%u valid=%d rows=(%0.4f,%0.4f)/(%0.4f,%0.4f) offset=%0.2f angle=%0.4f confidence=%0.3f correction=%0.4f direction=%d reason=%u tiles=%u",
              p.sequence,p.flags == 3 ? 1:0,p.detection.first.x,p.detection.first.y,
              p.detection.second.x,p.detection.second.y,p.detection.offset,p.detection.angle,
              p.detection.confidence,p.detection.correction,Int(p.direction),p.reason,p.crossing.count)
        DispatchQueue.main.async { self.onOverlay?(p) }
    }
    private func configure() throws {
        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera,for:.video,position:.back) else { throw Failure.message("Rear camera unavailable") }
        let input = try AVCaptureDeviceInput(device:device)
        capture.beginConfiguration(); defer { capture.commitConfiguration() }
        capture.sessionPreset = .vga640x480
        guard capture.canAddInput(input) else { throw Failure.message("Camera input unavailable") }
        capture.addInput(input)
        let output = AVCaptureVideoDataOutput()
        output.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String:kCVPixelFormatType_420YpCbCr8BiPlanarFullRange]
        output.alwaysDiscardsLateVideoFrames = true; output.setSampleBufferDelegate(self,queue:queue)
        guard capture.canAddOutput(output) else { throw Failure.message("Camera output unavailable") }
        capture.addOutput(output)
        if let connection = output.connection(with:.video) {
            connection.videoOrientation = .portrait
            if connection.isVideoStabilizationSupported { connection.preferredVideoStabilizationMode = .off }
            if connection.isCameraIntrinsicMatrixDeliverySupported { connection.isCameraIntrinsicMatrixDeliveryEnabled = true }
        }
        try device.lockForConfiguration(); defer { device.unlockForConfiguration() }
        device.videoZoomFactor = 1
        if device.activeFormat.videoSupportedFrameRateRanges.contains(where: { $0.minFrameRate<=30 && $0.maxFrameRate>=30 }) {
            device.activeVideoMinFrameDuration = CMTime(value:1,timescale:30)
            device.activeVideoMaxFrameDuration = CMTime(value:1,timescale:30)
        }
        if device.isAutoFocusRangeRestrictionSupported { device.autoFocusRangeRestriction = .near }
        camera = device; configured = true
    }
    private func intrinsic(_ sample: CMSampleBuffer, width: Int, height: Int) -> simd_double3x3 {
        let fov = Double(camera?.activeFormat.videoFieldOfView ?? 60)
        let f = Double(height)/(2*tan(fov * .pi/360))
        var k = simd_double3x3(columns:(SIMD3(f,0,0),SIMD3(0,f,0),SIMD3(Double(width)/2,Double(height)/2,1)))
        if let data = CMGetAttachment(sample,key:kCMSampleBufferAttachmentKey_CameraIntrinsicMatrix,attachmentModeOut:nil) as? Data,
           data.count == MemoryLayout<simd_float3x3>.size {
            var matrix = matrix_identity_float3x3
            _ = withUnsafeMutableBytes(of:&matrix) { data.copyBytes(to:$0) }
            let m = simd_double3x3(columns:(SIMD3<Double>(matrix.columns.0),SIMD3<Double>(matrix.columns.1),SIMD3<Double>(matrix.columns.2)))
            if m[0][0]>0 && m[1][1]>0 && abs(m[2][0]-Double(width)/2)<Double(width)*0.15 && abs(m[2][1]-Double(height)/2)<Double(height)*0.15 { k = m }
        }
        return k
    }
    func captureOutput(_ output: AVCaptureOutput,didOutput sample: CMSampleBuffer,from connection: AVCaptureConnection) {
        let session = captureSession
        guard isActive(session), let buffer = CMSampleBufferGetImageBuffer(sample) else { return }
        let now = ProcessInfo.processInfo.systemUptime
        let time = CMTimeGetSeconds(CMSampleBufferGetPresentationTimeStamp(sample))
        let width = CVPixelBufferGetWidth(buffer), height = CVPixelBufferGetHeight(buffer)
        health.setDimensions(width:width,height:height)
        lock.lock(); let g = gravity; let gt = gravityTime; var p = packet; lock.unlock()
        p.width = UInt16(clamping:width); p.height = UInt16(clamping:height)
        p.flags = 2; p.reason = 4; p.detection = GridDetection()
        if time.isFinite && time>0 && time<=now { p.frameUS = GroundPacket.us(time) }
        if now >= focusReadyAt && camera?.isAdjustingFocus == false {
            if time.isFinite && time>0 && time<=now && now-time<=0.15 && abs(time-gt)<=0.05 && -g.z>=cos(10 * .pi/180) {
                let k = intrinsic(sample,width:width,height:height)
                CVPixelBufferLockBaseAddress(buffer,.readOnly)
                if let base = CVPixelBufferGetBaseAddressOfPlane(buffer,0) {
                    p.detection = GridLine.detect(luma:base.assumingMemoryBound(to:UInt8.self),width:width,height:height,
                                                  stride:CVPixelBufferGetBytesPerRowOfPlane(buffer,0),k:k,gravity:g,config:config)
                    let band = GridCrossing.detect(luma:base.assumingMemoryBound(to:UInt8.self),width:width,height:height,
                                                   stride:CVPixelBufferGetBytesPerRowOfPlane(buffer,0),
                                                   config:self.crossingTracker.config)
                    self.lock.lock()
                    let event = self.crossingTracker.update(band,time:time)
                    self.crossingState = self.crossingTracker.state
                    let crossing = self.crossingState
                    self.lock.unlock()
                    p.crossing = crossing
                    if let event = event {
                        NSLog("GridRunner tile crossing count=%u time=%.6f y=%.4f confidence=%.3f interval=%.3f",
                              event.count,event.time,event.y,event.confidence,event.interval)
                    }
                    p.flags = p.detection.valid ? 3:2; p.reason = p.detection.valid ? 0:1
                } else { p.reason = 6 }
                CVPixelBufferUnlockBaseAddress(buffer,.readOnly)
            } else { p.reason = 5 }
        }
        lock.lock(); if activeSession == session { packet = p }; lock.unlock()
    }
    enum Failure: LocalizedError {
        case message(String)
        var errorDescription: String? { if case .message(let s) = self { return s }; return nil }
    }
}
