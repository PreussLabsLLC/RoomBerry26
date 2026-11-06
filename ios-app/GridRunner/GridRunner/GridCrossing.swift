// @(#)GridCrossing.swift 3.1.tiles.1 2026/11/05 16:00:00
import Foundation

/// Transverse grout-line parameters. All positions are normalised portrait
/// image coordinates (0...1). The detector never steers; it only observes.
struct GridCrossingConfiguration {
    var leftStrip = 0.22
    var rightStrip = 0.78
    var stripWidth = 16
    var referenceY = 0.50
    var searchTop = 0.16
    var searchBottom = 0.88
    var contrast = 16.0
    var minimumBandPixels = 3
    var maximumBandPixels = 64
    var stripAgreement = 0.040 // allow robot yaw; strips are ~38 mm apart
    var minimumConfidence = 0.45
    var confirmFrames = 2
    var clearDistance = 0.030
    var clearFrames = 2
    var minimumInterval = 1.5
    var valid: Bool {
        leftStrip.isFinite && rightStrip.isFinite && stripWidth >= 6
            && (0.02...0.48).contains(leftStrip) && (0.52...0.98).contains(rightStrip)
            && 0 < referenceY && referenceY < 1
            && 0 <= searchTop && searchTop < referenceY
            && referenceY < searchBottom && searchBottom <= 1
            && contrast.isFinite && contrast > 2
            && minimumBandPixels >= 2 && maximumBandPixels > minimumBandPixels
            && maximumBandPixels <= 128 && stripAgreement > 0 && stripAgreement <= 0.2
            && (0...1).contains(minimumConfidence)
            && confirmFrames >= 1 && clearDistance > 0 && clearFrames >= 1
            && minimumInterval >= 0
    }
}

/// One frame's transverse-band candidate in image coordinates.
struct GridCrossingBand {
    var valid = false
    var y = 0.0          // combined centre, normalised row
    var leftY = 0.0      // left-strip centre, normalised row
    var rightY = 0.0     // right-strip centre, normalised row
    var confidence = 0.0
    var pixels = 0
}

/// Local crossing telemetry. Phase 1/2 keeps this off the wire; the type-5
/// trailer is reserved for the later Pi-recording phase.
struct GridCrossingState {
    var valid = false
    var count: UInt32 = 0
    var y = 0.0
    var leftY = 0.0
    var rightY = 0.0
    var confidence = 0.0
    var lastCrossing = 0.0
    var lastInterval = 0.0
    var phase: UInt8 = 0   // 0 searching, 1 candidate, 2 clearing
}

struct GridCrossingEvent {
    var count: UInt32
    var time: Double
    var y: Double
    var confidence: Double
    var interval: Double
}

/// Detect a dark transverse band in two strips either side of the tracked
/// longitudinal line. The strips avoid the centre LED reflection, and the
/// two-strip agreement rejects one-sided tile texture.
struct GridCrossing {
    static func detect(luma: UnsafePointer<UInt8>, width: Int, height: Int, stride: Int,
                       config: GridCrossingConfiguration) -> GridCrossingBand {
        var result = GridCrossingBand()
        guard config.valid, width > 64, height > 64, stride >= width else { return result }
        let top = max(2, Int(Double(height) * config.searchTop))
        let bottom = min(height - 2, Int(Double(height) * config.searchBottom))
        guard bottom > top + 8 else { return result }
        let half = max(3, min(width / 10, config.stripWidth / 2))
        let leftX = Int(Double(width) * config.leftStrip)
        let rightX = Int(Double(width) * config.rightStrip)
        guard leftX - half > 0, rightX + half < width else { return result }

        var left = [Double](repeating: 0, count: bottom - top)
        var right = [Double](repeating: 0, count: bottom - top)
        for y in top..<bottom {
            left[y - top] = median(luma, row: y, start: leftX - half, count: half * 2 + 1, stride: stride)
            right[y - top] = median(luma, row: y, start: rightX - half, count: half * 2 + 1, stride: stride)
        }
        // A local maximum is the tile surface: the window is wider than the
        // widest accepted band, so the band itself cannot hide the background.
        let radius = max(16, config.maximumBandPixels)
        let leftBase = background(left, radius: radius)
        let rightBase = background(right, radius: radius)

        struct Run {
            var centre: Double
            var pixels: Int
            var confidence: Double
            var contrast: Double
            var score: Double { confidence * contrast }
        }
        func runs(_ values: [Double], _ base: [Double]) -> [Run] {
            var result: [Run] = []
            var i = 0
            while i < values.count {
                if values[i] > base[i] - config.contrast { i += 1; continue }
                let begin = i
                var total = 0.0, sum = 0.0
                while i < values.count {
                    let d = base[i] - values[i]
                    if d < config.contrast { break }
                    total += d; sum += Double(i) * d
                    i += 1
                }
                let count = i - begin
                guard count >= config.minimumBandPixels,
                      count <= config.maximumBandPixels,
                      total > 0 else { continue }
                let runContrast = total / Double(count)
                let confidence = min(1.0, runContrast / 60.0) * min(1.0, Double(count) / 5.0)
                guard confidence >= config.minimumConfidence else { continue }
                result.append(Run(centre: sum / total + Double(top), pixels: count,
                                  confidence: confidence, contrast: runContrast))
            }
            return result
        }
        func best(_ list: [Run]) -> Run? {
            guard !list.isEmpty else { return nil }
            let sorted = list.sorted { $0.score > $1.score }
            let top = sorted[0]
            // Two similarly strong bands far apart in the same strip are
            // ambiguous; do not guess which one is the tile edge.
            if sorted.dropFirst().contains(where: {
                $0.score >= top.score * 0.8 && abs($0.centre - top.centre) > Double(height) * 0.04
            }) { return nil }
            return top
        }
        guard let leftRun = best(runs(left, leftBase)),
              let rightRun = best(runs(right, rightBase)) else { return result }

        let leftY = leftRun.centre / Double(height)
        let rightY = rightRun.centre / Double(height)
        guard abs(leftY - rightY) <= config.stripAgreement,
              leftY > config.searchTop, rightY > config.searchTop,
              leftY < config.searchBottom, rightY < config.searchBottom else { return result }
        result.valid = true
        result.leftY = leftY
        result.rightY = rightY
        result.y = (leftY + rightY) / 2
        result.confidence = min(leftRun.confidence, rightRun.confidence)
        result.pixels = min(leftRun.pixels, rightRun.pixels)
        return result
    }

