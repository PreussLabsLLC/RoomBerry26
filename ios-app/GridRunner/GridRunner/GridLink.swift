// @(#)GridLink.swift 3.1.grid.1 2026/11/03 20:30:00
import Foundation
import Network

/// Latest-only NavLink transport. Sending is not acknowledgment by the robot.
final class GridLink {
    private let queue = DispatchQueue(label:"GridRunner.UDP")
    private var connection: NWConnection?
    private var session: UInt64 = 0
    private var pending: [UInt8:(Data,Double)] = [:]
    private var ready = false
    private var inFlight = false
    private var attempt = -Double.infinity
    private var avahi = false
    private var sent = 0
    var onStatus: ((String)->Void)?
    func start(session: UInt64) {
        queue.async {
            self.connection?.cancel(); self.connection = nil; self.session = session
            self.ready = false; self.inFlight = false; self.pending = [:]; self.sent = 0
            self.connect()
        }
    }
    func stop() {
        queue.async {
            self.session = 0; self.pending = [:]
            // Allow an already queued Stop datagram to leave before closing.
            let old = self.connection; self.connection = nil; self.ready = false
            self.queue.asyncAfter(deadline:.now()+0.15) { old?.cancel() }
        }
    }
    func send(_ data: Data, session: UInt64) {
        queue.async {
            guard self.session == session, session != 0, data.count == 128 else { return }
            if data[5] == 5 && data[28] == 0 && data[29] == 0 {
                self.pending = [:]
                self.connection?.send(content:data,completion:.contentProcessed { _ in })
                return
            }
            self.pending[data[5]] = (data,ProcessInfo.processInfo.systemUptime)
            if self.connection == nil || (!self.ready && ProcessInfo.processInfo.systemUptime-self.attempt > 5) { self.connect() }
            self.flush()
        }
    }
    private func report(_ s: String) { DispatchQueue.main.async { self.onStatus?(s) } }
    private func connect() {
        connection?.cancel(); ready = false; inFlight = false; attempt = ProcessInfo.processInfo.systemUptime
        let host = avahi ? "pi.local" : "pi"; avahi.toggle()
        let params = NWParameters.udp
        (params.defaultProtocolStack.internetProtocol as? NWProtocolIP.Options)?.version = .v4
        let current = NWConnection(host:NWEndpoint.Host(host),port:5010,using:params)
        connection = current
        current.stateUpdateHandler = { [weak self,weak current] state in
            guard let self = self, let current = current, self.connection === current else { return }
            switch state {
            case .ready: self.ready = true; self.report("UDP ready · Pi receipt unconfirmed"); self.flush()
            case .failed(let e), .waiting(let e): self.ready = false; self.report("UDP: "+e.localizedDescription)
            default: break
            }
        }
        current.start(queue:queue)
    }
    private func flush() {
        guard session != 0, ready, !inFlight, let connection = connection else { return }
        let now = ProcessInfo.processInfo.systemUptime
        pending = pending.filter { now-$0.value.1 < 0.25 }
        // Stop/line records precede health so a Stop cannot wait on its heartbeat.
        guard let kind = pending[5] != nil ? UInt8(5) : pending.keys.first,
              let item = pending.removeValue(forKey:kind) else { return }
        inFlight = true
        connection.send(content:item.0,completion:.contentProcessed { error in
            guard self.connection === connection else { return }
            self.inFlight = false
            if let error = error { self.ready = false; self.report(error.localizedDescription) }
            else { self.sent += 1; self.report("UDP sent \(self.sent) · Pi receipt unconfirmed"); self.flush() }
        })
    }
}
