// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Six-second timing probe; full visual checks are in ga102_visual_present.swift.
// Existing display mode; no graphics settings.
import AppKit
import QuartzCore
import Metal
import Dispatch
import CoreGraphics
import Darwin
import IOSurface
func fail(_ text: String) -> Never { fputs("FAIL: \(text)\n", stderr); exit(1) }
func stats(_ samples: [Double]) -> [String: Double] {
    let s = samples.sorted()
    guard !s.isEmpty else { return [:] }
    return ["p50_ms": s[(s.count - 1) / 2] * 1000,
            "p99_ms": s[min(s.count - 1, Int(ceil(Double(s.count) * 0.99)) - 1)] * 1000,
            "p95_ms": s[min(s.count - 1, Int(ceil(Double(s.count) * 0.95)) - 1)] * 1000,
            "max_ms": s.last! * 1000, "samples": Double(s.count)]
}
// Render resolution and composition load are independent of the window/display mode.
func argument(_ name:String)->String? {
    guard let index=CommandLine.arguments.firstIndex(of:name) else {return nil}
    guard index+1<CommandLine.arguments.count else {fail("missing \(name)")}
    return CommandLine.arguments[index+1]
}
let renderParts=(argument("--render-size") ?? "640x360").split(separator:"x")
guard renderParts.count==2,let renderWidth=Int(renderParts[0]),let renderHeight=Int(renderParts[1]),
      (64...3840).contains(renderWidth),(64...2160).contains(renderHeight),
      let compositeLayers=Int(argument("--composite-layers") ?? "0"),(0...16).contains(compositeLayers) else {fail("render workload parameters")}
let compositionSource="""
#include <metal_stdlib>
using namespace metal;
vertex float4 endgame_v(uint i [[vertex_id]]) {return float4(i==0?float2(-1,-1):(i==1?float2(3,-1):float2(-1,3)),0,1);}
fragment float4 endgame_f(constant float4 &color [[buffer(0)]]) {return color;}
"""
guard let device = MTLCopyAllDevices().first(where: { $0.name.contains("3080 Ti") }),
      let queue = device.makeCommandQueue() else { fail("RTX 3080 Ti / queue unavailable") }
print("device: \(device.name)"); fflush(stdout)
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 640, height: 360),
                      styleMask: [.titled], backing: .buffered, defer: false)
window.title = "GA102 bounded presentation probe (6 seconds)"
window.isReleasedWhenClosed = false
let view = NSView(frame: NSRect(x: 0, y: 0, width: 640, height: 360))
let layer = CAMetalLayer()
layer.device = device; layer.pixelFormat = .bgra8Unorm
layer.framebufferOnly = true; layer.displaySyncEnabled = true
let drawableCount=CommandLine.arguments.contains("--double-buffered") ? 2:3
layer.maximumDrawableCount = drawableCount; layer.allowsNextDrawableTimeout = true
layer.drawableSize = CGSize(width: renderWidth, height: renderHeight)
view.wantsLayer = true; view.layer = layer
window.contentView = view; window.center(); window.orderFront(nil)

