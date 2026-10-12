// GPU copy/readback across suballocation alignment and the 4 MiB pool threshold.
var boundaryRecords=[[String:Any]]()
let boundarySizes=[1,255,256,257,4096,65535,(4<<20)-1,4<<20,(4<<20)+1]
for (index,size) in boundarySizes.enumerated() {
    let row: [String:Any] = autoreleasepool {
        let before=resources()
        guard let source=device.makeBuffer(length:size,options:.storageModeShared),
              let destination=device.makeBuffer(length:size,options:.storageModeShared),
              let command=queue.makeCommandBuffer(),let encoder=command.makeBlitCommandEncoder() else {fail("boundary allocation")}
        owned(source);owned(destination);owned(command);owned(encoder)
        let input=source.contents().bindMemory(to:UInt8.self,capacity:size)
        for offset in 0..<size {input[offset]=UInt8(truncatingIfNeeded:offset+index*17)}
        encoder.copy(from:source,sourceOffset:0,to:destination,destinationOffset:0,size:size)
        encoder.endEncoding();complete(command)
        let output=destination.contents().bindMemory(to:UInt8.self,capacity:size)
        for offset in 0..<size {
            if output[offset] != UInt8(truncatingIfNeeded:offset+index*17) {fail("boundary copy mismatch")}
        }
        return ["bytes_verified":size,"before":before]
    }
    var final=row;final["after"]=resources();boundaryRecords.append(final)
}
