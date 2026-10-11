#!/usr/bin/env python3
"""Compare pre-fix/current AIR selector and decoder functions on one owned shader.

Foundation directory search is redirected to fixtures; all cache mutations stay
under a new output directory. CPU libLLVM is loaded read-only, never the candidate
Metal plugin. Three fresh processes per case; IR equality and exact hit/miss/store
counts are required. Times cover AIR decoding/cache lookup, not GPU compilation,
WindowServer or desktop presentation. No elevation, install or reboot.
"""
import pathlib,subprocess,json,shutil,statistics,argparse

# CPU-only production-function comparison. No candidate plugin is loaded.
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--bitcode",type=pathlib.Path,required=True)
parser.add_argument("--output",type=pathlib.Path,required=True)
parser.add_argument("--runtime",type=pathlib.Path,default=pathlib.Path("/Library/GPUBundles/NVMTLDriver.bundle/Contents/MacOS/air-runtime"))
parser.add_argument("--memory-cache",action="store_true",help="Compare current decoder against 005d714; both use corrected directory selection")
args=parser.parse_args()
if not args.bitcode.is_file() or not (args.runtime/"libLLVM.dylib").is_file(): parser.error("Test bitcode and original CPU LLVM runtime are required")
if args.output.exists(): parser.error("Output must be new; no cache or artifact overwrites")
args.output.mkdir(parents=True)
root=pathlib.Path(__file__).resolve().parents[2];work=args.output.resolve()
current=(root/'plugin/NVMTLLibraryLoad.m').read_text()
old=subprocess.check_output(['git','show',('005d714' if args.memory_cache else '0176303')+':plugin/NVMTLLibraryLoad.m'],text=True,cwd=root)
preamble=r"""#import <Foundation/Foundation.h>
#import <CommonCrypto/CommonDigest.h>
#include <dlfcn.h>
#include <stdatomic.h>
#include <spawn.h>
#include <sys/wait.h>
#include <signal.h>
#include <errno.h>
#include <fcntl.h>
#include <time.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "nvmtl_mesa_cache.h"
extern char **environ;
static void nvlog(const char *fmt,...) { (void)fmt; }
#define NVMTL_AIR_OPT "/Library/GPUBundles/nvmtl/air-opt"
static _Atomic unsigned long gAirHit,gAirMiss,gAirStored,gAirMemoryHit;
static NSString *testBase,*testTemp;
#define NSSearchPathForDirectoriesInDomains(...) @[testBase]
#define NSTemporaryDirectory() testTemp
"""
main=r"""
int main(int argc,char **argv){@autoreleasepool{
 if(argc!=4)return 2;unsetenv("NVMTL_AIRCACHE");unsetenv("NVMTL_NO_AIR_UNROLL");
 testBase=@(argv[2]);testTemp=@(argv[3]);NSData *bc=[NSData dataWithContentsOfFile:@(argv[1])];if(!bc.length)return 3;
 NSMutableArray *times=[NSMutableArray new];NSString *first=nil;
 for(int i=0;i<21;i++){
 uint64_t t=clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW);NSString *s=nvmtl_air_to_text(bc);
 double ms=(clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW)-t)/1e6;
 if(![s containsString:@"ga102_cache_probe"] || (first && ![s isEqualToString:first]))return 4;
 if(!first)first=s;[times addObject:@(ms)];}
 NSData *text=[first dataUsingEncoding:NSUTF8StringEncoding]; unsigned char h[CC_SHA256_DIGEST_LENGTH]; char hex[65]; CC_SHA256(text.bytes,(CC_LONG)text.length,h); for(int k=0;k<32;k++)snprintf(hex+2*k,3,"%02x",h[k]);
 NSData *out=[NSJSONSerialization dataWithJSONObject:@{@"memory_hits":@(gAirMemoryHit),@"hits":@(gAirHit),@"misses":@(gAirMiss),@"stores":@(gAirStored),@"ms":times,@"correct_identical_IR":@YES,@"ir_sha256":@(hex)} options:0 error:nil];
 puts([[NSString alloc]initWithData:out encoding:NSUTF8StringEncoding].UTF8String);return 0;
}}
"""
results={}
reuse={}
for case in ['valid','file']:
 folder=work/case;folder.mkdir();globalcache=folder/'global';user=folder/'user';tmp=folder/'tmp';tmp.mkdir()
 for variant,source in [('original',old),('corrected',current)]:
  selector=source[source.index('static NSString *nvmtl_aircache_dir(void)'):source.index('static _Atomic unsigned long gSpvHit')]
  decoder_source = source if args.memory_cache else current
  decoder=decoder_source[decoder_source.index('static BOOL nvmtl_air_unroll_wanted(NSData *air);'):decoder_source.index('static BOOL nvmtl_entry_of')]
  if not args.memory_cache:
   # Historical selector-only comparison retains the pre-memory decoder.
   decoder_source=subprocess.check_output(['git','show','005d714:plugin/NVMTLLibraryLoad.m'],text=True,cwd=root)
   decoder=decoder_source[decoder_source.index('static BOOL nvmtl_air_unroll_wanted(NSData *air);'):decoder_source.index('static BOOL nvmtl_entry_of')]
  build=folder/variant;build.mkdir();(build/'air-runtime').symlink_to(args.runtime.resolve(),target_is_directory=True)
  unit=build/'test.m';unit.write_text(preamble+selector+decoder+main)
  exe=build/'test'
  with (build/'compile.log').open('w') as log:
   subprocess.run(['xcrun','clang','-fobjc-arc','-O1','-D_DARWIN_C_SOURCE','-Wno-deprecated-declarations','-DNVMTL_AIRCACHE_DIR='+json.dumps(str(globalcache)),'-I'+str(root/'plugin'),str(unit),'-framework','Foundation','-o',str(exe)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=30)
  runs=[]
  for repeat in range(3):
   for path in [user,globalcache]:
    if path.is_dir():shutil.rmtree(path)
    elif path.exists():path.unlink()
   user.mkdir()
   if case=='valid':globalcache.mkdir()
   else:globalcache.write_text('test-owned non-directory cache path')
   r=subprocess.run([str(exe),str(args.bitcode.resolve()),str(user),str(tmp)],capture_output=True,text=True,timeout=15)
   if r.returncode:raise RuntimeError(str(r.returncode)+r.stderr)
   row=json.loads(r.stdout);runs.append(row)
   if args.memory_cache: assert row['memory_hits']==(20 if variant=='corrected' else 0)
   expected=(20,1,1) if args.memory_cache or case=='valid' or variant=='corrected' else (0,21,0)
   assert (row['hits'],row['misses'],row['stores'])==expected,(case,variant,row)
  results[case+'_'+variant]=runs
  # Reuse the last run's disk cache from a fresh process, without deleting it.
  r=subprocess.run([str(exe),str(args.bitcode.resolve()),str(user),str(tmp)],capture_output=True,text=True,timeout=15)
  if r.returncode:raise RuntimeError(str(r.returncode)+r.stderr)
  row=json.loads(r.stdout)
  expected=(21,0,0) if args.memory_cache or case=='valid' or variant=='corrected' else (0,21,0)
  assert (row['hits'],row['misses'],row['stores'])==expected
  assert row['ir_sha256']==runs[0]['ir_sha256']
  if args.memory_cache: assert row['memory_hits']==(20 if variant=='corrected' else 0)
  reuse[case+'_'+variant]=row
assert len({r["ir_sha256"] for runs in results.values() for r in runs})==1, "IR differs between original/corrected or processes"
summary={}
for key,runs in results.items():
 warm=sorted(x for r in runs for x in r['ms'][1:]);cold=[r['ms'][0] for r in runs]
 summary[key]={'repeats':3,'cold_ms':cold,'warm_p50_ms':statistics.median(warm),'warm_p95_ms':warm[int(.95*(len(warm)-1))],'memory_hits_per_run':runs[0]['memory_hits'],'hits_per_run':runs[0]['hits'],'misses_per_run':runs[0]['misses'],'stores_per_run':runs[0]['stores'],'reuse_process_first_ms':reuse[key]['ms'][0],'reuse_process_hits':reuse[key]['hits']}
(work/'results.json').write_text(json.dumps({'summary':summary,'runs':results,'reuse':reuse},indent=2))
print(json.dumps(summary,indent=2))
