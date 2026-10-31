// @(#)GroundLink.swift 3.1.compass.1 2026/10/31 12:10:00
import Foundation
import Network

/// Bounded latest-only UDP transport; health gets the next available send.
/// Completion means sent locally, not Pi receipt.
final class GroundLink {
    private let queue = DispatchQueue(label: "GroundHog.NavLink")
    private var connection: NWConnection?
    private var ready = false
    private var inFlight = false
    private var avahi = false
    private var attempted: Double = 0
    private var sent: UInt64 = 0
    private var running = false
    private struct Pending { let data: Data; let time: UInt64 }
    private var health: Pending?
    private var motion: Pending?
    private var compass: Pending?
    var onStatus: ((String) -> Void)?
    func start() { queue.async { self.running = true; self.sent = 0 } }
    func stop() {
        queue.async {
            self.running = false; self.connection?.cancel(); self.connection = nil
            self.ready = false; self.inFlight = false; self.health = nil; self.motion = nil; self.compass = nil
        }
    }
    func send(_ packet: GroundPacket) { enqueue(packet.encoded(),time: packet.sendUS,kind: 2) }
    func send(_ packet: HealthPacket) { enqueue(packet.encoded(),time: packet.sendUS,kind: 3) }
    func send(_ packet: CompassPacket) { enqueue(packet.encoded(),time: packet.sendUS,kind: 4) }
    private func enqueue(_ data: Data, time: UInt64, kind: Int) {
        queue.async {
            guard self.running else { return }
            let pending = Pending(data: data,time: time)
            if kind == 3 { self.health = pending } else if kind == 4 { self.compass = pending } else { self.motion = pending }
            if self.connection == nil || (!self.ready && ProcessInfo.processInfo.systemUptime-self.attempted > 5) { self.connect() }
            self.flush()
        }
    }
    private func flush() {
        guard running, ready, !inFlight, let connection = connection else { return }
        let now = ProcessInfo.processInfo.systemUptime
        if let p = health, now-Double(p.time)/1e6 >= 0.25 { health = nil }
        if let p = motion, now-Double(p.time)/1e6 >= 0.25 { motion = nil }
        if let p = compass, now-Double(p.time)/1e6 >= 0.25 { compass = nil }
        let pending: Pending
        if let p = health { pending = p; health = nil }
        else if let p = motion { pending = p; motion = nil }
        else if let p = compass { pending = p; compass = nil }
        else { return }
        inFlight = true
        connection.send(content: pending.data, completion: .contentProcessed { error in
            guard self.connection === connection else { return }
            self.inFlight = false
            if let error = error {
                self.ready = false; self.report("UDP error: \(error.localizedDescription)")
            } else {
                self.sent += 1; self.report("UDP sent \(self.sent) · receipt unconfirmed")
                self.flush()
            }
        })
    }
    private func report(_ text: String) { DispatchQueue.main.async { self.onStatus?(text) } }
    private func connect() {
        connection?.cancel(); ready = false; inFlight = false
        attempted = ProcessInfo.processInfo.systemUptime
        let host = avahi ? "pi.local" : "pi"; avahi.toggle()
        let parameters = NWParameters.udp
        (parameters.defaultProtocolStack.internetProtocol as? NWProtocolIP.Options)?.version = .v4
        let current = NWConnection(host: NWEndpoint.Host(host),port: 5010,using: parameters)
        connection = current
        current.stateUpdateHandler = { [weak self, weak current] state in
            guard let self = self, let current = current, self.connection === current else { return }
            switch state {
            case .ready: self.ready = true; self.report("UDP ready: \(host):5010 · receipt unconfirmed"); self.flush()
            case .failed(let error), .waiting(let error): self.ready = false; self.report("UDP: \(error.localizedDescription)")
            default: break
            }
        }
        current.start(queue: queue)
    }
}
