// Apple-framework source preparation only until qualified on macOS.
import Foundation
import Metal
import Dispatch
@_silgen_name("ga102_bound_device") private func boundDevice() -> UnsafeMutableRawPointer
@_silgen_name("ga102_graphics_snapshot") private func snapshotPointer() -> UnsafePointer<CChar>
@_silgen_name("ga102_graphics_resources") private func resourcesPointer() -> UnsafePointer<CChar>
@_silgen_name("ga102_graphics_provenance") private func provenancePointer() -> UnsafePointer<CChar>
@_silgen_name("ga102_graphics_check_object") private func checkObjectPointer(_ object: UnsafeMutableRawPointer)
func fail(_ message: String) -> Never { fputs("FAIL: \(message)\n", stderr); exit(1) }
func tick() -> UInt64 { DispatchTime.now().uptimeNanoseconds }
func owned(_ object: AnyObject) { checkObjectPointer(Unmanaged.passUnretained(object).toOpaque()) }
func snapshot() -> [String: Any] {
    guard let bytes=String(cString:snapshotPointer()).data(using:.utf8),
          let object=try? JSONSerialization.jsonObject(with:bytes) as? [String:Any] else { fail("metrics JSON") }
    return object
}
func resources() -> [String: Any] {
    guard let bytes=String(cString:resourcesPointer()).data(using:.utf8),
          let object=try? JSONSerialization.jsonObject(with:bytes) as? [String:Any] else { fail("resources JSON") }
    return object
}
func complete(_ command: MTLCommandBuffer) {
    let done=DispatchSemaphore(value:0)
    command.addCompletedHandler { _ in done.signal() }; command.commit()
    guard done.wait(timeout:.now()+10) == .success, command.status == .completed,
          command.error == nil else { fail("GPU command completion") }
}
guard CommandLine.arguments.count == 2 else { fail("one owned metallib argument required") }
let samplerFirst=ProcessInfo.processInfo.environment["GA102_TEST_SAMPLER_FIRST"] ?? "nearest"
guard samplerFirst == "nearest" || samplerFirst == "linear" else { fail("sampler order") }
let filterOrder=samplerFirst == "nearest" ? [0,1] : [1,0]
let device=Unmanaged<AnyObject>.fromOpaque(boundDevice()).takeRetainedValue() as! any MTLDevice
owned(device)
guard let queue=device.makeCommandQueue() else { fail("queue") }; owned(queue)
let data: Data
do { data=try Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1])) } catch { fail("metallib read") }
var records=[[String:Any]]()
let beforeLibrary=snapshot(), libraryStart=tick()
let library: MTLLibrary
let libraryData=data.withUnsafeBytes { DispatchData(bytes:$0) }
do { library=try device.makeLibrary(data:libraryData) } catch { fail("owned metallib load: \(error)") }
owned(library)
guard let vertex=library.makeFunction(name:"ga102_runtime_vertex"),
      let fragment=library.makeFunction(name:"ga102_runtime_fragment") else { fail("owned functions") }
owned(vertex); owned(fragment)
records.append(["label":"library","wall_ns":tick()-libraryStart,"before":beforeLibrary,"after":snapshot()])
func makePipeline(_ label: String) -> MTLRenderPipelineState {
    let d=MTLRenderPipelineDescriptor(); d.vertexFunction=vertex; d.fragmentFunction=fragment
    d.colorAttachments[0].pixelFormat = .rgba8Unorm
    let before=snapshot(), start=tick()
    let p: MTLRenderPipelineState
    do { p=try device.makeRenderPipelineState(descriptor:d) } catch { fail("render pipeline: \(error)") }
    owned(p)
    records.append(["label":label,"wall_ns":tick()-start,"before":before,"after":snapshot()])
    return p
}
let pipeline=makePipeline("pipeline-initial")
var samplers=[MTLSamplerState]()
for filter in [MTLSamplerMinMagFilter.nearest, .linear] {
    let d=MTLSamplerDescriptor(); d.minFilter=filter; d.magFilter=filter; d.mipFilter = .notMipmapped
    d.normalizedCoordinates=false; d.sAddressMode = .clampToEdge; d.tAddressMode = .clampToEdge; d.rAddressMode = .clampToEdge
    d.maxAnisotropy=1; d.lodMinClamp=0; d.lodMaxClamp=65504
    guard let s=device.makeSamplerState(descriptor:d) else { fail("sampler") }; owned(s); samplers.append(s)
}
let inputDescriptor=MTLTextureDescriptor.texture2DDescriptor(pixelFormat:.rgba8Unorm,width:8,height:8,mipmapped:false)
inputDescriptor.storageMode = .shared; inputDescriptor.usage = .shaderRead
let outputDescriptor=MTLTextureDescriptor.texture2DDescriptor(pixelFormat:.rgba8Unorm,width:32,height:32,mipmapped:false)
outputDescriptor.storageMode = .private; outputDescriptor.usage = [.renderTarget]
guard let input=device.makeTexture(descriptor:inputDescriptor), let target=device.makeTexture(descriptor:outputDescriptor),
      let readback=device.makeBuffer(length:256*32,options:.storageModeShared) else { fail("texture/readback") }
