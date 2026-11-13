// @(#)SpeechChecks.swift 3.2 2026/11/09 17:25:54
import Foundation
import AVFoundation

@main struct SpeechChecks {
    static func main() {
        let suite = "RoomTrek.SpeechChecks.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let speech = TrekSpeech(defaults: defaults)
        assert(abs(speech.pitch - 1.08) < 0.001 && abs(speech.rate - 0.52) < 0.001)
        speech.preferredIdentifier = "installed-au-voice"
        speech.pitch = 1.15; speech.rate = 0.45
        let restored = TrekSpeech(defaults: UserDefaults(suiteName: suite)!)
        assert(restored.preferredIdentifier == "installed-au-voice")
        assert(abs(restored.pitch - 1.15) < 0.001 && abs(restored.rate - 0.45) < 0.001)
        assert(TrekSpeech.selectedIdentifier(preferred: "au-b", installed: ["au-a", "au-b"]) == "au-b")
        assert(TrekSpeech.selectedIdentifier(preferred: "unavailable", installed: ["au-a"]) == "au-a")
        assert(TrekSpeech.selectedIdentifier(preferred: "unavailable", installed: []) == nil)
        speech.pitch = .nan; speech.rate = .infinity
        assert(abs(speech.pitch - 1.08) < 0.001 && abs(speech.rate - 0.52) < 0.001)
        speech.pitch = 99; speech.rate = -1
        assert(speech.pitch == 2 && speech.rate == AVSpeechUtteranceMinimumSpeechRate)
        var result = ""
        speech.speak("  ") { state, _ in result = state }
        assert(result == "failed")
        result = ""
        speech.speak(String(repeating: "x", count: 501)) { state, _ in result = state }
        assert(result == "failed")
        assert(TrekSpeech.testPhrase == "G’day, Captain! I’m running a bit low on juice!")
        var heartbeat = TrekHeartbeat()
        func tone(_ now: Double, enabled: Bool = true, foreground: Bool = true,
                  running: Bool = true, tracking: Bool = true, frame: Double? = nil,
                  navlink: Bool = true, speaking: Bool = false) -> Bool? {
            heartbeat.tone(now: now, enabled: enabled, foreground: foreground,
                running: running, trackingOK: tracking, frameTime: frame ?? now,
                navlink: navlink, speaking: speaking)
        }
        assert(tone(0, enabled: false) == nil)
        assert(tone(9) == nil)
        assert(tone(10) == true)
        assert(tone(19) == nil)
        assert(tone(20, tracking: false) == false)
        assert(tone(30, frame: 28) == false)
        assert(tone(40, running: false) == false)
        assert(tone(50, navlink: false) == false)
        assert(tone(60, speaking: true) == nil)
        assert(tone(61) == true) // speech delays, no burst of missed tones
        assert(tone(100, foreground: false) == nil)
        assert(tone(101) == nil)
        assert(tone(110) == true)
        for healthy in [true, false] {
            let data = TrekSpeech.pingData(healthy: healthy)
            assert(String(data: data.prefix(4), encoding: .utf8) == "RIFF")
            let player = try! AVAudioPlayer(data: data)
            assert(player.duration > 0.08 && player.duration < 0.4)
        }
        print("Heartbeat cadence, tracking/staleness, foreground, speech and PCM tone checks passed")
        print("Speech preference, persistence, fallback, bounds and input checks passed")
    }
}
