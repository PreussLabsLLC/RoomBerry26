// @(#)RoomTrekViewController.swift 3.2.mothership.1 2026/11/12 11:51:06
import AVFoundation
import ARKit
import SceneKit
import UIKit
import CryptoKit
import UniformTypeIdentifiers

final class RoomTrekViewController: UIViewController, UITableViewDataSource, UITableViewDelegate, UIDocumentPickerDelegate {
    private let sceneView = ARSCNView()
    private let sessionCtrl = RoomTrekSession()
    private let store = MapStore()
    private let speech = TrekSpeech()
    private let heartbeatSwitch = UISwitch()
    private var heartbeat = TrekHeartbeat()
    private var heartbeatTimer: Timer?
    private var heartbeatFrame: TimeInterval?
    private var heartbeatTrackingOK = false
    private let voiceButton = UIButton(type: .system)
    private let testVoiceButton = UIButton(type: .system)
    private let pitchSlider = UISlider()
    private let rateSlider = UISlider()
    private let speechSettingsLabel = UILabel()
    private let speechStatusLabel = UILabel()
    private var entries: [MapStore.Entry] = []
    private var selectedMapID: UUID?
    private var active = false
    private var modeIsSurveyor = true
    private var surveyAvailable = false
    private var surveyParentID: UUID?
    private var savingMap = false
    private var saveToken: UUID?
    private var remoteSaveCompletion: ((String, String) -> Void)?

    private let titleLabel = UILabel()
    private let modeControl = UISegmentedControl(items: ["Surveyor", "Navigator"])
    private let trackingLabel = UILabel()
    private let mappingLabel = UILabel()
    private let relocLabel = UILabel()
    private let poseLabel = UILabel()
    private let navlinkLabel = UILabel()
    private let mapTable = UITableView()
    private let nameField = UITextField()
    private let notesField = UITextField()
    private let hostField = UITextField()
    private let navlinkSwitch = UISwitch()
    private let logRate = UISegmentedControl(items: ["Log 1 Hz", "2 Hz", "5 Hz"])
    private let startButton = UIButton(type: .system)
    private let saveButton = UIButton(type: .system)
    private let resetButton = UIButton(type: .system)
    private let importButton = UIButton(type: .system)
    private let exportMapButton = UIButton(type: .system)
    private let logButton = UIButton(type: .system)
    private let deleteButton = UIButton(type: .system)
    private let renameButton = UIButton(type: .system)

