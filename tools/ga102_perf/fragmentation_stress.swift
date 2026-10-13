// Physical joined-hole test: keep all other ranges live while freeing 0/2/1.
@_silgen_name("ga102_graphics_pool_trace") private func fragmentationTracePointer() -> UnsafePointer<CChar>
func fragmentationTrace() -> [String:Any] {
 guard let data=String(cString:fragmentationTracePointer()).data(using:.utf8),let object=try? JSONSerialization.jsonObject(with:data) as? [String:Any] else {fail("fragmentation trace")}
 return object
}
var fragmentationRecords=[[String:Any]]()
for round in 0..<3 {
 let sample:[String:Any]=autoreleasepool {
  let before=resources(), bytes=1<<20
  var ranges=[MTLBuffer?]()
  for index in 0..<31 { autoreleasepool {
   guard let buffer=device.makeBuffer(length:bytes,options:.storageModeShared) else {fail("fragmentation sentinel")};owned(buffer)
   memset(buffer.contents(),Int32(index+1),bytes);ranges.append(buffer)
  }}
  let filled=resources()
  ranges[0]=nil;ranges[2]=nil;ranges[1]=nil
  let holes=resources()
  guard holes["buffer_live"] as! Int == (filled["buffer_live"] as! Int)-3 else {fail("fragment holes not freed") }
  let traceBefore=fragmentationTrace(), start=tick()
  guard let joined=device.makeBuffer(length:3*bytes,options:.storageModeShared) else {fail("joined allocation")}
  let allocationNS=tick()-start, held=resources(),traceAfter=fragmentationTrace();owned(joined)
  memset(joined.contents(),231,3*bytes)
  // Dedicated destination avoids disturbing the pooled allocation observation.
  guard let destination=device.makeBuffer(length:5*bytes,options:.storageModeShared) else {fail("fragmentation readback")};owned(destination)
  var checked=0
  for index in 3..<32 {
   let source=index==31 ? joined : ranges[index]!
   let count=index==31 ? 3*bytes : bytes, value:UInt8=index==31 ? 231 : UInt8(index+1)
   guard let command=queue.makeCommandBuffer(),let blit=command.makeBlitCommandEncoder() else {fail("fragmentation copy")};owned(command);owned(blit)
   blit.copy(from:source,sourceOffset:0,to:destination,destinationOffset:0,size:count);blit.endEncoding();complete(command)
   let data=destination.contents().bindMemory(to:UInt8.self,capacity:count)
   for offset in 0..<count {if data[offset] != value {fail("fragmentation overlap or copy")}}
   checked += count
  }
  return ["round":round,"before":before,"filled":filled,"holes":holes,"held":held,"trace_before":traceBefore,"trace_after":traceAfter,"allocation_ns":allocationNS,"bytes_verified":checked]
 }
 var row=sample;row["after"]=resources();fragmentationRecords.append(row)
}
