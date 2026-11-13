// @(#)MapPackage.swift 3.2 2026/11/09 18:09:21
import Foundation

/// Metadata preserved with every saved map. The ISO-8601 creation
/// timestamp and device strings are for experiment traceability;
/// `worldAlignmentNote` records that ARKit coordinates are gravity-aligned
/// with the origin at the session origin, not a room/dock fixture.
struct MapMetadata: Codable {
    var version: Int = 1
    var mapID: UUID
    var name: String
    var created: Date
    var deviceModel: String
    var osVersion: String
    var trackingAtCapture: String
    var mappingAtCapture: String
    var worldAlignmentNote: String = "gravity-aligned ARKit world; origin is the session origin, not a surveyed room fixture"
    var description: String = ""
    // Optional fields preserve decoding of all version1 map packages.
    var parentMapID: UUID?
    var lineageID: UUID?
    var revision: Int?
    var featureCount: Int?
}

/// Versioned JSON container for offline transfer. `mapData` is the
/// NSKeyedArchived ARWorldMap (JSON encodes Data as base64). No cloud
/// services required; the operator moves the single `.roomtrek` file via
/// the Files app (document picker) between the two phones.
struct MapPackage: Codable {
    var version: Int = 1
    var format: String = "roomtrek-map"
    var metadata: MapMetadata
    var mapData: Data
}

enum MapPackageError: Error, LocalizedError {
    case emptyFile
    case unsupportedVersion(Int)
    case wrongFormat(String)
    case emptyMapData
    case decodeFailed(String)

    var errorDescription: String? {
        switch self {
        case .emptyFile: return "Map file is empty."
        case .unsupportedVersion(let v): return "Unsupported map version \(v)."
        case .wrongFormat(let f): return "Not a RoomTrek map (format \(f))."
        case .emptyMapData: return "Map file contains no world map data."
        case .decodeFailed(let m): return "Map file could not be decoded: \(m)"
        }
    }
}

enum MapPackageIO {
    static let currentVersion = 1
    static let containerFormat = "roomtrek-map"
    static let fileExtension = "roomtrek"

    static func encode(_ package: MapPackage) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        return try encoder.encode(package)
    }

    static func decode(_ data: Data) throws -> MapPackage {
        guard !data.isEmpty else { throw MapPackageError.emptyFile }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let package: MapPackage
        do {
            package = try decoder.decode(MapPackage.self, from: data)
        } catch {
            throw MapPackageError.decodeFailed(error.localizedDescription)
        }
        guard package.version == currentVersion else {
            throw MapPackageError.unsupportedVersion(package.version)
        }
        guard package.metadata.version == currentVersion else {
            throw MapPackageError.unsupportedVersion(package.metadata.version)
        }
        guard package.format == containerFormat else {
            throw MapPackageError.wrongFormat(package.format)
        }
        guard !package.mapData.isEmpty else {
            throw MapPackageError.emptyMapData
        }
        return package
    }

    static func makeMetadata(mapID: UUID = UUID(), name: String, description: String,
                               trackingAtCapture: String, mappingAtCapture: String,
                               deviceModel: String = deviceModelString(),
                               osVersion: String = osVersionString()) -> MapMetadata {
        MapMetadata(version: currentVersion, mapID: mapID, name: name, created: Date(),
                    deviceModel: deviceModel, osVersion: osVersion,
                    trackingAtCapture: trackingAtCapture, mappingAtCapture: mappingAtCapture,
                    description: description)
    }

    static func deviceModelString() -> String {
        var systemInfo = utsname()
        uname(&systemInfo)
        let machine = withUnsafeBytes(of: &systemInfo.machine) { raw -> String in
            let chars = raw.bindMemory(to: Int8.self).map { $0 == 0 ? "" : String(UnicodeScalar(UInt8($0))) }.joined()
            return chars
        }
        return machine.isEmpty ? UIDeviceModelFallback.displayName : machine
    }

    static func osVersionString() -> String {
        ProcessInfo.processInfo.operatingSystemVersionString
    }
}

enum UIDeviceModelFallback {
    static var displayName: String {
#if targetEnvironment(macCatalyst)
        "MacCatalyst"
#else
        "iPhone"
#endif
    }
}

/// Pure save policy shared by the AR session and host-side checks.
enum MapRevisionPolicy {
    static func canAmend(localized: Bool, trackingNormal: Bool, frameAge: TimeInterval,
                         mapping: String, operationError: String) -> Bool {
        localized && trackingNormal && frameAge >= 0 && frameAge <= 0.25
            && ["mapped", "extending"].contains(mapping) && operationError.isEmpty
    }
}
