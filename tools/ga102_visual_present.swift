// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Owned-window GPU readback and optional window-only capture. Never requests TCC access.
import AppKit
import Metal
import QuartzCore
import ScreenCaptureKit
import CoreGraphics
import Dispatch
let negative=CommandLine.arguments.dropFirst().first ?? "none"
func fail(_ s:String)->Never {fputs("FAIL: \(s)\n",stderr);exit(1)}
guard let device=MTLCopyAllDevices().first(where:{$0.name.contains("3080 Ti")}),let queue=device.makeCommandQueue() else {fail("target device")}
let app=NSApplication.shared;app.setActivationPolicy(.accessory)
let width=640,height=360,frames=12
let window=NSWindow(contentRect:NSRect(x:0,y:0,width:width,height:height),styleMask:.borderless,backing:.buffered,defer:false)
window.isReleasedWhenClosed=false
let view=NSView(frame:NSRect(x:0,y:0,width:width,height:height));view.wantsLayer=true
let layer=CAMetalLayer();layer.device=device;layer.pixelFormat = .bgra8Unorm;layer.framebufferOnly=false
// Define the expected rendered color space; nil bypasses layer color matching.
layer.colorspace=CGColorSpace(name:CGColorSpace.sRGB)
layer.drawableSize=CGSize(width:width,height:height);layer.displaySyncEnabled=true;layer.allowsNextDrawableTimeout=true
view.layer=layer;window.contentView=view;window.center()
if negative != "hidden" {window.orderFront(nil)}
let source="""
#include <metal_stdlib>
using namespace metal;
vertex float4 visual_v(uint i [[vertex_id]]) {return float4(i==0?float2(-1,-1):(i==1?float2(3,-1):float2(-1,3)),0,1);}
fragment float4 visual_f(float4 p [[position]], constant uint &id [[buffer(0)]]) {
    uint x=uint(p.x),y=uint(p.y);
    if(y<40 || y>=320) { uint bit=min(x/80,7u);return ((id>>bit)&1u)?float4(1):float4(0,0,0,1); }
    uint bar=(id%8)*80;
    if(x>=bar && x<bar+40) return float4(1);
    return id%3==0?float4(1,0,0,1):(id%3==1?float4(0,1,0,1):float4(0,0,1,1));
}
"""
let pipeline:MTLRenderPipelineState
do {
    let lib=try device.makeLibrary(source:source,options:nil),d=MTLRenderPipelineDescriptor()
    d.vertexFunction=lib.makeFunction(name:"visual_v");d.fragmentFunction=lib.makeFunction(name:"visual_f");d.colorAttachments[0].pixelFormat = .bgra8Unorm
    pipeline=try device.makeRenderPipelineState(descriptor:d)
}catch{fail("pipeline: \(error)")}
guard let readback=device.makeBuffer(length:width*height*4,options:.storageModeShared) else {fail("readback")}
func expected(_ id:Int,_ x:Int,_ y:Int)->[Int] {
    if y<40 || y>=320 {return ((id>>(x/80))&1)==1 ? [255,255,255]:[0,0,0]}
    if x>=(id%8)*80 && x<(id%8)*80+40{return [255,255,255]}
    return id%3==0 ? [255,0,0]:(id%3==1 ? [0,255,0]:[0,0,255])
}
func checks(_ id:Int)->[(Int,Int)] {
    var points=[(Int,Int)]()
    for i in 0..<8 {let x=i*80;points.append((x+20,20));points.append((x+20,180));points.append((x+60,180))}
    return points
}
func visible()->Bool {
    let display=(window.screen?.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber)?.uint32Value ?? CGMainDisplayID()
    let session=CGSessionCopyCurrentDictionary() as? [String:Any]
    return window.isVisible && window.isOnActiveSpace && window.occlusionState.contains(.visible) && CGDisplayIsAsleep(display)==0 && CGDisplayIsActive(display) != 0 && (session?[kCGSessionOnConsoleKey as String] as? Bool)==true
}
let lock=NSLock();var times=[Int:Double]()
func timeSnapshot()->[Int:Double] {lock.lock();defer{lock.unlock()};return times}
func complete(_ commands:MTLCommandBuffer) async {
    await withCheckedContinuation { (continuation:CheckedContinuation<Void,Never>) in
        commands.addCompletedHandler {_ in continuation.resume()};commands.commit()
    }
}
var gpuCorrect=0,captureCorrect=0,captureAttempted=0,captureReceived=0,visibleFrames=0
var distinct=Set<String>(),captureDistinct=Set<String>()
let captureIPC = ProcessInfo.processInfo.environment["GA102_CAPTURE_IPC"].map { URL(fileURLWithPath:$0,isDirectory:true) }
let captureAllowed = captureIPC != nil ? ProcessInfo.processInfo.environment["GA102_CAPTURE_PERMISSION"] == "1" : CGPreflightScreenCaptureAccess()
var captureState=captureAllowed ? "available":"NOT VERIFIED: screen-capture permission unavailable; not requested"
var captureBrokerStopped=false
Task { @MainActor in
    var filter:SCContentFilter?
    if captureIPC == nil && captureAllowed && negative != "hidden" {
        do {
            let shared=try await SCShareableContent.excludingDesktopWindows(true,onScreenWindowsOnly:true)
            if let own=shared.windows.first(where:{$0.windowID==UInt32(window.windowNumber) && $0.owningApplication?.processID==getpid()}) {
                filter=SCContentFilter(desktopIndependentWindow:own)
            } else {captureState="NOT VERIFIED: own on-screen window unavailable"}
        }catch{captureState="NOT VERIFIED: own-window capture API unavailable"}
    }
    for id in 0..<frames {
        guard let drawable=layer.nextDrawable(),let commands=queue.makeCommandBuffer() else{fail("drawable/command unavailable")}
        let pass=MTLRenderPassDescriptor();pass.colorAttachments[0].texture=drawable.texture
        pass.colorAttachments[0].loadAction = .clear;pass.colorAttachments[0].storeAction = .store
        guard let e=commands.makeRenderCommandEncoder(descriptor:pass) else{fail("encoder")}
        e.setRenderPipelineState(pipeline);var rendered=UInt32(negative=="static" ? 0:id)
        e.setFragmentBytes(&rendered,length:4,index:0);e.drawPrimitives(type:.triangle,vertexStart:0,vertexCount:3);e.endEncoding()
        guard let b=commands.makeBlitCommandEncoder() else{fail("blit")}
        b.copy(from:drawable.texture,sourceSlice:0,sourceLevel:0,sourceOrigin:MTLOrigin(x:0,y:0,z:0),sourceSize:MTLSize(width:width,height:height,depth:1),to:readback,destinationOffset:0,destinationBytesPerRow:width*4,destinationBytesPerImage:width*height*4);b.endEncoding()
        drawable.addPresentedHandler {d in lock.lock();times[id]=negative=="timestamps" ? 0:d.presentedTime;lock.unlock()}
        commands.present(drawable);await complete(commands)
        guard commands.status == .completed else{fail("GPU completion")}
        let bytes=readback.contents().assumingMemoryBound(to:UInt8.self)
        var signature="",good=true
        for (x,y) in checks(id) {
            let offset=(y*width+x)*4,exp=expected(id,x,y)
            let rgb=[Int(bytes[offset+2]),Int(bytes[offset+1]),Int(bytes[offset])]
            signature += rgb.map{String($0)}.joined(separator:",")+";"
            if zip(rgb,exp).contains(where:{abs($0-$1)>2}){good=false}
        }
        if good{gpuCorrect+=1};distinct.insert(signature)
        // Keep each pattern stable for capture; this is visual correctness, not a 60 Hz pacing test.
        try? await Task.sleep(nanoseconds:300_000_000)
        if visible(){visibleFrames+=1}
        if let root=captureIPC, captureAllowed && !captureBrokerStopped {
            captureAttempted+=1
            let request:[String:Any] = ["frame":id,"window_id":window.windowNumber,"pid":getpid()]
            let data=try! JSONSerialization.data(withJSONObject:request)
            try! data.write(to:root.appendingPathComponent("request.json"),options:.atomic)
            let response=root.appendingPathComponent("response-\(id).json")
            let deadline=Date().addingTimeInterval(6)
            while !FileManager.default.fileExists(atPath:response.path) && Date()<deadline {
                try? await Task.sleep(nanoseconds:10_000_000)
            }
            if let data=try? Data(contentsOf:response),let value=(try? JSONSerialization.jsonObject(with:data)) as? [String:Any] {
                if value["received"] as? Bool == true {captureReceived+=1}
                if value["correct"] as? Bool == true {captureCorrect+=1}
                // The broker retains signatures, never images. Count arrives independently of GPU readback.
                if let count=value["distinct_patterns"] as? Int {for n in 0..<count {captureDistinct.insert(String(n))}}
                if value["received"] as? Bool != true {captureState="NOT VERIFIED: own-window broker capture unavailable"}
            }else{captureState="NOT VERIFIED: own-window broker deadline";captureBrokerStopped=true}
        }
        if let f=filter {
            captureAttempted+=1
            let cfg=SCStreamConfiguration();cfg.width=width;cfg.height=height;cfg.showsCursor=false;cfg.ignoreShadowsSingleWindow=true
            cfg.colorSpaceName=CGColorSpace.sRGB
            do {
                let image=try await SCScreenshotManager.captureImage(contentFilter:f,configuration:cfg)
                captureReceived+=1
                var rgba=[UInt8](repeating:0,count:width*height*4)
                let matched=rgba.withUnsafeMutableBytes {raw -> Bool in
                    guard let c=CGContext(data:raw.baseAddress,width:width,height:height,bitsPerComponent:8,bytesPerRow:width*4,space:CGColorSpace(name:CGColorSpace.sRGB)!,bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue|CGBitmapInfo.byteOrder32Big.rawValue) else{return false}
                    c.draw(image,in:CGRect(x:0,y:0,width:width,height:height))
                    let pixels=raw.bindMemory(to:UInt8.self)
                    var sig="",ok=true
                    for (x,y) in checks(id) {
                        let offset=(y*width+x)*4,exp=expected(id,x,y),rgb=[Int(pixels[offset]),Int(pixels[offset+1]),Int(pixels[offset+2])]
                        sig+=rgb.map{String($0)}.joined(separator:",")+";"
                        if zip(rgb,exp).contains(where:{abs($0-$1)>40}){ok=false}
                    };captureDistinct.insert(sig);return ok
                }
                if matched{captureCorrect+=1}
            }catch{captureState="NOT VERIFIED: window capture failed";filter=nil}
        }
    }
    let observed=timeSnapshot();let positive=observed.values.filter{$0>0}.count;let zeroIDs=observed.filter{$0.value<=0}.keys.sorted()
    let ordered=observed.sorted{$0.key<$1.key}.map{$0.value}.filter{$0>0}
    let increasing=zip(ordered.dropFirst(),ordered).allSatisfy{$0>$1}
    let result:[String:Any]=["probe":"visual","frames":frames,"negative_control":negative,"gpu_correct_frames":gpuCorrect,"gpu_distinct_patterns":distinct.count,
        "capture_method":captureIPC != nil ? "ScreenCaptureKit owned-window broker":"ScreenCaptureKit in probe",
        "positive_timestamps":positive,"timestamps_increasing":increasing,"distinct_timestamps":Set(ordered).count,"zero_timestamp_ids":zeroIDs,"visible_frames":visibleFrames,
        "capture_permission":captureAllowed,"capture_state":captureState,"capture_attempted":captureAttempted,"capture_received_frames":captureReceived,"capture_correct_frames":captureCorrect,"capture_distinct_patterns":captureDistinct.count,
        "physical_scanout":"NOT VERIFIED"]
    let json=try! JSONSerialization.data(withJSONObject:result,options:.sortedKeys);print("result: \(String(data:json,encoding:.utf8)!)")
    window.orderOut(nil);window.close();fflush(stdout);exit(0)
}
app.run()
