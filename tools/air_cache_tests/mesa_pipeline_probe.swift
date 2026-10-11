// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Installed-driver probe; eight owned kernels, bounded completion, no window.
import Foundation
import Metal
import Dispatch
func fail(_ s: String) -> Never { fputs("FAIL: \(s)\n", stderr); exit(1) }
func tick() -> UInt64 { DispatchTime.now().uptimeNanoseconds }
func ms(_ t: UInt64) -> Double { Double(tick() - t) / 1e6 }
guard let d = MTLCopyAllDevices().first(where: {$0.name.contains("3080 Ti")}),
      let q = d.makeCommandQueue() else { fail("GA102 device/queue unavailable") }
let sameFunction = CommandLine.arguments.dropFirst().elementsEqual(["--same-function"])
if CommandLine.arguments.count > 1 && !sameFunction { fail("unknown probe argument") }
let source = "#include <metal_stdlib>\nusing namespace metal;\n" + (0..<8).map {
    "kernel void cache_case_\($0)(device float *a [[buffer(0)]], uint i [[thread_position_in_grid]]) { if(i<4) a[i]=a[i]*\($0+2).0f+\($0).0f; }"
}.joined(separator: "\n")
do {
    let start = tick()
    let lib = try d.makeLibrary(source: source, options: nil)
    let libraryMS = ms(start)
    var rows: [[String: Any]] = []
    var retainedFunction: MTLFunction?
    for index in 0..<8 {
        let k = sameFunction ? 0 : index
        let ft = tick()
        guard let f = retainedFunction ?? lib.makeFunction(name: "cache_case_\(k)") else {fail("missing kernel")}
        if sameFunction { retainedFunction = f }
        let functionMS = ms(ft)
        let pt = tick()
        let p = try d.makeComputePipelineState(function: f)
        let pipelineMS = ms(pt)
        guard let b = d.makeBuffer(length: 16, options: .storageModeShared),
              let c = q.makeCommandBuffer(), let e = c.makeComputeCommandEncoder() else {fail("allocation failed")}
        let a = b.contents().bindMemory(to: Float.self, capacity: 4)
        for i in 0..<4 { a[i] = Float(i+1) }
        e.setComputePipelineState(p); e.setBuffer(b, offset: 0, index: 0)
        e.dispatchThreads(MTLSize(width: 4,height: 1,depth: 1), threadsPerThreadgroup: MTLSize(width: 4,height: 1,depth: 1))
        e.endEncoding()
        let done = DispatchSemaphore(value: 0)
        c.addCompletedHandler { _ in done.signal() }
        c.commit()
        guard done.wait(timeout: .now()+15) == .success, c.status == .completed else {fail("GPU completion failed")}
        for i in 0..<4 { guard a[i] == Float((i+1)*(k+2)+k) else {fail("incorrect output")}}
        rows.append(["iteration":index,"kernel":k,"function_ms":functionMS,"pipeline_ms":pipelineMS,"correct":true])
    }
    let data = try JSONSerialization.data(withJSONObject: ["library_ms":libraryMS,"same_function":sameFunction,"rows":rows], options: [.sortedKeys])
    print("result: " + String(data:data,encoding:.utf8)!)
} catch {fail("library/pipeline failed: \(error)")}
