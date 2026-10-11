// Only image capture of a supplied owned probe window, never a display filter.
#import <Foundation/Foundation.h>
#import <AppKit/AppKit.h>
#import <ScreenCaptureKit/ScreenCaptureKit.h>
#import <CoreGraphics/CoreGraphics.h>
#import <CoreMedia/CoreMedia.h>
#import <CoreVideo/CoreVideo.h>
#include <math.h>

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

// A single owned-window stream, bounded to 512 numeric sample records. No full
// frame, audio, image file, display filter, or other-window content is retained.
@interface GA102StreamReply : NSObject <SCStreamOutput, SCStreamDelegate>
@property(strong) SCStream *stream;
@property(strong) dispatch_queue_t queue;
@property(strong) NSMutableArray *records;
@property(strong) NSMutableDictionary *statuses;
@property BOOL failed;
@property BOOL overflow;
@end
@implementation GA102StreamReply
- (void)stream:(SCStream *)stream didStopWithError:(NSError *)error {
    (void)stream; (void)error; @synchronized(self) { self.failed = YES; }
}
- (void)stream:(SCStream *)stream didOutputSampleBuffer:(CMSampleBufferRef)sample ofType:(SCStreamOutputType)type {
    (void)stream;
    if (type != SCStreamOutputTypeScreen || !CMSampleBufferIsValid(sample)) return;
    @autoreleasepool {
        NSArray *attachments = (__bridge NSArray *)CMSampleBufferGetSampleAttachmentsArray(sample, NO);
        NSNumber *status = attachments.firstObject[SCStreamFrameInfoStatus];
        @synchronized(self) {
            if (!status) {self.failed = YES; return;}
            self.statuses[status.stringValue] = @([self.statuses[status.stringValue] unsignedIntegerValue] + 1);
        }
        if (status.integerValue != SCFrameStatusComplete) return;
        CVPixelBufferRef image = CMSampleBufferGetImageBuffer(sample);
        if (!image || CVPixelBufferGetPixelFormatType(image) != kCVPixelFormatType_32BGRA ||
            CVPixelBufferGetWidth(image) != 640 || CVPixelBufferGetHeight(image) != 360 ||
            CVPixelBufferLockBaseAddress(image, kCVPixelBufferLock_ReadOnly) != kCVReturnSuccess) {
            @synchronized(self) {self.failed = YES;} return;
        }
        const unsigned char *pixels = CVPixelBufferGetBaseAddress(image);
        size_t stride = CVPixelBufferGetBytesPerRow(image);
        NSMutableArray *rgb = [NSMutableArray arrayWithCapacity:72];
        if (pixels) for (int cell=0;cell<8;cell++) {
            int x[3]={cell*80+20,cell*80+20,cell*80+60}, y[3]={20,180,180};
            for (int point=0;point<3;point++) {
                const unsigned char *p=pixels+y[point]*stride+x[point]*4;
                [rgb addObject:@(p[2])]; [rgb addObject:@(p[1])]; [rgb addObject:@(p[0])];
            }
        }
        CVPixelBufferUnlockBaseAddress(image, kCVPixelBufferLock_ReadOnly);
        double pts=CMTimeGetSeconds(CMSampleBufferGetPresentationTimeStamp(sample));
        @synchronized(self) {
            if (rgb.count != 72 || !isfinite(pts)) self.failed = YES;
            else if (self.records.count >= 512) self.overflow = YES;
            else [self.records addObject:@{@"pts_seconds":@(pts), @"samples":rgb}];
        }
    }
}
@end
static GA102StreamReply *ga102Stream;

int ga102_stream_start(unsigned windowID, int ownerPID) {
    @autoreleasepool {
        if (ga102Stream) return -8;
        if (!CGPreflightScreenCaptureAccess()) return -1;
        if (ownerPID <= 0 || !windowID) return -2;
        [NSApplication sharedApplication]; [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];
        GA102CaptureReply *list=[GA102CaptureReply new];
        [SCShareableContent getShareableContentExcludingDesktopWindows:YES onScreenWindowsOnly:YES
            completionHandler:^(SCShareableContent *content, NSError *error) {
                @synchronized(list) {list.content=error ? nil:content; list.done=YES;}
            }];
        if (!awaitReply(list)) return -3;
        SCWindow *own=nil;
        for (SCWindow *window in list.content.windows)
            if (window.windowID == windowID && window.owningApplication.processID == ownerPID) {own=window; break;}
        if (!own) return -4;
        SCContentFilter *filter=[[SCContentFilter alloc] initWithDesktopIndependentWindow:own];
        SCStreamConfiguration *config=[SCStreamConfiguration new];
        config.width=640; config.height=360; config.showsCursor=NO; config.ignoreShadowsSingleWindow=YES;
        config.pixelFormat=kCVPixelFormatType_32BGRA; config.colorSpaceName=kCGColorSpaceSRGB;
        config.minimumFrameInterval=CMTimeMake(1,60); config.queueDepth=3; config.capturesAudio=NO;
        GA102StreamReply *collector=[GA102StreamReply new];
        collector.records=[NSMutableArray new]; collector.statuses=[NSMutableDictionary new];
        collector.queue=dispatch_queue_create("ga102.owned.capture",DISPATCH_QUEUE_SERIAL);
        collector.stream=[[SCStream alloc] initWithFilter:filter configuration:config delegate:collector];
        NSError *error=nil;
        if (![collector.stream addStreamOutput:collector type:SCStreamOutputTypeScreen sampleHandlerQueue:collector.queue error:&error]) return -5;
        GA102CaptureReply *ready=[GA102CaptureReply new];
        [collector.stream startCaptureWithCompletionHandler:^(NSError *failure) {
            @synchronized(collector) {collector.failed=failure != nil;}
            @synchronized(ready) {ready.done=YES;}
        }];
        ga102Stream=collector;
        if (!awaitReply(ready)) return -3;
        @synchronized(collector) {return collector.failed ? -5:0;}
    }
}

// Caller must copy/free this JSON. Stop affects only the stream created above.
char *ga102_stream_stop(void) {
    @autoreleasepool {
        GA102StreamReply *collector=ga102Stream;
        if (!collector) return NULL;
        GA102CaptureReply *ready=[GA102CaptureReply new];
        [collector.stream stopCaptureWithCompletionHandler:^(NSError *error) {
            @synchronized(collector) {if (error) collector.failed=YES;}
            @synchronized(ready) {ready.done=YES;}
        }];
        BOOL stopped=awaitReply(ready);
        // Drain our callback queue before copying numeric evidence.
        dispatch_sync(collector.queue, ^{});
        NSData *data;
        @synchronized(collector) {
            data=[NSJSONSerialization dataWithJSONObject:@{@"stopped":@(stopped),@"failed":@(collector.failed),
                @"overflow":@(collector.overflow),@"statuses":collector.statuses,@"records":collector.records}
                options:0 error:NULL];
        }
        [collector.stream removeStreamOutput:collector type:SCStreamOutputTypeScreen error:NULL];
        collector.stream=nil;
        ga102Stream=nil;
        return data ? strdup([[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding].UTF8String):NULL;
    }
}
void ga102_capture_free(void *pointer) { free(pointer); }
