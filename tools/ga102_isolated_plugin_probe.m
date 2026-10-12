// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Explicitly bind one plugin in one owned process. No Metal device enumeration,
// window, display configuration, kext load or installed-file replacement.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <IOKit/IOKitLib.h>
#import <objc/runtime.h>
#import <objc/message.h>
#include <dlfcn.h>
#include <mach-o/dyld.h>
#include <time.h>
#include <unistd.h>

static void fail(const char *reason) { fprintf(stderr, "FAIL: %s\n", reason); fflush(stderr); _Exit(1); }
static NSString *canonical(const char *path) {
    return [[@(path) stringByStandardizingPath] stringByResolvingSymlinksInPath];
}
static void checkImage(Class cls, NSString *expected) {
    const char *image = cls ? class_getImageName(cls) : NULL;
    if (!image || ![canonical(image) isEqual:expected]) fail("object class is not owned by requested plugin");
}
static void checkMethod(id object, SEL selector, NSString *expected) {
    Dl_info info = {0};
    IMP implementation = class_getMethodImplementation([object class], selector);
    if (!implementation || !dladdr((const void *)implementation, &info) ||
        !info.dli_fname || ![canonical(info.dli_fname) isEqual:expected])
        fail("method implementation is not owned by requested plugin");
}
static void checkSinglePlugin(NSString *expected) {
    unsigned count = 0;
    for (uint32_t i = 0; i < _dyld_image_count(); ++i) {
        const char *path = _dyld_get_image_name(i);
        if (path && [[canonical(path) lastPathComponent] isEqual:@"NVMTLDriver"]) {
            if (![canonical(path) isEqual:expected]) fail("another Metal driver image was loaded");
            ++count;
        }
    }
    if (count != 1) fail("expected exactly one explicit driver image");
}
static id<MTLDevice> bindDevice(NSString *expected) {
    if (objc_getClass("NVMTLDevice")) fail("Metal plugin already loaded before explicit binding");
    // +load forwarding changes are restricted to this process's NVMTL classes.
    void *handle = dlopen(expected.fileSystemRepresentation, RTLD_NOW | RTLD_LOCAL);
    if (!handle) { fprintf(stderr, "FAIL: dlopen: %s\n", dlerror()); fail("requested image could not be loaded"); }
    Class cls = objc_getClass("NVMTLDevice");
    checkImage(cls, expected); checkSinglePlugin(expected);
    io_service_t accelerator = IOServiceGetMatchingService(kIOMainPortDefault, IOServiceMatching("NVAccel"));
    if (!accelerator) fail("NVAccel service unavailable");
    // This is the IOKit accelerator service right expected by MTLIOAccelDevice.
    id<MTLDevice> device = ((id (*)(id, SEL, mach_port_t))objc_msgSend)(
        [cls alloc], sel_registerName("initWithAcceleratorPort:"), accelerator);
    IOObjectRelease(accelerator);
    if (!device || ![device.name containsString:@"3080 Ti"]) fail("requested GA102 device did not initialize");
    checkImage([device class], expected);
    checkMethod(device, @selector(newLibraryWithSource:options:error:), expected);
    checkMethod(device, @selector(newComputePipelineStateWithFunction:error:), expected);
    checkMethod(device, @selector(newCommandQueue), expected);
    checkMethod(device, @selector(newTextureWithDescriptor:), expected);
    return device;
}

