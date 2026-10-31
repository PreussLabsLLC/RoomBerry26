// @(#)ProcessMetrics.swift 3.1.health.1 2026/10/31 12:00:00
import Foundation
import Darwin

/// Own-process counters only. CPU 100% means one fully busy core.
struct ProcessMetrics {
    private var previous: (wall: UInt64, cpu: UInt64)?
    mutating func read() -> (cpu: Float?, footprint: UInt64?) {
        var absolute = task_absolutetime_info_data_t()
        var count = mach_msg_type_number_t(MemoryLayout.size(ofValue: absolute)/MemoryLayout<integer_t>.size)
        let cpuResult = withUnsafeMutablePointer(to: &absolute) { p in
            p.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(mach_task_self_, task_flavor_t(TASK_ABSOLUTETIME_INFO), $0, &count)
            }
        }
        let wall = mach_absolute_time()
        var percent: Float?
        if cpuResult == KERN_SUCCESS {
            let total = absolute.total_user &+ absolute.total_system
            if let old = previous, wall > old.wall, total >= old.cpu {
                percent = Float(Double(total-old.cpu)/Double(wall-old.wall)*100)
            }
            previous = (wall,total)
        } else { previous = nil }
        var memory = task_vm_info_data_t()
        count = mach_msg_type_number_t(MemoryLayout.size(ofValue: memory)/MemoryLayout<integer_t>.size)
        let memoryResult = withUnsafeMutablePointer(to: &memory) { p in
            p.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(mach_task_self_, task_flavor_t(TASK_VM_INFO), $0, &count)
            }
        }
        let bytes = memoryResult == KERN_SUCCESS ? memory.phys_footprint : nil
        return (percent, bytes)
    }
}
