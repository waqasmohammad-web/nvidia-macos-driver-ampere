// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Bounded offscreen timing/correctness probe; no window, display or driver changes.
// Run through ga102_run_metal.py for an external compilation/execution deadline.
import Foundation
import Metal
import IOSurface
import Dispatch

func fail(_ text: String) -> Never {
    fputs("FAIL: \(text)\n", stderr)
    exit(1)
}
func now() -> Double { Double(DispatchTime.now().uptimeNanoseconds) / 1e9 }
func report(_ label: String, _ value: Any) {
    print("\(label): \(value)")
    fflush(stdout)
}
func stats(_ samples: [Double]) -> [String: Double] {
    guard !samples.isEmpty else { return [:] }
    let sorted = samples.sorted()
    func percentile(_ p: Double) -> Double {
        sorted[min(sorted.count - 1, max(0, Int(ceil(p * Double(sorted.count))) - 1))] * 1000
    }
    return ["p50_ms": percentile(0.50), "p95_ms": percentile(0.95),
            "max_ms": sorted.last! * 1000, "samples": Double(samples.count)]
}
let start = now()
guard let device = MTLCopyAllDevices().first(where: { $0.name.contains("3080 Ti") }) else {
    fail("RTX 3080 Ti is absent; refusing to benchmark a different GPU")
}
report("device", device.name)
report("device_creation_ms", (now() - start) * 1000)
guard let queue = device.makeCommandQueue() else { fail("command queue unavailable") }
let shader = """
#include <metal_stdlib>
using namespace metal;
vertex float4 ga102_vertex(uint i [[vertex_id]]) {
    float2 p = i == 0 ? float2(-1, -1) : (i == 1 ? float2(3, -1) : float2(-1, 3));
    return float4(p, 0, 1);
}
fragment float4 ga102_color(constant float4 &color [[buffer(0)]]) { return color; }
"""
let library: MTLLibrary
let compileStart = now()
do { library = try device.makeLibrary(source: shader, options: nil) }
catch { fail("library compilation: \(error)") }
report("library_creation_ms", (now() - compileStart) * 1000)
guard let vertex = library.makeFunction(name: "ga102_vertex"),
      let fragment = library.makeFunction(name: "ga102_color") else { fail("shader entry points absent") }

func pipeline(_ format: MTLPixelFormat) -> MTLRenderPipelineState {
    let descriptor = MTLRenderPipelineDescriptor()
    descriptor.vertexFunction = vertex
    descriptor.fragmentFunction = fragment
    descriptor.colorAttachments[0].pixelFormat = format
    do { return try device.makeRenderPipelineState(descriptor: descriptor) }
    catch { fail("pipeline creation: \(error)") }
}
var pipelineTimes = [Double]()
var rgbaPipeline: MTLRenderPipelineState?
for _ in 0..<4 {
    let t = now()
    rgbaPipeline = pipeline(.rgba8Unorm)
    pipelineTimes.append(now() - t)
}
report("pipeline_creation_ms_in_order", pipelineTimes.map { $0 * 1000 })
let bgraPipeline = pipeline(.bgra8Unorm)

func complete(_ commands: MTLCommandBuffer) {
    let done = DispatchSemaphore(value: 0)
    commands.addCompletedHandler { _ in done.signal() }
    commands.commit()
    guard done.wait(timeout: .now() + .seconds(10)) == .success else { fail("completion deadline exceeded") }
    guard commands.status == .completed else { fail("command status \(commands.status): \(String(describing: commands.error))") }
}

