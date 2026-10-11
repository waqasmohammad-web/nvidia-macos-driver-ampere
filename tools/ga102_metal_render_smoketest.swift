// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
//
// RTX 3080 Ti / GA102 Metal render-pipeline smoke test.
// Renders a full-screen triangle to an OFFSCREEN 16x16 RGBA8 texture,
// reads back its center pixel, and checks the expected color.
// No changes to screen mode, framebuffer, OpenCore or installed driver.
// Run: swift tools/ga102_metal_render_smoketest.swift

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

let shader = """
#include <metal_stdlib>
using namespace metal;

struct VertexOutput {
    float4 position [[position]];
};

vertex VertexOutput ga102_triangle(uint vertexID [[vertex_id]]) {
    float2 p;
    if (vertexID == 0) p = float2(-1.0, -1.0);
    else if (vertexID == 1) p = float2(3.0, -1.0);
    else p = float2(-1.0, 3.0);

    VertexOutput out;
    out.position = float4(p, 0.0, 1.0);
    return out;
}

fragment float4 ga102_fragment() {
    return float4(0.25, 0.50, 0.75, 1.0);
}
"""

do {
    let library = try device.makeLibrary(source: shader, options: nil)
    guard let vertex = library.makeFunction(name: "ga102_triangle"),
          let fragment = library.makeFunction(name: "ga102_fragment") else {
        fail("Shader functions were not found")
    }
    let descriptor = MTLRenderPipelineDescriptor()
    descriptor.vertexFunction = vertex
    descriptor.fragmentFunction = fragment
    descriptor.colorAttachments[0].pixelFormat = .rgba8Unorm
    let pipeline = try device.makeRenderPipelineState(descriptor: descriptor)

    let width = 16
    let height = 16
    let target = MTLTextureDescriptor.texture2DDescriptor(
        pixelFormat: .rgba8Unorm, width: width, height: height, mipmapped: false)
    target.usage = [.renderTarget]
    target.storageMode = .shared
    guard let texture = device.makeTexture(descriptor: target) else {
        fail("Offscreen RGBA8 texture creation failed")
    }

    let renderPass = MTLRenderPassDescriptor()
    renderPass.colorAttachments[0].texture = texture
    renderPass.colorAttachments[0].loadAction = .clear
    renderPass.colorAttachments[0].storeAction = .store
    renderPass.colorAttachments[0].clearColor = MTLClearColorMake(0, 0, 0, 1)

    guard let queue = device.makeCommandQueue(),
          let commands = queue.makeCommandBuffer(),
          let encoder = commands.makeRenderCommandEncoder(descriptor: renderPass) else {
        fail("Unable to create Metal queue, command buffer or render encoder")
    }
    encoder.setRenderPipelineState(pipeline)
    encoder.drawPrimitives(type: .triangle, vertexStart: 0, vertexCount: 3)
    encoder.endEncoding()

    let completed = DispatchSemaphore(value: 0)
    commands.addCompletedHandler { _ in completed.signal() }
    print("Rendering an offscreen 16x16 texture...")
    commands.commit()
    guard completed.wait(timeout: .now() + .seconds(15)) == .success else {
        fail("GPU render command did not complete within 15 seconds")
    }
    guard commands.status == .completed else {
        fail("Metal render command status \(commands.status); error: \(String(describing: commands.error))")
    }

    var pixels = [UInt8](repeating: 0, count: width * height * 4)
    texture.getBytes(&pixels,
                     bytesPerRow: width * 4,
                     from: MTLRegionMake2D(0, 0, width, height),
                     mipmapLevel: 0)
    let index = ((height / 2) * width + width / 2) * 4
    let color = (0..<4).map { Int(pixels[index + $0]) }
    print("Center pixel RGBA8: \(color)")
    let expected = [64, 128, 191, 255]
    guard zip(color, expected).allSatisfy({ abs($0 - $1) <= 2 }) else {
        fail("Rendered pixel differs from expected RGBA8 values near \(expected)")
    }
    let evidence: [String: Any] = ["probe": "render", "rgba": color, "width": width, "height": height, "checked_pixels": 1]
    let json = try JSONSerialization.data(withJSONObject: evidence, options: [.sortedKeys])
    print("result: \(String(data: json, encoding: .utf8)!)")
    print("PASS: Metal offscreen rendering completed with correct GPU output")
} catch {
    fail("Render shader or pipeline creation failed: \(error)")
}
