// @(#)RoomTrekViewController.swift 3.1.roomtrek.3 2026/11/08 14:00:00
import AVFoundation
import ARKit
import SceneKit
import UIKit
import UniformTypeIdentifiers

final class RoomTrekViewController: UIViewController, UITableViewDataSource, UITableViewDelegate, UIDocumentPickerDelegate {
    private let sceneView = ARSCNView()
    private let sessionCtrl = RoomTrekSession()
    private let store = MapStore()
    private var entries: [MapStore.Entry] = []
    private var selectedMapID: UUID?
    private var active = false
    private var modeIsSurveyor = true
    private var surveyAvailable = false
    private var savingMap = false

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
        titleLabel.text = "RoomTrek"
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
        hostField.placeholder = "NavLink host (pi)"
        hostField.text = "pi"
        hostField.borderStyle = .roundedRect
        hostField.autocorrectionType = .no
        logRate.selectedSegmentIndex = 1
        logRate.addTarget(self, action: #selector(logRateChanged), for: .valueChanged)
        navlinkSwitch.isOn = false
        navlinkSwitch.addTarget(self, action: #selector(navlinkToggled), for: .valueChanged)
        let navlinkRow = UIStackView(arrangedSubviews: [UILabel(), navlinkSwitch])
        (navlinkRow.arrangedSubviews[0] as? UILabel)?.text = "NavLink telemetry"

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

        let stack = UIStackView(arrangedSubviews: [
            titleLabel, modeControl, trackingLabel, mappingLabel, relocLabel, poseLabel, navlinkLabel,
            startButton, saveButton, resetButton, nameField, notesField,
            UILabel().withText("Map library (tap to select)"),
            mapTable, renameButton, deleteButton,
            importButton, exportMapButton, logButton,
            logRate, hostField, navlinkRow
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
        linkStatusFlush()

        NotificationCenter.default.addObserver(self, selector: #selector(stopSession), name: UIApplication.willResignActiveNotification, object: nil)
        reloadMaps()
        updateButtons()
    }

    private func mappingText(from pose: TrekPose) -> String { pose.worldMappingStatus }

    @objc private func modeChanged() {
        if active { stopSession() }
        modeIsSurveyor = (modeControl.selectedSegmentIndex == 0)
        reloadMaps(); updateButtons()
    }

    @objc private func logRateChanged() {
        sessionCtrl.poseLogInterval = [1.0, 0.5, 0.2][logRate.selectedSegmentIndex]
    }

    @objc private func navlinkToggled() {
        if let host = hostField.text, !host.isEmpty { sessionCtrl.link.host = host }
        sessionCtrl.navLinkEnabled = navlinkSwitch.isOn
        navlinkLabel.text = navlinkSwitch.isOn ? "NavLink: enqueued (pi:5010) · receipt unconfirmed" : "NavLink: off"
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
            surveyAvailable = true
            sessionCtrl.startSurveyor(arSession: sceneView.session)
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
                showAlert("Could not load the selected map: \(error.localizedDescription)")
                return
            }
        }
        active = true
        UIApplication.shared.isIdleTimerDisabled = true
        updateButtons()
        sceneView.session.delegate = sessionCtrl
        sceneView.session.delegateQueue = .main
    }

    @objc private func resetTapped() {
        guard active, !modeIsSurveyor else { return }
        sessionCtrl.resetNavigator()
    }

    @objc private func saveTapped() {
        guard modeIsSurveyor, surveyAvailable, !savingMap else { return }
        guard sceneView.session.currentFrame != nil else {
            showAlert("No survey frames available. Start a survey and scan the room first.")
            return
        }
        view.endEditing(true)
        savingMap = true
        updateButtons()
        sessionCtrl.logger.logEvent("map_save_requested", active ? "running" : "stopped")
        let name = nameField.text?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let notes = notesField.text ?? ""
        let currentMapping = sceneView.session.currentFrame.map { RoomTrekSession.mappingLabel($0.worldMappingStatus) } ?? "unknown"
        let captureTracking = String(describing: sceneView.session.currentFrame?.camera.trackingState)
        sceneView.session.getCurrentWorldMap { [weak self] worldMap, error in
            DispatchQueue.main.async {
            guard let self = self else { return }
            defer {
                self.savingMap = false
                self.updateButtons()
            }
            if let error = error {
                self.showAlert("Save failed: \(error.localizedDescription)")
                self.sessionCtrl.logger.logEvent("map_save_error", error.localizedDescription)
                return
            }
            guard let worldMap = worldMap else {
                self.showAlert("No world map returned.")
                return
            }
            do {
                try self.store.save(name: name, description: notes, worldMap: worldMap,
                                    tracking: captureTracking, mapping: currentMapping)
                self.sessionCtrl.logger.logEvent("map_save", name)
                self.reloadMaps()
                self.showAlert("Map saved.")
            } catch {
                self.showAlert("Save failed: \(error.localizedDescription)")
                self.sessionCtrl.logger.logEvent("map_save_error", error.localizedDescription)
            }
            }
        }
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
            self?.store.delete(mapID: mapID)
            self?.selectedMapID = nil
            self?.reloadMaps()
        })
        present(alert, animated: true)
    }

    @objc private func stopSession() {
        guard active else { return }
        active = false
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
        cell.detailTextLabel?.text = "\(formatter.string(from: m.created)) · \(m.deviceModel) · \(m.mappingAtCapture)"
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
