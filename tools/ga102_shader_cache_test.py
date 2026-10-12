#!/usr/bin/env python3
"""Measure production shader-transform memo retention with CPU-only fixtures.

The lowering function is replaced with immutable tracked NSData payloads. This
tests memoization/ownership, not shader translation, GPU execution or desktop
memory pressure. Each case runs in a fresh process; logs remain private.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
PREAMBLE=r'''
#import <Foundation/Foundation.h>
#include <pthread.h>
#include <stdatomic.h>
#include <assert.h>
#include <string.h>
static _Atomic uint64_t liveBytes, lowerCalls;
@interface TrackedPayload:NSData { void *_bytes; NSUInteger _length; }
- (instancetype)initWithLength:(NSUInteger)length byte:(unsigned char)byte;
@end
@implementation TrackedPayload
- (instancetype)initWithLength:(NSUInteger)length byte:(unsigned char)byte {
    self=[super init]; if(self) { _length=length;_bytes=malloc(length);assert(_bytes);
        memset(_bytes,byte,length);atomic_fetch_add(&liveBytes,length); } return self;
}
- (NSUInteger)length {return _length;}
- (const void *)bytes {return _bytes;}
- (void)dealloc {atomic_fetch_sub(&liveBytes,_length);free(_bytes);}
@end
static NSData *nvmtl_address_shader_g_uncached(const void *data,size_t len,uint32_t flags,uint32_t *info) {
    atomic_fetch_add(&lowerCalls,1);unsigned char byte=len ? ((const unsigned char *)data)[0]:0;
    info[0]=flags;info[1]=(uint32_t)len;info[2]=byte;info[3]=0x1234;
    if(byte==0xff)return nil;
    size_t size=byte>=0x90 && byte<0xa0 ? 12u*1024u*1024u:byte==0xee ? 65u*1024u*1024u:32;
    return [[TrackedPayload alloc]initWithLength:size byte:byte^(unsigned char)flags];
}
'''
MAIN=r'''
static void check(const void *key,size_t len,uint32_t flags) {
    uint32_t got[4]={0};NSData *d=nvmtl_address_shader_g(key,len,flags,got);
    unsigned char byte=len ? ((const unsigned char *)key)[0]:0;
    assert(got[0]==flags && got[1]==len && got[2]==byte && got[3]==0x1234);
    if(byte==0xff) {assert(!d);return;}
    assert(d.length);const unsigned char *p=d.bytes;
    assert(p[0]==(byte^(unsigned char)flags) && p[d.length-1]==p[0]);
}
int main(int argc,char **argv) { @autoreleasepool {
    if(argc!=2)return 2;NSString *mode=@(argv[1]);uint64_t maximum=0;
    if([mode isEqual:@"payload"]) {
        for(unsigned char i=0x90;i<0x96;++i) {
            @autoreleasepool {check(&i,1,0);}
            uint64_t live=atomic_load(&liveBytes);if(live>maximum)maximum=live;
        }
        assert(TEST_EXPECT_BOUNDED ? maximum<=64u*1024u*1024u:maximum>64u*1024u*1024u);
    } else if([mode isEqual:@"oversized"]) {
        unsigned char key=0xee;
        for(unsigned i=0;i<2;++i) {@autoreleasepool {check(&key,1,0);}}
        maximum=atomic_load(&liveBytes);
        assert(atomic_load(&lowerCalls)==(TEST_EXPECT_BOUNDED ? 2:1));
        assert(TEST_EXPECT_BOUNDED ? maximum==0:maximum>64u*1024u*1024u);
    } else if([mode isEqual:@"keys"]) {
        unsigned char key=5;check(&key,1,0);check(&key,1,1);key=6;check(&key,1,0);key=5;check(&key,1,0);
        assert(atomic_load(&lowerCalls)==3);
        key=0xff;check(&key,1,0);check(&key,1,0);check(&key,1,1);assert(atomic_load(&lowerCalls)==5);
    } else if([mode isEqual:@"count"]) {
        // Keep the first byte outside the large/nil fixture selectors.
        for(uint32_t i=0;i<4097;++i) {@autoreleasepool {uint32_t key=i<<8;check(&key,sizeof key,0);}}
        uint64_t before=atomic_load(&lowerCalls);uint32_t key=0;check(&key,sizeof key,0);
        assert(atomic_load(&lowerCalls)==before+1);
    } else if([mode isEqual:@"concurrent"]) {
        dispatch_apply(16,dispatch_get_global_queue(QOS_CLASS_DEFAULT,0),^(size_t worker) {
            @autoreleasepool {for(unsigned i=0;i<100;++i) {unsigned char key=(worker+i)%32;check(&key,1,i%2);}}
        });
    } else return 2;
    if(!maximum)maximum=atomic_load(&liveBytes);
    printf("{\"correct\":true,\"tracked_retained_value_bytes\":%llu,\"lower_calls\":%llu}\n",
           (unsigned long long)maximum,(unsigned long long)atomic_load(&lowerCalls));
    return 0;
}}
'''


def helper(source):
    start=source.index('static NSData *nvmtl_address_shader_g(const void *data, size_t len, uint32_t flags, uint32_t *info) {')
    return source[start:source.index('static NSData *nvmtl_address_shader_g_uncached(',start)]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--baseline-only',action='store_true')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    original=subprocess.check_output(['git','show','ab1cf45:plugin/nvmtl_vk.c'],cwd=ROOT,text=True)
    sources=[('original',original,False)]
    if not args.baseline_only:sources.append(('candidate',(ROOT/'plugin/nvmtl_vk.c').read_text(),True))
    rows=[]
    for label,source,bounded in sources:
        function=helper(source);unit=args.output/(label+'.m');unit.write_text(PREAMBLE+function+MAIN)
        for sanitizer,cases in [('address,undefined',['payload','oversized','keys','count']),('thread',['concurrent'])]:
            exe=args.output/(label+'-'+sanitizer.replace(',','-'))
            with (args.output/(exe.name+'-compile.private.log')).open('w') as log:
                subprocess.run(['xcrun','clang','-fobjc-arc','-O1','-DTEST_EXPECT_BOUNDED='+str(int(bounded)),
                                '-fsanitize='+sanitizer,str(unit),'-framework','Foundation','-o',str(exe)],
                               stdout=log,stderr=subprocess.STDOUT,check=True,timeout=30)
            for case in cases:
                r=subprocess.run([str(exe.resolve()),case],capture_output=True,text=True,timeout=20)
                (args.output/(exe.name+'-'+case+'.private.log')).write_text(r.stdout+r.stderr)
                if r.returncode:raise SystemExit(f'FAIL: {label} {case}; private evidence retained')
                row=json.loads(r.stdout);row.update(variant=label,case=case,sanitizer=sanitizer,
                    production_helper_sha256=hashlib.sha256(function.encode()).hexdigest())
                rows.append(row)
    (args.output/'results.json').write_text(json.dumps({'rows':rows,'limits':'CPU lowering stub; tracked output payload only, not RSS or desktop workloads'},indent=2)+'\n')
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
