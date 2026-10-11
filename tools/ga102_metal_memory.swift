// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// 4 MiB shared/managed/private buffers; bounded transfers and full output checks.
import Foundation
import Metal
import Dispatch
func fail(_ text: String) -> Never { fputs("FAIL: \(text)\n", stderr); exit(1) }
func now() -> Double { Double(DispatchTime.now().uptimeNanoseconds) / 1e9 }
func complete(_ commands: MTLCommandBuffer) {
    let done = DispatchSemaphore(value: 0)
    commands.addCompletedHandler { _ in done.signal() }
    commands.commit()
    guard done.wait(timeout: .now() + .seconds(10)) == .success,
          commands.status == .completed else { fail("command completion: \(String(describing: commands.error))") }
}
guard let device = MTLCopyAllDevices().first(where: { $0.name.contains("3080 Ti") }),
      let queue = device.makeCommandQueue() else { fail("RTX 3080 Ti / queue unavailable") }
print("device: \(device.name)")
let count = 1024 * 1024, length = 4 * 1024 * 1024, iterations = 8
let source = """
#include <metal_stdlib>
using namespace metal;
kernel void ga102_memory(device float *values [[buffer(0)]], uint i [[thread_position_in_grid]]) {
    if (i < 1048576) values[i] *= 2.0f;
}
"""
let pipeline: MTLComputePipelineState
do {
    let library = try device.makeLibrary(source: source, options: nil)
    guard let function = library.makeFunction(name: "ga102_memory") else { fail("kernel missing") }
    pipeline = try device.makeComputePipelineState(function: function)
} catch { fail("compile: \(error)") }
for (name, mode) in [("shared", MTLResourceOptions.storageModeShared),
                     ("managed", .storageModeManaged), ("private", .storageModePrivate)] {
    autoreleasepool {
        let allocation = now()
        guard let buffer = device.makeBuffer(length: length, options: mode),
              let staging = device.makeBuffer(length: length, options: .storageModeShared) else { fail("\(name) allocation") }
        let allocationMS = (now() - allocation) * 1000
        let initial = staging.contents().bindMemory(to: Float.self, capacity: count)
        for i in 0..<count { initial[i] = Float(i % 127 + 1) }
        let upload = now()
        if name == "private" {
            guard let command = queue.makeCommandBuffer(), let blit = command.makeBlitCommandEncoder() else { fail("upload encoder") }
            blit.copy(from: staging, sourceOffset: 0, to: buffer, destinationOffset: 0, size: length)
            blit.endEncoding(); complete(command)
        } else {
            memcpy(buffer.contents(), staging.contents(), length)
            if name == "managed" { buffer.didModifyRange(0..<length) }
        }
        let uploadMS = (now() - upload) * 1000
        var wall = [Double](), gpu = [Double]()
        for _ in 0..<iterations {
            guard let command = queue.makeCommandBuffer(), let encoder = command.makeComputeCommandEncoder() else { fail("compute encoder") }
            let t = now()
            encoder.setComputePipelineState(pipeline); encoder.setBuffer(buffer, offset: 0, index: 0)
            encoder.dispatchThreads(MTLSize(width: count, height: 1, depth: 1),
                                    threadsPerThreadgroup: MTLSize(width: min(256, pipeline.maxTotalThreadsPerThreadgroup), height: 1, depth: 1))
            encoder.endEncoding(); complete(command); wall.append((now() - t) * 1000)
            let a = command.gpuStartTime, b = command.gpuEndTime
            if a > 0 && b >= a { gpu.append((b - a) * 1000) }
        }
        let readback = now()
        guard let command = queue.makeCommandBuffer(), let blit = command.makeBlitCommandEncoder() else { fail("readback encoder") }
        blit.copy(from: buffer, sourceOffset: 0, to: staging, destinationOffset: 0, size: length)
        blit.endEncoding(); complete(command)
        let readMS = (now() - readback) * 1000
        for i in 0..<count {
            let expected = Float(i % 127 + 1) * Float(1 << iterations)
            guard initial[i] == expected else { fail("\(name) element \(i): \(initial[i]) != \(expected)") }
        }
        let result: [String: Any] = ["mode": name, "bytes": length, "allocation_ms": allocationMS,
            "initial_upload_ms": uploadMS, "encode_to_completion_ms_in_order": wall,
            "gpu_ms_in_order": gpu, "readback_ms": readMS, "checked_elements": count, "output": "PASS"]
        let data = try! JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
        print("result: \(String(data: data, encoding: .utf8)!)"); fflush(stdout)
    }
}
print("PASS: shared/managed/private buffer execution and 3 x 1048576 element checks")
