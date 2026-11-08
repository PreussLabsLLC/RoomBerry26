// @(#)TrekLink.swift 3.1.roomtrek.2 2026/11/08 12:00:00
import Foundation
import Network

/// Latest-only NavLink transport for type 6, modeled on GridLink.
/// Sending is not acknowledgment by the robot. One pending datagram;
/// intermediate ticks are dropped when a send is in flight.
final class TrekLink {
    private let queue = DispatchQueue(label: "RoomTrek.UDP")
    private var connection: NWConnection?
    private var session: UInt64 = 0
    private var pending: [UInt8: (Data, Double)] = [:]
    private var ready = false
    private var inFlight = false
    private var attempt = -Double.infinity
    private var avahi = false
    private var sent = 0
    var host: String = "pi"
    var port: UInt16 = 5010
    var onStatus: ((String) -> Void)?

    func start(session: UInt64) {
        queue.async {
            self.connection?.cancel(); self.connection = nil
            self.session = session
            self.ready = false; self.inFlight = false; self.pending = [:]; self.sent = 0
            self.connect()
        }
    }

    func stop() {
        queue.async {
            self.session = 0; self.pending = [:]
            // Allow an already queued datagram to leave before closing.
            let old = self.connection; self.connection = nil; self.ready = false
            self.queue.asyncAfter(deadline: .now() + 0.15) { old?.cancel() }
        }
    }

    func send(_ data: Data, session: UInt64) {
        queue.async {
            guard self.session == session, session != 0, data.count == 128 else { return }
            self.pending[data[5]] = (data, ProcessInfo.processInfo.systemUptime)
            if self.connection == nil || (!self.ready && ProcessInfo.processInfo.systemUptime - self.attempt > 5) {
                self.connect()
            }
            self.flush()
        }
    }

    private func report(_ s: String) { DispatchQueue.main.async { self.onStatus?(s) } }

    private func connect() {
        connection?.cancel(); ready = false; inFlight = false
        attempt = ProcessInfo.processInfo.systemUptime
        let currentHost = avahi && !host.contains(".") ? "\(host).local" : host
        avahi.toggle()
        let params = NWParameters.udp
        (params.defaultProtocolStack.internetProtocol as? NWProtocolIP.Options)?.version = .v4
        let hostPort = NWEndpoint.Port(rawValue: port) ?? NWEndpoint.Port(rawValue: 5010)!
        let current = NWConnection(host: NWEndpoint.Host(currentHost), port: hostPort, using: params)
        connection = current
        current.stateUpdateHandler = { [weak self, weak current] state in
            guard let self = self, let current = current, self.connection === current else { return }
            switch state {
            case .ready:
                self.ready = true
                self.report("UDP ready (\(currentHost):\(self.port)) · Pi receipt unconfirmed")
                self.flush()
            case .failed(let e), .waiting(let e):
                self.ready = false
                self.report("UDP \(currentHost): " + e.localizedDescription)
            default: break
            }
        }
        current.start(queue: queue)
    }

    private func flush() {
        guard session != 0, ready, !inFlight, let connection = connection else { return }
        let now = ProcessInfo.processInfo.systemUptime
        pending = pending.filter { now - $0.value.1 < 0.25 }
        guard let kind = pending.keys.first, let item = pending.removeValue(forKey: kind) else { return }
        inFlight = true
        connection.send(content: item.0, completion: .contentProcessed { error in
            guard self.connection === connection else { return }
            self.inFlight = false
            if let error = error {
                self.ready = false
                self.report(error.localizedDescription)
            } else {
                self.sent += 1
                self.report("UDP sent \(self.sent) · Pi receipt unconfirmed")
                self.flush()
            }
        })
    }
}
