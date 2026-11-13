// @(#)TrekLink.swift 3.2.mothership.1 2026/11/12 11:51:06
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
    private var host: String = "pi3.local"
    var port: UInt16 = 5010
    var onReceive: ((Data) -> Void)?
    var onHeartbeat: (() -> Void)?
    private var heartbeatTimer: DispatchSourceTimer?
    var onStatus: ((String) -> Void)?

    func configureHost(_ host: String) {
        queue.async {
            guard self.host != host else { return }
            self.host = host
            self.avahi = false
            if self.connection != nil { self.connect() }
        }
    }

    func start(session: UInt64) {
        queue.async {
            self.session = session
            self.pending = [:]
            if self.connection == nil { self.connect() }
            if self.heartbeatTimer == nil {
                let timer = DispatchSource.makeTimerSource(queue: self.queue)
                timer.schedule(deadline: .now(), repeating: 2)
                timer.setEventHandler { [weak self] in
                    guard let self = self else { return }
                    if !self.ready && ProcessInfo.processInfo.systemUptime - self.attempt > 5 { self.connect() }
                    DispatchQueue.main.async { self.onHeartbeat?() }
                }
                self.heartbeatTimer = timer; timer.resume()
            }
        }
    }

    func stop() {
        queue.async {
            self.heartbeatTimer?.cancel(); self.heartbeatTimer = nil
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
                self.receive(current)
                DispatchQueue.main.async { self.onHeartbeat?() }
                self.flush()
            case .failed(let e), .waiting(let e):
                self.ready = false
                self.report("UDP \(currentHost): " + e.localizedDescription)
            default: break
            }
        }
        current.start(queue: queue)
    }

    // Connected UDP filters inbound datagrams to the configured Pi endpoint.
    func sendControl(_ data: Data) {
        queue.async {
            guard self.ready, let connection = self.connection else { return }
            connection.send(content: data, completion: .contentProcessed { _ in })
        }
    }

    private func receive(_ current: NWConnection) {
        current.receiveMessage { [weak self, weak current] data, _, _, error in
            guard let self = self, let current = current, self.connection === current else { return }
            if let data = data { DispatchQueue.main.async { self.onReceive?(data) } }
            if error == nil { self.receive(current) }
            else { self.ready = false }
        }
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
