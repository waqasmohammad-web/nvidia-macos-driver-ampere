#!/usr/bin/env python3
"""Extract the real capacity-release method and test application-held monitors."""
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def method(source):
    start=source.index('- (void)nvmtlReleaseCapacity {')
    end=source.index('\n- (void)nvmtlRecordEncodingError:',start)
    return source[start:end]


def main():
    candidate=(ROOT/'plugin/NVMTLObjects.m').read_text()
    baseline=subprocess.check_output(['git','-C',str(ROOT),'show','4095041:plugin/NVMTLObjects.m'],text=True)
    with tempfile.TemporaryDirectory() as directory:
        p=Path(directory)
        for name,body,expected in [('baseline',method(baseline),0),('candidate',method(candidate),200)]:
            code=r'''
#import <Foundation/Foundation.h>
#import <dispatch/dispatch.h>
@interface NVMTLCommandQueue:NSObject { @public dispatch_semaphore_t _capacity; }
@end
@implementation NVMTLCommandQueue @end
@interface NVMTLCommandBuffer:NSObject { @public BOOL _capacityHeld; NVMTLCommandQueue *_queue; }
- (void)nvmtlReleaseCapacity;
@end
@implementation NVMTLCommandBuffer
''' + body + r'''
@end
int main(void) { @autoreleasepool {
    unsigned progress=0;
    dispatch_queue_t worker=dispatch_queue_create("owned-completion-test",DISPATCH_QUEUE_SERIAL);
    for (unsigned i=0;i<200;++i) { @autoreleasepool {
        NVMTLCommandQueue *q=[NVMTLCommandQueue new];q->_capacity=dispatch_semaphore_create(0);
        NVMTLCommandBuffer *b=[NVMTLCommandBuffer new];b->_queue=q;b->_capacityHeld=YES;
        dispatch_semaphore_t done=dispatch_semaphore_create(0);
        @synchronized(b) {
            dispatch_async(worker,^{[b nvmtlReleaseCapacity];dispatch_semaphore_signal(done);});
            if (!dispatch_semaphore_wait(done,dispatch_time(DISPATCH_TIME_NOW,20*NSEC_PER_MSEC))) progress++;
        }
        // Always drain after releasing the monitor: the baseline is bounded.
        dispatch_sync(worker,^{});
        if (dispatch_semaphore_wait(q->_capacity,DISPATCH_TIME_NOW)) return 2;
        dispatch_apply(8,dispatch_get_global_queue(QOS_CLASS_DEFAULT,0),^(size_t k){(void)k;[b nvmtlReleaseCapacity];});
        if (!dispatch_semaphore_wait(q->_capacity,DISPATCH_TIME_NOW)) return 3;
    }}
    printf("monitor progress %u/200; exactly-once release verified\n",progress);
    return progress == EXPECTED ? 0 : 4;
}}
'''
            (p/(name+'.m')).write_text(code)
            subprocess.run(['xcrun','clang','-fobjc-arc','-fblocks','-O1','-Wall','-Wextra','-Werror',
                            '-DEXPECTED='+str(expected),str(p/(name+'.m')),'-framework','Foundation','-o',str(p/name)],check=True)
            subprocess.run([str(p/name)],check=True,timeout=15)


if __name__=='__main__': main()
