// @(#)GroundHogViewController.swift 3.1.compass.1 2026/10/31 12:10:00
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
    private var fields: [UITextField] = []
    private var active = false
    private var requestID = UUID()
    private var batteryTimer: Timer?
    private var calibration = MountCalibration()
    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        if let data = UserDefaults.standard.data(forKey: "mount"), let c = try? JSONDecoder().decode(MountCalibration.self, from: data) { calibration = c }
        let title = UILabel(); title.text = "GroundHog"; title.font = .boldSystemFont(ofSize: 30)
        let help = UILabel(); help.numberOfLines = 0
        help.text = "Floor odometry · NavLink\nRear camera down, screen up. Measure lens height and offset from robot center. Phone top angle: 0° forward, +90° left."
        let preview = FloorPreview()
        preview.cameraLayer.session = tracker.capture
        preview.cameraLayer.videoGravity = .resizeAspect
        preview.heightAnchor.constraint(equalToConstant: 140).isActive = true
        let stack = UIStackView(arrangedSubviews: [title, help, preview]); stack.axis = .vertical; stack.spacing = 10
        let labels = ["Lens height above floor (mm)","Phone top angle (degrees)","Lens forward offset (mm)","Lens left offset (mm)"]
        let values = [calibration.heightMM,calibration.yawDegrees,calibration.lensForwardMM,calibration.lensLeftMM]
        for (name,value) in zip(labels,values) {
            let label = UILabel(); label.text = name; label.font = .systemFont(ofSize: 13)
            let field = UITextField(); field.borderStyle = .roundedRect; field.keyboardType = .numbersAndPunctuation
            field.text = String(format: "%.1f",value); fields.append(field)
            stack.addArrangedSubview(label); stack.addArrangedSubview(field)
        }
        button.setTitle("Start tracking", for: .normal); button.addTarget(self, action: #selector(toggle), for: .touchUpInside)
        status.numberOfLines = 0; status.font = .monospacedSystemFont(ofSize: 13, weight: .regular)
        status.text = "Enter measured mount calibration to begin."
        network.numberOfLines = 0; network.font = .systemFont(ofSize: 12)
        healthStatus.numberOfLines = 0; healthStatus.font = .monospacedSystemFont(ofSize: 12, weight: .regular)
        compassStatus.numberOfLines = 0; compassStatus.font = .monospacedSystemFont(ofSize: 12,weight: .regular)
        stack.addArrangedSubview(button); stack.addArrangedSubview(healthStatus); stack.addArrangedSubview(compassStatus)
        stack.addArrangedSubview(status); stack.addArrangedSubview(network)
        let scroll = UIScrollView(); scroll.keyboardDismissMode = .onDrag
        view.addSubview(scroll); scroll.translatesAutoresizingMaskIntoConstraints = false
        scroll.addSubview(stack); stack.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            scroll.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),scroll.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor),
            scroll.leadingAnchor.constraint(equalTo: view.leadingAnchor),scroll.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            stack.topAnchor.constraint(equalTo: scroll.contentLayoutGuide.topAnchor, constant: 16),stack.bottomAnchor.constraint(equalTo: scroll.contentLayoutGuide.bottomAnchor, constant: -16),
            stack.leadingAnchor.constraint(equalTo: scroll.contentLayoutGuide.leadingAnchor, constant: 20),stack.trailingAnchor.constraint(equalTo: scroll.contentLayoutGuide.trailingAnchor, constant: -20),
            stack.widthAnchor.constraint(equalTo: scroll.frameLayoutGuide.widthAnchor, constant: -40)])
        tracker.onPacket = { [weak self] in self?.link.send($0) }
        tracker.health.onPacket = { [weak self] in self?.link.send($0) }
        tracker.health.onStatus = { [weak self] text in self?.healthStatus.text = text }
        tracker.health.onCompassPacket = { [weak self] in self?.link.send($0) }
        tracker.health.onCompassStatus = { [weak self] text in self?.compassStatus.text = text }
        tracker.onStatus = { [weak self] text in self?.status.text = text }
        link.onStatus = { [weak self] text in self?.network.text = text }
        NotificationCenter.default.addObserver(self, selector: #selector(stop), name: UIApplication.willResignActiveNotification, object: nil)
    }
    deinit { NotificationCenter.default.removeObserver(self) }
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
        network.text = "Stopped"
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