// Warmups excluded; serialize iterations deliberately to measure latency, not FPS.
let iterations = 24
let comparison = CommandLine.arguments.contains("--surface-comparison")
let sizes = comparison ? [(3440, 1440)] : [(256, 256), (1024, 1024), (3440, 1440)]
let modes = comparison ? ["bgra-private", "iosurface"] : ["shared", "private", "iosurface"]
for (width, height) in sizes {
    for mode in modes {
        autoreleasepool {
            let isBGRA = mode == "iosurface" || mode == "bgra-private"
            let allocationStart = now()
            let descriptor = MTLTextureDescriptor.texture2DDescriptor(
                pixelFormat: isBGRA ? .bgra8Unorm : .rgba8Unorm,
                width: width, height: height, mipmapped: false)
            descriptor.usage = [.renderTarget, .shaderRead]
            descriptor.storageMode = mode.contains("private") ? .private : .shared
            var surface: IOSurfaceRef?
            let texture: MTLTexture
            if mode == "iosurface" {
                let row = IOSurfaceAlignProperty(kIOSurfaceBytesPerRow, width * 4)
                let properties: [String: Any] = [
                    kIOSurfaceWidth as String: width, kIOSurfaceHeight as String: height,
                    kIOSurfaceBytesPerElement as String: 4, kIOSurfaceBytesPerRow as String: row,
                    kIOSurfaceAllocSize as String: IOSurfaceAlignProperty(kIOSurfaceAllocSize, row * height),
                    kIOSurfacePixelFormat as String: UInt32(0x42475241)]
                surface = IOSurfaceCreate(properties as CFDictionary)
                guard let s = surface, let made = device.makeTexture(descriptor: descriptor, iosurface: s, plane: 0) else {
                    fail("IOSurface texture allocation \(width)x\(height)")
                }
                texture = made
            } else {
                guard let made = device.makeTexture(descriptor: descriptor) else { fail("texture allocation") }
                texture = made
            }
            let allocationMS = (now() - allocationStart) * 1000
            var encode = [Double](), commit = [Double](), total = [Double](), gpu = [Double]()
            var invalidGPU = 0
            for iteration in 0..<(iterations + 3) {
                guard let commands = queue.makeCommandBuffer() else { fail("command buffer allocation") }
                let pass = MTLRenderPassDescriptor()
                pass.colorAttachments[0].texture = texture
                pass.colorAttachments[0].loadAction = .clear
                pass.colorAttachments[0].storeAction = .store
                pass.colorAttachments[0].clearColor = MTLClearColorMake(0, 0, 0, 1)
                let t = now()
                guard let encoder = commands.makeRenderCommandEncoder(descriptor: pass) else { fail("render encoder allocation") }
                encoder.setRenderPipelineState(isBGRA ? bgraPipeline : rgbaPipeline!)
                // Each frame differs by more than the readback tolerance.
                var color = SIMD4<Float>(Float(iteration + 1) / Float(iterations + 4), 0.5, 0.75, 1)
                encoder.setFragmentBytes(&color, length: MemoryLayout<SIMD4<Float>>.stride, index: 0)
                encoder.drawPrimitives(type: .triangle, vertexStart: 0, vertexCount: 3)
                encoder.endEncoding()
                let encoded = now()
                let done = DispatchSemaphore(value: 0)
                commands.addCompletedHandler { _ in done.signal() }
                commands.commit()
                let committed = now()
                guard done.wait(timeout: .now() + .seconds(10)) == .success else { fail("render completion deadline") }
                let finished = now()
                guard commands.status == .completed else { fail("render command: \(String(describing: commands.error))") }
                if iteration >= 3 {
                    encode.append(encoded - t); commit.append(committed - encoded); total.append(finished - t)
                    let a = commands.gpuStartTime, b = commands.gpuEndTime
                    if a > 0 && b >= a && (b - a) <= (finished - t) + 0.1 { gpu.append(b - a) }
                    else { invalidGPU += 1 }
                }
            }
            // Readback is a separate submission and excluded from render latency.
            let row = ((width * 4 + 255) / 256) * 256
            guard let buffer = device.makeBuffer(length: row * height, options: .storageModeShared),
                  let commands = queue.makeCommandBuffer(), let blit = commands.makeBlitCommandEncoder() else {
                fail("readback allocation")
            }
            blit.copy(from: texture, sourceSlice: 0, sourceLevel: 0,
                      sourceOrigin: MTLOrigin(x: 0, y: 0, z: 0), sourceSize: MTLSize(width: width, height: height, depth: 1),
                      to: buffer, destinationOffset: 0, destinationBytesPerRow: row, destinationBytesPerImage: row * height)
            blit.endEncoding()
            let readStart = now()
            complete(commands)
            let readMS = (now() - readStart) * 1000
            let bytes = buffer.contents().bindMemory(to: UInt8.self, capacity: row * height)
            let red = Int((Double(iterations + 3) / Double(iterations + 4) * 255).rounded())
            let expected = isBGRA ? [191, 128, red, 255] : [red, 128, 191, 255]
            for (x, y) in [(0, 0), (width / 2, height / 2), (width - 1, height - 1)] {
                let offset = y * row + x * 4
                for channel in 0..<4 {
                    guard abs(Int(bytes[offset + channel]) - expected[channel]) <= 2 else {
                        fail("\(mode) \(width)x\(height) pixel (\(x),\(y)) channel \(channel): \(bytes[offset + channel]), expected \(expected[channel])")
                    }
                }
            }
            let result: [String: Any] = ["mode": mode, "width": width, "height": height,
                "allocation_ms": allocationMS, "encode": stats(encode), "commit_return": stats(commit),
                "encode_to_completion": stats(total), "gpu": stats(gpu), "invalid_gpu_samples": invalidGPU,
                "readback_ms": readMS, "pixels": "PASS"]
            guard let data = try? JSONSerialization.data(withJSONObject: result, options: [.sortedKeys]),
                  let json = String(data: data, encoding: .utf8) else { fail("JSON serialization") }
            report("result", json)
            withExtendedLifetime(surface) {}
        }
    }
}
report("PASS", "\(sizes.count * modes.count) bounded offscreen cases; completion latency is not desktop FPS or physical presentation timing")
