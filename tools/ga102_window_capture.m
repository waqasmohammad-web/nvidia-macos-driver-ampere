// Only image capture of a supplied owned probe window, never a display filter.
#import <Foundation/Foundation.h>
#import <AppKit/AppKit.h>
#import <ScreenCaptureKit/ScreenCaptureKit.h>
#import <CoreGraphics/CoreGraphics.h>

@interface GA102CaptureReply : NSObject
@property BOOL done;
@property(strong) SCShareableContent *content;
@property CGImageRef image;
@end
@implementation GA102CaptureReply
- (void)dealloc { if (_image) CGImageRelease(_image); }
@end

static BOOL awaitReply(GA102CaptureReply *reply) {
    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:5];
    while ([deadline timeIntervalSinceNow] > 0) {
        @synchronized(reply) { if (reply.done) return YES; }
        [[NSRunLoop currentRunLoop] runMode:NSDefaultRunLoopMode
                              beforeDate:[NSDate dateWithTimeIntervalSinceNow:.01]];
    }
    return NO;
}

static int sampleImage(CGImageRef image, unsigned char *rgb) {
        unsigned char *pixels = calloc(640 * 360, 4);
        if (!pixels) return -6;
        CGColorSpaceRef space = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
        CGContextRef context = CGBitmapContextCreate(pixels,640,360,8,640*4,space,
            kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Big);
        CGColorSpaceRelease(space);
        if (!context) { free(pixels); return -6; }
        CGContextDrawImage(context, CGRectMake(0,0,640,360), image);
        size_t index = 0;
        for (int cell = 0; cell < 8; cell++) {
            int x[3] = {cell*80+20,cell*80+20,cell*80+60}, y[3] = {20,180,180};
            for (int point = 0; point < 3; point++)
                for (int channel = 0; channel < 3; channel++)
                    rgb[index++] = pixels[(y[point]*640+x[point])*4+channel];
        }
        CGContextRelease(context); free(pixels); return 0;
}

int ga102_capture_preflight(void) { return CGPreflightScreenCaptureAccess() ? 1 : 0; }

// RGB samples only: 8 cells, each sampled at top bit strip and two center points.
// Caller binds both identifiers to its own child; mismatched ownership is refused.
int ga102_capture_window(unsigned windowID, int ownerPID, unsigned char *rgb, size_t length) {
    @autoreleasepool {
        if (!CGPreflightScreenCaptureAccess()) return -1;
        if (!rgb || length != 72 || ownerPID <= 0) return -2;
        // A Python host has no NSApplication yet. SCK's window APIs require its
        // CoreGraphics connection; this creates only a client in this process.
        [NSApplication sharedApplication];
        [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];
        GA102CaptureReply *list = [GA102CaptureReply new];
        [SCShareableContent getShareableContentExcludingDesktopWindows:YES onScreenWindowsOnly:YES
            completionHandler:^(SCShareableContent *content, NSError *error) {
                @synchronized(list) { list.content = error ? nil : content; list.done = YES; }
            }];
        if (!awaitReply(list)) return -3;
        SCWindow *own = nil;
        for (SCWindow *window in list.content.windows)
            if (window.windowID == windowID && window.owningApplication.processID == ownerPID) { own = window; break; }
        if (!own) return -4;
        SCContentFilter *filter = [[SCContentFilter alloc] initWithDesktopIndependentWindow:own];
        SCStreamConfiguration *config = [SCStreamConfiguration new];
        config.width = 640; config.height = 360; config.showsCursor = NO; config.ignoreShadowsSingleWindow = YES;
        config.colorSpaceName = kCGColorSpaceSRGB;
        GA102CaptureReply *image = [GA102CaptureReply new];
        [SCScreenshotManager captureImageWithFilter:filter configuration:config
            completionHandler:^(CGImageRef value, NSError *error) {
                @synchronized(image) { if (value && !error) image.image = CGImageRetain(value); image.done = YES; }
            }];
        if (!awaitReply(image)) return -3;
        if (!image.image) return -5;
        return sampleImage(image.image, rgb);
    }
}

// Known CPU-owned BGRA fixture tests normalization independently of capture/GPU.
int ga102_capture_conversion_control(void) {
    @autoreleasepool {
        [NSApplication sharedApplication];
        unsigned char *data = calloc(640 * 360, 4);
        if (!data) return -1;
        for (int y=0;y<360;y++) for (int x=0;x<640;x++) {
            unsigned char *p=data+(y*640+x)*4;
            int channel=(x/80)%3;
            p[2-channel]=255; p[3]=255;
        }
        CGColorSpaceRef space=CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
        CGDataProviderRef provider=CGDataProviderCreateWithData(NULL,data,640*360*4,NULL);
        CGImageRef image=CGImageCreate(640,360,8,32,640*4,space,
            kCGImageAlphaPremultipliedFirst|kCGBitmapByteOrder32Little,provider,NULL,NO,kCGRenderingIntentDefault);
        unsigned char samples[72]; int result=image ? sampleImage(image,samples) : -1;
        if (!result) for (int i=0;i<72;i++) {
            int expected=(i%3)==((i/9)%3) ? 255:0;
            if (abs((int)samples[i]-expected)>2) { result=1; break; }
        }
        if (image) CGImageRelease(image);
        CGDataProviderRelease(provider); CGColorSpaceRelease(space); free(data);
        return result;
    }
}
