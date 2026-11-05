// @(#)GridRunnerViewController.swift 3.1.grid.2 2026/11/03 20:30:00
import UIKit
import AVFoundation

final class GridPreview: UIView {
    let cameraLayer = AVCaptureVideoPreviewLayer()
    let rotatedContent = UIView()
    override init(frame: CGRect = .zero) {
        super.init(frame: frame)
        configure()
    }
    required init?(coder: NSCoder) {
        super.init(coder: coder)
        configure()
    }
    private func configure() {
        clipsToBounds = true
        addSubview(rotatedContent)
        rotatedContent.layer.addSublayer(cameraLayer)
    }
    override func layoutSubviews() {
        super.layoutSubviews()
        // Rotate image and overlay together. Capture/detection stay portrait.
        rotatedContent.transform = .identity
        rotatedContent.bounds = CGRect(x: 0, y: 0, width: bounds.height, height: bounds.width)
        rotatedContent.center = CGPoint(x: bounds.midX, y: bounds.midY)
        cameraLayer.frame = rotatedContent.bounds
        rotatedContent.transform = CGAffineTransform(rotationAngle: .pi / 2)
    }
}

final class GridOverlay: UIView {
    var packet: GridPacket? { didSet { setNeedsDisplay() } }
    override func draw(_ rect: CGRect) {
        guard let p = packet, let ctx = UIGraphicsGetCurrentContext() else { return }
        let aspect = CGFloat(p.width)/CGFloat(p.height)
        var area = bounds
        if area.width/area.height > aspect { area.size.width = area.height*aspect; area.origin.x = (bounds.width-area.width)/2 }
        else { area.size.height = area.width/aspect; area.origin.y = (bounds.height-area.height)/2 }
        func point(_ v: SIMD2<Double>) -> CGPoint { CGPoint(x:area.minX+CGFloat(v.x)*area.width,y:area.minY+CGFloat(v.y)*area.height) }
        let d = p.detection
        ctx.setLineWidth(1); ctx.setStrokeColor(UIColor.systemYellow.cgColor)
        for v in [d.first,d.second] {
            let y = point(v).y
            ctx.move(to:CGPoint(x:area.minX,y:y)); ctx.addLine(to:CGPoint(x:area.maxX,y:y)); ctx.strokePath()
        }
        ctx.setLineWidth(2); ctx.setStrokeColor(UIColor.systemCyan.cgColor)
        ctx.move(to:point(d.targetFirst)); ctx.addLine(to:point(d.targetSecond)); ctx.strokePath()
        if p.flags == 3 {
            ctx.setStrokeColor(UIColor.systemGreen.cgColor)
            ctx.move(to:point(d.first)); ctx.addLine(to:point(d.second)); ctx.strokePath()
            ctx.setFillColor(UIColor.systemGreen.cgColor)
            for v in [d.first,d.second] { let q = point(v); ctx.fillEllipse(in:CGRect(x:q.x-4,y:q.y-4,width:8,height:8)) }
        }
    }
}

