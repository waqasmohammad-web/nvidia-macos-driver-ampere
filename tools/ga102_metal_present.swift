// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Six-second timing probe; full visual checks are in ga102_visual_present.swift.
// Existing display mode; no graphics settings.
import AppKit
import QuartzCore
import Metal
import Dispatch
import CoreGraphics
func fail(_ text: String) -> Never { fputs("FAIL: \(text)\n", stderr); exit(1) }
func stats(_ samples: [Double]) -> [String: Double] {
    let s = samples.sorted()
    guard !s.isEmpty else { return [:] }
    return ["p50_ms": s[(s.count - 1) / 2] * 1000,
            "p95_ms": s[min(s.count - 1, Int(ceil(Double(s.count) * 0.95)) - 1)] * 1000,
            "max_ms": s.last! * 1000, "samples": Double(s.count)]
}
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
layer.maximumDrawableCount = 3; layer.allowsNextDrawableTimeout = true
layer.drawableSize = CGSize(width: 640, height: 360)
view.wantsLayer = true; view.layer = layer
window.contentView = view; window.center(); window.orderFront(nil)

let lock = NSLock()
var inFlight = 0, completed = 0, errors = 0, skipped = 0, attempted = 0
var presented = [Int: Double](), acquisition = [Double](), gpu = [Double]()
var drawStarts = [Double]()
var encoding = [Double](), commitReturn = [Double](), scheduledLatency = [Double](), completionLatency = [Double]()
var visibility = [[String: Any]]()
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
    encoder.endEncoding()
    let encodedAt = CACurrentMediaTime()
    encoding.append(encodedAt - acquired)
    let id = attempted; attempted += 1; acquisition.append(acquired - t)
    drawable.addPresentedHandler { shown in
        lock.lock(); presented[id] = shown.presentedTime; lock.unlock()
    }
    lock.lock(); inFlight += 1; lock.unlock()
    let commitAt = CACurrentMediaTime()
    commands.addScheduledHandler { _ in
        let observedAt = CACurrentMediaTime()
        lock.lock(); scheduledLatency.append(observedAt - commitAt); lock.unlock()
    }
    commands.addCompletedHandler { command in
        lock.lock(); defer { lock.unlock() }
        inFlight -= 1; completed += 1
        completionLatency.append(CACurrentMediaTime() - commitAt)
        if command.status != .completed { errors += 1 }
        let a = command.gpuStartTime, b = command.gpuEndTime
        if a > 0 && b >= a { gpu.append(b - a) }
    }
    commands.present(drawable); commands.commit()
    commitReturn.append(CACurrentMediaTime() - commitAt)
}
let tick = DisplayTick { draw() }
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
