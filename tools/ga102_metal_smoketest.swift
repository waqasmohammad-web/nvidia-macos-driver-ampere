// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
//
// Minimal GA102 macOS Metal compute smoke test.
// This test allocates a 4-float shared buffer, runs a tiny compute shader,
// waits for command completion (with a timeout), and verifies GPU results.
// It does not alter display settings, EFI, kexts, or the driver installation.
//
// Run with: swift tools/ga102_metal_smoketest.swift

import Foundation
import Metal
import Dispatch

func fail(_ message: String) -> Never {
    fputs("FAIL: \(message)\n", stderr)
    exit(EXIT_FAILURE)
}

guard let device = MTLCopyAllDevices().first(where: { $0.name.contains("3080 Ti") }) else {
    fail("RTX 3080 Ti unavailable")
}
print("Metal GPU: \(device.name)")

guard let queue = device.makeCommandQueue() else {
    fail("Could not create a Metal command queue")
}

let shader = """
#include <metal_stdlib>
using namespace metal;
kernel void ga102_double(device float *numbers [[buffer(0)]],
                         uint id [[thread_position_in_grid]]) {
    if (id < 4) numbers[id] *= 2.0f;
}
"""

do {
    let library = try device.makeLibrary(source: shader, options: nil)
    guard let function = library.makeFunction(name: "ga102_double") else {
        fail("Metal library did not contain ga102_double")
    }
    let pipeline = try device.makeComputePipelineState(function: function)

    let count = 4
    guard let buffer = device.makeBuffer(
        length: MemoryLayout<Float>.stride * count,
        options: .storageModeShared
    ) else {
        fail("Could not allocate a shared Metal buffer")
    }

    let values = buffer.contents().bindMemory(to: Float.self, capacity: count)
    for index in 0..<count {
        values[index] = Float(index + 1)
    }

    guard let commands = queue.makeCommandBuffer() else {
        fail("Could not allocate a Metal command buffer")
    }
    guard let encoder = commands.makeComputeCommandEncoder() else {
        fail("Could not create a Metal compute encoder")
    }
    encoder.setComputePipelineState(pipeline)
    encoder.setBuffer(buffer, offset: 0, index: 0)
    encoder.dispatchThreads(
        MTLSize(width: count, height: 1, depth: 1),
        threadsPerThreadgroup: MTLSize(width: count, height: 1, depth: 1)
    )
    encoder.endEncoding()

    let completed = DispatchSemaphore(value: 0)
    commands.addCompletedHandler { _ in completed.signal() }
    print("Submitting a four-element Metal compute workload...")
    commands.commit()

    if completed.wait(timeout: .now() + .seconds(15)) != .success {
        fail("No completion callback within 15 seconds; GPU/driver may be stalled")
    }
    guard commands.status == .completed else {
        fail("Command buffer status: \(commands.status); error: \(String(describing: commands.error))")
    }
    let result = (0..<count).map { values[$0] }
    print("Computed values: \(result)")
    guard result == [2.0, 4.0, 6.0, 8.0] else {
        fail("GPU output differs from expected [2, 4, 6, 8]")
    }
    let evidence: [String: Any] = ["probe": "compute", "values": result, "checked_elements": count]
    let json = try JSONSerialization.data(withJSONObject: evidence, options: [.sortedKeys])
    print("result: \(String(data: json, encoding: .utf8)!)")
    print("PASS: Metal compute dispatch completed with correct results")
} catch {
    fail("Metal shader compilation/pipeline creation failed: \(error)")
}
