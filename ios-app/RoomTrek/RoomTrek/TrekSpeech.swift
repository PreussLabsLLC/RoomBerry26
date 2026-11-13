// @(#)TrekSpeech.swift 3.2 2026/11/09 17:25:54
import AVFoundation
import Foundation

/// Voice identity is chosen by listening; no age or gender inference from names.
final class TrekSpeech: NSObject, AVSpeechSynthesizerDelegate, AVAudioPlayerDelegate {
    static let testPhrase = "G’day, Captain! I’m running a bit low on juice!"
    private var pingPlayer: AVAudioPlayer?
    var isSpeaking: Bool { completion != nil }
    private let defaults: UserDefaults
    private let synthesizer = AVSpeechSynthesizer()
    private var currentUtterance: AVSpeechUtterance?
    private var completion: ((String, String) -> Void)?
    var log: ((String, String) -> Void)?
    private(set) var voices: [AVSpeechSynthesisVoice] = []

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        super.init()
        synthesizer.delegate = self
    }

    var preferredIdentifier: String {
        get { defaults.string(forKey: "speech.voiceIdentifier") ?? "" }
        set { defaults.set(newValue, forKey: "speech.voiceIdentifier") }
    }
    var pitch: Float {
        get { setting("speech.pitch", initial: 1.08, range: 0.5...2) }
        set { defaults.set(Self.clamped(newValue, initial: 1.08, range: 0.5...2), forKey: "speech.pitch") }
    }
    var rate: Float {
        get { setting("speech.rate", initial: 0.52, range: AVSpeechUtteranceMinimumSpeechRate...AVSpeechUtteranceMaximumSpeechRate) }
        set { defaults.set(Self.clamped(newValue, initial: 0.52, range: AVSpeechUtteranceMinimumSpeechRate...AVSpeechUtteranceMaximumSpeechRate), forKey: "speech.rate") }
    }
    private func setting(_ key: String, initial: Float, range: ClosedRange<Float>) -> Float {
        guard let number = defaults.object(forKey: key) as? NSNumber else { return initial }
        return Self.clamped(number.floatValue, initial: initial, range: range)
    }
    static func clamped(_ value: Float, initial: Float, range: ClosedRange<Float>) -> Float {
        value.isFinite ? min(range.upperBound, max(range.lowerBound, value)) : initial
    }
    static func selectedIdentifier(preferred: String, installed: [String]) -> String? {
        installed.contains(preferred) ? preferred : installed.first
    }
    static func qualityLabel(_ voice: AVSpeechSynthesisVoice) -> String {
        if #available(iOS 16.0, macOS 13.0, *), voice.quality == .premium { return "premium (\(voice.quality.rawValue))" }
        if voice.quality == .enhanced { return "enhanced (\(voice.quality.rawValue))" }
        if voice.quality == .default { return "default (\(voice.quality.rawValue))" }
        return "unknown (\(voice.quality.rawValue))"
    }
    func refreshVoices() {
        dispatchPrecondition(condition: .onQueue(.main))
        voices = AVSpeechSynthesisVoice.speechVoices().filter { $0.language.caseInsensitiveCompare("en-AU") == .orderedSame }
            .sorted { $0.quality.rawValue == $1.quality.rawValue ? $0.identifier < $1.identifier : $0.quality.rawValue > $1.quality.rawValue }
        log?("speech_voice_inventory", "en-AU installed=\(voices.count)")
        for voice in voices {
            log?("speech_voice", "name=\(voice.name) identifier=\(voice.identifier) quality=\(Self.qualityLabel(voice)) language=\(voice.language)")
        }
    }
    func speak(_ text: String, finish: @escaping (String, String) -> Void) {
        dispatchPrecondition(condition: .onQueue(.main))
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, text.count <= 500 else {
            finish("failed", "SPEAK text must contain 1–500 characters"); return
        }
        guard completion == nil else { finish("failed", "Speech already in progress"); return }
        stopPing()
        refreshVoices()
        let id = Self.selectedIdentifier(preferred: preferredIdentifier, installed: voices.map { $0.identifier })
        let utterance = AVSpeechUtterance(string: text)
        // nil deliberately delegates to the system default if no en-AU voice exists.
        utterance.voice = voices.first { $0.identifier == id }
        utterance.pitchMultiplier = pitch; utterance.rate = rate
        do {
#if os(iOS)
            let audio = AVAudioSession.sharedInstance()
            try audio.setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
            try audio.setActive(true)
#endif
        } catch { finish("failed", "Speech audio setup: \(error.localizedDescription)"); return }
        log?("speech_selected", "preferred=\(preferredIdentifier) selected=\(id ?? "system default") pitch=\(pitch) rate=\(rate)")
        completion = finish; currentUtterance = utterance
        synthesizer.speak(utterance)
    }
    /// Generated PCM tones avoid relying on undocumented system sound IDs.
    func ping(healthy: Bool) {
        dispatchPrecondition(condition: .onQueue(.main))
        guard !isSpeaking, pingPlayer?.isPlaying != true else { return }
        do {
#if os(iOS)
            let audio = AVAudioSession.sharedInstance()
            try audio.setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
            try audio.setActive(true)
#endif
            let player = try AVAudioPlayer(data: Self.pingData(healthy: healthy))
            player.delegate = self
            pingPlayer = player
            if !player.play() { stopPing() }
        } catch {
            stopPing()
            log?("heartbeat_audio_error", error.localizedDescription)
        }
    }
    func stopPing() {
        dispatchPrecondition(condition: .onQueue(.main))
        pingPlayer?.stop(); pingPlayer = nil
#if os(iOS)
        if !isSpeaking { try? AVAudioSession.sharedInstance().setActive(false, options: [.notifyOthersOnDeactivation]) }
#endif
    }
    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        guard player === pingPlayer else { return }
        stopPing()
    }
    static func pingData(healthy: Bool) -> Data {
        let sampleRate = 22050
        let pulse = Int(Double(sampleRate) * 0.09)
        let gap = Int(Double(sampleRate) * 0.10)
        let frames = healthy ? pulse : pulse * 2 + gap
        var pcm = Data()
        for i in 0..<frames {
            let offset = healthy ? i : i % (pulse + gap)
            let envelope = offset < pulse ? min(1, Double(min(offset, pulse - offset)) / 100) : 0
            let value = Int16(5000 * envelope * sin(2 * .pi * (healthy ? 1100 : 440) * Double(offset) / Double(sampleRate)))
            var sample = value.littleEndian
            withUnsafeBytes(of: &sample) { pcm.append(contentsOf: $0) }
        }
        var wave = Data()
        func word(_ value: UInt16) { var v = value.littleEndian; withUnsafeBytes(of: &v) { wave.append(contentsOf: $0) } }
        func dword(_ value: UInt32) { var v = value.littleEndian; withUnsafeBytes(of: &v) { wave.append(contentsOf: $0) } }
        wave.append(Data("RIFF".utf8)); dword(UInt32(36 + pcm.count)); wave.append(Data("WAVEfmt ".utf8))
        dword(16); word(1); word(1); dword(UInt32(sampleRate)); dword(UInt32(sampleRate * 2)); word(2); word(16)
        wave.append(Data("data".utf8)); dword(UInt32(pcm.count)); wave.append(pcm)
        return wave
    }
    func cancel() {
        dispatchPrecondition(condition: .onQueue(.main))
        synthesizer.stopSpeaking(at: .immediate)
        finishSpeech("failed", "Speech cancelled or interrupted")
    }
    private func finishSpeech(_ state: String, _ detail: String) {
        guard let callback = completion else { return }
        completion = nil; currentUtterance = nil
#if os(iOS)
        try? AVAudioSession.sharedInstance().setActive(false, options: [.notifyOthersOnDeactivation])
#endif
        log?("speech_result", "\(state): \(detail)")
        callback(state, detail)
    }
    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        DispatchQueue.main.async {
            guard self.currentUtterance === utterance else { return }
            self.finishSpeech("completed", "Speech finished")
        }
    }
    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
        DispatchQueue.main.async {
            guard self.currentUtterance === utterance else { return }
            self.finishSpeech("failed", "Speech cancelled or interrupted")
        }
    }
}

/// Main-thread heartbeat decision; independent of ARKit and audio hardware.
struct TrekHeartbeat {
    private var nextDue: TimeInterval = 0
    mutating func tone(now: TimeInterval, enabled: Bool, foreground: Bool,
                       running: Bool, trackingOK: Bool, frameTime: TimeInterval?,
                       navlink: Bool, speaking: Bool) -> Bool? {
        guard enabled, foreground else { nextDue = now + 10; return nil }
        guard now >= nextDue, !speaking else { return nil }
        nextDue = now + 10
        let age = frameTime.map { now - $0 }
        return running && trackingOK && navlink && age.map { $0 >= 0 && $0 <= 1 } == true
    }
}
