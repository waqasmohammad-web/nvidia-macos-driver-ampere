// CPU IOSurface import exercises the whole-image synchronous upload staging path.
import IOSurface
@_silgen_name("ga102_graphics_surface_backing") private func uploadBacking(_ object:UnsafeMutableRawPointer)->UInt32
func uploadTrial(_ width:Int,_ height:Int,_ value:UInt8,_ workQueue:MTLCommandQueue)->[String:Any] {
 let row=width*4, count=row*height,sourceRow=width*4+256,sourceBytes=(width*4+256)*height,start=tick()
 guard let readback=device.makeBuffer(length:count,options:.storageModeShared),let command=workQueue.makeCommandBuffer() else {fail("upload readback")}
 owned(readback);owned(command)
 autoreleasepool {
  let props:[String:Any]=[kIOSurfaceWidth as String:width,kIOSurfaceHeight as String:height,kIOSurfaceBytesPerElement as String:4,kIOSurfaceBytesPerRow as String:sourceRow,kIOSurfaceAllocSize as String:sourceBytes,kIOSurfacePixelFormat as String:UInt32(0x42475241)]
  guard let surface=IOSurfaceCreate(props as CFDictionary),IOSurfaceLock(surface,[],nil)==0 else {fail("upload surface")};let base=IOSurfaceGetBaseAddress(surface)
  memset(base,238,sourceBytes);for y in 0..<height {memset(base+y*sourceRow,Int32(value),row)};guard IOSurfaceUnlock(surface,[],nil)==0 else {fail("upload unlock")}
  let descriptor=MTLTextureDescriptor.texture2DDescriptor(pixelFormat:.bgra8Unorm,width:width,height:height,mipmapped:false)
  descriptor.storageMode = .shared;descriptor.usage = [.shaderRead,.renderTarget]
  guard let texture=device.makeTexture(descriptor:descriptor,iosurface:surface,plane:0),let blit=command.makeBlitCommandEncoder() else {fail("upload encode")}
  owned(texture);owned(blit)
  guard uploadBacking(Unmanaged.passUnretained(texture as AnyObject).toOpaque())==2 else {fail("upload family backing")}
  blit.copy(from:texture,sourceSlice:0,sourceLevel:0,sourceOrigin:MTLOrigin(x:0,y:0,z:0),sourceSize:MTLSize(width:width,height:height,depth:1),to:readback,destinationOffset:0,destinationBytesPerRow:row,destinationBytesPerImage:count)
  blit.endEncoding()
 } // Application's surface/texture references disappear before commit.
 let encodeNS=tick()-start,submitted=tick();complete(command)
 let data=readback.contents().bindMemory(to:UInt8.self,capacity:count)
 for i in 0..<count {if data[i] != value {fail("upload lifetime bytes")}}
 return ["width":width,"height":height,"source_row_bytes":sourceRow,"bytes_verified":count,"encode_ns":encodeNS,"completion_ns":tick()-submitted]
}
let uploadLock=NSLock(),group=DispatchGroup()
var uploadRecords=[[String:Any]]()
for worker in 0..<4 {
 group.enter();DispatchQueue.global().async {
  autoreleasepool {
   guard let workQueue=device.makeCommandQueue() else {fail("upload worker queue")};owned(workQueue)
   for trial in 0..<8 {autoreleasepool {
    var row=uploadTrial([64,128,256,512][(worker+trial)%4],128,UInt8(worker*8+trial+1),workQueue);row["worker"]=worker;row["trial"]=trial
    uploadLock.lock();uploadRecords.append(row);uploadLock.unlock()
   }}
  };group.leave()
 }
}
guard group.wait(timeout:.now()+60) == .success else {fail("upload workers timeout")}
// Above the 32 MiB retention cap, then a small import; check every byte.
let largeUpload=uploadTrial(4096,2049,219,queue),smallAfterLarge=uploadTrial(256,128,117,queue)
uploadRecords.append(["large":largeUpload,"small_after_large":smallAfterLarge])