owned(input); owned(target); owned(readback)
var gradient=[UInt8]()
for y in 0..<8 { for x in 0..<8 { gradient += [UInt8(32*x),UInt8(32*y),UInt8(16*(x+y)),255] } }
gradient.withUnsafeBytes { input.replace(region:MTLRegionMake2D(0,0,8,8),mipmapLevel:0,withBytes:$0.baseAddress!,bytesPerRow:32) }
func draw(_ p: MTLRenderPipelineState, _ filter: Int, _ label: String) {
    guard let c=queue.makeCommandBuffer() else { fail("command") }; owned(c)
    let pass=MTLRenderPassDescriptor(); pass.colorAttachments[0].texture=target
    pass.colorAttachments[0].loadAction = .clear; pass.colorAttachments[0].storeAction = .store
    let before=snapshot(), start=tick()
    guard let e=c.makeRenderCommandEncoder(descriptor:pass) else { fail("encoder") }; owned(e)
    e.setRenderPipelineState(p); e.setFragmentTexture(input,index:0); e.setFragmentSamplerState(samplers[filter],index:3)
    e.drawPrimitives(type:.triangle,vertexStart:0,vertexCount:3); e.endEncoding()
    let encodeNS=tick()-start, afterEncode=snapshot(), submitStart=tick()
    complete(c); let completionNS=tick()-submitStart
    // Separate GPU blit/readback from render completion and compilation timing.
    let readStart=tick()
    guard let copy=queue.makeCommandBuffer(), let blit=copy.makeBlitCommandEncoder() else { fail("readback command") }
    owned(copy); owned(blit)
    blit.copy(from:target,sourceSlice:0,sourceLevel:0,sourceOrigin:MTLOrigin(x:0,y:0,z:0),
        sourceSize:MTLSize(width:32,height:32,depth:1),to:readback,destinationOffset:0,destinationBytesPerRow:256,destinationBytesPerImage:8192)
    blit.endEncoding(); complete(copy)
    let readNS=tick()-readStart, expected=filter == 0 ? [64,96,80,255] : [56,104,80,255]
    let bytes=readback.contents().bindMemory(to:UInt8.self,capacity:8192)
    var maximumError=0
    for y in 0..<32 { for x in 0..<32 { for channel in 0..<4 {
        let error=abs(Int(bytes[y*256+x*4+channel])-expected[channel]); maximumError=max(maximumError,error)
        if error > 2 { fail("\(label) pixel \(x),\(y),\(channel) mismatch") }
    } } }
    var record:[String:Any]=["label":label,"filter":filter,"encode_ns":encodeNS,"completion_ns":completionNS,
        "readback_ns":readNS,"before":before,"after":afterEncode,"checked_pixels":1024,"max_error":maximumError,
        "center_rgba":(0..<4).map { Int(bytes[16*256+16*4+$0]) }]
    if c.gpuStartTime > 0 && c.gpuEndTime >= c.gpuStartTime { record["gpu_ns"]=(c.gpuEndTime-c.gpuStartTime)*1e9 }
    records.append(record)
}
for filter in filterOrder {
    let name=filter == 0 ? "nearest" : "linear"
    draw(pipeline,filter,name+"-miss"); draw(pipeline,filter,name+"-local-hit")
}
let equivalent=makePipeline("pipeline-equivalent")
for filter in filterOrder { draw(equivalent,filter,(filter == 0 ? "nearest" : "linear")+"-device-hit") }
guard let provenanceData=String(cString:provenancePointer()).data(using:.utf8),
      let provenance=try? JSONSerialization.jsonObject(with:provenanceData) else { fail("provenance") }
let result:[String:Any]=["schema_version":2,"sampler_first":samplerFirst,"records":records,"provenance":provenance,"final_metrics":snapshot(),"resources":resources(),
    "scope":"owned runtime-sampler graphics; no desktop or scanout claim"]
do {
    let encoded=try JSONSerialization.data(withJSONObject:result,options:[.sortedKeys])
    print("result: "+String(data:encoded,encoding:.utf8)!)
} catch { fail("result JSON") }
