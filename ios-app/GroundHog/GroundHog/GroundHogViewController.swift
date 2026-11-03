// @(#)GroundHogViewController.swift 3.1.torch.6 2026/11/02 22:30:00
import UIKit
import AVFoundation

final class GroundHogViewController: UIViewController {
    private let tracker = FloorTracker()
    private let link = GroundLink()
    private let status = UILabel()
    private let network = UILabel()
    private let healthStatus = UILabel()
    private let compassStatus = UILabel()
    private let button = UIButton(type: .system)
    private let ledButton = UIButton(type: .system)
    private var torchRequested = false
    private var fields: [UITextField] = []
    private var active = false
    private var requestID = UUID()
    private var batteryTimer: Timer?
    private var displayTimer: Timer?
    private var latestStatus: String?
    private var latestHealth: String?
    private var latestCompass: String?
    private var latestNetwork: String?
    override var supportedInterfaceOrientations: UIInterfaceOrientationMask { .landscape }
    override var preferredInterfaceOrientationForPresentation: UIInterfaceOrientation { .landscapeRight }
    private var calibration = MountCalibration()
    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        if let data = UserDefaults.standard.data(forKey: "mount"), let c = try? JSONDecoder().decode(MountCalibration.self, from: data) { calibration = c }
        let title = UILabel(); title.text = "GroundHog"; title.font = .boldSystemFont(ofSize: 24)
        status.numberOfLines = 0; status.font = .monospacedSystemFont(ofSize: 13, weight: .regular)
        status.text = "Enter measured mount calibration to begin."
        network.numberOfLines = 0; network.font = .systemFont(ofSize: 12)
        healthStatus.numberOfLines = 0; healthStatus.font = .monospacedSystemFont(ofSize: 12, weight: .regular)
        compassStatus.numberOfLines = 0; compassStatus.font = .monospacedSystemFont(ofSize: 12, weight: .regular)
        let stack = UIStackView(arrangedSubviews: [title, status, healthStatus, compassStatus, network])
        stack.axis = .vertical; stack.spacing = 8
        let help = UILabel(); help.numberOfLines = 0; help.font = .systemFont(ofSize: 12)
        help.text = "Rear camera down, screen up. Measure lens height and offsets. Phone physical top edge: 0° forward, +90° left."
        stack.addArrangedSubview(help)
        let labels = ["Lens height (mm)","Phone top angle (°)","Lens forward (mm)","Lens left (mm)"]
        let values = [calibration.heightMM,calibration.yawDegrees,calibration.lensForwardMM,calibration.lensLeftMM]
        for (name,value) in zip(labels,values) {
            let label = UILabel(); label.text = name; label.font = .systemFont(ofSize: 12)
            let field = UITextField(); field.borderStyle = .roundedRect; field.keyboardType = .numbersAndPunctuation
            field.text = String(format: "%.1f",value); fields.append(field)
            field.widthAnchor.constraint(equalToConstant: 100).isActive = true
            let row = UIStackView(arrangedSubviews: [label,field]); row.spacing = 8
            stack.addArrangedSubview(row)
        }
        let preview = FloorPreview()
        preview.cameraLayer.session = tracker.capture
        preview.cameraLayer.videoGravity = .resizeAspect
        preview.backgroundColor = .black; preview.layer.cornerRadius = 8; preview.clipsToBounds = true
        preview.translatesAutoresizingMaskIntoConstraints = false
        button.setTitle("Start tracking", for: .normal)
        button.titleLabel?.font = .boldSystemFont(ofSize: 20)
        button.titleLabel?.numberOfLines = 2
        button.backgroundColor = .systemGreen; button.setTitleColor(.white, for: .normal)
        button.layer.cornerRadius = 14
        button.addTarget(self, action: #selector(toggle), for: .touchUpInside)
        button.translatesAutoresizingMaskIntoConstraints = false
        ledButton.setTitle("LED: Off", for: .normal)
        ledButton.titleLabel?.font = .boldSystemFont(ofSize: 18)
        ledButton.titleLabel?.numberOfLines = 2
        ledButton.titleLabel?.textAlignment = .center
        ledButton.backgroundColor = .secondarySystemBackground
        ledButton.layer.cornerRadius = 12
        ledButton.accessibilityHint = "Toggle the rear camera light for floor tracking"
        ledButton.addTarget(self, action: #selector(toggleLED), for: .touchUpInside)
        ledButton.translatesAutoresizingMaskIntoConstraints = false
        let controls = UIView(); controls.translatesAutoresizingMaskIntoConstraints = false
        controls.addSubview(preview); controls.addSubview(button); controls.addSubview(ledButton)
        let scroll = UIScrollView(); scroll.keyboardDismissMode = .onDrag
        scroll.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(scroll); view.addSubview(controls)
        scroll.addSubview(stack); stack.translatesAutoresizingMaskIntoConstraints = false
        let safe = view.safeAreaLayoutGuide
        NSLayoutConstraint.activate([
            controls.topAnchor.constraint(equalTo: safe.topAnchor, constant: 12),
            controls.trailingAnchor.constraint(equalTo: safe.trailingAnchor, constant: -12),
            controls.bottomAnchor.constraint(equalTo: safe.bottomAnchor, constant: -12),
            controls.widthAnchor.constraint(equalToConstant: 160),
            preview.topAnchor.constraint(equalTo: controls.topAnchor),
            preview.centerXAnchor.constraint(equalTo: controls.centerXAnchor),
            preview.widthAnchor.constraint(equalToConstant: 72), preview.heightAnchor.constraint(equalToConstant: 96),
            button.topAnchor.constraint(equalTo: preview.bottomAnchor, constant: 16),
            button.leadingAnchor.constraint(equalTo: controls.leadingAnchor),
            button.trailingAnchor.constraint(equalTo: controls.trailingAnchor),
            button.heightAnchor.constraint(equalToConstant: 76),
            ledButton.topAnchor.constraint(equalTo: button.bottomAnchor, constant: 12),
            ledButton.leadingAnchor.constraint(equalTo: controls.leadingAnchor),
            ledButton.trailingAnchor.constraint(equalTo: controls.trailingAnchor),
            ledButton.heightAnchor.constraint(equalToConstant: 52),
            ledButton.bottomAnchor.constraint(lessThanOrEqualTo: controls.bottomAnchor),
            scroll.topAnchor.constraint(equalTo: safe.topAnchor), scroll.bottomAnchor.constraint(equalTo: safe.bottomAnchor),
            scroll.leadingAnchor.constraint(equalTo: safe.leadingAnchor), scroll.trailingAnchor.constraint(equalTo: controls.leadingAnchor, constant: -12),
            stack.topAnchor.constraint(equalTo: scroll.contentLayoutGuide.topAnchor, constant: 12),
            stack.bottomAnchor.constraint(equalTo: scroll.contentLayoutGuide.bottomAnchor, constant: -12),
            stack.leadingAnchor.constraint(equalTo: scroll.contentLayoutGuide.leadingAnchor, constant: 12),
            stack.trailingAnchor.constraint(equalTo: scroll.contentLayoutGuide.trailingAnchor, constant: -12),
            stack.widthAnchor.constraint(equalTo: scroll.frameLayoutGuide.widthAnchor, constant: -24)])
        tracker.onTorchStatus = { [weak self] requested, text in
            self?.torchRequested = requested
            self?.ledButton.setTitle(text, for: .normal)
            self?.ledButton.backgroundColor = requested ? .systemYellow : .secondarySystemBackground
        }
        tracker.onPacket = { [weak self] in self?.link.send($0) }
        tracker.health.onPacket = { [weak self] in self?.link.send($0) }
        tracker.health.onStatus = { [weak self] text in self?.latestHealth = text }
        tracker.health.onCompassPacket = { [weak self] in self?.link.send($0) }
        tracker.health.onCompassStatus = { [weak self] text in self?.latestCompass = text }
        tracker.onStatus = { [weak self] text in self?.latestStatus = text }
        link.onStatus = { [weak self] text in self?.latestNetwork = text }
        let timer = Timer(timeInterval: 0.5, repeats: true) { [weak self] _ in self?.refreshDisplay() }
        RunLoop.main.add(timer, forMode: .common); displayTimer = timer
        NotificationCenter.default.addObserver(self, selector: #selector(stop), name: UIApplication.willResignActiveNotification, object: nil)
    }
    deinit { displayTimer?.invalidate(); NotificationCenter.default.removeObserver(self) }
    private func refreshDisplay() {
        if let text = latestStatus { status.text = text; latestStatus = nil }
        if let text = latestHealth { healthStatus.text = text; latestHealth = nil }
        if let text = latestCompass { compassStatus.text = text; latestCompass = nil }
        if let text = latestNetwork { network.text = text; latestNetwork = nil }
    }
    @objc private func toggleLED() {
        torchRequested.toggle()
        tracker.setTorch(torchRequested)
    }
    @objc private func toggle() {
        if active { stop(); return }
        view.endEditing(true)
        let values = fields.compactMap { Double(($0.text ?? "").replacingOccurrences(of: ",", with: ".")) }
        guard values.count == 4 else { status.text = "Enter four numeric calibration values."; return }
        var c = MountCalibration(heightMM: values[0],yawDegrees: values[1],lensForwardMM: values[2],lensLeftMM: values[3],identity: calibration.identity)
        if [c.heightMM,c.yawDegrees,c.lensForwardMM,c.lensLeftMM] != [calibration.heightMM,calibration.yawDegrees,calibration.lensForwardMM,calibration.lensLeftMM] || c.identity == 0 {
            c.identity = UInt64.random(in: 1...UInt64.max)
        }
        guard c.valid else { status.text = "Height must be 50–1500 mm, angle ±360°, offsets ±1000 mm."; return }
        calibration = c; UserDefaults.standard.set(try? JSONEncoder().encode(c), forKey: "mount")
        let id = UUID(); requestID = id
        AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in
            DispatchQueue.main.async {
                guard let self = self, self.requestID == id, UIApplication.shared.applicationState == .active else { return }
                guard granted else { self.status.text = "Allow camera access in Settings to track the floor."; return }
                self.active = true; self.fields.forEach { $0.isEnabled = false }
                self.button.setTitle("Stop tracking", for: .normal)
                self.button.backgroundColor = .systemRed
                UIApplication.shared.isIdleTimerDisabled = true
                UIDevice.current.isBatteryMonitoringEnabled = true
                self.updateBattery()
                self.batteryTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in self?.updateBattery() }
                self.link.start(); self.tracker.start(c)
            }
        }
    }
    private func updateBattery() {
        let device = UIDevice.current
        let percent: UInt8 = device.batteryLevel < 0 ? 255 : UInt8(min(100,max(0,device.batteryLevel*100)))
        let state: UInt8
        switch device.batteryState { case .unplugged: state = 1; case .charging: state = 2; case .full: state = 3; default: state = 0 }
        tracker.setBattery(percent,state)
    }
    @objc private func stop() {
        requestID = UUID(); active = false
        tracker.stop(); link.stop(); batteryTimer?.invalidate(); batteryTimer = nil
        UIDevice.current.isBatteryMonitoringEnabled = false
        UIApplication.shared.isIdleTimerDisabled = false
        fields.forEach { $0.isEnabled = true }; button.setTitle("Start tracking", for: .normal)
        button.backgroundColor = .systemGreen
        latestNetwork = "Stopped"; latestStatus = "Stopped"
        latestHealth = nil; latestCompass = nil
        refreshDisplay()
    }
}

private final class FloorPreview: UIView {
    override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }
    var cameraLayer: AVCaptureVideoPreviewLayer { layer as! AVCaptureVideoPreviewLayer }
    override func layoutSubviews() {
        super.layoutSubviews()
        if cameraLayer.connection?.isVideoOrientationSupported == true {
            cameraLayer.connection?.videoOrientation = .portrait
        }
    }
}
