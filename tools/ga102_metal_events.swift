// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Two queues, consumer-first waits and changing shared-event values; bounded.
import Foundation
import Metal
import Dispatch
func fail(_ s: String) -> Never { fputs("FAIL: \(s)\n",stderr); exit(1) }
guard let d = MTLCopyAllDevices().first(where:{$0.name.contains("3080 Ti")}),
      let producer = d.makeCommandQueue(), let consumer = d.makeCommandQueue(),
      let event = d.makeSharedEvent(),
      let input = d.makeBuffer(length:4096,options:.storageModePrivate),
      let output = d.makeBuffer(length:4096,options:.storageModeShared) else { fail("queues/shared event/resources") }
var timings = [Double]()
for frame in 1...16 {
    guard let a = producer.makeCommandBuffer(), let b = consumer.makeCommandBuffer(),
          let fill = a.makeBlitCommandEncoder() else { fail("producer allocation") }
    fill.fill(buffer:input,range:0..<4096,value:UInt8(frame*11)); fill.endEncoding()
    a.encodeSignalEvent(event,value:UInt64(frame))
    b.encodeWaitForEvent(event,value:UInt64(frame))
    guard let copy = b.makeBlitCommandEncoder() else { fail("consumer allocation") }
    copy.copy(from:input,sourceOffset:0,to:output,destinationOffset:0,size:4096); copy.endEncoding()
    let done = DispatchSemaphore(value:0)
    b.addCompletedHandler {_ in done.signal()}
    let t = DispatchTime.now().uptimeNanoseconds
    // Half deliberately commit the blocked consumer before its producer.
    if frame%2 == 0 { b.commit(); a.commit() } else { a.commit(); b.commit() }
    guard done.wait(timeout:.now()+5) == .success else { fail("cross-queue wait stalled at frame \(frame)") }
    a.waitUntilCompleted()
    guard a.status == .completed, b.status == .completed else { fail("command error") }
    timings.append(Double(DispatchTime.now().uptimeNanoseconds-t)/1e6)
    let bytes = output.contents().assumingMemoryBound(to:UInt8.self)
    for i in 0..<4096 { if bytes[i] != UInt8(frame*11) { fail("frame \(frame) stale byte \(i)") } }
    guard event.signaledValue >= UInt64(frame) else { fail("event completion value") }
}
let result:[String:Any] = ["iterations":16,"consumer_first_iterations":8,"checked_bytes":65536,
    "commit_to_consumer_completion_ms_in_order":timings,"output":"PASS"]
let json = try! JSONSerialization.data(withJSONObject:result,options:.sortedKeys)
print("result: \(String(data:json,encoding:.utf8)!)")
print("PASS: two-queue shared-event ordering; consumer-first commits completed with fresh data")
