// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Compile one owned shader with the original installed Metal driver and export
// its AIR text/bitcode. No queues, pipelines, command buffers or GPU submission.
// Uses NVMTLLibrary private ivars; fails if the original implementation changes.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <objc/runtime.h>
int main(int argc,char **argv){@autoreleasepool{
 if(argc!=2)return 2; if([[NSFileManager defaultManager] fileExistsAtPath:@(argv[1])] || [[NSFileManager defaultManager] fileExistsAtPath:[@(argv[1]) stringByAppendingPathExtension:@"bc"]])return 9;
 id<MTLDevice> d=MTLCreateSystemDefaultDevice();NSError *err=nil;
 NSString *s=@"#include <metal_stdlib>\nusing namespace metal; kernel void ga102_cache_probe(device float *a [[buffer(0)]], uint i [[thread_position_in_grid]]) { if(i<4) a[i]*=2.0f; }";
 id lib=[d newLibraryWithSource:s options:nil error:&err];
 if(!lib || ![NSStringFromClass([lib class]) containsString:@"NVMTL"])return 3;
 Ivar v=class_getInstanceVariable([lib class],"_airs");if(!v)return 4;
 id airs=object_getIvar(lib,v);NSString *ir=airs[@"ga102_cache_probe"];
 if(![ir containsString:@"ga102_cache_probe"])return 5;
 if(![ir writeToFile:@(argv[1]) atomically:YES encoding:NSUTF8StringEncoding error:&err])return 6;
 Ivar b=class_getInstanceVariable([lib class],"_fns");if(!b)return 7; NSData *bc=object_getIvar(lib,b)[@"ga102_cache_probe"]; if(!bc.length || ![bc writeToFile:[@(argv[1]) stringByAppendingPathExtension:@"bc"] atomically:YES])return 8;
 puts("PASS: test-owned shader AIR extracted; no command queue or GPU submission");return 0;
}}
