// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Enumerate actual mapped Mach-O UUIDs after ordinary production Metal work.
// This process observes itself; it does not inspect WindowServer's address space.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#include <uuid/uuid.h>
#include <objc/runtime.h>
#include <dlfcn.h>

int main(void) {
    @autoreleasepool {
        id<MTLDevice> device = MTLCreateSystemDefaultDevice();
        if (!device) return 1;
        NSError *error = nil;
        NSString *source = @"#include <metal_stdlib>\nusing namespace metal;\n"
            "kernel void provenance(device uint *out [[buffer(0)]], uint i [[thread_position_in_grid]])"
            "{ out[i] = (i + 1u) * 17u; }";
        id<MTLLibrary> library = [device newLibraryWithSource:source options:nil error:&error];
        id<MTLFunction> function = [library newFunctionWithName:@"provenance"];
        id<MTLComputePipelineState> pipeline = function ? [device newComputePipelineStateWithFunction:function error:&error] : nil;
        id<MTLBuffer> buffer = [device newBufferWithLength:16 options:MTLResourceStorageModeShared];
        id<MTLCommandQueue> queue = [device newCommandQueue];
        id<MTLCommandBuffer> command = [queue commandBuffer];
        id<MTLComputeCommandEncoder> encoder = [command computeCommandEncoder];
        if (!pipeline || !buffer || !queue || !command || !encoder) {
            fprintf(stderr, "Metal setup failed: %s\n", error.description.UTF8String);
            return 2;
        }
        memset(buffer.contents, 0, 16);
        [encoder setComputePipelineState:pipeline];
        [encoder setBuffer:buffer offset:0 atIndex:0];
        [encoder dispatchThreads:MTLSizeMake(4,1,1) threadsPerThreadgroup:MTLSizeMake(4,1,1)];
        [encoder endEncoding]; [command commit]; [command waitUntilCompleted];
        BOOL correct = command.status == MTLCommandBufferStatusCompleted && !command.error;
        for (unsigned i = 0; i < 4; ++i)
            correct = correct && ((uint32_t *)buffer.contents)[i] == (i + 1) * 17;
        NSMutableArray *images = [NSMutableArray array];
        for (uint32_t i = 0; i < _dyld_image_count(); ++i) {
            const char *name = _dyld_get_image_name(i);
            if (!name || (!strstr(name, "/Library/GPUBundles/") &&
                          !strstr(name, "libnvmtl_translate") && !strstr(name, "libvulkan_nouveau"))) continue;
            const struct mach_header_64 *header = (const void *)_dyld_get_image_header(i);
            if (header->magic != MH_MAGIC_64) return 3;
            const struct load_command *lc = (const void *)(header + 1);
            NSString *identity = nil;
            for (uint32_t j = 0; j < header->ncmds; ++j) {
                if (lc->cmd == LC_UUID && lc->cmdsize >= sizeof(struct uuid_command)) {
                    char text[37]; uuid_unparse_upper(((const struct uuid_command *)lc)->uuid, text);
                    identity = @(text); break;
                }
                if (lc->cmdsize < sizeof(*lc)) return 3;
                lc = (const void *)((const char *)lc + lc->cmdsize);
            }
            [images addObject:@{@"path":@(name), @"mapped_uuid":identity ?: @"unavailable"}];
        }
        Dl_info origin = {0};
        Method method = class_getInstanceMethod(object_getClass(device), @selector(newCommandQueue));
        if (!method || !dladdr((const void *)method_getImplementation(method), &origin)) return 4;
        NSDictionary *result = @{@"device":device.name, @"class":NSStringFromClass(object_getClass(device)),
            @"queue_method_image":@(origin.dli_fname), @"images":images,
            @"command_completed":@(command.status == MTLCommandBufferStatusCompleted),
            @"gpu_values_correct":@(correct), @"scope":@"own production Metal process; not WindowServer"};
        NSData *data = [NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:&error];
        if (!data) return 5;
        fwrite(data.bytes, 1, data.length, stdout); fputc('\n', stdout);
        return correct ? 0 : 6;
    }
}
