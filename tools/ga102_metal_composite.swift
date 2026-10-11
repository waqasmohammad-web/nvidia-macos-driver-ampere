// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Bounded sampled premultiplied-alpha workload; existing driver, no display APIs.
import Foundation
import Metal
import IOSurface
import Dispatch
func fail(_ s: String) -> Never { fputs("FAIL: \(s)\n", stderr); exit(1) }
func now() -> Double { Double(DispatchTime.now().uptimeNanoseconds) / 1e9 }
func stats(_ a: [Double]) -> [String: Double] {
    let s = a.sorted(); if s.isEmpty { return [:] }
    return ["p50_ms": s[(s.count-1)/2]*1000,
            "p95_ms": s[min(s.count-1, Int(ceil(Double(s.count)*0.95))-1)]*1000,
            "max_ms": s.last!*1000, "samples": Double(s.count)]
}
func complete(_ c: MTLCommandBuffer) {
    let done = DispatchSemaphore(value: 0); c.addCompletedHandler { _ in done.signal() }; c.commit()
    guard done.wait(timeout: .now()+10) == .success, c.status == .completed else { fail("GPU completion") }
}
guard let device = MTLCopyAllDevices().first(where: { $0.name.contains("3080 Ti") }),
      let queue = device.makeCommandQueue() else { fail("RTX 3080 Ti unavailable") }