    private static func median(_ luma: UnsafePointer<UInt8>, row: Int, start: Int,
                               count: Int, stride: Int) -> Double {
        var values = [UInt8](repeating: 0, count: count)
        let base = row * stride + start
        for i in 0..<count { values[i] = luma[base + i] }
        values.sort()
        return Double(values[count / 2])
    }

    private static func background(_ values: [Double], radius: Int) -> [Double] {
        values.indices.map { index in
            let low = max(0, index - radius)
            let high = min(values.count - 1, index + radius)
            var maximum = values[low]
            for i in (low + 1)...high where values[i] > maximum { maximum = values[i] }
            return maximum
        }
    }
}

/// Count a band once as it passes the reference row. Motion is observed, not
/// taken from the app's direction setting: the Pi keeps "Reverse" selected
/// during the forward return leg as well.
struct GridCrossingTracker {
    var config = GridCrossingConfiguration()
    private(set) var state = GridCrossingState()
    private var previous: GridCrossingBand?
    private var previousTime = 0.0
    private var candidateFrames = 0
    private var clearFrames = 0
    private var armed = true
    private var motion = 0.0

    init(config: GridCrossingConfiguration = GridCrossingConfiguration()) {
        self.config = config
    }

    mutating func reset() {
        self = GridCrossingTracker(config: config)
    }

    mutating func update(_ band: GridCrossingBand, time: Double) -> GridCrossingEvent? {
        state.valid = band.valid
        if band.valid {
            state.y = band.y
            state.leftY = band.leftY
            state.rightY = band.rightY
            state.confidence = band.confidence
        }
        guard band.valid, time.isFinite else {
            previous = nil
            candidateFrames = 0
            if armed {
                state.phase = 0
            } else {
                state.phase = 2
                clearFrames += 1
                if clearFrames >= config.clearFrames { armed = true; clearFrames = 0; state.phase = 0 }
            }
            return nil
        }
        guard let prior = previous, time > previousTime, time - previousTime <= 0.5 else {
            previous = band
            previousTime = time
            candidateFrames = 0
            state.phase = armed ? 0 : 2
            return nil
        }
        let reference = config.referenceY
        let delta = band.y - prior.y
        if !armed {
            if abs(band.y - reference) >= config.clearDistance {
                clearFrames += 1
                if clearFrames >= config.clearFrames {
                    armed = true
                    clearFrames = 0
                    state.phase = 0
                }
            } else {
                clearFrames = 0
                state.phase = 2
            }
            previous = band
            previousTime = time
            return nil
        }

        // Use the previous position: on the count frame the band has just
        // crossed the row, so testing the current side would cancel the
        // candidate immediately before it can be counted.
        let approaching = (reference - prior.y) * delta > 0
        if approaching {
            let direction = delta > 0 ? 1.0 : -1.0
            if motion == 0 || motion * direction > 0 {
                candidateFrames += 1
            } else {
                candidateFrames = 1
            }
            motion = direction
        } else {
            candidateFrames = 0
            motion = 0
        }
        state.phase = candidateFrames > 0 ? 1 : 0

        let before = prior.y - reference
        let after = band.y - reference
        if before * after < 0 && abs(delta) > 0.002 {
            let fraction = max(0.0, min(1.0, (reference - prior.y) / delta))
            let crossingTime = previousTime + fraction * (time - previousTime)
            let interval = state.lastCrossing > 0 ? crossingTime - state.lastCrossing : 0
            let intervalOK = state.lastCrossing == 0 || interval >= config.minimumInterval
            if candidateFrames >= config.confirmFrames && intervalOK {
                state.count &+= 1
                state.lastCrossing = crossingTime
                state.lastInterval = interval
                state.phase = 2
                armed = false
                clearFrames = 0
                candidateFrames = 0
                motion = 0
                previous = band
                previousTime = time
                return GridCrossingEvent(count: state.count, time: crossingTime,
                                         y: band.y, confidence: band.confidence,
                                         interval: interval)
            }
            if !intervalOK {
                // A second passage inside the minimum interval is jitter or a
                // duplicate detection. Do not count it; require a clear first.
                armed = false
                clearFrames = 0
                candidateFrames = 0
                motion = 0
                state.phase = 2
            }
        }
        previous = band
        previousTime = time
        return nil
    }
}
