// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Ordinary Core Animation content. Own-window broker only; no Metal injection,
// permission requests, activation, mode changes, or presentation-time claims.
import AppKit
import QuartzCore
import CoreGraphics
import Darwin

let negative=CommandLine.arguments.dropFirst().first(where:{!$0.hasPrefix("--")}) ?? "none"
let continuous=CommandLine.arguments.contains("--continuous")
let linked=CommandLine.arguments.contains("--display-linked")
let referenceOnly=CommandLine.arguments.contains("--reference-only")
@MainActor class VisualPulse:NSObject {
    var pending:CheckedContinuation<Bool,Never>?,generation=0
    @objc func fire(_ link:CADisplayLink) {
        if let next=pending {pending=nil;next.resume(returning:true)}
    }
    func wait() async -> Bool {
        generation+=1;let token=generation
        return await withCheckedContinuation {next in
            pending=next
            DispatchQueue.main.asyncAfter(deadline:.now()+0.1) {
                if self.generation==token,let waiting=self.pending {self.pending=nil;waiting.resume(returning:false)}
            }
        }
    }
}
let queryEveryFrame=CommandLine.arguments.contains("--onscreen-every-frame")
let frameCount=continuous ? 120:12
let app=NSApplication.shared;app.setActivationPolicy(.accessory)
let window=NSWindow(contentRect:NSRect(x:0,y:0,width:640,height:360),styleMask:.borderless,backing:.buffered,defer:false)
window.isReleasedWhenClosed=false
let view=NSView(frame:NSRect(x:0,y:0,width:640,height:360));view.wantsLayer=true
window.contentView=view;window.center()
let root=view.layer!
let space=CGColorSpace(name:CGColorSpace.sRGB)!
func color(_ r:CGFloat,_ g:CGFloat,_ b:CGFloat,_ a:CGFloat=1)->CGColor {
    return CGColor(colorSpace:space,components:[r,g,b,a])!
}
// These animated translucent layers exercise normal compositor content between
// the independent reference sample rows. They are not themselves pixel-validated.
for i in 0..<(referenceOnly ? 0:32) {
    let l=CALayer();l.bounds=CGRect(x:0,y:0,width:24,height:24)
    l.position=CGPoint(x:20+(i%16)*40,y:i<16 ? 95:265)
    l.backgroundColor=color(1,0.5,0,0.55);l.cornerRadius=6
    l.shadowColor=color(0,0,0);l.shadowOpacity=0.35;l.shadowRadius=4
    root.addSublayer(l)
    let animation=CABasicAnimation(keyPath:"position.x")
    animation.fromValue=l.position.x;animation.toValue=l.position.x+10
    animation.duration=0.6;animation.autoreverses=true;animation.repeatCount=10
    l.add(animation,forKey:"bounded-motion")
}
var bits=[CALayer]()
for y in [0,320] {for cell in 0..<8 {
    let l=CALayer();l.frame=CGRect(x:cell*80,y:y,width:80,height:40)
    root.addSublayer(l);bits.append(l)
}}
let bar=CALayer();bar.backgroundColor=color(1,1,1)
root.addSublayer(bar)
// A valid frame-zero placeholder prevents the stream's initial window image
// from being misclassified as a corrupt reference before timed updates begin.
CATransaction.begin();CATransaction.setDisableActions(true)
root.backgroundColor=color(1,0,0)
for bit in bits {bit.backgroundColor=color(0,0,0)}
bar.frame=CGRect(x:0,y:40,width:40,height:280)
CATransaction.commit();CATransaction.flush()
if negative != "hidden" {window.orderFront(nil)}
var visibilityCosts=[String:Double]()
func visible(_ queryOnscreen:Bool=true)->Bool {
    let started=CACurrentMediaTime()
    if !queryOnscreen {
        let eligible=window.isVisible && window.occlusionState.contains(.visible)
        visibilityCosts=["cached_appkit_ms":(CACurrentMediaTime()-started)*1000]
        return eligible
    }
    var previous=started,costs=[String:Double]()
    func lap(_ name:String) {let now=CACurrentMediaTime();costs[name]=(now-previous)*1000;previous=now}
    let display=(window.screen?.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber)?.uint32Value ?? CGMainDisplayID()
    lap("display_lookup_ms")
    let session=CGSessionCopyCurrentDictionary() as? [String:Any]
    lap("session_query_ms")
    let listed = !queryOnscreen || ((CGWindowListCopyWindowInfo(.optionOnScreenOnly,kCGNullWindowID) as? [[String:Any]])?.contains {
        ($0[kCGWindowOwnerPID as String] as? NSNumber)?.int32Value==getpid() &&
        ($0[kCGWindowNumber as String] as? NSNumber)?.intValue==window.windowNumber
    } ?? false)
    lap("onscreen_query_ms")
    let local=window.isVisible && window.isOnActiveSpace && window.occlusionState.contains(.visible)
    lap("appkit_eligibility_ms")
    let awake=CGDisplayIsAsleep(display)==0 && CGDisplayIsActive(display) != 0
    lap("display_state_ms");visibilityCosts=costs
    return listed && local && awake &&
        (session?[kCGSessionOnConsoleKey as String] as? Bool)==true
}
let channel=ProcessInfo.processInfo.environment["GA102_CAPTURE_IPC"].map {URL(fileURLWithPath:$0,isDirectory:true)}
let permission=channel != nil && ProcessInfo.processInfo.environment["GA102_CAPTURE_PERMISSION"]=="1"
var attempted=0,received=0,correct=0,distinct=0,visibleFrames=0,transactions=0
var stopped=false,preflightReady=false
var samples=[[String:Any]]()
var fullVisibility=[Bool]()
func reference(_ rendered:Int) {
    CATransaction.begin();CATransaction.setDisableActions(true)
    root.backgroundColor=color(rendered%3==0 ? 1:0,rendered%3==1 ? 1:0,rendered%3==2 ? 1:0)
    for (index,l) in bits.enumerated() {
        let value=(rendered>>(index%8))&1
        l.backgroundColor=color(CGFloat(value),CGFloat(value),CGFloat(value))
    }
    bar.frame=CGRect(x:(rendered%8)*80,y:40,width:40,height:280)
    CATransaction.commit();CATransaction.flush()
}
func streamOperation(_ operation:String) async -> [String:Any]? {
    guard let directory=channel else{return nil}
    do {
        let request:[String:Any]=["operation":operation,"pid":getpid(),"window_id":window.windowNumber]
        try JSONSerialization.data(withJSONObject:request).write(to:directory.appendingPathComponent("request.json"),options:.atomic)
        let response=directory.appendingPathComponent(operation+".json"),deadline=Date().addingTimeInterval(6)
        while !FileManager.default.fileExists(atPath:response.path) && Date()<deadline {
            try? await Task.sleep(nanoseconds:10_000_000)
        }
        return try JSONSerialization.jsonObject(with:Data(contentsOf:response)) as? [String:Any]
    }catch{return nil}
}
Task { @MainActor in
    let pulse=VisualPulse();var displayLink:CADisplayLink?,missedTicks=0
    // Allow window publication, without waking/activating anything.
    try? await Task.sleep(nanoseconds:250_000_000)
    let readyDeadline=Date().addingTimeInterval(2)
    while !visible() && negative != "hidden" && Date()<readyDeadline {
        try? await Task.sleep(nanoseconds:50_000_000)
    }
    preflightReady=visible()
    fullVisibility.append(preflightReady)
    var streamStarted=false
    if continuous && permission && preflightReady {
        // AppKit can publish an initial gray view image on orderFront. Commit
        // the frame-zero reference after readiness and allow its publication.
        reference(0);try? await Task.sleep(nanoseconds:100_000_000)
        let response=await streamOperation("stream-start")
        streamStarted=response?["started"] as? Bool==true
    }
    if continuous && linked && preflightReady {
        displayLink=view.displayLink(target:pulse,selector:#selector(VisualPulse.fire(_:)))
        displayLink?.add(to:.main,forMode:.common)
    }
    for frame in 0..<frameCount {
        if linked && displayLink != nil {if !(await pulse.wait()) {missedTicks+=1}}
        let rendered=negative=="static" ? 0:frame
        let started=CACurrentMediaTime()
        reference(rendered);transactions+=1
        let transactionMS=(CACurrentMediaTime()-started)*1000
        if !continuous || !linked {try? await Task.sleep(nanoseconds:continuous ? 16_666_667:300_000_000)}
        let visibilityStart=CACurrentMediaTime()
        let fullQuery = !continuous || queryEveryFrame || frame%30==0
        let eligible=visible(fullQuery);if eligible {visibleFrames+=1}
        if fullQuery {fullVisibility.append(eligible)}
        let visibilityMS=(CACurrentMediaTime()-visibilityStart)*1000
        var captureMS:Double=0,matched=false
        // Hidden/inactive content cannot produce a full visual PASS. Never ask
        // SCK for another window or retry an unavailable capture method.
        if let directory=channel,!continuous && permission && !stopped && eligible {
            attempted+=1
            let request:[String:Any]=["frame":frame,"window_id":window.windowNumber,"pid":getpid()]
            do {
                let bytes=try JSONSerialization.data(withJSONObject:request)
                try bytes.write(to:directory.appendingPathComponent("request.json"),options:.atomic)
                let response=directory.appendingPathComponent("response-\(frame).json")
                let captureStart=CACurrentMediaTime(),deadline=Date().addingTimeInterval(6)
                while !FileManager.default.fileExists(atPath:response.path) && Date()<deadline {
                    try? await Task.sleep(nanoseconds:10_000_000)
                }
                captureMS=(CACurrentMediaTime()-captureStart)*1000
                let value=try JSONSerialization.jsonObject(with:Data(contentsOf:response)) as? [String:Any]
                if value?["received"] as? Bool==true {
                    received+=1;matched=value?["correct"] as? Bool==true
                    if matched {correct+=1}
                    distinct=value?["distinct_patterns"] as? Int ?? distinct
                }else{stopped=true}
            }catch{stopped=true}
        }
        samples.append(["frame":frame,"eligible":eligible,"full_onscreen_query":fullQuery,"visibility_ms":visibilityMS,
                        "visibility_breakdown_ms":visibilityCosts,
                        "transaction_ms":transactionMS,"transaction_start_seconds":started,
                        "capture_roundtrip_ms":captureMS,"captured_pattern_correct":matched])
    }
    displayLink?.invalidate()
    var streamAnalysis:[String:Any]=["captured_reference_contents":"NOT VERIFIED"]
    if streamStarted {
        try? await Task.sleep(nanoseconds:300_000_000)
        let response=await streamOperation("stream-stop")
        streamAnalysis=response?["analysis"] as? [String:Any] ?? streamAnalysis
    }
    fullVisibility.append(visible())
    // Export only relative client transaction clocks.
    if let origin=samples.first?["transaction_start_seconds"] as? Double {
        for index in samples.indices {
            let value=samples[index].removeValue(forKey:"transaction_start_seconds") as! Double
            samples[index]["transaction_start_ms"]=(value-origin)*1000
        }
    }
    let result:[String:Any]=["probe":"ca_visual","frames":frameCount,"negative_control":negative,
        "display_linked":linked,"reference_only":referenceOnly,"missed_display_ticks":missedTicks,
        "continuous":continuous,"stream_started":streamStarted,"stream_analysis":streamAnalysis,
        "full_visibility_samples":fullVisibility,"onscreen_query_every_frame":queryEveryFrame,
        "preflight_ready":preflightReady,"transactions":transactions,"visible_frames":visibleFrames,
        "capture_permission":permission,"capture_attempted":attempted,"capture_received_frames":received,
        "capture_correct_frames":correct,"capture_distinct_patterns":distinct,"samples":samples,
        "capture_method":"ScreenCaptureKit owned-window broker",
        "scope":continuous ? "120 client CA reference transactions; capture cadence may coalesce; extra animated layers unsampled":"12 held Core Animation reference patterns; 32 additional animated layers unsampled",
        "physical_scanout":"NOT VERIFIED","presentation_timestamps":"NOT VERIFIED",
        "gpu_completion":"not measured by this probe"]
    let data=try! JSONSerialization.data(withJSONObject:result,options:.sortedKeys)
    print("result: \(String(data:data,encoding:.utf8)!)")
    window.orderOut(nil);window.close();fflush(stdout);exit(0)
}
app.run()