    override var supportedInterfaceOrientations: UIInterfaceOrientationMask { .landscape }
    override var preferredInterfaceOrientationForPresentation: UIInterfaceOrientation { .landscapeRight }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        titleLabel.text = RoomTrekBuild.headline
        titleLabel.numberOfLines = 0
        titleLabel.font = .boldSystemFont(ofSize: 22)
        modeControl.selectedSegmentIndex = 0
        modeControl.addTarget(self, action: #selector(modeChanged), for: .valueChanged)

        for label in [trackingLabel, mappingLabel, relocLabel, poseLabel, navlinkLabel] {
            label.numberOfLines = 0
            label.font = .monospacedSystemFont(ofSize: 12, weight: .regular)
            label.backgroundColor = UIColor.secondarySystemBackground
            label.textColor = .label
        }
        trackingLabel.text = "Tracking: —"
        mappingLabel.text = "Mapping: —"
        relocLabel.text = "Relocalization: —"
        poseLabel.text = "Pose: —"
        navlinkLabel.text = "NavLink: off"

        nameField.placeholder = "Map name (Surveyor Save)"
        nameField.borderStyle = .roundedRect
        notesField.placeholder = "Optional note"
        notesField.borderStyle = .roundedRect
        hostField.placeholder = "pi3.local, pi3, or IPv4 address"
        hostField.text = UserDefaults.standard.string(forKey: "navlink.mothership") ?? "pi3.local"
        hostField.borderStyle = .roundedRect
        hostField.autocorrectionType = .no
        hostField.autocapitalizationType = .none
        hostField.keyboardType = .URL
        hostField.returnKeyType = .done
        hostField.accessibilityLabel = "Mothership hostname or IPv4 address"
        hostField.addTarget(self, action: #selector(mothershipChanged), for: .editingDidEnd)
        hostField.addTarget(self, action: #selector(mothershipDone), for: .editingDidEndOnExit)
        logRate.selectedSegmentIndex = 1
        logRate.addTarget(self, action: #selector(logRateChanged), for: .valueChanged)
        navlinkSwitch.isOn = (UserDefaults.standard.object(forKey: "navlink.enabled") as? Bool)
            ?? (TrekControl.loadKey()?.isEmpty == false)
        navlinkSwitch.addTarget(self, action: #selector(navlinkToggled), for: .valueChanged)
        let navlinkRow = UIStackView(arrangedSubviews: [UILabel(), navlinkSwitch])
        (navlinkRow.arrangedSubviews[0] as? UILabel)?.text = "NavLink telemetry"

        heartbeatSwitch.isOn = (UserDefaults.standard.object(forKey: "heartbeat.enabled") as? Bool) ?? true
        heartbeatSwitch.addTarget(self, action: #selector(heartbeatChanged), for: .valueChanged)
        let heartbeatRow = UIStackView(arrangedSubviews: [UILabel().withText("10s tracking ping: high OK / low double needs attention"), heartbeatSwitch])

        startButton.setTitle("Start Survey", for: .normal)
        startButton.titleLabel?.font = .boldSystemFont(ofSize: 18)
        startButton.backgroundColor = .systemGreen
        startButton.setTitleColor(.white, for: .normal)
        startButton.layer.cornerRadius = 10
        startButton.addTarget(self, action: #selector(startTapped), for: .touchUpInside)
        saveButton.setTitle("Save Map", for: .normal)
        saveButton.backgroundColor = .systemBlue
        saveButton.setTitleColor(.white, for: .normal)
        saveButton.setTitleColor(.lightGray, for: .disabled)
        saveButton.layer.cornerRadius = 10
        saveButton.addTarget(self, action: #selector(saveTapped), for: .touchUpInside)
        resetButton.setTitle("Reset / Retry", for: .normal)
        resetButton.addTarget(self, action: #selector(resetTapped), for: .touchUpInside)
        importButton.setTitle("Import Map (Files)", for: .normal)
        importButton.addTarget(self, action: #selector(importTapped), for: .touchUpInside)
        exportMapButton.setTitle("Export Selected Map", for: .normal)
        exportMapButton.addTarget(self, action: #selector(exportTapped), for: .touchUpInside)
        logButton.setTitle("Export Log + Pose CSV", for: .normal)
        logButton.addTarget(self, action: #selector(logTapped), for: .touchUpInside)
        renameButton.setTitle("Rename Selected", for: .normal)
        renameButton.addTarget(self, action: #selector(renameTapped), for: .touchUpInside)
        deleteButton.setTitle("Delete Selected", for: .normal)
        deleteButton.setTitleColor(.systemRed, for: .normal)
        deleteButton.addTarget(self, action: #selector(deleteTapped), for: .touchUpInside)

        speech.log = { [weak self] event, detail in self?.sessionCtrl.logger.logEvent(event, detail) }
        voiceButton.showsMenuAsPrimaryAction = true
        testVoiceButton.setTitle("Test Voice", for: .normal)
        testVoiceButton.addTarget(self, action: #selector(testVoice), for: .touchUpInside)
        pitchSlider.minimumValue = 0.5; pitchSlider.maximumValue = 2; pitchSlider.value = speech.pitch
        rateSlider.minimumValue = AVSpeechUtteranceMinimumSpeechRate
        rateSlider.maximumValue = AVSpeechUtteranceMaximumSpeechRate; rateSlider.value = speech.rate
        pitchSlider.addTarget(self, action: #selector(speechSettingsChanged), for: .valueChanged)
        rateSlider.addTarget(self, action: #selector(speechSettingsChanged), for: .valueChanged)
        speechSettingsLabel.numberOfLines = 0; speechStatusLabel.numberOfLines = 0
        refreshSpeechMenu()
        updateSpeechSettingsLabel()

        let stack = UIStackView(arrangedSubviews: [
            titleLabel, modeControl, trackingLabel, mappingLabel, relocLabel, poseLabel, navlinkLabel,
            startButton, saveButton, resetButton, nameField, notesField,
            UILabel().withText("Map library (tap to select)"),
            mapTable, renameButton, deleteButton,
            importButton, exportMapButton, logButton,
            logRate, UILabel().withText("Mothership — report to (UDP 5010)"), hostField, navlinkRow, heartbeatRow,
            UILabel().withText("Australian voice — listen to choose the character"),
            voiceButton, speechSettingsLabel,
            UILabel().withText("Pitch"), pitchSlider,
            UILabel().withText("Speaking rate"), rateSlider, testVoiceButton, speechStatusLabel
        ])
        stack.axis = .vertical; stack.spacing = 6
        stack.translatesAutoresizingMaskIntoConstraints = false

        sceneView.frame = .zero
        sceneView.scene = SCNScene()
        sceneView.preferredFramesPerSecond = 15
        sceneView.debugOptions = [.showFeaturePoints]
        sceneView.translatesAutoresizingMaskIntoConstraints = false
        sceneView.automaticallyUpdatesLighting = false

        let scroll = UIScrollView()
        scroll.keyboardDismissMode = .onDrag
        scroll.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(scroll); view.addSubview(sceneView)
        scroll.addSubview(stack)

        mapTable.dataSource = self; mapTable.delegate = self
        mapTable.register(UITableViewCell.self, forCellReuseIdentifier: "map")
        mapTable.heightAnchor.constraint(equalToConstant: 120).isActive = true

        let safe = view.safeAreaLayoutGuide
        NSLayoutConstraint.activate([
            sceneView.leadingAnchor.constraint(equalTo: safe.leadingAnchor),
            sceneView.widthAnchor.constraint(equalTo: safe.widthAnchor, multiplier: 0.48),
            sceneView.topAnchor.constraint(equalTo: safe.topAnchor),
            sceneView.bottomAnchor.constraint(equalTo: safe.bottomAnchor),
            scroll.leadingAnchor.constraint(equalTo: sceneView.trailingAnchor, constant: 12),
            scroll.trailingAnchor.constraint(equalTo: safe.trailingAnchor, constant: -12),
            scroll.topAnchor.constraint(equalTo: safe.topAnchor),
            scroll.bottomAnchor.constraint(equalTo: safe.bottomAnchor),
            stack.leadingAnchor.constraint(equalTo: scroll.contentLayoutGuide.leadingAnchor),
            stack.trailingAnchor.constraint(equalTo: scroll.contentLayoutGuide.trailingAnchor),
            stack.topAnchor.constraint(equalTo: scroll.contentLayoutGuide.topAnchor),
            stack.bottomAnchor.constraint(equalTo: scroll.contentLayoutGuide.bottomAnchor),
            stack.widthAnchor.constraint(equalTo: scroll.frameLayoutGuide.widthAnchor)
        ])

        sessionCtrl.onPose = { [weak self] pose, valid, trackingText, relocText in
            self?.heartbeatFrame = pose.timestamp
            self?.heartbeatTrackingOK = valid && pose.tracking == 2 && pose.reason == 0
            self?.trackingLabel.text = "Tracking: \(trackingText) · Map: \(self?.mappingText(from: pose) ?? "—")"
            self?.mappingLabel.text = "Mapping: \(pose.worldMappingStatus) · Features: \(pose.features) · Coverage unverified; revisit landmarks"
            self?.relocLabel.text = "Relocalization: \(relocText) · Valid: \(valid ? "YES" : "no (pose unreliable)")"
            let yawDeg = Double(pose.yaw) * 180 / .pi
            self?.poseLabel.text = String(format: "Pose (m, mapped AR): x %.3f  y %.3f  z %.3f\nYaw %.1f°  q(%.2f, %.2f, %.2f, %.2f)\nMap: %@  Valid: %@  Pose is CAMERA, not robot center.",
                                          pose.position.x, pose.position.y, pose.position.z,
                                          yawDeg, pose.orientation.x, pose.orientation.y, pose.orientation.z, pose.orientation.w,
                                          String(pose.mapID?.uuidString.prefix(8) ?? "none"), valid ? "YES" : "NO")
        }
        sessionCtrl.onStatus = { [weak self] text in self?.navlinkLabel.text = text }
        sessionCtrl.control.execute = { [weak self] body, finish in
            self?.executeRemote(body, finish: finish)
        }
        linkStatusFlush()
        if navlinkSwitch.isOn { applyNavLinkSetting() }

        NotificationCenter.default.addObserver(self, selector: #selector(stopSession), name: UIApplication.willResignActiveNotification, object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(refreshSpeechMenu), name: UIApplication.didBecomeActiveNotification, object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(cancelSpeech), name: UIApplication.willResignActiveNotification, object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(cancelSpeech), name: AVAudioSession.interruptionNotification, object: nil)
        reloadMaps()
        updateButtons()
        heartbeatTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in self?.heartbeatTick() }
        _ = heartbeat.tone(now: ProcessInfo.processInfo.systemUptime, enabled: false, foreground: true,
                           running: false, trackingOK: false, frameTime: nil, navlink: false, speaking: false)
    }

    deinit { heartbeatTimer?.invalidate() }

    @objc private func heartbeatChanged() {
        UserDefaults.standard.set(heartbeatSwitch.isOn, forKey: "heartbeat.enabled")
        if !heartbeatSwitch.isOn { speech.stopPing() }
    }
    private func heartbeatTick() {
        let foreground = UIApplication.shared.applicationState == .active
        guard let healthy = heartbeat.tone(now: ProcessInfo.processInfo.systemUptime,
            enabled: heartbeatSwitch.isOn, foreground: foreground, running: active,
            trackingOK: heartbeatTrackingOK, frameTime: heartbeatFrame,
            navlink: navlinkSwitch.isOn, speaking: speech.isSpeaking) else { return }
        speech.ping(healthy: healthy)
        sessionCtrl.logger.logEvent("heartbeat", healthy ? "tracking_ok" : "attention_required")
    }

    @objc private func refreshSpeechMenu() {
        speech.refreshVoices()
        let preferred = speech.preferredIdentifier
        let chosen = speech.voices.first { $0.identifier == preferred }
        voiceButton.setTitle(preferred.isEmpty ? "Automatic Australian voice" : (chosen?.name ?? "Preferred voice unavailable — using fallback"), for: .normal)
        var actions = [UIAction(title: "Automatic Australian voice", state: preferred.isEmpty ? .on : .off) { [weak self] _ in
            self?.speech.preferredIdentifier = ""; self?.refreshSpeechMenu()
        }]
        actions += speech.voices.map { voice in
            UIAction(title: "\(voice.name) · \(TrekSpeech.qualityLabel(voice))", subtitle: voice.identifier,
                     state: voice.identifier == preferred ? .on : .off) { [weak self] _ in
                self?.speech.preferredIdentifier = voice.identifier; self?.refreshSpeechMenu()
            }
        }
        voiceButton.menu = UIMenu(children: actions)
    }
    private func updateSpeechSettingsLabel() {
        speechSettingsLabel.text = String(format: "Pitch %.2f · Rate %.2f", speech.pitch, speech.rate)
    }
    @objc private func speechSettingsChanged() {
        speech.pitch = pitchSlider.value; speech.rate = rateSlider.value
        updateSpeechSettingsLabel()
    }
    @objc private func testVoice() {
        speechStatusLabel.text = "Testing voice…"
        speech.speak(TrekSpeech.testPhrase) { [weak self] state, detail in self?.speechStatusLabel.text = "\(state): \(detail)" }
    }
    @objc private func cancelSpeech() {
        if Thread.isMainThread { speech.stopPing(); speech.cancel() }
        else { DispatchQueue.main.async { [weak self] in self?.speech.stopPing(); self?.speech.cancel() } }
    }

    private func mappingText(from pose: TrekPose) -> String { pose.worldMappingStatus }

    @objc private func modeChanged() {
        if active { stopSession() }
        modeIsSurveyor = (modeControl.selectedSegmentIndex == 0)
        surveyParentID = nil
        reloadMaps(); updateButtons()
    }

    @objc private func logRateChanged() {
        sessionCtrl.poseLogInterval = [1.0, 0.5, 0.2][logRate.selectedSegmentIndex]
    }

    @objc private func navlinkToggled() {
        UserDefaults.standard.set(navlinkSwitch.isOn, forKey: "navlink.enabled")
        applyNavLinkSetting()
    }

    @objc private func mothershipDone() { hostField.resignFirstResponder() }

    @objc private func mothershipChanged() {
        let host = (hostField.text ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        // A host only: no URL scheme, path or port. Transport uses IPv4 UDP.
        let labels = host.split(separator: ".", omittingEmptySubsequences: false)
        let valid = !host.isEmpty && host.utf8.count <= 253 && labels.allSatisfy {
            $0.range(of: "^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$",
                     options: .regularExpression) != nil
        }
        guard valid else {
            hostField.text = UserDefaults.standard.string(forKey: "navlink.mothership") ?? "pi3.local"
            showAlert("Enter a hostname such as pi3.local or an IPv4 address, without a URL or port.")
            return
        }
        hostField.text = host
        UserDefaults.standard.set(host, forKey: "navlink.mothership")
        applyNavLinkSetting()
    }

    private func applyNavLinkSetting() {
        let host = UserDefaults.standard.string(forKey: "navlink.mothership") ?? "pi3.local"
        sessionCtrl.link.configureHost(host)
        sessionCtrl.navLinkEnabled = navlinkSwitch.isOn
        navlinkLabel.text = navlinkSwitch.isOn ? "NavLink: enqueued (\(host):5010) · receipt unconfirmed" : "NavLink: off"
        sessionCtrl.logger.logEvent("navlink_toggle", navlinkSwitch.isOn ? "on" : "off")
    }

    @objc private func startTapped() {
        if active { stopSession(); return }
        view.endEditing(true)
        let token = UUID()
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized: begin(token)
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in
                DispatchQueue.main.async {
                    guard let self = self else { return }
                    granted ? self.begin(token) : self.showAlert("Camera access required.")
                }
            }
        default: showAlert("Enable camera permission in Settings.")
        }
    }

    private func begin(_ token: UUID) {
        guard ARWorldTrackingConfiguration.isSupported else {
            showAlert("ARKit world tracking is not supported on this device.")
            return
        }
        if modeIsSurveyor {
            do {
                let map = try surveyParentID.map { try store.loadWorldMap(for: $0) }
                surveyAvailable = true
                sessionCtrl.startSurveyor(arSession: sceneView.session, map: map, mapID: surveyParentID)
            } catch {
                surveyAvailable = false
                sessionCtrl.failOperation("map_load: \(error.localizedDescription)")
                return
            }
            startButton.setTitle("Stop", for: .normal)
            startButton.backgroundColor = .systemRed
        } else {
            guard let mapID = selectedMapID else {
                showAlert("Select a map in the library first.")
                return
            }
            do {
                let map = try store.loadWorldMap(for: mapID)
                surveyAvailable = false
                sessionCtrl.startNavigator(arSession: sceneView.session, map: map, mapID: mapID)
                startButton.setTitle("Stop", for: .normal)
                startButton.backgroundColor = .systemRed
            } catch {
                sessionCtrl.failOperation("map_load: \(error.localizedDescription)")
                showAlert("Could not load the selected map: \(error.localizedDescription)")
                return
            }
        }
        heartbeatFrame = nil; heartbeatTrackingOK = false
        active = true
        UIApplication.shared.isIdleTimerDisabled = true
        updateButtons()
        sceneView.session.delegate = sessionCtrl
        sceneView.session.delegateQueue = .main
    }

    /// Invoked by the authenticated transport on main, like UI actions.
    private func executeRemote(_ body: [String: Any], finish: @escaping (String, String) -> Void) {
        dispatchPrecondition(condition: .onQueue(.main))
        let command = body["command"] as? String ?? ""
        if command == "STATUS" {
            var status = sessionCtrl.operationSnapshot()
            status["capabilities"] = ["survey_resume_v1", "map_library_v1"]
            let prefix = body["map_prefix"] as? String
            let requestedID = body["map_id"] as? String
            status["maps"] = store.entries().filter { (requestedID == nil || $0.package.metadata.mapID.uuidString == requestedID?.uppercased()) && (prefix == nil || $0.package.metadata.name.hasPrefix(prefix! + "-") || $0.package.metadata.name == prefix!) }.prefix(10).map { entry -> [String: Any] in
                let m = entry.package.metadata
                return ["id": m.mapID.uuidString, "name": String(m.name.prefix(40)),
                        "created": m.created.timeIntervalSince1970, "parent_map_id": m.parentMapID?.uuidString ?? "",
                        "lineage_id": (m.lineageID ?? m.mapID).uuidString, "revision": m.revision ?? 1,
                        "features": m.featureCount ?? -1, "mapping": m.mappingAtCapture]
            }
            status["map_inventory_errors"] = store.inventoryErrors.count
            let data = (try? JSONSerialization.data(withJSONObject: status, options: [.sortedKeys])) ?? Data()
            finish("completed", String(data: data, encoding: .utf8) ?? ""); return
        }
        if command == "MAP_LIST" {
            guard let offset = body["offset"] as? Int, offset >= 0 else { finish("failed", "Nonnegative offset required"); return }
            let entries = store.entries()
            guard offset <= entries.count else { finish("failed", "Library changed; refresh again"); return }
            let maps = entries.dropFirst(offset).prefix(6).map { entry -> [String: Any] in
                let m = entry.package.metadata
                let bytes = (try? entry.url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
                return ["id": m.mapID.uuidString, "name": String(m.name.prefix(80)),
                        "created": m.created.timeIntervalSince1970, "parent_map_id": m.parentMapID?.uuidString ?? "",
                        "revision": m.revision ?? 1, "features": m.featureCount ?? -1,
                        "mapping": m.mappingAtCapture, "bytes": bytes]
            }
            let storage = entries.reduce(0) { $0 + ((try? $1.url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0) }
            // Includes names so an intervening rename also invalidates pagination.
            let revision = entries.map { $0.package.metadata.mapID.uuidString + ":" + $0.package.metadata.name }.joined(separator: "|")
            let digest = SHA256.hash(data: Data(revision.utf8)).map { String(format: "%02x", $0) }.joined()
            let next: Any = offset + maps.count < entries.count ? offset + maps.count : NSNull()
            let result: [String: Any] = ["maps": maps, "next_offset": next,
                "inventory_revision": digest, "inventory_errors": store.inventoryErrors.count, "storage_bytes": storage]
            let data = (try? JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])) ?? Data()
            finish("completed", String(data: data, encoding: .utf8) ?? ""); return
        }
        guard UIApplication.shared.applicationState == .active else { finish("failed", "App must be foreground"); return }
        if command == "MAP_RENAME" || command == "MAP_DELETE" {
            guard !savingMap, let value = body["map_id"] as? String, let id = UUID(uuidString: value) else {
                finish("failed", "Map UUID required; wait for any save to finish"); return
            }
            if command == "MAP_DELETE", active, sessionCtrl.operationSnapshot()["map_id"] as? String == id.uuidString {
                finish("failed", "Stop the session before deleting its active map"); return
            }
            do {
                if command == "MAP_RENAME" {
                    guard let name = body["name"] as? String, !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                          name.count <= 80 else { finish("failed", "Map name must contain 1–80 characters"); return }
                    try store.rename(mapID: id, to: name)
                } else { try store.delete(mapID: id) }
                reloadMaps()
                sessionCtrl.logger.logEvent(command == "MAP_DELETE" ? "map_delete" : "map_rename", id.uuidString)
                finish("completed", id.uuidString)
            } catch { finish("failed", "Map storage: \(error.localizedDescription)") }
            return
        }
        if command == "SPEAK" {
            guard let text = body["text"] as? String else { finish("failed", "SPEAK requires text"); return }
            speech.speak(text, finish: finish); return
        }
        if command == "SESSION_STOP" { stopSession(); finish("completed", "Session stopped"); return }
        guard !savingMap else { finish("failed", "Map save in progress"); return }
        if command == "SURVEY_SAVE" {
            guard modeIsSurveyor, surveyAvailable, sceneView.session.currentFrame != nil else {
                finish("failed", "No survey frames available"); return
            }
            guard sessionCtrl.canAmendSurvey else { finish("failed", "Map save requires fresh normal tracking, successful relocalization and extending/mapped status"); return }
            nameField.text = body["name"] as? String ?? nameField.text
            remoteSaveCompletion = finish
            saveTapped(); return
        }
        if command == "NAV_RETRY" {
            guard active, !modeIsSurveyor, sessionCtrl.navigationCompletion == nil else { finish("failed", "Navigator unavailable or operation pending"); return }
            sessionCtrl.navigationCompletion = finish
            sessionCtrl.resetNavigator(); return
        }
        guard !active else { finish("failed", "Stop the current session first"); return }
        guard AVCaptureDevice.authorizationStatus(for: .video) == .authorized,
              ARWorldTrackingConfiguration.isSupported else { finish("failed", "Camera permission or ARKit unavailable"); return }
        if command == "NAV_START" {
            guard let value = body["map_id"] as? String, let id = UUID(uuidString: value) else { finish("failed", "map_id UUID required"); return }
            selectedMapID = id; modeIsSurveyor = false
            sessionCtrl.navigationCompletion = finish
        } else if command == "SURVEY_START" {
            modeIsSurveyor = true; surveyParentID = nil
            if body["map_id"] != nil {
                guard let value = body["map_id"] as? String, let id = UUID(uuidString: value) else { finish("failed", "map_id UUID required"); return }
                surveyParentID = id
                sessionCtrl.navigationCompletion = finish
            }
        }
        else { finish("failed", "Unknown command"); return }
        modeControl.selectedSegmentIndex = modeIsSurveyor ? 0 : 1
        begin(UUID())
        if !active && sessionCtrl.operationError.isEmpty { sessionCtrl.navigationCompletion = nil; finish("failed", "Session could not start") }
        else if modeIsSurveyor && surveyParentID == nil { finish("completed", "Fresh survey started") }
    }

    @objc private func resetTapped() {
        guard active, !modeIsSurveyor else { return }
        sessionCtrl.failOperation("Navigation superseded by local retry")
        sessionCtrl.resetNavigator()
    }

    @objc private func saveTapped() {
        guard modeIsSurveyor, surveyAvailable, !savingMap else { return }
        guard sceneView.session.currentFrame != nil else {
            showAlert("No survey frames available. Start a survey and scan the room first.")
            return
        }
        if surveyParentID != nil && !sessionCtrl.canAmendSurvey {
            reportSaveResult("failed", "Cannot amend: relocalization/tracking/mapping is not ready")
            return
        }
        view.endEditing(true)
        savingMap = true
        let token = UUID(); saveToken = token
        DispatchQueue.main.asyncAfter(deadline: .now() + 20) { [weak self] in
            guard let self = self, self.saveToken == token else { return }
            self.saveToken = nil; self.savingMap = false
            self.remoteSaveCompletion?("failed", "map_save_timeout: capture exceeded 20 seconds")
            self.remoteSaveCompletion = nil
            self.sessionCtrl.failOperation("map_save_timeout: capture exceeded 20 seconds")
            self.updateButtons()
        }
        updateButtons()
        sessionCtrl.logger.logEvent("map_save_requested", active ? "running" : "stopped")
        let name = nameField.text?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let notes = notesField.text ?? ""
        let currentMapping = sceneView.session.currentFrame.map { RoomTrekSession.mappingLabel($0.worldMappingStatus) } ?? "unknown"
        let captureTracking = String(describing: sceneView.session.currentFrame?.camera.trackingState)
        sceneView.session.getCurrentWorldMap { [weak self] worldMap, error in
            DispatchQueue.main.async {
            guard let self = self, self.saveToken == token else { return }
            defer {
                self.saveToken = nil
                self.savingMap = false
                self.updateButtons()
            }
            if let error = error {
                self.reportSaveResult("failed", "Save failed: \(error.localizedDescription)")
                self.sessionCtrl.logger.logEvent("map_save_error", error.localizedDescription)
                return
            }
            guard let worldMap = worldMap else {
                self.reportSaveResult("failed", "No world map returned")
                return
            }
            do {
                if self.surveyParentID != nil || self.remoteSaveCompletion != nil {
                    guard self.sessionCtrl.canAmendSurvey else {
                        self.reportSaveResult("failed", "Map capture rejected: tracking/relocalization/mapping changed")
                        return
                    }
                }
                let saved = try self.store.save(name: name, description: notes, worldMap: worldMap,
                                    tracking: captureTracking, mapping: currentMapping, parentMapID: self.surveyParentID)
                self.sessionCtrl.logger.logEvent("map_save", name)
                self.reloadMaps()
                let result: [String: Any] = ["map_id": saved.mapID.uuidString,
                    "parent_map_id": saved.parentMapID?.uuidString ?? "", "revision": saved.revision ?? 1]
                let data = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
                self.reportSaveResult("completed", String(data: data, encoding: .utf8) ?? "Map saved")
            } catch {
                self.reportSaveResult("failed", "Save failed: \(error.localizedDescription)")
                self.sessionCtrl.logger.logEvent("map_save_error", error.localizedDescription)
            }
            }
        }
    }

    private func reportSaveResult(_ state: String, _ detail: String) {
        if let completion = remoteSaveCompletion {
            remoteSaveCompletion = nil
            completion(state, detail)
        } else { showAlert(detail) }
    }

    @objc private func importTapped() {
        let picker = UIDocumentPickerViewController(forOpeningContentTypes: [.data], asCopy: true)
        picker.delegate = self
        picker.allowsMultipleSelection = false
        present(picker, animated: true)
    }

    @objc private func exportTapped() {
        guard let mapID = selectedMapID else { showAlert("Select a map to export."); return }
        let url = store.exportURL(for: mapID)
        let share = UIDocumentPickerViewController(forExporting: [url], asCopy: true)
        present(share, animated: true)
        sessionCtrl.logger.logEvent("map_export", mapID.uuidString)
    }

    @objc private func logTapped() {
        sessionCtrl.logger.flush()
        let share = UIActivityViewController(activityItems: [sessionCtrl.logger.csvURL, sessionCtrl.logger.jsonlURL], applicationActivities: nil)
        present(share, animated: true)
    }

    @objc private func renameTapped() {
        guard let mapID = selectedMapID else { showAlert("Select a map to rename."); return }
        let alert = UIAlertController(title: "Rename map", message: nil, preferredStyle: .alert)
        alert.addTextField { field in
            field.text = self.entries.first { $0.package.metadata.mapID == mapID }?.package.metadata.name
        }
        alert.addAction(UIAlertAction(title: "Cancel", style: .cancel))
        alert.addAction(UIAlertAction(title: "Save", style: .default) { [weak self] _ in
            let text = alert.textFields?.first?.text?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            if !text.isEmpty, let self = self {
                do {
                    try self.store.rename(mapID: mapID, to: text)
                    self.sessionCtrl.logger.logEvent("map_rename", mapID.uuidString)
                    self.reloadMaps()
                } catch { self.showAlert("Rename failed: \(error.localizedDescription)") }
            }
        })
        present(alert, animated: true)
    }

    @objc private func deleteTapped() {
        guard let mapID = selectedMapID else { showAlert("Select a map to delete."); return }
        let alert = UIAlertController(title: "Delete map?", message: "This cannot be undone.", preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "Cancel", style: .cancel))
        alert.addAction(UIAlertAction(title: "Delete", style: .destructive) { [weak self] _ in
            guard let self = self else { return }
            guard !self.savingMap, !(self.active && self.sessionCtrl.operationSnapshot()["map_id"] as? String == mapID.uuidString) else {
                self.showAlert("Stop the session before deleting its active map."); return
            }
            do {
                try self.store.delete(mapID: mapID)
                self.selectedMapID = nil
                self.reloadMaps()
            } catch { self.showAlert("Could not delete map: \(error.localizedDescription)") }
        })
        present(alert, animated: true)
    }

    @objc private func stopSession() {
        guard active else { return }
        active = false
        heartbeatFrame = nil; heartbeatTrackingOK = false
        sessionCtrl.stop()
        UIApplication.shared.isIdleTimerDisabled = false
        startButton.setTitle(modeIsSurveyor ? "Start Survey" : "Start Navigator", for: .normal)
        startButton.backgroundColor = .systemGreen
        poseLabel.text = "Pose: stopped"
        updateButtons()
    }

    // MARK: - Map library

    private func reloadMaps() {
        entries = store.entries()
        if selectedMapID != nil && !entries.contains(where: { $0.package.metadata.mapID == selectedMapID }) {
            selectedMapID = entries.first?.package.metadata.mapID
        } else if selectedMapID == nil {
            selectedMapID = entries.first?.package.metadata.mapID
        }
        mapTable.reloadData()
    }

    private func updateButtons() {
        hostField.isEnabled = !active
        saveButton.isEnabled = surveyAvailable && modeIsSurveyor && !savingMap
        saveButton.setTitle(savingMap ? "Saving Map…" : "Save Map", for: .normal)
        saveButton.backgroundColor = saveButton.isEnabled || savingMap ? .systemBlue : .systemGray
        startButton.isEnabled = !savingMap
        modeControl.isEnabled = !savingMap
        resetButton.isEnabled = active && !modeIsSurveyor
        startButton.setTitle(active ? "Stop" : (modeIsSurveyor ? "Start Survey" : "Start Navigator"), for: .normal)
        startButton.backgroundColor = active ? .systemRed : .systemGreen
    }

    func tableView(_ tableView: UITableView, numberOfRowsInSection section: Int) -> Int { entries.count }

    func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {
        let cell = UITableViewCell(style: .subtitle, reuseIdentifier: nil)
        let entry = entries[indexPath.row]
        let m = entry.package.metadata
        let formatter = DateFormatter()
        formatter.dateStyle = .short; formatter.timeStyle = .none
        cell.textLabel?.text = m.name + (m.mapID == selectedMapID ? "  ✓" : "")
        cell.detailTextLabel?.text = "\(formatter.string(from: m.created)) · revision \(m.revision ?? 1) · \(m.mappingAtCapture) · features \(m.featureCount.map(String.init) ?? "unknown")"
        cell.detailTextLabel?.numberOfLines = 2
        cell.accessoryType = (m.mapID == selectedMapID) ? .checkmark : .none
        return cell
    }

    func tableView(_ tableView: UITableView, didSelectRowAt indexPath: IndexPath) {
        selectedMapID = entries[indexPath.row].package.metadata.mapID
        tableView.reloadData()
    }

    // MARK: - DocumentPicker

    func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
        guard let url = urls.first else { return }
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        do {
            let metadata = try store.importPackage(from: url)
            sessionCtrl.logger.logEvent("map_import", metadata.mapID.uuidString)
            reloadMaps()
            selectedMapID = metadata.mapID
            mapTable.reloadData()
            showAlert("Imported “\(metadata.name)”.")
        } catch {
            sessionCtrl.logger.logEvent("map_import_error", error.localizedDescription)
            showAlert("Import failed: \(error.localizedDescription)")
        }
    }

    private func showAlert(_ message: String) {
        let alert = UIAlertController(title: "RoomTrek", message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "OK", style: .default))
        present(alert, animated: true)
    }

    private func linkStatusFlush() {
        // Session owns link diagnostics and routes status to the HUD.
    }
}

extension UILabel {
    fileprivate func withText(_ text: String) -> UILabel {
        self.text = text; self.font = .boldSystemFont(ofSize: 14); return self
    }
}
