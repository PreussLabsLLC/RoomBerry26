// @(#)GridPacket.swift 3.1.tiles.2 2026/11/05 17:30:00
import Foundation

struct GridPacket {
    var session: UInt64 = 1
    var calibration: UInt64 = 1
    var sequence: UInt32 = 0
    var flags: UInt16 = 2
    var direction: Int8 = -1
    var reason: UInt8 = 4
    var frameUS: UInt64 = 0
    var sendUS: UInt64 = 0
    var detection = GridDetection()
    var config = GridConfiguration()
    // Tile crossings occupy the 28-byte type-5 trailer; see encoded().
    var crossing = GridCrossingState()
    var width: UInt16 = 480
    var height: UInt16 = 640
    func encoded() -> Data {
        var data = Data("NVLK".utf8)
        func put<T: FixedWidthInteger>(_ n: T) {
            var value = n.littleEndian
            withUnsafeBytes(of:&value) { data.append(contentsOf:$0) }
        }
        put(UInt8(1)); put(UInt8(5)); put(UInt16(128)); put(session); put(calibration)
        put(sequence); put(flags); put(direction); put(reason); put(frameUS); put(sendUS)
        let d = detection
        let values = [d.first.x,d.first.y,d.second.x,d.second.y,d.offset,d.angle,d.confidence,
                      flags & 1 != 0 ? d.correction : 0,config.gain,config.limit,config.leftMM,config.heightMM]
        for value in values { precondition(value.isFinite); put(Float(value).bitPattern) }
        put(width); put(height)
        // 28-byte crossing trailer, replacing the former reserved padding:
        // magic, version, flags, count, last-crossing uptime us, band row,
        // confidence, interval seconds. A legacy all-zero trailer stays valid.
        let c = crossing
        precondition(c.y.isFinite && c.confidence.isFinite && c.lastInterval.isFinite)
        put(GridPacket.crossingMagic); put(GridPacket.crossingVersion)
        put(UInt16(c.valid ? 1 : 0)); put(c.count)
        put(c.count > 0 ? GroundPacket.us(c.lastCrossing) : 0)
        put(Float(c.y).bitPattern); put(Float(c.confidence).bitPattern)
        put(Float(c.lastInterval).bitPattern)
        precondition(data.count == 128)
        return data
    }
    private static let crossingMagic: UInt8 = 0xc7
    private static let crossingVersion: UInt8 = 1
}
