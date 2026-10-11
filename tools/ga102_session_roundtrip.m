// Bounded public read-only session IPC diagnostic. No private values exported.
#include <CoreGraphics/CoreGraphics.h>
#include <CoreFoundation/CoreFoundation.h>
#include <stdio.h>
#include <time.h>
#include <unistd.h>

int main(void) {
    for (unsigned index=0;index<12;index++) {
        uint64_t start=clock_gettime_nsec_np(CLOCK_UPTIME_RAW);
        CFDictionaryRef session=CGSessionCopyCurrentDictionary();
        uint64_t end=clock_gettime_nsec_np(CLOCK_UPTIME_RAW);
        int onConsole=0;
        if (session) {
            CFTypeRef value=CFDictionaryGetValue(session,kCGSessionOnConsoleKey);
            if (value && CFGetTypeID(value)==CFBooleanGetTypeID()) onConsole=CFBooleanGetValue((CFBooleanRef)value);
        }
        printf("result: {\"index\":%u,\"latency_ms\":%.9f,\"available\":%s,\"on_console\":%s}\n",index,(end-start)/1e6,session ? "true":"false",onConsole ? "true":"false");
        if (session) CFRelease(session);
        fflush(stdout);
        if (index<11) usleep(125000);
    }
    return 0;
}
