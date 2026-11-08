// @(#)TrekLogger.swift 3.1.roomtrek.2 2026/11/08 12:00:00
import Foundation

/// Bounded on-device logging. Session events go to JSONL; poses go to CSV
/// at a configurable throttle (session enforces the rate; the logger only
/// formats). Logging is capped by file size so an unattended run cannot
/// fill storage; logging stops at the cap. Export is via the share
/// sheet; no camera video is retained.
final class TrekLogger {
    private let queue = DispatchQueue(label: "RoomTrek.Logger")
    private let directory: URL
    private var jsonlHandle: FileHandle?
    private var csvHandle: FileHandle?
    private let sessionStarted: Date
    private(set) var jsonlBytes: Int = 0
    private(set) var csvBytes: Int = 0
    private let maxBytes = 16 * 1024 * 1024 // 16 MiB per file; export and relaunch for another file

    init(directory: URL = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!.appendingPathComponent("RoomTrekLogs", isDirectory: true)) {
        self.directory = directory
        self.sessionStarted = Date()
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let stamp = ISO8601DateFormatter().string(from: sessionStarted).replacingOccurrences(of: ":", with: "-")
        let jsonl = directory.appendingPathComponent("trek-\(stamp).jsonl")
        let csv = directory.appendingPathComponent("trek-\(stamp).csv")
        queue.sync {
            FileManager.default.createFile(atPath: jsonl.path, contents: nil)
            FileManager.default.createFile(atPath: csv.path, contents: nil)
            jsonlHandle = try? FileHandle(forWritingTo: jsonl)
            csvHandle = try? FileHandle(forWritingTo: csv)
        }
        writeCSVHeader()
    }

    var jsonlURL: URL {
        directory.appendingPathComponent("trek-\(ISO8601DateFormatter().string(from: sessionStarted).replacingOccurrences(of: ":", with: "-")).jsonl")
    }

    var csvURL: URL {
        directory.appendingPathComponent("trek-\(ISO8601DateFormatter().string(from: sessionStarted).replacingOccurrences(of: ":", with: "-")).csv")
    }

    /// Session lifecycle events: start/stop, tracking/mapping transitions,
    /// map save/load/export/import, relocalization attempts/outcomes,
    /// NavLink errors. One JSON object per line.
    func logEvent(_ event: String, _ detail: String = "") {
        let entry: [String: String] = [
            "ts": ISO8601DateFormatter().string(from: Date()),
            "event": event,
            "detail": detail
        ]
        guard let data = try? JSONSerialization.data(withJSONObject: entry),
              var line = String(data: data, encoding: .utf8) else { return }
        line += "\n"
        queue.async { [weak self] in
            guard let self = self, self.jsonlBytes < self.maxBytes,
                  let handle = self.jsonlHandle else { return }
            try? handle.write(contentsOf: Data(line.utf8))
            self.jsonlBytes += line.utf8.count
        }
    }

    /// Pose sample. CSV columns are documented in the README.
    /// `yawDeg` is yaw in degrees for the CSV; the raw radian value is
    /// recoverable from it. Never call this per video frame; the session
    /// throttles to the configured pose-log frequency (default 2 Hz).
    func logPose(_ pose: TrekPose, _ yawDeg: Double, _ valid: Bool) {
        let iso = ISO8601DateFormatter().string(from: Date())
        let map = pose.mapID?.uuidString ?? "none"
        let row = [
            iso, "\(pose.timestamp)", "\(pose.session)", map,
            "\(pose.tracking)", "\(pose.reason)", pose.relocalization.rawValue,
            valid ? "1" : "0", "\(pose.worldMappingStatus)",
            String(format: "%.4f", pose.position.x),
            String(format: "%.4f", pose.position.y),
            String(format: "%.4f", pose.position.z),
            String(format: "%.4f", pose.orientation.x),
            String(format: "%.4f", pose.orientation.y),
            String(format: "%.4f", pose.orientation.z),
            String(format: "%.4f", pose.orientation.w),
            String(format: "%.2f", yawDeg),
            "\(pose.features)"
        ].joined(separator: ",") + "\n"
        queue.async { [weak self] in
            guard let self = self, self.csvBytes < self.maxBytes,
                  let handle = self.csvHandle else { return }
            try? handle.write(contentsOf: Data(row.utf8))
            self.csvBytes += row.utf8.count
        }
    }

    func flush() {
        queue.sync {
            try? jsonlHandle?.synchronize()
            try? csvHandle?.synchronize()
        }
    }

    func close() {
        queue.sync {
            try? jsonlHandle?.synchronize()
            try? csvHandle?.synchronize()
            try? jsonlHandle?.close()
            try? csvHandle?.close()
            jsonlHandle = nil
            csvHandle = nil
        }
    }

    private func writeCSVHeader() {
        let header = "iso_ts,frame_ts_s,session,map_id,tracking,reason,reloc,valid,mapping,x_m,y_m,z_m,qx,qy,qz,qw,yaw_deg,features\n"
        queue.sync {
            try? csvHandle?.write(contentsOf: Data(header.utf8))
            csvBytes += header.utf8.count
        }
    }
}
