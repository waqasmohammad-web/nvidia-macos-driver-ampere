// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
#import <Foundation/Foundation.h>
#define NVMTL_AIR_TEXT_ENTRIES 3u
#define NVMTL_AIR_TEXT_BYTES 512u
#include "nvmtl_air_text_cache.h"
#include <assert.h>
int main(void) { @autoreleasepool {
    assert(!nvmtl_air_text_cached(nil,nil));
    NSMutableString *k=[@"owned.ll" mutableCopy], *v=[@"original IR" mutableCopy];
    assert([nvmtl_air_text_cached(k,v) isEqualToString:@"original IR"]);
    [k appendString:@"changed"]; [v appendString:@"changed"];
    assert([nvmtl_air_text_cached(@"owned.ll",nil) isEqualToString:@"original IR"]);
    assert(!nvmtl_air_text_cached(@"owned.u2.ll",nil));
    nvmtl_air_text_cached(@"second",@"b"); nvmtl_air_text_cached(@"third",@"c");
    nvmtl_air_text_cached(@"fourth",@"d");
    assert(!nvmtl_air_text_cached(@"owned.ll",nil)); // Entry count eviction.
    NSString *large=[@"x" stringByPaddingToLength:200 withString:@"x" startingAtIndex:0];
    nvmtl_air_text_cached(@"payload1",large); nvmtl_air_text_cached(@"payload2",large);
    assert(!nvmtl_air_text_cached(@"payload1",nil)); // Payload budget eviction.
    NSString *oversize=[@"x" stringByPaddingToLength:300 withString:@"x" startingAtIndex:0];
    assert(!nvmtl_air_text_cached(@"oversize",oversize));
    assert([nvmtl_air_text_cached(@"payload2",nil) isEqualToString:large]);
    // Two keys under the limits; concurrent immutable values must never cross.
    dispatch_apply(8,dispatch_get_global_queue(QOS_CLASS_DEFAULT,0),^(size_t worker){
        @autoreleasepool { for(unsigned i=0;i<128;i++) {
            NSString *key=worker%2 ? @"thread.u2.ll" : @"thread.ll";
            NSString *value=worker%2 ? @"unrolled" : @"plain";
            assert([nvmtl_air_text_cached(key,value) isEqualToString:value]);
        }}
    });
    puts("PASS: immutable snapshots, option keys, capacity/payload eviction, oversized rejection, concurrent values");
    return 0;
}}
