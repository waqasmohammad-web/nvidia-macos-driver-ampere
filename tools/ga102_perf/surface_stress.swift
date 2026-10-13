// Owned offscreen IOSurface correctness + command scheduling fixture.
// Source-prepared in Cloud; requires Apple compilation and physical qualification.
import IOSurface
@_silgen_name("ga102_graphics_surface_backing") private func surfaceBacking(_ object: UnsafeMutableRawPointer) -> UInt32
@_silgen_name("ga102_graphics_pool_trace") private func poolTracePointer() -> UnsafePointer<CChar>
func poolTrace() -> [String:Any] {
    guard let data=String(cString:poolTracePointer()).data(using:.utf8),
          let value=try? JSONSerialization.jsonObject(with:data) as? [String:Any] else { fail("pool trace") }
    return value
}
final class CommandTimeline {
    let lock=NSLock(); var scheduled: UInt64=0; var completed: UInt64=0
    func mark(_ isComplete: Bool) { lock.lock(); if isComplete { completed=tick() } else { scheduled=tick() }; lock.unlock() }
    func values() -> (UInt64,UInt64) { lock.lock(); defer { lock.unlock() }; return (scheduled,completed) }
}
func observe(_ command: MTLCommandBuffer) -> (CommandTimeline,DispatchSemaphore) {
    let times=CommandTimeline(), done=DispatchSemaphore(value:0)
    command.addScheduledHandler { _ in times.mark(false) }
    command.addCompletedHandler { _ in times.mark(true);done.signal() }
    return (times,done)
}
func finishObserved(_ command: MTLCommandBuffer, _ done: DispatchSemaphore) {
    guard done.wait(timeout:.now()+10) == .success, command.status == .completed, command.error == nil else { fail("surface completion") }
}
let backingMode=ProcessInfo.processInfo.environment["GA102_TEST_SURFACE_BACKING"] ?? "family"
guard backingMode == "private" || backingMode == "family" else { fail("surface backing mode") }
let modes=["queued","alias","alias_read","cross","partial","partial_alias","same","wait","cpu","abandoned","alpha","private"]
let surfaceWidth=640, surfaceHeight=360, surfaceRow=640*4, surfaceBytes=640*360*4
var surfaceRecords=[[String:Any]]()
for mode in modes { for frame in 0..<20 { autoreleasepool {
    let frameStart=tick(), poolBefore=poolTrace()
    let properties:[String:Any]=[kIOSurfaceWidth as String:surfaceWidth,kIOSurfaceHeight as String:surfaceHeight,
        kIOSurfaceBytesPerElement as String:4,kIOSurfaceBytesPerRow as String:surfaceRow,kIOSurfaceAllocSize as String:surfaceBytes,
        kIOSurfacePixelFormat as String:UInt32(0x42475241)]
    guard let surface=IOSurfaceCreate(properties as CFDictionary) else { fail("surface create") }
    guard IOSurfaceLock(surface,[],nil)==0 else { fail("surface lock") }; let base=IOSurfaceGetBaseAddress(surface)
    memset(base,0,IOSurfaceGetAllocSize(surface));guard IOSurfaceUnlock(surface,[],nil)==0 else { fail("surface unlock") }
    let descriptor=MTLTextureDescriptor.texture2DDescriptor(pixelFormat:.bgra8Unorm,width:surfaceWidth,height:surfaceHeight,mipmapped:false)
    descriptor.storageMode = .shared;descriptor.usage = [.renderTarget,.shaderRead]
    guard let texture=(mode == "private" ? device.makeTexture(descriptor:descriptor) : device.makeTexture(descriptor:descriptor,iosurface:surface,plane:0)) else { fail("surface texture") }
    owned(texture)
    let backing=surfaceBacking(Unmanaged.passUnretained(texture as AnyObject).toOpaque())
    let expectedBacking:UInt32=mode == "private" ? 0 : backingMode == "family" ? 2 : 1
    guard backing == expectedBacking else { fail("requested backing not exercised") }
    let pass=MTLRenderPassDescriptor();pass.colorAttachments[0].texture=texture
    pass.colorAttachments[0].loadAction = .clear;pass.colorAttachments[0].storeAction = .store
    // Specify the alpha byte away from a UNORM half-step; require exact 128.
    pass.colorAttachments[0].clearColor=mode == "alpha" ? MTLClearColorMake(0.25,0.5,0.75,128.0/255.0) : MTLClearColorMake(1,0.5,0,1)
    guard let writer=queue.makeCommandBuffer(), let encoder=writer.makeRenderCommandEncoder(descriptor:pass) else { fail("surface clear") }
    owned(writer);owned(encoder);encoder.endEncoding()
    let same=mode == "same", abandoned=mode == "abandoned", cross=mode == "cross"
    let event=cross ? device.makeSharedEvent() : nil
    if cross { guard let event=event else { fail("surface event") };owned(event);writer.encodeSignalEvent(event,value:1) }
    let (writerTimes,writerDone)=observe(writer)
    let writerCommit=tick();if !same && !abandoned { writer.commit() }
    if mode == "wait" || mode == "cpu" { finishObserved(writer,writerDone) }
    var expected:[UInt8]=abandoned ? [0,0,0,0] : mode == "alpha" ? [191,128,64,128] : [0,128,255,255]
    if mode == "cpu" {
        expected=[199,71,23,255]
        guard IOSurfaceLock(surface,[],nil)==0 else { fail("CPU seed lock") };let bytes=IOSurfaceGetBaseAddress(surface)
        let row=IOSurfaceGetBytesPerRow(surface)
        expected.withUnsafeBytes { color in for y in 0..<surfaceHeight { for x in 0..<surfaceWidth { memcpy(bytes+y*row+x*4,color.baseAddress!,4) } } }
        guard IOSurfaceUnlock(surface,[],nil)==0 else { fail("CPU seed unlock") }
    }
    if mode == "alias_read" { descriptor.usage = .shaderRead }
    let alias=mode == "alias" || mode == "alias_read" || mode == "partial_alias"
    guard let readerTexture=(alias ? device.makeTexture(descriptor:descriptor,iosurface:surface,plane:0) : texture) else { fail("alias texture") }
    owned(readerTexture)
    guard surfaceBacking(Unmanaged.passUnretained(readerTexture as AnyObject).toOpaque())==expectedBacking else { fail("alias backing") }
    guard let readback=device.makeBuffer(length:surfaceBytes,options:.storageModeShared),
          let readerQueue=(cross ? device.makeCommandQueue() : queue),
          let reader=(same ? writer : readerQueue.makeCommandBuffer()) else { fail("surface read command") }
    owned(readback);owned(readerQueue);owned(reader)
    if let event=event { reader.encodeWaitForEvent(event,value:1) }
    guard let blit=reader.makeBlitCommandEncoder() else { fail("surface blit") };owned(blit)
    let partial=mode == "partial" || mode == "partial_alias"
    if partial {
        guard let patch=device.makeBuffer(length:1024,options:.storageModeShared) else { fail("patch") };owned(patch)
        let pixels=patch.contents().bindMemory(to:UInt8.self,capacity:1024)
        for i in 0..<256 { pixels[i*4]=255;pixels[i*4+1]=0;pixels[i*4+2]=0;pixels[i*4+3]=255 }
        blit.copy(from:patch,sourceOffset:0,sourceBytesPerRow:64,sourceBytesPerImage:1024,sourceSize:MTLSize(width:16,height:16,depth:1),
                  to:readerTexture,destinationSlice:0,destinationLevel:0,destinationOrigin:MTLOrigin(x:16,y:16,z:0))
    }
    blit.copy(from:readerTexture,sourceSlice:0,sourceLevel:0,sourceOrigin:MTLOrigin(x:0,y:0,z:0),
              sourceSize:MTLSize(width:surfaceWidth,height:surfaceHeight,depth:1),to:readback,destinationOffset:0,
              destinationBytesPerRow:surfaceRow,destinationBytesPerImage:surfaceBytes)
    blit.endEncoding();let encodeEnd=tick(), (readerTimes,readerDone)=observe(reader), readerCommit=tick()
    reader.commit();finishObserved(reader,readerDone)
    if !same && !abandoned && mode != "wait" && mode != "cpu" { finishObserved(writer,writerDone) }
    let pixels=readback.contents().bindMemory(to:UInt8.self,capacity:surfaceBytes)
    var maximumError=0
    for y in 0..<surfaceHeight { for x in 0..<surfaceWidth {
        let want:[UInt8]=partial && x>=16 && x<32 && y>=16 && y<32 ? [255,0,0,255] : expected
        for channel in 0..<4 { let error=abs(Int(pixels[y*surfaceRow+x*4+channel])-Int(want[channel]));maximumError=max(maximumError,error);if error>1 || (channel == 3 && error != 0) { fail("surface pixel \(mode) \(frame) \(x),\(y),\(channel): got \(pixels[y*surfaceRow+x*4+channel]) expected \(want[channel])") } }
    } }
    var cpuError=0,cpuChecked=0
    if mode != "private" {
        guard IOSurfaceLock(surface,.readOnly,nil)==0 else {fail("publication CPU lock")}
        let cpu=IOSurfaceGetBaseAddress(surface).bindMemory(to:UInt8.self,capacity:surfaceBytes),row=IOSurfaceGetBytesPerRow(surface)
        for y in 0..<surfaceHeight {for x in 0..<surfaceWidth {
            let want:[UInt8]=partial && x>=16 && x<32 && y>=16 && y<32 ? [255,0,0,255] : expected
            for channel in 0..<4 {let error=abs(Int(cpu[y*row+x*4+channel])-Int(want[channel]));cpuError=max(cpuError,error);if error>1 || (channel==3 && error != 0) {fail("publication CPU pixel \(mode) \(frame): got \(cpu[y*row+x*4+channel]) expected \(want[channel])")}}
        }}
        guard IOSurfaceUnlock(surface,.readOnly,nil)==0 else {fail("publication CPU unlock")};cpuChecked=surfaceWidth*surfaceHeight
    }
    let (scheduled,completed)=readerTimes.values()
    guard scheduled>=readerCommit && completed>=scheduled else { fail("callback ordering") }
    let (ws,wc)=writerTimes.values()
    surfaceRecords.append(["mode":mode,"frame":frame,"backing":backing,"checked_pixels":surfaceWidth*surfaceHeight,"max_error":maximumError,"cpu_checked_pixels":cpuChecked,"cpu_max_error":cpuError,
        "frame_start_ns":frameStart,"encode_end_ns":encodeEnd,"commit_ns":readerCommit,"scheduled_ns":scheduled,"completed_ns":completed,
        "writer_commit_ns":writerCommit,"writer_scheduled_ns":ws,"writer_completed_ns":wc,
        "writer_gpu_start_s":writer.gpuStartTime,"writer_gpu_end_s":writer.gpuEndTime,"gpu_start_s":reader.gpuStartTime,"gpu_end_s":reader.gpuEndTime,"pool_before":poolBefore,"pool_after":poolTrace(),
        "scope":"offscreen IOSurface; no presentation/scanout" ])
    let sampleData=try! JSONSerialization.data(withJSONObject:surfaceRecords.last!,options:[.sortedKeys]);print("surface_sample: \(String(data:sampleData,encoding:.utf8)!)")
} } }
