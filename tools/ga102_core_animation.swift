// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Ordinary AppKit/Core Animation window; idle/animation/idle phases, eight seconds.
// Presentation-layer state is NOT physical scanout or GPU completion evidence.
import AppKit
import QuartzCore
import CoreGraphics
import Darwin
func stats(_ a:[Double])->[String:Double] {
    let s=a.sorted(); guard !s.isEmpty else{return [:]}
    return ["p50_ms":s[(s.count-1)/2]*1000,"p95_ms":s[min(s.count-1,Int(ceil(Double(s.count)*0.95))-1)]*1000,"max_ms":s.last!*1000,"samples":Double(s.count)]
}
func counters()->[String:Int64] {
    var result=[String:Int64]()
    for name in ["nvaccel_iop_flips","nvaccel_iop_fail","nvaccel_iop_async_refused","nvaccel_iop_async_drop","nvrmfb_flip_n","nvrmfb_flip_us_sum"] {
        var value:Int64=0; var size=MemoryLayout<Int64>.size
        if sysctlbyname("debug."+name,&value,&size,nil,0)==0 && size==MemoryLayout<Int64>.size {result[name]=value}
    }; return result
}
func readCommand(_ exe:String,_ args:[String])->String? {
    let p=Process();p.executableURL=URL(fileURLWithPath:exe);p.arguments=args
    let pipe=Pipe();p.standardOutput=pipe;p.standardError=FileHandle.nullDevice
    do {try p.run()}catch{return nil}
    let data=pipe.fileHandleForReading.readDataToEndOfFile();p.waitUntilExit()
    return p.terminationStatus==0 ? String(data:data,encoding:.utf8)?.trimmingCharacters(in:.whitespacesAndNewlines):nil
}
let compositorPID=readCommand("/usr/bin/pgrep",["-x","WindowServer"])
func compositorCPU()->Double? {
    guard let pid=compositorPID, !pid.isEmpty, pid.allSatisfy({$0.isNumber}),
          let clock=readCommand("/bin/ps",["-p",pid,"-o","time="]) else{return nil}
    let parts=clock.split(separator:":")
    let fields=parts.compactMap{Double($0)}
    guard fields.count==parts.count && (fields.count==2 || fields.count==3) else{return nil}
    return fields.reduce(0){$0*60+$1}
}
let app=NSApplication.shared; app.setActivationPolicy(.accessory)
let window=NSWindow(contentRect:NSRect(x:0,y:0,width:960,height:600),styleMask:[.titled],backing:.buffered,defer:false)
window.title="GA102 Core Animation probe (8 seconds)"; window.isReleasedWhenClosed=false
let view=NSView(frame:NSRect(x:0,y:0,width:960,height:600)); view.wantsLayer=true
window.contentView=view
let root=view.layer!; root.backgroundColor=NSColor.darkGray.cgColor
let backdrop=CAGradientLayer(); backdrop.frame=view.bounds
backdrop.colors=[NSColor.systemBlue.cgColor,NSColor.systemOrange.cgColor]; root.addSublayer(backdrop)
// Explicit animations run through ordinary Core Animation, no custom Metal commands.
var layers=[CALayer]()
for i in 0..<32 {
    let l=CALayer(); l.bounds=CGRect(x:0,y:0,width:180,height:90)
    l.position=CGPoint(x:CGFloat(100+(i%8)*100),y:CGFloat(80+(i/8)*130))
    l.backgroundColor=NSColor(calibratedHue:CGFloat(i)/32,saturation:0.7,brightness:0.9,alpha:0.55).cgColor
    l.cornerRadius=18; l.shadowColor=NSColor.black.cgColor; l.shadowOpacity=0.35; l.shadowRadius=12
    l.shadowOffset=CGSize(width:3,height:-3); root.addSublayer(l); layers.append(l)
}
window.center(); window.orderFront(nil)
func visibility()->[String:Bool] {
    let display=(window.screen?.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber)?.uint32Value ?? CGMainDisplayID()
    let session=CGSessionCopyCurrentDictionary() as? [String:Any]
    let listed=(CGWindowListCopyWindowInfo(.optionOnScreenOnly,kCGNullWindowID) as? [[String:Any]])?.contains {
        ($0[kCGWindowOwnerPID as String] as? NSNumber)?.int32Value==getpid() && ($0[kCGWindowNumber as String] as? NSNumber)?.intValue==window.windowNumber
    } ?? false
    return ["visible":window.isVisible,"unoccluded":window.occlusionState.contains(.visible),"active_space":window.isOnActiveSpace,
            "onscreen":listed,"display_awake":CGDisplayIsAsleep(display)==0,"display_active":CGDisplayIsActive(display) != 0,
            "console":session?[kCGSessionOnConsoleKey as String] as? Bool ?? false]
}
var phase="idle_before", previous=CACurrentMediaTime(), intervals=[String:[Double]]()
var snapshots=[[String:Any]](), animationChanges=0, lastPosition=layers[0].position
var start=[String:Int64](), phaseResults=[[String:Any]](), timer:Timer?
var phaseStart=CACurrentMediaTime(),cpuStart:Double?
func endPhase() {
    let after=counters(); var delta=[String:Int64]()
    for (key,value) in start {if let end=after[key] {delta[key]=end-value}}
    let cpuEnd=compositorCPU()
    let cpuDelta:Any = (cpuStart != nil && cpuEnd != nil && cpuEnd! >= cpuStart!) ? (cpuEnd!-cpuStart!) as Any:NSNull()
    phaseResults.append(["windowserver_cpu_seconds":cpuDelta,"phase":phase,"elapsed_seconds":CACurrentMediaTime()-phaseStart,"counter_deltas":delta,"client_timer_intervals":stats(intervals[phase] ?? [])])
    cpuStart=cpuEnd; start=after; phaseStart=CACurrentMediaTime(); snapshots.append(["phase":phase,"visibility":visibility()])
}
DispatchQueue.main.asyncAfter(deadline:.now()+0.25) {
    start=counters(); cpuStart=compositorCPU(); phaseStart=CACurrentMediaTime(); snapshots.append(["phase":phase,"visibility":visibility()]); previous=CACurrentMediaTime()
    timer=Timer.scheduledTimer(withTimeInterval:1/60,repeats:true) {_ in
        let t=CACurrentMediaTime(); intervals[phase,default:[]].append(t-previous); previous=t
        if phase=="animation", let p=layers[0].presentation()?.position, p != lastPosition {animationChanges+=1;lastPosition=p}
    }
}
DispatchQueue.main.asyncAfter(deadline:.now()+2) {
    endPhase(); phase="animation"; previous=CACurrentMediaTime()
    CATransaction.begin(); CATransaction.setDisableActions(true)
    for (i,l) in layers.enumerated() {
        let a=CABasicAnimation(keyPath:"position.x"); a.fromValue=l.position.x; a.toValue=l.position.x+CGFloat(i%2==0 ? 65:-65)
        a.duration=1; a.autoreverses=true; a.repeatCount=2; a.timingFunction=CAMediaTimingFunction(name:.easeInEaseOut)
        l.add(a,forKey:"bounded-motion")
    }; CATransaction.commit()
}
DispatchQueue.main.asyncAfter(deadline:.now()+6) {
    endPhase(); phase="idle_after"; previous=CACurrentMediaTime()
    CATransaction.begin(); CATransaction.setDisableActions(true); for l in layers {l.removeAllAnimations()}; CATransaction.commit()
}
DispatchQueue.main.asyncAfter(deadline:.now()+8) {
    timer?.invalidate();endPhase()
    let result:[String:Any]=["workload":"32 translucent rounded layers with shadows","phases":phaseResults,
        "visibility_samples":snapshots,"client_presentation_position_changes":animationChanges,
        "visual_validation":"NOT VERIFIED","physical_scanout":"NOT VERIFIED","gpu_completion":"not measured by this probe"]
    let json=try! JSONSerialization.data(withJSONObject:result,options:[.sortedKeys])
    print("result: \(String(data:json,encoding:.utf8)!)")
    print("PASS: bounded Core Animation observation completed; timer/presentation-tree samples are not displayed frame timestamps")
    window.orderOut(nil);window.close();fflush(stdout);exit(0)
}
app.run()
