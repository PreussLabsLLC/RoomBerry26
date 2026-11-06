// @(#)GridCrossingCheck.swift 3.1.tiles.1 2026/11/05 16:00:00
import Foundation

@main struct GridCrossingCheck {
    static let width = 480, height = 640

    static func image(full: Int? = nil, left: Int? = nil, right: Int? = nil,
                      bandPixels: Int = 10, level: UInt8 = 25,
                      texture: Bool = true, corona: Bool = false) -> [UInt8] {
        var pixels = [UInt8](repeating: 210, count: width * height)
        // Longitudinal grout under the camera.
        for y in 0..<height {
            for x in 236...244 { pixels[y * width + x] = 25 }
        }
        if texture {
            for y in 0..<height {
                for x in 0..<width {
                    if (x * 7 + y * 13) % 11 < 2 {
                        pixels[y * width + x] = UInt8(max(0, Int(pixels[y * width + x]) - 6))
                    }
                }
            }
        }
        if corona {
            for y in 220...420 {
                for x in 150...330 { pixels[y * width + x] = 255 }
            }
        }
        func paint(_ top: Int, _ x0: Int, _ x1: Int) {
            let first = max(0, top), last = min(height, top + bandPixels)
            guard first < last, x0 <= x1 else { return }
            for y in first..<last {
                for x in max(0, x0)...min(width - 1, x1) { pixels[y * width + x] = level }
            }
        }
        if let row = full { paint(row, 0, width - 1) }
        let half = 8
        let leftX = Int(Double(width) * 0.22)
        let rightX = Int(Double(width) * 0.78)
        if let row = left { paint(row, leftX - half, leftX + half) }
        if let row = right { paint(row, rightX - half, rightX + half) }
        return pixels
    }

    static func detect(_ pixels: [UInt8], config: GridCrossingConfiguration) -> GridCrossingBand {
        pixels.withUnsafeBufferPointer {
            GridCrossing.detect(luma: $0.baseAddress!, width: width, height: height,
                                stride: width, config: config)
        }
    }

    static func sequence(_ rows: [Int], dt: Double = 0.5,
                         config: GridCrossingConfiguration = testConfiguration(),
                         left: [Int]? = nil, right: [Int]? = nil,
                         level: UInt8 = 25, corona: Bool = false,
                         oneSided: Bool = false) -> (UInt32, [GridCrossingEvent]) {
        var tracker = GridCrossingTracker(config: config)
        var events: [GridCrossingEvent] = []
        for (index, row) in rows.enumerated() {
            var pixels: [UInt8]
            if oneSided {
                pixels = image(left: row, bandPixels: 10, level: level, corona: corona)
            } else if let left = left, let right = right {
                pixels = image(left: left[index], right: right[index],
                               bandPixels: 10, level: level, corona: corona)
            } else {
                pixels = image(full: row, bandPixels: 10, level: level, corona: corona)
            }
            let band = detect(pixels, config: config)
            if let event = tracker.update(band, time: Double(index) * dt) { events.append(event) }
        }
        return (tracker.state.count, events)
    }

    static func testConfiguration() -> GridCrossingConfiguration {
        var config = GridCrossingConfiguration()
        config.minimumInterval = 0.1
        config.clearFrames = 2
        return config
    }

    static func main() {
        let config = testConfiguration()
        let down = Array(stride(from: 275, through: 365, by: 5))
        let up = Array(stride(from: 365, through: 275, by: -5))
        let reverse = [275, 285, 295, 305, 315, 305, 295, 285, 275]
        let jitter = [275, 285, 295, 305, 315, 325, 315, 325, 315, 335, 345]

        let moving = sequence(down, config: config)
        precondition(moving.0 == 1, "a moving band must count once")
        precondition(moving.1.count == 1 && moving.1[0].count == 1)
        precondition(moving.1[0].time >= 0 && moving.1[0].time <= 0.5 * Double(down.count))
        let returning = sequence(up, config: config)
        precondition(returning.0 == 1, "reverse motion must count once")
        let stationary = sequence([300, 300, 300, 300, 300], config: config)
        precondition(stationary.0 == 0, "a stationary band is not a crossing")
        let turned = sequence(reverse, config: config)
        precondition(turned.0 == 0, "reversal before the row is not a crossing")
        let duplicate = sequence(jitter, config: config)
        precondition(duplicate.0 == 1, "jitter around the row must not double count")
        let oneSided = sequence(down, config: config, oneSided: true)
        precondition(oneSided.0 == 0, "one-strip texture is not a band")
        let tilted = sequence(Array(repeating: 0, count: down.count), config: config,
                              left: down, right: down.map { $0 + 20 })
        precondition(tilted.0 == 1, "a slightly tilted band must still count")
        let misaligned = sequence(Array(repeating: 0, count: down.count), config: config,
                                  left: down, right: down.map { $0 + 36 })
        precondition(misaligned.0 == 0, "misaligned strips are not a band")
        let low = sequence(down, config: config, level: 198)
        precondition(low.0 == 0, "low contrast is rejected")
        let corona = sequence(down, config: config, corona: true)
        precondition(corona.0 == 1, "the side strips keep working through the LED corona")

        var tracker = GridCrossingTracker(config: config)
        var fifteen: UInt32 = 0
        var clock = 0.0
        var lastEvent: GridCrossingEvent?
        for _ in 0..<15 {
            for row in down {
                let band = detect(image(full: row), config: config)
                if let event = tracker.update(band, time: clock) {
                    fifteen += 1
                    lastEvent = event
                }
                clock += 0.5
            }
        }
        precondition(fifteen == 15, "fifteen tiles must count fifteen crossings")
        precondition(tracker.state.count == 15)
        precondition(lastEvent != nil && lastEvent!.confidence > 0.9)
        print("crossings=\(fifteen) expected=15")
        print("tile crossings: moving, reverse, stationary, reversal, one-sided, tilted, misaligned, low contrast, corona, jitter, 15-tile sequence verified")
    }
}
