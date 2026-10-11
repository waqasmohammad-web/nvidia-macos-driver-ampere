// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Read-only API capability check: no command submission, other-process access,
// XPC service, permission request, driver injection, or persistent handle file.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>

int main(void) {
    @autoreleasepool {
        id<MTLDevice> device=nil;
        for (id<MTLDevice> candidate in MTLCopyAllDevices())
            if ([candidate.name containsString:@"3080 Ti"]) {device=candidate; break;}
        id<MTLSharedEvent> event=[device newSharedEvent];
        BOOL valueOK=NO;
        if (event) {event.signaledValue=7;valueOK=event.signaledValue==7;}
        // Objective-C allows a nil return to be observed without assuming the
        // SDK's nonnull shared-handle contract or trapping a Swift bridge.
        MTLSharedEventHandle *handle=event ? [event newSharedEventHandle]:nil;
        id<MTLSharedEvent> imported=handle ? [device newSharedEventWithHandle:handle]:nil;
        NSString *exportStatus=!event ? @"NOT VERIFIED":handle ? @"PASS":@"FAIL";
        NSDictionary *result=@{@"probe":@"shared_event_handle_capability",
            @"target_device_available":@(device != nil),@"event_created":@(event != nil),
            @"same_process_value_roundtrip":event ? (valueOK ? @"PASS":@"FAIL"):@"NOT VERIFIED",
            @"handle_export":exportStatus,
            @"same_process_handle_import":handle ? (imported ? @"PASS":@"FAIL"):@"NOT VERIFIED",
            @"cross_process_ordering":@"NOT VERIFIED",@"desktop_causality":@"NOT VERIFIED",
            @"scope":@"API handle creation/reimport only; no GPU work or XPC transfer"};
        NSData *json=[NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingSortedKeys error:NULL];
        printf("result: %s\n",[[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding].UTF8String);
        return device ? 0:2;
    }
}
