// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Two unprivileged processes, one synthetic global test IOSurface, bounded handoffs.
// ID sharing is legacy test transport; production sharing should transfer a Mach/XPC right.
import Foundation
import Metal
import IOSurface
import Dispatch
func fail(_ s: String) -> Never { fputs("FAIL: \(s)\n", stderr); exit(1) }
func complete(_ c: MTLCommandBuffer) {
    let done = DispatchSemaphore(value: 0); c.addCompletedHandler { _ in done.signal() }; c.commit()
    guard done.wait(timeout: .now()+5) == .success, c.status == .completed else { fail("GPU completion") }
}
func waitFile(_ file: URL) {
    let end = Date().addingTimeInterval(8)
    while !FileManager.default.fileExists(atPath: file.path) {
        if Date() > end { fail("handoff deadline") }; Thread.sleep(forTimeInterval: 0.005)
    }
}
func publish(_ file: URL) { do { try Data([1]).write(to: file, options: .atomic) } catch { fail("handoff write") } }
let worker = CommandLine.arguments.count == 4 && CommandLine.arguments[1] == "--worker"
guard let device = MTLCopyAllDevices().first(where: { $0.name.contains("3080 Ti") }),
      let queue = device.makeCommandQueue() else { fail("RTX 3080 Ti unavailable") }
let width = 64, height = 64, frames = 8
let root: URL, surface: IOSurfaceRef
if worker {
    root = URL(fileURLWithPath: CommandLine.arguments[3], isDirectory: true)
    guard let id = UInt32(CommandLine.arguments[2]), let s = IOSurfaceLookup(id) else { fail("cross-process IOSurface lookup unavailable") }
    surface = s
} else {
    root = FileManager.default.temporaryDirectory.appendingPathComponent("ga102-surface-"+UUID().uuidString, isDirectory: true)
    do { try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700]) } catch { fail("private scratch") }
    let row = IOSurfaceAlignProperty(kIOSurfaceBytesPerRow,width*4)
    guard let s = IOSurfaceCreate([kIOSurfaceWidth:width,kIOSurfaceHeight:height,
        kIOSurfaceBytesPerRow:row,kIOSurfaceBytesPerElement:4,
        kIOSurfaceAllocSize:IOSurfaceAlignProperty(kIOSurfaceAllocSize,row*height),
        kIOSurfacePixelFormat:UInt32(0x42475241),kIOSurfaceIsGlobal:true] as CFDictionary) else { fail("surface allocation") }
    surface = s
}
let d = MTLTextureDescriptor.texture2DDescriptor(pixelFormat:.bgra8Unorm,width:width,height:height,mipmapped:false)
d.storageMode = .shared; d.usage = [.renderTarget,.shaderRead]
guard let texture = device.makeTexture(descriptor:d,iosurface:surface,plane:0),
      let buffer = device.makeBuffer(length:width*height*4,options:.storageModeShared) else { fail("surface import/readback buffer") }
func color(_ frame: Int, _ response: Bool) -> [UInt8] {
    let red = UInt8(20+frame*20)
    return response ? [73,151,255-red,255] : [191,127,red,255]
}
func gpuWrite(_ bytes: [UInt8]) {
    guard let c = queue.makeCommandBuffer() else { fail("write command") }
    let p = MTLRenderPassDescriptor(); let a = p.colorAttachments[0]!
    a.texture=texture; a.loadAction = .clear; a.storeAction = .store
    a.clearColor = MTLClearColorMake(Double(bytes[2])/255,Double(bytes[1])/255,Double(bytes[0])/255,1)
    guard let e = c.makeRenderCommandEncoder(descriptor:p) else { fail("write encoder") }; e.endEncoding(); complete(c)
}
func check(_ expected: [UInt8], _ label: String) {
    guard let c = queue.makeCommandBuffer(), let e = c.makeBlitCommandEncoder() else { fail("read encoder") }
    e.copy(from:texture,sourceSlice:0,sourceLevel:0,sourceOrigin:MTLOrigin(x:0,y:0,z:0),
           sourceSize:MTLSize(width:width,height:height,depth:1),to:buffer,destinationOffset:0,
           destinationBytesPerRow:width*4,destinationBytesPerImage:width*height*4)
    e.endEncoding(); complete(c)
    let p = buffer.contents().bindMemory(to:UInt8.self,capacity:width*height*4)
    for i in 0..<(width*height*4) {
        if abs(Int(p[i])-Int(expected[i%4])) > 1 { fail("\(label) byte \(i): \(p[i]) expected \(expected[i%4])") }
    }
}
if worker {
    publish(root.appendingPathComponent("ready"))
    for frame in 0..<frames {
        waitFile(root.appendingPathComponent("send-\(frame)"))
        check(color(frame,false),"consumer frame \(frame)")
        gpuWrite(color(frame,true))
        publish(root.appendingPathComponent("ack-\(frame)"))
    }
    exit(0)
}
let process = Process(); process.executableURL = URL(fileURLWithPath:CommandLine.arguments[0])
process.arguments = ["--worker",String(IOSurfaceGetID(surface)),root.path]
let childLog = root.appendingPathComponent("worker.log")
FileManager.default.createFile(atPath:childLog.path,contents:nil)
let output = try! FileHandle(forWritingTo:childLog); process.standardOutput=output; process.standardError=output
try! process.run()
waitFile(root.appendingPathComponent("ready"))
var wall = [Double]()
for frame in 0..<frames {
    let t = DispatchTime.now().uptimeNanoseconds
    let bytes = color(frame,false)
    if frame % 2 == 0 {
        guard IOSurfaceLock(surface,[],nil) == kIOReturnSuccess else { fail("CPU writer lock") }
        let base = IOSurfaceGetBaseAddress(surface)
        let row = IOSurfaceGetBytesPerRow(surface); let p = base.assumingMemoryBound(to:UInt8.self)
        for y in 0..<height { for x in 0..<width { for ch in 0..<4 { p[y*row+x*4+ch]=bytes[ch] } } }
        guard IOSurfaceUnlock(surface,[],nil) == kIOReturnSuccess else { fail("CPU writer unlock") }
    } else { gpuWrite(bytes) }
    publish(root.appendingPathComponent("send-\(frame)")); waitFile(root.appendingPathComponent("ack-\(frame)"))
    check(color(frame,true),"producer response \(frame)")
    wall.append(Double(DispatchTime.now().uptimeNanoseconds-t)/1e6)
}
process.waitUntilExit(); output.closeFile()
guard process.terminationStatus == 0 else { fail("consumer exit \(process.terminationStatus); details in private scratch") }
let result: [String:Any] = ["frames":frames,"processes":2,"cpu_producer_frames":4,"gpu_producer_frames":4,
    "checked_bytes":frames*width*height*4*2,"roundtrip_ms_in_order":wall,"output":"PASS"]
let json = try! JSONSerialization.data(withJSONObject:result,options:.sortedKeys)
print("result: \(String(data:json,encoding:.utf8)!)")
print("PASS: cross-process persistent IOSurface CPU/GPU writes and GPU roundtrip readbacks; serialized handoffs, not unsynchronized concurrent access")