print("device: \(device.name)")
let source = """
#include <metal_stdlib>
using namespace metal;
vertex float4 composite_v(uint i [[vertex_id]]) {
    return float4(i == 0 ? float2(-1,-1) : (i == 1 ? float2(3,-1) : float2(-1,3)),0,1);
}
fragment float4 composite_f(texture2d<float> image [[texture(0)]]) {
    constexpr sampler point(coord::normalized, filter::nearest, address::clamp_to_edge);
    return image.sample(point, float2(0.5));
}
"""
let pipeline: MTLRenderPipelineState
do {
    let lib = try device.makeLibrary(source: source, options: nil)
    let d = MTLRenderPipelineDescriptor(); d.vertexFunction = lib.makeFunction(name: "composite_v")
    d.fragmentFunction = lib.makeFunction(name: "composite_f")
    let a = d.colorAttachments[0]!
    a.pixelFormat = .bgra8Unorm; a.isBlendingEnabled = true
    a.sourceRGBBlendFactor = .one; a.destinationRGBBlendFactor = .oneMinusSourceAlpha
    a.sourceAlphaBlendFactor = .one; a.destinationAlphaBlendFactor = .oneMinusSourceAlpha
    pipeline = try device.makeRenderPipelineState(descriptor: d)
} catch { fail("pipeline compilation: \(error)") }
var inputs = [MTLTexture]()
for color in 0..<3 {
    let d = MTLTextureDescriptor.texture2DDescriptor(pixelFormat: .rgba8Unorm, width: 1, height: 1, mipmapped: false)
    d.storageMode = .shared; d.usage = .shaderRead
    guard let t = device.makeTexture(descriptor: d) else { fail("source texture") }
    var bytes: [UInt8] = [0,0,0,64]; bytes[color] = 64
    bytes.withUnsafeBytes { t.replace(region: MTLRegionMake2D(0,0,1,1), mipmapLevel: 0, withBytes: $0.baseAddress!, bytesPerRow: 4) }
    inputs.append(t)
}
let width = 3440, height = 1440, samples = 8
for layers in [16,32] {
    for mode in ["private", "iosurface"] {
        autoreleasepool {
            let d = MTLTextureDescriptor.texture2DDescriptor(pixelFormat: .bgra8Unorm, width: width, height: height, mipmapped: false)
            d.storageMode = mode == "private" ? .private : .shared; d.usage = .renderTarget
            var surface: IOSurfaceRef?
            let texture: MTLTexture
            if mode == "iosurface" {
                let row = IOSurfaceAlignProperty(kIOSurfaceBytesPerRow, width*4)
                surface = IOSurfaceCreate([kIOSurfaceWidth: width, kIOSurfaceHeight: height,
                    kIOSurfaceBytesPerElement: 4, kIOSurfaceBytesPerRow: row,
                    kIOSurfaceAllocSize: IOSurfaceAlignProperty(kIOSurfaceAllocSize, row*height),
                    kIOSurfacePixelFormat: UInt32(0x42475241)] as CFDictionary)
                guard let s = surface, let t = device.makeTexture(descriptor: d, iosurface: s, plane: 0) else { fail("IOSurface allocation") }
                texture = t
            } else {
                guard let t = device.makeTexture(descriptor: d) else { fail("private allocation") }; texture = t
            }
            var gpu = [Double](), wall = [Double]()
            for frame in 0..<(samples+2) {
                guard let c = queue.makeCommandBuffer() else { fail("command allocation") }
                let pass = MTLRenderPassDescriptor(); let a = pass.colorAttachments[0]!
                a.texture = texture; a.loadAction = .clear; a.storeAction = .store
                a.clearColor = MTLClearColorMake(0.1,0.2,0.3,1)
                let t = now()
                guard let e = c.makeRenderCommandEncoder(descriptor: pass) else { fail("render encoder") }
                e.setRenderPipelineState(pipeline)
                for index in 0..<layers {
                    e.setFragmentTexture(inputs[(index+frame)%3], index: 0)
                    e.drawPrimitives(type: .triangle, vertexStart: 0, vertexCount: 3)
                }
                e.endEncoding(); complete(c)
                if frame >= 2 {
                    wall.append(now()-t)
                    if c.gpuStartTime > 0 && c.gpuEndTime >= c.gpuStartTime { gpu.append(c.gpuEndTime-c.gpuStartTime) }
                }
            }
            let row = ((width*4+255)/256)*256
            guard let b = device.makeBuffer(length: row*height, options: .storageModeShared),
                  let c = queue.makeCommandBuffer(), let e = c.makeBlitCommandEncoder() else { fail("readback allocation") }
            e.copy(from: texture, sourceSlice: 0, sourceLevel: 0, sourceOrigin: MTLOrigin(x: 0,y: 0,z: 0),
                   sourceSize: MTLSize(width: width,height: height,depth: 1), to: b, destinationOffset: 0,
                   destinationBytesPerRow: row, destinationBytesPerImage: row*height)
            e.endEncoding(); complete(c)
            // Model UNORM rounding after each blend, with tolerance for hardware precision.
            var expected = [26.0,51.0,77.0]
            for index in 0..<layers {
                for ch in 0..<3 { expected[ch] = (expected[ch]*(191.0/255.0) + (ch == (index+samples+1)%3 ? 64 : 0)).rounded() }
            }
            let bgra = [expected[2],expected[1],expected[0],255.0]
            let bytes = b.contents().bindMemory(to: UInt8.self, capacity: row*height)
            for y in [0,height/3,2*height/3,height-1] {
                for x in [0,width/3,2*width/3,width-1] {
                    for ch in 0..<4 {
                        guard abs(Double(bytes[y*row+x*4+ch])-bgra[ch]) <= 3 else {
                            fail("\(mode) \(layers) layers pixel \(x),\(y) channel \(ch) value \(bytes[y*row+x*4+ch]), expected \(bgra[ch])")
                        }
                    }
                }
            }
            let result: [String: Any] = ["mode":mode,"layers":layers,"width":width,"height":height,
                "gpu":stats(gpu),"encode_to_completion":stats(wall),"pixels":"PASS","checked_pixels":16]
            let data = try! JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
            print("result: \(String(data:data,encoding:.utf8)!)"); fflush(stdout)
            withExtendedLifetime(surface) {}
        }
    }
}
print("PASS: 4 sampled alpha-compositing cases; full-screen overdraw stress, not a desktop trace")
