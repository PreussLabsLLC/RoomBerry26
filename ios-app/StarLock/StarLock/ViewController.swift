// @(#)ViewController.swift 2.3.navlink.2 2026/10/30 10:16:06
//
//  ViewController.swift
//  StarLock
//
//  Created by Peter Preuss on 10/30/26.
//

import UIKit
import ARKit
import SceneKit

class ViewController: UIViewController {

    var sceneView: ARSCNView!
    private var telemetry: NavLinkTelemetry!
    private let statusLabel = UILabel()
    private var tracking = false
    private var previousIdleTimerDisabled = false

    override func viewDidLoad() {
        super.viewDidLoad()

        sceneView = ARSCNView(frame: view.bounds)
        sceneView.autoresizingMask = [
            .flexibleWidth, .flexibleHeight
        ]
        view.addSubview(sceneView)

        sceneView.scene = SCNScene()
        sceneView.preferredFramesPerSecond = 15
        sceneView.showsStatistics = false
        sceneView.debugOptions = []
        statusLabel.numberOfLines = 0
        statusLabel.textColor = .white
        statusLabel.backgroundColor = UIColor.black.withAlphaComponent(0.7)
        statusLabel.font = .monospacedSystemFont(ofSize: 12, weight: .medium)
        statusLabel.text = "NAVLINK pi:5010 · starting\nObservation only · uncalibrated"
        statusLabel.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(statusLabel)
        NSLayoutConstraint.activate([
            statusLabel.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor, constant: 8),
            statusLabel.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor, constant: -8),
            statusLabel.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor, constant: -8)
        ])
        telemetry = NavLinkTelemetry(session: sceneView.session)
        telemetry.onStatus = { [weak self] text in
            self?.statusLabel.text = text + "\nObservation only · uncalibrated"
        }
        NotificationCenter.default.addObserver(self, selector: #selector(startTracking),
            name: UIApplication.didBecomeActiveNotification, object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(stopTracking),
            name: UIApplication.willResignActiveNotification, object: nil)
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        startTracking()
    }

    @objc private func startTracking() {
        guard !tracking, viewIfLoaded?.window != nil,
              UIApplication.shared.applicationState == .active else { return }

        guard ARWorldTrackingConfiguration.isSupported else {
            print("ARKit world tracking unsupported")
            return
        }

        let config = ARWorldTrackingConfiguration()
        config.worldAlignment = .gravity
        // Camera capture is independent of SceneKit's preview rendering rate.
        // Use a supported format rather than requesting an arbitrary frame rate.
        let formats = ARWorldTrackingConfiguration.supportedVideoFormats
        if let format = formats.filter({ $0.framesPerSecond == 30 }).min(by: {
            $0.imageResolution.width * $0.imageResolution.height <
                $1.imageResolution.width * $1.imageResolution.height
        }) {
            config.videoFormat = format
        }
        config.isLightEstimationEnabled = false
        print("STARLOCK camera \(config.videoFormat.framesPerSecond) fps, \(config.videoFormat.imageResolution); preview 15 fps; NavLink 10 Hz")
        sceneView.session.run(config, options: [.resetTracking, .removeExistingAnchors])
        tracking = true
        previousIdleTimerDisabled = UIApplication.shared.isIdleTimerDisabled
        UIApplication.shared.isIdleTimerDisabled = true
        telemetry.start()
        sceneView.scene.rootNode.childNodes.forEach { $0.removeFromParentNode() }

        // Cube: 10 cm on each side
        let cube = SCNBox(
            width: 0.1,
            height: 0.1,
            length: 0.1,
            chamferRadius: 0.005
        )

        cube.firstMaterial?.diffuse.contents = UIColor.red

        let node = SCNNode(geometry: cube)

        // Half a meter in front of initial camera
        node.position = SCNVector3(0, 0, -0.5)

        sceneView.scene.rootNode.addChildNode(node)
    }

    override func viewWillDisappear(_ animated: Bool) {
        super.viewWillDisappear(animated)
        stopTracking()
    }

    override func didReceiveMemoryWarning() {
        super.didReceiveMemoryWarning()
        print("STARLOCK received iOS memory warning; thermal state \(ProcessInfo.processInfo.thermalState.rawValue)")
    }

    @objc private func stopTracking() {
        guard tracking else { return }
        tracking = false
        telemetry.stop()
        sceneView.session.pause()
        UIApplication.shared.isIdleTimerDisabled = previousIdleTimerDisabled
        statusLabel.text = "NAVLINK paused"
    }
}