var compositionPipeline: MTLRenderPipelineState?
if compositeLayers>0 {
    do {
        let library=try device.makeLibrary(source:compositionSource,options:nil)
        let descriptor=MTLRenderPipelineDescriptor()
        descriptor.vertexFunction=library.makeFunction(name:"endgame_v")
        descriptor.fragmentFunction=library.makeFunction(name:"endgame_f")
        descriptor.colorAttachments[0].pixelFormat = .bgra8Unorm
        descriptor.colorAttachments[0].isBlendingEnabled=true
        descriptor.colorAttachments[0].sourceRGBBlendFactor = .sourceAlpha
        descriptor.colorAttachments[0].destinationRGBBlendFactor = .oneMinusSourceAlpha
        descriptor.colorAttachments[0].sourceAlphaBlendFactor = .one
        descriptor.colorAttachments[0].destinationAlphaBlendFactor = .oneMinusSourceAlpha
        compositionPipeline=try device.makeRenderPipelineState(descriptor:descriptor)
    } catch {fail("composition pipeline: \(error)")}
}
let lock = NSLock()
var inFlight = 0, completed = 0, errors = 0, skipped = 0, attempted = 0
var presented = [Int: Double](), acquisition = [Double](), gpu = [Double]()
var drawStarts = [Double]()
var encoding = [Double](), commitReturn = [Double](), scheduledLatency = [Double](), completionLatency = [Double]()
var visibility = [[String: Any]]()
let traceStart=CACurrentMediaTime()
var frameTrace=[Int:[String:Double]]()
var surfaceSlots=[UInt32:Int]()
func flipCount()->Double? {
    var value:Int64=0;var size=MemoryLayout<Int64>.size
    return sysctlbyname("debug.nvrmfb_flip_n",&value,&size,nil,0)==0 && size==MemoryLayout<Int64>.size ? Double(value):nil
}
func snapshot() -> [String: Any] {
    let session = CGSessionCopyCurrentDictionary() as? [String: Any]
    let display = (window.screen?.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber)?.uint32Value ?? CGMainDisplayID()
    let own = (CGWindowListCopyWindowInfo(.optionOnScreenOnly, kCGNullWindowID) as? [[String: Any]])?.contains {
        ($0[kCGWindowOwnerPID as String] as? NSNumber)?.int32Value == getpid() &&
        ($0[kCGWindowNumber as String] as? NSNumber)?.intValue == window.windowNumber
    }
    return ["window_visible": window.isVisible, "window_on_active_space": window.isOnActiveSpace,
            "window_unoccluded": window.occlusionState.contains(.visible),
            "window_in_onscreen_list": own as Any? ?? "unavailable",
            "quartz_session": session != nil,
            "session_on_console": session?[kCGSessionOnConsoleKey as String] ?? "unavailable",
            "session_login_done": session?[kCGSessionLoginDoneKey as String] ?? "unavailable",
            "display_active": CGDisplayIsActive(display) != 0,
            "display_asleep": CGDisplayIsAsleep(display) != 0]
}
let linked = CommandLine.arguments.contains("--display-linked")
func isEligible(_ state:[String:Any])->Bool {
    ["window_visible", "window_on_active_space", "window_unoccluded", "window_in_onscreen_list", "session_on_console", "display_active"].allSatisfy { state[$0] as? Bool == true }
    && state["display_asleep"] as? Bool == false
}
let preflightStart=CACurrentMediaTime()
var preflightReady=false, preflightMs=0.0
var displayLink: CADisplayLink?
class DisplayTick: NSObject {
    let callback: () -> Void
    init(_ callback: @escaping () -> Void) { self.callback = callback; super.init() }
    @objc func fire(_ link: CADisplayLink) { callback() }
}
var timer: Timer?
func draw() {
    if attempted % 60 == 0 && visibility.count < 4 { visibility.append(snapshot()) }
    guard attempted < 120 else { timer?.invalidate(); displayLink?.invalidate(); return }
    lock.lock(); let busy = inFlight >= 3; lock.unlock()
    if busy { skipped += 1; return }
    let t = CACurrentMediaTime()
    guard let drawable = layer.nextDrawable() else { skipped += 1; return }
    let acquired = CACurrentMediaTime()
    drawStarts.append(t)
    guard let commands = queue.makeCommandBuffer() else { fail("command buffer allocation") }
    let pass = MTLRenderPassDescriptor()
    pass.colorAttachments[0].texture = drawable.texture
    pass.colorAttachments[0].loadAction = .clear; pass.colorAttachments[0].storeAction = .store
    let phase = (attempted / 30) % 3
    pass.colorAttachments[0].clearColor = MTLClearColorMake(phase == 0 ? 1 : 0, phase == 1 ? 1 : 0, phase == 2 ? 1 : 0, 1)
    guard let encoder = commands.makeRenderCommandEncoder(descriptor: pass) else { fail("render encoder allocation") }
    if let pipeline=compositionPipeline {
        encoder.setRenderPipelineState(pipeline)
        for index in 0..<compositeLayers {
            var color=SIMD4<Float>(index%3 == 0 ? 1:0,index%3 == 1 ? 1:0,index%3 == 2 ? 1:0,0.25)
            encoder.setFragmentBytes(&color,length:MemoryLayout<SIMD4<Float>>.size,index:0)
            encoder.drawPrimitives(type:.triangle,vertexStart:0,vertexCount:3)
        }
    }
    encoder.endEncoding()
    let encodedAt = CACurrentMediaTime()
    encoding.append(encodedAt - acquired)
    let id = attempted; attempted += 1; acquisition.append(acquired - t)
    lock.lock()
    frameTrace[id] = ["draw_start_ms":(t-traceStart)*1000,"acquisition_ms":(acquired-t)*1000,
                      "encode_ms":(encodedAt-acquired)*1000]
    lock.unlock()
    if let surface=drawable.texture.iosurface {
        let identity=IOSurfaceGetID(surface)
        if surfaceSlots[identity] == nil {surfaceSlots[identity]=surfaceSlots.count}
        lock.lock();frameTrace[id]?["surface_slot"]=Double(surfaceSlots[identity]!);lock.unlock()
    }
    if id < 6,let count=flipCount() {lock.lock();frameTrace[id]?["system_flips_at_draw"]=count;lock.unlock()}
    drawable.addPresentedHandler { shown in
        let observed=CACurrentMediaTime(), count=id < 6 ? flipCount():nil
        lock.lock(); presented[id] = shown.presentedTime
        frameTrace[id]?["presented_callback_ms"]=(observed-traceStart)*1000
        frameTrace[id]?["presented_time_available"]=shown.presentedTime > 0 ? 1:0
        if shown.presentedTime > 0 {frameTrace[id]?["presented_time_ms"]=(shown.presentedTime-traceStart)*1000}
        if let count=count {frameTrace[id]?["system_flips_at_presented_callback"]=count}
        lock.unlock()
    }
    lock.lock(); inFlight += 1; lock.unlock()
    let commitAt = CACurrentMediaTime()
    lock.lock();frameTrace[id]?["commit_start_ms"]=(commitAt-traceStart)*1000;lock.unlock()
    commands.addScheduledHandler { _ in
        let observedAt = CACurrentMediaTime()
        lock.lock(); scheduledLatency.append(observedAt - commitAt)
        frameTrace[id]?["scheduled_callback_ms"]=(observedAt-traceStart)*1000;lock.unlock()
    }
    commands.addCompletedHandler { command in
        let observedAt=CACurrentMediaTime()
        lock.lock(); defer { lock.unlock() }
        inFlight -= 1; completed += 1
        completionLatency.append(observedAt - commitAt)
        frameTrace[id]?["completed_callback_ms"]=(observedAt-traceStart)*1000
        if command.status != .completed { errors += 1 }
        let a = command.gpuStartTime, b = command.gpuEndTime
        if a > 0 && b >= a { gpu.append(b - a);frameTrace[id]?["gpu_ms"]=(b-a)*1000 }
    }
    commands.present(drawable); commands.commit()
    let returned=CACurrentMediaTime();commitReturn.append(returned - commitAt)
    lock.lock();frameTrace[id]?["commit_return_ms"]=(returned-traceStart)*1000;lock.unlock()
}
// Test-only start-phase control: delay just the first client draw, never the
// display link, refresh mode, compositor, or GPU completion synchronization.
let shiftFirst=CommandLine.arguments.contains("--first-frame-half-period")
var shiftedFirst=false
let tick = DisplayTick {
    if shiftFirst && !shiftedFirst {
        shiftedFirst=true
        DispatchQueue.main.asyncAfter(deadline:.now()+0.008333333) { draw() }
    } else {draw()}
}
func startWhenReady() {
    guard isEligible(snapshot()) else {
        if CACurrentMediaTime()-preflightStart < 2 {
            DispatchQueue.main.asyncAfter(deadline:.now()+0.05) { startWhenReady() }
        }
        return
    }
    preflightReady=true;preflightMs=(CACurrentMediaTime()-preflightStart)*1000
    if linked {
        displayLink = view.displayLink(target: tick, selector: #selector(DisplayTick.fire(_:)))
        displayLink?.add(to: .main, forMode: .common)
    } else {
        timer = Timer.scheduledTimer(withTimeInterval: 1.0 / 60, repeats: true) { _ in draw() }
    }
}
// Allow AppKit to publish window occlusion/onscreen state before measurement.
DispatchQueue.main.asyncAfter(deadline:.now()+0.25) { startWhenReady() }
DispatchQueue.main.asyncAfter(deadline: .now() + .seconds(6)) {
    timer?.invalidate(); displayLink?.invalidate()
    lock.lock()
    let shown = presented.filter { $0.value > 0 }.sorted { $0.key < $1.key }
    let finish = completed, failure = errors, outstanding = inFlight, callbackCount = presented.count
    let GPU = gpu, scheduled = scheduledLatency, completion = completionLatency
    let trace=frameTrace.sorted{$0.key<$1.key}.map {key,value -> [String:Double] in
        var row=value;row["frame"]=Double(key);return row
    }
    lock.unlock()
    // presentedTime is an API observation; physical scanout is not independently measured.
    let latePairs = zip(shown.dropFirst(), shown).filter { $0.0.value - $0.1.value > 0.025 }
    let lateCorrelation: [[String: Any]] = latePairs.prefix(24).map { current, previous in
        let id = current.key
        return ["frame": id, "interval_ms": (current.value - previous.value) * 1000,
                "acquisition_ms": id < acquisition.count ? acquisition[id] * 1000 : -1,
                "cpu_draw_interval_ms": id > 0 && id < drawStarts.count ? (drawStarts[id] - drawStarts[id-1]) * 1000 : -1]
    }
    let times = shown.dropFirst(10).map { $0.value }
    let intervals = zip(times.dropFirst(), times).map { $0 - $1 }
    let states = visibility + [snapshot()]
    let eligible = preflightReady && states.allSatisfy { isEligible($0) }
    let display = (window.screen?.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber)?.uint32Value ?? CGMainDisplayID()
    let mode = CGDisplayCopyDisplayMode(display)
    let result: [String: Any] = ["probe": "pacing", "pacing": linked ? "AppKit display link" : "60 Hz timer", "attempted": attempted, "completed": finish,
        "visibility_samples": states, "command_errors": failure, "outstanding": outstanding, "timer_skips": skipped,
        "preflight_ready":preflightReady,"preflight_wait_ms":preflightMs,
        "frame_trace":trace,
        "drawable_count":drawableCount,"render_width":renderWidth,"render_height":renderHeight,"composite_layers":compositeLayers,
        "display_width": mode?.width ?? 0, "display_height": mode?.height ?? 0, "display_refresh_hz": mode?.refreshRate ?? 0,
        "presented_callbacks": callbackCount, "positive_presented_times": shown.count,
        "presented_frame_ids": shown.map { $0.key }, "presented_times": shown.map { $0.value },
        "presentation_intervals": stats(intervals), "intervals_above_25ms": intervals.filter { $0 > 0.025 }.count,
        "late_frame_correlations": lateCorrelation, "cpu_draw_intervals": stats(zip(drawStarts.dropFirst(), drawStarts).map { $0 - $1 }),
        "encode": stats(encoding), "commit_return": stats(commitReturn),
        "commit_to_scheduled_callback": stats(scheduled), "commit_to_completed_callback": stats(completion),
        "drawable_acquisition": stats(acquisition), "gpu": stats(GPU)]
    let data = try! JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
    print("result: \(String(data: data, encoding: .utf8)!)")
    window.orderOut(nil); window.close()
    if !eligible && finish == attempted && failure == 0 && outstanding == 0 {
        print("NOT VERIFIED: view/display not continuously eligible for visible presentation; no driver failure inferred")
        fflush(stdout); exit(0)
    }
    guard attempted == 120 && finish == 120 && failure == 0 && outstanding == 0 else { fail("bounded presentation submission/completion") }
    if shown.count < 110 {
        print("NOT VERIFIED: GPU submissions completed; presentation timing unavailable")
    } else { print("PASS: windowed presentation API observations collected; not physical scanout verification") }
    fflush(stdout); exit(0)
}
app.run()
