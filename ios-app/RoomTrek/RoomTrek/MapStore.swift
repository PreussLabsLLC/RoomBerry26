// @(#)MapStore.swift 3.2.maps.1 2026/11/10 10:15:00
import ARKit
import Foundation

/// Persistent map library. Maps are stored as `.roomtrek` JSON packages in
/// Documents/RoomTrekMaps/ so the operator can see them in Files (the app
/// declares UIFileSharingEnabled). All operations are synchronous and
/// bounded; failures throw rather than crashing the session.
final class MapStore {
    private let directory: URL
    private(set) var inventoryErrors: [String] = []

    init(directory: URL = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!.appendingPathComponent("RoomTrekMaps", isDirectory: true)) {
        self.directory = directory
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    struct Entry {
        var package: MapPackage
        var url: URL
    }

    func entries() -> [Entry] {
        inventoryErrors = []
        let fm = FileManager.default
        guard let items = try? fm.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil) else { inventoryErrors = ["Map directory unreadable"]; return [] }
        var result: [Entry] = []
        for url in items where url.pathExtension == MapPackageIO.fileExtension {
            guard let data = try? Data(contentsOf: url),
                  let package = try? MapPackageIO.decode(data) else {
                inventoryErrors.append(url.lastPathComponent); continue
            }
            result.append(Entry(package: package, url: url))
        }
        return result.sorted { $0.package.metadata.created > $1.package.metadata.created }
    }

    func fileURL(for mapID: UUID) -> URL {
        directory.appendingPathComponent("\(mapID.uuidString).\(MapPackageIO.fileExtension)")
    }

    func save(name: String, description: String, worldMap: ARWorldMap, tracking: String, mapping: String, parentMapID: UUID? = nil) throws -> MapMetadata {
        var metadata = MapPackageIO.makeMetadata(name: name.isEmpty ? "Untitled map" : name,
                                                   description: description,
                                                   trackingAtCapture: tracking,
                                                   mappingAtCapture: mapping)
        if let parentMapID = parentMapID {
            let parent = try loadPackage(for: parentMapID).metadata
            metadata.parentMapID = parentMapID
            metadata.lineageID = parent.lineageID ?? parent.mapID
            metadata.revision = (parent.revision ?? 1) + 1
        } else {
            metadata.lineageID = metadata.mapID
            metadata.revision = 1
        }
        metadata.featureCount = worldMap.rawFeaturePoints.points.count
        let mapData = try NSKeyedArchiver.archivedData(withRootObject: worldMap, requiringSecureCoding: true)
        let package = MapPackage(metadata: metadata, mapData: mapData)
        let data = try MapPackageIO.encode(package)
        try data.write(to: fileURL(for: metadata.mapID), options: .atomic)
        return metadata
    }

    func loadWorldMap(for mapID: UUID) throws -> ARWorldMap {
        let url = fileURL(for: mapID)
        let data = try Data(contentsOf: url)
        let package = try MapPackageIO.decode(data)
        return try ARWorldMap.unarchived(from: package.mapData)
    }

    func loadPackage(for mapID: UUID) throws -> MapPackage {
        try MapPackageIO.decode(try Data(contentsOf: fileURL(for: mapID)))
    }

    func exportURL(for mapID: UUID) -> URL {
        fileURL(for: mapID)
    }

    func delete(mapID: UUID) throws {
        try FileManager.default.removeItem(at: fileURL(for: mapID))
    }

    func rename(mapID: UUID, to newName: String) throws {
        var package = try loadPackage(for: mapID)
        package.metadata.name = newName
        try MapPackageIO.encode(package).write(to: fileURL(for: mapID), options: .atomic)
    }

    /// Validate an imported file before touching the library: JSON shape,
    /// version/format, and that the archived payload really is an
    /// ARWorldMap. Returns the metadata on success.
    func importPackage(from source: URL) throws -> MapMetadata {
        let size = try source.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
        guard size > 0 && size <= 128 * 1024 * 1024 else {
            throw MapPackageError.decodeFailed("file is empty or exceeds 128 MiB")
        }
        let data = try Data(contentsOf: source)
        let package = try MapPackageIO.decode(data)
        _ = try ARWorldMap.unarchived(from: package.mapData) // throws if corrupted
        let destination = fileURL(for: package.metadata.mapID)
        try data.write(to: destination, options: .atomic)
        return package.metadata
    }
}

extension ARWorldMap {
    /// Failable convenience wrapper used by the store; mirrors
    /// `NSKeyedUnarchiver.unarchivedObject(ofClass:from:)`.
    static func unarchived(from data: Data) throws -> ARWorldMap {
        guard let map = try NSKeyedUnarchiver.unarchivedObject(ofClass: ARWorldMap.self, from: data) else {
            throw MapPackageError.decodeFailed("archived payload is not an ARWorldMap")
        }
        return map
    }
}