#ifdef GA102_BINDING_ONLY
static NSString *boundImage;
static void verifyAtExit(void) { @autoreleasepool {
    checkSinglePlugin(boundImage);
    puts("binding_verified: true"); fflush(stdout);
}}
// Swift takes the retained object. The image stays resident until process exit.
void *ga102_bound_device(void) { @autoreleasepool {
    const char *path = getenv("GA102_PLUGIN_IMAGE");
    if (!path || !*path) fail("explicit plugin path missing");
    boundImage = canonical(path);
    id device = bindDevice(boundImage);
    if (atexit(verifyAtExit)) fail("provenance exit check unavailable");
    return (__bridge_retained void *)device;
}}
#else
static double elapsed(uint64_t start) { return (clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW)-start)/1e6; }
int main(int argc, char **argv) { @autoreleasepool {
    if (argc != 2 && !(argc == 3 && !strcmp(argv[2], "--initialize-only"))) return 2;
    NSString *expected = canonical(argv[1]);
    id<MTLDevice> device = bindDevice(expected);
    if (argc == 3) {
        checkSinglePlugin(expected);
        puts("result: {\"explicit_plugin_binding\":true,\"device_initialized\":true,\"gpu_execution\":false}");
        return 0;
    }
    NSError *error = nil;
    NSString *source = @"#include <metal_stdlib>\nusing namespace metal; kernel void isolated_probe(device float *a [[buffer(0)]], uint i [[thread_position_in_grid]]) { if(i<4) a[i]=a[i]*2.0f+1.0f; }";
    uint64_t start = clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW);
    id<MTLLibrary> library = [device newLibraryWithSource:source options:nil error:&error];
    double libraryMS = elapsed(start);
    if (!library || error) fail("library compilation failed");
    checkImage([library class], expected);
    id<MTLFunction> function = [library newFunctionWithName:@"isolated_probe"];
    if (!function) fail("function unavailable");
    checkImage([function class], expected);
    id<MTLCommandQueue> queue = [device newCommandQueue];
    if (!queue) fail("queue unavailable");
    checkImage([queue class], expected);
    NSMutableArray *rows = [NSMutableArray new];
    for (unsigned iteration = 0; iteration < 8; ++iteration) { @autoreleasepool {
        start = clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW);
        id<MTLComputePipelineState> pipeline = [device newComputePipelineStateWithFunction:function error:&error];
        double pipelineMS = elapsed(start);
        if (!pipeline || error) fail("pipeline compilation failed");
        checkImage([pipeline class], expected);
        id<MTLBuffer> buffer = [device newBufferWithLength:16 options:MTLResourceStorageModeShared];
        if (!buffer) fail("buffer unavailable");
        float *values = buffer.contents;
        for (unsigned i = 0; i < 4; ++i) values[i] = i + 1;
        id<MTLCommandBuffer> commands = [queue commandBuffer];
        id<MTLComputeCommandEncoder> encoder = [commands computeCommandEncoder];
        if (!commands || !encoder) fail("encoder unavailable");
        checkImage([commands class], expected); checkImage([encoder class], expected);
        [encoder setComputePipelineState:pipeline]; [encoder setBuffer:buffer offset:0 atIndex:0];
        [encoder dispatchThreads:MTLSizeMake(4,1,1) threadsPerThreadgroup:MTLSizeMake(4,1,1)];
        [encoder endEncoding];
        dispatch_semaphore_t done = dispatch_semaphore_create(0);
        [commands addCompletedHandler:^(id<MTLCommandBuffer> completed) { (void)completed; dispatch_semaphore_signal(done); }];
        [commands commit];
        if (dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, 15*NSEC_PER_SEC)) ||
            commands.status != MTLCommandBufferStatusCompleted || commands.error) fail("GPU completion failed");
        for (unsigned i = 0; i < 4; ++i) if (values[i] != (i+1)*2+1) fail("GPU output mismatch");
        [rows addObject:@{@"iteration":@(iteration),@"pipeline_ms":@(pipelineMS),@"correct":@YES}];
    }}
    checkSinglePlugin(expected);
    NSData *result = [NSJSONSerialization dataWithJSONObject:@{@"explicit_plugin_binding":@YES,
        @"device_initialized":@YES,@"gpu_execution":@YES,@"library_ms":@(libraryMS),@"rows":rows}
        options:NSJSONWritingSortedKeys error:&error];
    if (!result) fail("JSON encoding failed");
    printf("result: %s\n", [[NSString alloc] initWithData:result encoding:NSUTF8StringEncoding].UTF8String);
    // Keep the explicit image resident until process exit. Unloading Objective-C
    // classes or the backend while callbacks may exist would be unsafe.
    return 0;
}}
#endif
