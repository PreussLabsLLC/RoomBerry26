// @(#)TrekChecks.swift 3.2 2026/11/09 18:09:21
import Foundation
import simd

@main struct TrekChecks {
    static func main() {
        // Yaw: facing mapped +X -> 0 rad; facing mapped +Y -> +pi/2.
        let fx = TrekPoseMath.yaw(fromForwardMapped: SIMD3(1, 0, 0))
        let fy = TrekPoseMath.yaw(fromForwardMapped: SIMD3(0, 1, 0))
        assert(abs(fx) < 1e-6, "yaw +X expected 0, got \(fx)")
        assert(abs(fy - .pi / 2) < 1e-6, "yaw +Y expected +pi/2, got \(fy)")
        // Near-vertical forward is rejected by the validity gate.
        assert(!TrekPoseMath.isValid(tracking: 2, interrupted: false, failed: false, frameAge: 0.05, forwardMapped: SIMD3(0, 0, 1)), "vertical forward must be invalid")
        assert(TrekPoseMath.isValid(tracking: 2, interrupted: false, failed: false, frameAge: 0.05, forwardMapped: SIMD3(1, 0, 0)), "normal fresh forward must be valid")
        assert(!TrekPoseMath.isValid(tracking: 1, interrupted: false, failed: false, frameAge: 0.05, forwardMapped: SIMD3(1, 0, 0)), "limited must be invalid")

        // Map token: stable and nonzero.
        let id = UUID()
        let token = TrekPoseMath.token(for: id)
        assert(token != 0 && token == TrekPoseMath.token(for: id), "map token must be stable and nonzero")

        // Type 6 preserves full UUID and quaternion without ABI padding.
        var packet = TrekPacket()
        packet.session = 42; packet.mapID = id; packet.sequence = 7
        packet.flags = 1; packet.tracking = 2; packet.relocalization = 2
        packet.frameUS = 1_000_000; packet.sendUS = 1_010_000
        packet.position = SIMD3(1, 2, 3)
        let data = packet.encoded()
        assert(data.count == 128 && Array(data.prefix(4)) == Array("NVLK".utf8))
        assert(data[4] == 1 && data[5] == 6 && data[6] == 128)
        var uuid = id.uuid
        withUnsafeBytes(of: &uuid) { assert(Array(data[40..<56]) == Array($0)) }
        assert(data[94] == 2 && data[96..<128].allSatisfy { $0 == 0 })
        assert(!TrekPoseMath.isValid(tracking: 2, interrupted: false, failed: false, frameAge: 0.251, forwardMapped: SIMD3(1, 0, 0)))
        assert(!TrekPoseMath.isValid(tracking: 2, interrupted: true, failed: false, frameAge: 0.01, forwardMapped: SIMD3(1, 0, 0)))
        var mount = MountTransform.identity
        mount.translation = SIMD3(1, 0, 0)
        let body = mount.robotTransform(cameraTransform: matrix_identity_float4x4)
        assert(abs(body.columns.3.x + 1) < 1e-6, "camera offset must be inverted to find body")

        // Map package JSON round-trip (without ARWorldMap bytes).
        let metadata = MapPackageIO.makeMetadata(name: "Kitchen", description: "test", trackingAtCapture: "NORMAL", mappingAtCapture: "mapped")
        let package = MapPackage(metadata: metadata, mapData: Data([1, 2, 3, 4]))
        let encoded = try! MapPackageIO.encode(package)
        let decoded = try! MapPackageIO.decode(encoded)
        assert(decoded.metadata.mapID == metadata.mapID && decoded.mapData == Data([1, 2, 3, 4]), "package round-trip must preserve metadata and map data")
        assert(decoded.metadata.parentMapID == nil && decoded.metadata.revision == nil)
        var revision = package
        revision.metadata.parentMapID = metadata.mapID
        revision.metadata.lineageID = metadata.mapID
        revision.metadata.revision = 2
        revision.metadata.featureCount = 500
        let revisionCopy = try! MapPackageIO.decode(MapPackageIO.encode(revision))
        assert(revisionCopy.metadata.parentMapID == metadata.mapID && revisionCopy.metadata.revision == 2)
        assert(revisionCopy.metadata.featureCount == 500)
        assert(MapRevisionPolicy.canAmend(localized: true, trackingNormal: true, frameAge: 0.1, mapping: "mapped", operationError: ""))
        assert(MapRevisionPolicy.canAmend(localized: true, trackingNormal: true, frameAge: 0.1, mapping: "extending", operationError: ""))
        assert(!MapRevisionPolicy.canAmend(localized: false, trackingNormal: true, frameAge: 0.1, mapping: "mapped", operationError: ""))
        assert(!MapRevisionPolicy.canAmend(localized: true, trackingNormal: false, frameAge: 0.1, mapping: "mapped", operationError: ""))
        for age in [-1.0, 0.251, Double.nan] {
            assert(!MapRevisionPolicy.canAmend(localized: true, trackingNormal: true, frameAge: age, mapping: "mapped", operationError: ""))
        }
        assert(!MapRevisionPolicy.canAmend(localized: true, trackingNormal: true, frameAge: 0.1, mapping: "limited", operationError: ""))
        assert(!MapRevisionPolicy.canAmend(localized: true, trackingNormal: true, frameAge: 0.1, mapping: "mapped", operationError: "relocalization_timeout"))
        for malformed in [Data(), Data("{}".utf8)] {
            do { _ = try MapPackageIO.decode(malformed); assertionFailure("invalid package accepted") } catch {}
        }
        var incompatible = package
        incompatible.version = 99
        do { _ = try MapPackageIO.decode(MapPackageIO.encode(incompatible)); assertionFailure("version accepted") } catch {}
        incompatible = package; incompatible.metadata.version = 99
        do { _ = try MapPackageIO.decode(MapPackageIO.encode(incompatible)); assertionFailure("metadata version accepted") } catch {}
        print("TrekPose yaw/validity, map token, type-6 wire bytes and JSON package round-trip verified")
    }
}
