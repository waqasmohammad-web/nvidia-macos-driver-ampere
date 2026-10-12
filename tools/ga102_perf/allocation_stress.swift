// Inserted into the owned graphics child after its ordinary qualification draws.
// Every stress command completes and reads back; no drawable or display API.
var growthRecords=[[String:Any]]()
guard let alternate=device.makeTexture(descriptor:inputDescriptor) else { fail("alternate texture") }
owned(alternate)
gradient.withUnsafeBytes { alternate.replace(region:MTLRegionMake2D(0,0,8,8),mipmapLevel:0,withBytes:$0.baseAddress!,bytesPerRow:32) }
for round in 0..<3 {
    let sample: [String:Any] = autoreleasepool {
        let before=resources(), metricsBefore=snapshot()
        guard let command=queue.makeCommandBuffer() else { fail("stress command") };owned(command)
        let pass=MTLRenderPassDescriptor();pass.colorAttachments[0].texture=target
        pass.colorAttachments[0].loadAction = .clear;pass.colorAttachments[0].storeAction = .store
        let start=tick()
        guard let encoder=command.makeRenderCommandEncoder(descriptor:pass) else { fail("stress encoder") };owned(encoder)
        encoder.setRenderPipelineState(pipeline);encoder.setFragmentSamplerState(samplers[0],index:3)
        for drawIndex in 0..<1536 {
            encoder.setFragmentTexture(drawIndex%2 == 0 ? input:alternate,index:0)
            encoder.drawPrimitives(type:.triangle,vertexStart:0,vertexCount:3)
        }
        encoder.endEncoding();let encodeNS=tick()-start, held=resources(), submit=tick()
        complete(command);let completionNS=tick()-submit
        guard let copy=queue.makeCommandBuffer(),let blit=copy.makeBlitCommandEncoder() else { fail("stress readback") }
        owned(copy);owned(blit)
        blit.copy(from:target,sourceSlice:0,sourceLevel:0,sourceOrigin:MTLOrigin(x:0,y:0,z:0),sourceSize:MTLSize(width:32,height:32,depth:1),
                  to:readback,destinationOffset:0,destinationBytesPerRow:256,destinationBytesPerImage:8192)
        blit.endEncoding();complete(copy)
        let bytes=readback.contents().bindMemory(to:UInt8.self,capacity:8192),expected=[64,96,80,255]
        for y in 0..<32 { for x in 0..<32 { for channel in 0..<4 {
            if Int(bytes[y*256+x*4+channel]) != expected[channel] { fail("growth final pixel mismatch") }
        } } }
        return ["round":round,"draws":1536,"checked_pixels":1024,"before":before,"held":held,
                "encode_ns":encodeNS,"completion_ns":completionNS,"metrics_before":metricsBefore,"metrics_after":snapshot()]
    }
    var row=sample;row["after"]=resources();growthRecords.append(row)
}
// Hold 128 MiB of 1 MiB source/destination buffers, copy all 64 MiB on the GPU,
// check every destination word, release the wave, then repeat. This exercises
// pool growth, completed-command resource retirement, range reuse and trimming.
var bufferRecords=[[String:Any]]()
for round in 0..<3 {
    let sample: [String:Any] = autoreleasepool {
        let before=resources(), waveStart=tick()
        var sources=[MTLBuffer](), destinations=[MTLBuffer](),allocationTimes=[UInt64]()
        let bytes=1<<20,words=bytes/4
        for index in 0..<64 {
            let first=tick()
            guard let src=device.makeBuffer(length:bytes,options:.storageModeShared) else { fail("source buffer") }
            allocationTimes.append(tick()-first);owned(src)
            let second=tick()
            guard let dst=device.makeBuffer(length:bytes,options:.storageModeShared) else { fail("destination buffer") }
            allocationTimes.append(tick()-second);owned(dst)
            let data=src.contents().bindMemory(to:UInt32.self,capacity:words)
            for word in 0..<words {data[word]=UInt32(word) ^ (UInt32(index)&*1664525) ^ UInt32(round)}
            sources.append(src);destinations.append(dst)
        }
        let held=resources()
        guard let command=queue.makeCommandBuffer(),let blit=command.makeBlitCommandEncoder() else { fail("buffer copy") }
        owned(command);owned(blit)
        let copyStart=tick()
        for index in 0..<64 {blit.copy(from:sources[index],sourceOffset:0,to:destinations[index],destinationOffset:0,size:bytes)}
        blit.endEncoding();complete(command);let copyNS=tick()-copyStart
        for index in 0..<64 {
            let data=destinations[index].contents().bindMemory(to:UInt32.self,capacity:words)
            for word in 0..<words {
                if data[word] != UInt32(word) ^ (UInt32(index)&*1664525) ^ UInt32(round) { fail("buffer lifetime/copy mismatch") }
            }
        }
        return ["round":round,"buffer_count":128,"bytes_verified":64*bytes,"before":before,"held":held,
                "allocation_samples_ns":allocationTimes,"allocation_total_ns":allocationTimes.reduce(0,+),
                "copy_ns":copyNS,"wave_ns":tick()-waveStart]
    }
    var row=sample;row["after"]=resources();bufferRecords.append(row)
}