final class GridRunnerViewController: UIViewController {
    private let camera = GridCamera()
    private let link = GridLink()
    private let preview = GridPreview()
    private let overlay = GridOverlay()
    private let status = UILabel()
    private let network = UILabel()
    private let button = UIButton(type:.system)
    private let ledButton = UIButton(type:.system)
    private let direction = UISegmentedControl(items:["Reverse","Forward"])
    private var fields: [UITextField] = []
    private var config = GridConfiguration()
    private var active = false
    private var session: UInt64 = 0
    private var request = UUID()
    private var led = false
    private var batteryTimer: Timer?
    override var supportedInterfaceOrientations: UIInterfaceOrientationMask { .landscape }
    override var preferredInterfaceOrientationForPresentation: UIInterfaceOrientation { .landscapeRight }
    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        if let data = UserDefaults.standard.data(forKey:"GridRunner.configuration"),
           let c = try? JSONDecoder().decode(GridConfiguration.self,from:data),c.valid { config = c }
        let title = UILabel(); title.text = "GridRunner"; title.font = .boldSystemFont(ofSize:24)
        status.numberOfLines = 0; status.font = .monospacedSystemFont(ofSize:13,weight:.regular)
        status.text = "Align over grout. Start stream, then press Rosie's Clock."
        network.numberOfLines = 0; network.font = .systemFont(ofSize:11)
        let help = UILabel(); help.numberOfLines = 0; help.font = .systemFont(ofSize:12)
        help.text = "50 mm/s · Clock starts GRID; Stop ends the stream. Yellow: scan rows · green: detected grout · cyan: camera-center target. Align the camera over the grout. Motion stops on stale data or hazards."
        let stack = UIStackView(arrangedSubviews:[title,status,network,help,direction]); stack.axis = .vertical; stack.spacing = 7
        direction.selectedSegmentIndex = config.direction < 0 ? 0:1
        let names = ["Lens height (mm)","Top-edge angle (°)","Lens forward (mm)","Lens left (mm)","Steering gain","Correction limit"]
        let values = [config.heightMM,config.yawDegrees,config.forwardMM,config.leftMM,config.gain,config.limit]
        for (name,value) in zip(names,values) {
            let label = UILabel(); label.text = name; label.font = .systemFont(ofSize:12)
            let field = UITextField(); field.borderStyle = .roundedRect; field.keyboardType = .numbersAndPunctuation
            field.text = String(format:"%0.2f",value); field.widthAnchor.constraint(equalToConstant:95).isActive = true
            fields.append(field); let row = UIStackView(arrangedSubviews:[label,field]); row.spacing = 6; stack.addArrangedSubview(row)
        }
        let scroll = UIScrollView(); scroll.keyboardDismissMode = .onDrag; scroll.translatesAutoresizingMaskIntoConstraints = false
        scroll.addSubview(stack); stack.translatesAutoresizingMaskIntoConstraints = false; view.addSubview(scroll)
        let controls = UIStackView(); controls.axis = .vertical; controls.spacing = 8; controls.translatesAutoresizingMaskIntoConstraints = false
        preview.backgroundColor = .black; preview.cameraLayer.session = camera.capture; preview.cameraLayer.videoGravity = .resizeAspect
        preview.translatesAutoresizingMaskIntoConstraints = false
        overlay.backgroundColor = .clear; overlay.isUserInteractionEnabled = false; overlay.translatesAutoresizingMaskIntoConstraints = false
        overlay.contentMode = .redraw
        preview.rotatedContent.addSubview(overlay)
        button.setTitle("Start stream",for:.normal); button.titleLabel?.font = .boldSystemFont(ofSize:20)
        button.backgroundColor = .systemGreen; button.setTitleColor(.white,for:.normal); button.layer.cornerRadius = 12
        button.addTarget(self,action:#selector(toggle),for:.touchUpInside)
        ledButton.setTitle("LED: Off",for:.normal); ledButton.titleLabel?.font = .boldSystemFont(ofSize:18)
        ledButton.addTarget(self,action:#selector(toggleLED),for:.touchUpInside)
        controls.addArrangedSubview(preview); controls.addArrangedSubview(button); controls.addArrangedSubview(ledButton); view.addSubview(controls)
        NSLayoutConstraint.activate([
            scroll.leadingAnchor.constraint(equalTo:view.safeAreaLayoutGuide.leadingAnchor,constant:12),
            scroll.topAnchor.constraint(equalTo:view.safeAreaLayoutGuide.topAnchor,constant:8),scroll.bottomAnchor.constraint(equalTo:view.safeAreaLayoutGuide.bottomAnchor,constant:-8),
            scroll.trailingAnchor.constraint(equalTo:controls.leadingAnchor,constant:-12),
            stack.leadingAnchor.constraint(equalTo:scroll.contentLayoutGuide.leadingAnchor),stack.trailingAnchor.constraint(equalTo:scroll.contentLayoutGuide.trailingAnchor),
            stack.topAnchor.constraint(equalTo:scroll.contentLayoutGuide.topAnchor),stack.bottomAnchor.constraint(equalTo:scroll.contentLayoutGuide.bottomAnchor),stack.widthAnchor.constraint(equalTo:scroll.frameLayoutGuide.widthAnchor),
            controls.trailingAnchor.constraint(equalTo:view.safeAreaLayoutGuide.trailingAnchor,constant:-12),controls.topAnchor.constraint(equalTo:view.safeAreaLayoutGuide.topAnchor,constant:8),controls.bottomAnchor.constraint(lessThanOrEqualTo:view.safeAreaLayoutGuide.bottomAnchor,constant:-8),
            controls.widthAnchor.constraint(equalToConstant:200),preview.heightAnchor.constraint(equalToConstant:190),button.heightAnchor.constraint(equalToConstant:56),ledButton.heightAnchor.constraint(equalToConstant:40),
            overlay.leadingAnchor.constraint(equalTo:preview.rotatedContent.leadingAnchor),overlay.trailingAnchor.constraint(equalTo:preview.rotatedContent.trailingAnchor),overlay.topAnchor.constraint(equalTo:preview.rotatedContent.topAnchor),overlay.bottomAnchor.constraint(equalTo:preview.rotatedContent.bottomAnchor)])
        camera.onPacket = { [weak self] p in self?.link.send(p.encoded(),session:p.session) }
        camera.health.onPacket = { [weak self] p in self?.link.send(p.encoded(),session:p.session) }
        link.onStatus = { [weak self] in self?.network.text = $0 }
        camera.onOverlay = { [weak self] p in
            guard let self = self,self.active,self.session == p.session else { return }
            self.overlay.packet = p
            self.status.text = String(format:"%@\nCamera-line error %+0.1f mm · angle %+0.1f°\nConfidence %0.0f%% · correction %+0.3f\n%@ · seq %u · reason %u",p.flags == 3 ? "LINE LOCKED":"LINE LOST / WAIT",p.detection.offset-p.config.leftMM,p.detection.angle*180 / .pi,p.detection.confidence*100,p.detection.correction,p.direction<0 ? "REVERSE":"FORWARD",p.sequence,p.reason)
        }
        camera.onError = { [weak self] message in self?.stop(); self?.status.text = message }
        NotificationCenter.default.addObserver(self,selector:#selector(background),name:UIApplication.willResignActiveNotification,object:nil)
        UIDevice.current.isBatteryMonitoringEnabled = true
    }
    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        preview.cameraLayer.connection?.videoOrientation = .portrait
    }
    deinit { NotificationCenter.default.removeObserver(self) }
    @objc private func toggleLED() { led.toggle(); camera.setTorch(led); ledButton.setTitle(led ? "LED: On":"LED: Off",for:.normal) }
    @objc private func background() { stop() }
    @objc private func toggle() {
        if active { stop(); return }
        guard fields.count == 6 else { return }
        let values = fields.compactMap { Double($0.text ?? "") }
        guard values.count == 6 else { status.text = "Enter numeric mount and gain values."; return }
        config.heightMM = values[0]; config.yawDegrees = values[1]; config.forwardMM = values[2]; config.leftMM = values[3]; config.gain = values[4]; config.limit = values[5]
        config.direction = direction.selectedSegmentIndex == 0 ? -1:1
        config.identity = UInt64.random(in:1...UInt64.max)
        guard config.valid else { status.text = "Invalid settings. Height 50–1500 mm, gain 0.1–8, correction 0.01–0.35."; return }
        UserDefaults.standard.set(try? JSONEncoder().encode(config),forKey:"GridRunner.configuration")
        view.endEditing(true)
        let token = UUID(); request = token
        func begin() {
            guard self.request == token else { return }
            self.session = UInt64.random(in:1...UInt64.max); self.active = true
            self.fields.forEach { $0.isEnabled = false }; self.direction.isEnabled = false
            self.button.setTitle("STOP",for:.normal); self.button.backgroundColor = .systemRed
            UIApplication.shared.isIdleTimerDisabled = true
            self.link.start(session:self.session); self.camera.setTorch(self.led)
            self.camera.start(config:self.config,session:self.session)
            self.batteryTimer = Timer.scheduledTimer(withTimeInterval:1,repeats:true) { [weak self] _ in
                let level = UIDevice.current.batteryLevel
                self?.camera.health.setBattery(level<0 ? 255:UInt8(min(100,max(0,Int(level*100)))),UInt8(UIDevice.current.batteryState.rawValue))
            }
        }
        switch AVCaptureDevice.authorizationStatus(for:.video) {
        case .authorized: begin()
        case .notDetermined:
            AVCaptureDevice.requestAccess(for:.video) { granted in DispatchQueue.main.async { if granted { begin() } else { self.status.text = "Camera access required." } } }
        default: status.text = "Enable camera permission in Settings."
        }
    }
    private func stop() {
        request = UUID(); camera.stop(); link.stop(); active = false
        batteryTimer?.invalidate(); batteryTimer = nil
        fields.forEach { $0.isEnabled = true }; direction.isEnabled = true
        button.setTitle("Start stream",for:.normal); button.backgroundColor = .systemGreen
        led = false; ledButton.setTitle("LED: Off",for:.normal)
        overlay.packet = nil; status.text = "Stopped. Align, restart stream, then press Clock for a new run."
        UIApplication.shared.isIdleTimerDisabled = false
    }
}
