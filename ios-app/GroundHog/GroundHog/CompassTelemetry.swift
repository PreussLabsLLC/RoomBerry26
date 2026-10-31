// @(#)CompassTelemetry.swift 3.1.compass.1 2026/10/31 12:10:00
import Foundation
import CoreLocation
import simd

/// Main-thread Core Location heading only; no GPS/location updates or permission request.
final class CompassTelemetry: NSObject, CLLocationManagerDelegate {
    private let manager = CLLocationManager()
    private var timer: Timer?
    private var packet = CompassPacket()
    private var mountYawDegrees: Double = 0
    private var began: Date = .distantFuture
    var onPacket: ((CompassPacket) -> Void)?
    var onStatus: ((String) -> Void)?
    override init() {
        super.init()
        manager.delegate = self; manager.headingOrientation = .portrait
        manager.headingFilter = kCLHeadingFilterNone
    }
    func start(session: UInt64, calibration: UInt64, mountYawDegrees: Double) {
        stop(); began = Date(); self.mountYawDegrees = mountYawDegrees
        packet = CompassPacket(); packet.session = session; packet.calibration = calibration
        if CLLocationManager.headingAvailable() { manager.startUpdatingHeading() }
        else { packet.state = 0 }
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in self?.emit() }
        emit()
    }
    func stop() { timer?.invalidate(); timer = nil; manager.stopUpdatingHeading(); began = .distantFuture }
    func locationManager(_ manager: CLLocationManager, didUpdateHeading heading: CLHeading) {
        guard timer != nil, heading.timestamp >= began else { return }
        let now = ProcessInfo.processInfo.systemUptime
        let age = Date().timeIntervalSince(heading.timestamp)
        // CLHeading timestamps use wall time; reject clock anomalies and old
        // callbacks. Preserve the original wall timestamp on the wire as well.
        guard age.isFinite, age >= 0, age <= 1, now >= age else { return }
        let sourceUS = GroundPacket.us(now-age)
        guard sourceUS > packet.sampleUS else { return }
        packet.update(magneticDegrees: heading.magneticHeading, accuracyDegrees: heading.headingAccuracy,
                      field: SIMD3(heading.x,heading.y,heading.z),sampleUS: sourceUS,
                      epochUS: GroundPacket.us(heading.timestamp.timeIntervalSince1970),mountYawDegrees: mountYawDegrees)
    }
    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) { packet.fail() }
    func locationManagerShouldDisplayHeadingCalibration(_ manager: CLLocationManager) -> Bool { false }
    private func emit() {
        guard packet.sequence < .max else { return }
        packet.sequence += 1; packet.prepare(nowUS: GroundPacket.us(ProcessInfo.processInfo.systemUptime))
        onPacket?(packet)
        if packet.flags & 1 != 0 {
            let bearing = Double(packet.values[1])*180 / .pi
            let accuracy = Double(packet.values[2])*180 / .pi
            onStatus?(String(format: "Compass robot %.1f° magnetic ±%.1f°",bearing,accuracy))
        } else {
            let labels = ["unsupported","acquiring","usable","unreliable","stale","error"]
            onStatus?("Compass \(labels[Int(packet.state)])")
        }
    }
}
