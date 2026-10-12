#!/usr/bin/env python3
"""Fail-closed owned graphics A/B preparation and execution. No default launch.

Darwin-only subcommands need separate authorization. Linux can test the policy,
source transformation and real translator ABI without loading any Apple library.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import statistics
import subprocess
import sys
import tempfile
import shutil
try:
    from .ga102_run_metal import run_owned
except ImportError:
    from ga102_run_metal import run_owned

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT/'tools/ga102_perf/runtime_sampler.metal'
EVENTS = ('air_extract','reflect','rust','sampler_abi','lower','vk_pipeline','local_hit','local_miss',
          'device_hit','device_miss','variant_build','air_memory_hit','air_disk_hit','air_miss','spv_hit','spv_miss',
          'index_disk_hit','sampler_bind','local_lookup','device_lookup','vk_error')
DIAGNOSTIC_EVENTS = EVENTS + ('pipeline_total',)
LABELS = ('library','pipeline-initial','nearest-miss','nearest-local-hit','linear-miss',
          'linear-local-hit','pipeline-equivalent','nearest-device-hit','linear-device-hit')
SYSTEM_IMAGES=('/System/Library/','/usr/lib/','/Library/Apple/System/Library/')


def labels(sampler_first):
    if sampler_first not in ('nearest','linear'): raise ValueError('unknown sampler order')
    second='linear' if sampler_first=='nearest' else 'nearest'
    return ('library','pipeline-initial',sampler_first+'-miss',sampler_first+'-local-hit',
            second+'-miss',second+'-local-hit','pipeline-equivalent',
            sampler_first+'-device-hit',second+'-device-hit')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def private(path, directory):
    st=path.lstat()
    if path.is_symlink() or (path.is_dir() if directory else path.is_file()) is False or st.st_uid != os.getuid() or st.st_mode & 0o777 != (0o700 if directory else 0o600):
        raise ValueError('owned private directory/file required: '+str(path))


def new_cache(parent):
    # mkdtemp establishes a new root; never adopt an existing installed cache.
    root=Path(tempfile.mkdtemp(prefix='ga102-owned-',dir=parent)).resolve()
    token=secrets.token_hex(32)
    marker=root/'.ga102-owned'; marker.write_text(token); marker.chmod(0o600)
    for name in ('air','spvcache','mesa','capture'): (root/name).mkdir(mode=0o700)
    verify_cache(root,token)
    return root,token


def verify_cache(root,token):
    if str(root.resolve()) != str(root): raise ValueError('canonical root required')
    private(root,True); private(root/'.ga102-owned',False)
    if len(token) != 64 or (root/'.ga102-owned').read_text() != token: raise ValueError('cache token mismatch')
    for name in ('air','spvcache','mesa','capture'): private(root/name,True)
    for p in root.rglob('*'):
        if p.is_symlink(): raise ValueError('cache descendant symlink refused')


def cache_snapshot(root):
    return {name:{'files':len(files),'bytes':sum(p.stat().st_size for p in files)}
            for name in ('air','spvcache','mesa','capture')
            for files in [[p for p in (root/name).rglob('*') if p.is_file()]]}


def metrics(value):
    if not isinstance(value,dict) or set(value) not in (set(EVENTS),set(DIAGNOSTIC_EVENTS)): raise ValueError('missing/unknown metrics')
    for item in value.values():
        if not isinstance(item,dict) or set(item) != {'count','ns','failures'}: raise ValueError('metric fields')
        if any(type(n) is not int or n < 0 for n in item.values()) or item['failures'] > item['count']: raise ValueError('invalid metric')
    return value


def delta(row):
    a,b=metrics(row['before']),metrics(row['after'])
    if set(a)!=set(b): raise ValueError('metrics schema changed during operation')
    d={key:{field:b[key][field]-a[key][field] for field in a[key]} for key in a}
    if any(n < 0 for item in d.values() for n in item.values()): raise ValueError('metrics went backwards')
    if any(item['failures'] for item in b.values()): raise ValueError('measured operation failed')
    return d


def validate_record(result,condition,paths):
    if condition not in ('cold','reuse'): raise ValueError('unknown cache condition')
    rows=result.get('records',[])
    schema=result.get('schema_version')
    first=result.get('sampler_first','nearest')
    if schema not in (1,2) or (schema==1 and first!='nearest') or [r.get('label') for r in rows] != list(labels(first)): raise ValueError('operation sequence incomplete')
    provenance=result.get('provenance',{})
    final=metrics(result['final_metrics'])
    event_names=DIAGNOSTIC_EVENTS if schema==2 else EVENTS
    if set(final)!=set(event_names): raise ValueError('metric schema does not match record version')
    expected_images=[paths['translator']]*3+[paths['icd']]*2+[paths['llvm'] if final['air_extract']['count'] else None]
    if provenance.get('images') != expected_images or provenance.get('namespace_verified') is not True:
        raise ValueError('actual function images not verified')
    if provenance.get('cache') != paths['cache'] or provenance.get('mesa') != str(Path(paths['cache'])/'mesa'):
        raise ValueError('effective cache path mismatch')
    inventory=provenance.get('inventory',[])
    if not inventory or any(p not in inventory for p in expected_images+[paths['plugin']] if p is not None): raise ValueError('dyld dependency inventory incomplete')
    previous={key:{field:0 for field in ('count','ns','failures')} for key in event_names}
    totals={key:0 for key in event_names}; differences={}
    for row in rows:
        d=delta(row); differences[row['label']]=d
        if set(d)!=set(event_names): raise ValueError('inconsistent metric schema')
        if any(row['before'][key][field] < previous[key][field] for key in event_names for field in previous[key]): raise ValueError('record timeline went backwards')
        previous=row['after']
        for key in event_names: totals[key]+=d[key]['count']
        if schema==2:
            if d['pipeline_total']['count']!=d['vk_pipeline']['count'] or d['pipeline_total']['ns']<d['vk_pipeline']['ns']:
                raise ValueError('inclusive pipeline timing/count differs from Vulkan creation')
        for name in ('wall_ns','encode_ns','completion_ns','readback_ns','gpu_ns'):
            if name in row and (isinstance(row[name],bool) or not isinstance(row[name],(int,float)) or not math.isfinite(row[name]) or row[name]<0):
                raise ValueError('invalid timing')
        label=row['label']
        if 'hit' in label or label.endswith('-miss'):
            filter_index=0 if label.startswith('nearest') else 1
            expected=[64,96,80,255] if filter_index == 0 else [56,104,80,255]
            rgba=row.get('center_rgba',[])
            if row.get('filter') != filter_index or row.get('checked_pixels') != 1024 or type(row.get('max_error')) is not int or not 0 <= row['max_error'] <= 2 or len(rgba)!=4 or any(type(x) is not int or abs(x-e)>2 for x,e in zip(rgba,expected)):
                raise ValueError('GPU pixel oracle failed')
            expected_counts = {'local_hit':0,'local_miss':1,'device_hit':0,'device_miss':1,'variant_build':1,'sampler_abi':1,'vk_pipeline':1}
            if label.endswith('local-hit'):
                expected_counts.update(local_hit=1,local_miss=0,device_miss=0,variant_build=0,sampler_abi=0,vk_pipeline=0)
            elif label.endswith('device-hit'):
                expected_counts.update(device_hit=1,device_miss=0,variant_build=0,sampler_abi=0,vk_pipeline=0)
            if any(d[k]['count'] != n for k,n in expected_counts.items()) or d['sampler_bind']['count'] != 1:
                raise ValueError('actual sampler miss/hit path differs: '+label)
        elif label.startswith('pipeline-'):
            if d['vk_pipeline']['count'] != 1: raise ValueError('public pipeline did not execute exactly one Vulkan creation')
    final=metrics(result['final_metrics'])
    if any(final[k][f] < previous[k][f] for k in event_names for f in previous[k]) or any(v['failures'] for v in final.values()): raise ValueError('final metrics invalid')
    if totals['sampler_abi'] != 2 or totals['variant_build'] != 2: raise ValueError('sampler ABI/build evidence absent')
    # Persistent reuse must not suppress the two fresh-process sampler variants.
    if condition == 'cold':
        if not all(totals[k] > 0 for k in ('air_miss','air_extract','rust','spv_miss')): raise ValueError('owned-cold compilation not exercised')
        if any(totals[k] for k in ('air_disk_hit','spv_hit','index_disk_hit')): raise ValueError('cold caches were already populated')
    else:
        if any(totals[k] for k in ('air_miss','air_extract','rust','spv_miss')): raise ValueError('persistent reuse recompiled ordinary shaders')
        if not (totals['spv_hit'] > 0 and totals['index_disk_hit'] > 0): raise ValueError('persistent cache hits not observed')
    return differences


def artifact(plugin):
    plugin=plugin.resolve(); proof=json.loads((plugin.parent/'isolation-proof.json').read_text())
    perf=proof.get('performance',{})
    if proof.get('schema_version') != 2 or proof.get('class_prefix') != 'NVMTLGA102_' or not proof.get('c_symbols_hidden') or proof.get('binary_sha256') != sha(plugin) or perf.get('profile') != 'ga102-graphics-v2':
        raise ValueError('compiled performance profile proof required')
    if perf.get('metrics_header_sha256') != sha(ROOT/'tools/ga102_perf/metrics.h') or perf.get('transformer_sha256') != sha(ROOT/'build/ga102_perf_instrumentation.py'):
        raise ValueError('instrumentation revision mismatch')
    for name,digest in perf['transformed_source_sha256'].items():
        if sha(plugin.parent/'source'/name) != digest: raise ValueError('transformed input changed')
    translator=(plugin.parent/'libnvmtl_translate.dylib').resolve()
    build_proof=translator.with_name('translator-proof.json')
    build=json.loads(build_proof.read_text())
    if sha(build_proof) != proof.get('translator_build_proof_sha256') or build.get('source_commit') != proof.get('source_commit') or build.get('binary_sha256') != sha(translator) or build.get('build_succeeded') is not True:
        raise ValueError('translator build/source provenance mismatch')
    icd=Path(proof['icd_path']).resolve(); llvm=Path(proof['air_runtime_path']).resolve()
    hashes={str(plugin):sha(plugin),str(translator):sha(translator),str(icd):sha(icd),str(llvm):sha(llvm)}
    hashes[str(build_proof)]=sha(build_proof)
    if hashes[str(translator)] != proof.get('translator_sha256') or hashes[str(icd)] != proof.get('icd_sha256') or hashes[str(llvm)] != proof.get('air_runtime_sha256'):
        raise ValueError('dependency hash mismatch')
    proof['translator_build']=build
    return dict(plugin=str(plugin),translator=str(translator),icd=str(icd),llvm=str(llvm)),hashes,proof


def summary(samples):
    s=sorted(samples)
    q=statistics.quantiles(s,n=4,method='inclusive') if len(s)>=2 else [s[0]]*3
    mean=statistics.mean(s)
    return dict(n=len(s),median_ns=statistics.median(s),p95_ns=s[math.ceil(.95*len(s))-1],
                min_ns=min(s),max_ns=max(s),iqr_ns=q[2]-q[0],cv_percent=100*statistics.pstdev(s)/mean if mean else None,samples_ns=samples)


def paired_statistics(rows):
    """Pair process measurements; never pool cold/reuse or qualification data."""
    groups={}
    for row in rows:
        if row['qualification']: continue
        key=(row['pair'],row['condition'])
        if row['arm'] not in ('baseline','candidate') or row['condition'] not in ('cold','reuse'):
            raise ValueError('unknown comparison arm/condition')
        group=groups.setdefault(key,{})
        if row['arm'] in group: raise ValueError('duplicate comparison arm')
        group[row['arm']]=row
    output={}
    for (pair,condition),group in sorted(groups.items()):
        if set(group)!= {'baseline','candidate'}: raise ValueError('incomplete paired comparison')
        for label in LABELS:
            for event in ('sampler_abi','vk_pipeline','pipeline_total','sampler_bind','lower'):
                a=group['baseline']['differences'][label].get(event)
                b=group['candidate']['differences'][label].get(event)
                if a is None and b is None: continue  # Legacy v1 has no inclusive span.
                if a is None or b is None or a['count']!=b['count']:
                    raise ValueError('comparison event counts differ')
                if not a['count']: continue
                if a['ns']<=0 or b['ns']<=0: raise ValueError('nonpositive comparison span')
                key=f'{condition}:{label}:{event}'
                output.setdefault(key,[]).append(dict(pair=pair,baseline_ns=a['ns'],candidate_ns=b['ns'],
                    saved_ns=a['ns']-b['ns'],change_percent=100*(1-b['ns']/a['ns'])))
    return {key:dict(pairs=values,paired_median_change_percent=statistics.median(v['change_percent'] for v in values),
                    paired_median_saved_ns=statistics.median(v['saved_ns'] for v in values),
                    faster_pairs=sum(v['saved_ns']>0 for v in values),n=len(values))
            for key,values in output.items()}


def verify_inventory(inventory,approved):
    for path in inventory:
        if not isinstance(path,str): raise ValueError('invalid image inventory')
        if not path.startswith(SYSTEM_IMAGES) and path not in approved:
            raise ValueError('unreviewed non-system loaded dependency: '+path)


def captures(root):
    modules=[]
    for p in sorted((root/'capture').glob('*.spv')):
        subprocess.run(['spirv-val','--target-env','vulkan1.2','--scalar-block-layout',str(p)],check=True,capture_output=True,timeout=10)
        modules.append((p.name.split('-')[0],sha(p)))
    if not modules: raise ValueError('no actual SPIR-V captured')
    sampler=[digest for event,digest in modules if event=='3']
    if len(sampler)!=2 or len(set(sampler))!=2:
        raise ValueError('nearest/linear sampler ABI must emit two distinct real modules')
    return Counter(modules)


def prepare_metallib(output):
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    air=output/'runtime_sampler.air'; lib=output/'runtime_sampler.metallib'
    commands=[['xcrun','--sdk','macosx','metal','-c',str(FIXTURE),'-o',str(air)],
              ['xcrun','--sdk','macosx','metallib',str(air),'-o',str(lib)]]
    for i,cmd in enumerate(commands):
        with (output/f'compile-{i}.log').open('w') as log:
            subprocess.run(cmd,check=True,stdout=log,stderr=subprocess.STDOUT,timeout=90)
    sdk=subprocess.run(['xcrun','--sdk','macosx','--show-sdk-version'],check=True,capture_output=True,text=True,timeout=10).stdout.strip()
    (output/'fixture-proof.json').write_text(json.dumps(dict(source_sha256=sha(FIXTURE),metallib_sha256=sha(lib),sdk=sdk,commands=commands),indent=2)+'\n')


def prepare_translator(source,output,target):
    source=source.resolve(); output=output.resolve(); target=target.resolve()
    status=subprocess.run(['git','-C',str(source),'status','--porcelain','--untracked-files=all','--','plugin','translator',':(exclude)translator/translator/target',':(exclude)translator/wrapper/target'],check=True,capture_output=True,text=True)
    if status.stdout.strip(): raise ValueError('translator source must be pinned and clean')
    def git(revision): return subprocess.run(['git','-C',str(source),'rev-parse',revision],check=True,capture_output=True,text=True).stdout.strip()
    commit,tree=git('HEAD'),git('HEAD^{tree}')
    files=subprocess.run(['git','-C',str(source),'ls-files','translator'],check=True,capture_output=True,text=True).stdout.splitlines()
    inputs={p:sha(source/p) for p in files}
    output.mkdir(parents=True,mode=0o700,exist_ok=False)
    command=['cargo','build','--offline','--locked','--release','--lib','--target','x86_64-apple-darwin',
             '--manifest-path',str(source/'translator/wrapper/Cargo.toml'),'--target-dir',str(target)]
    env={**os.environ,'CARGO_BUILD_JOBS':'1','CARGO_PROFILE_RELEASE_CODEGEN_UNITS':'16','CARGO_PROFILE_RELEASE_INCREMENTAL':'false'}
    # Exclude inherited Rust flags/profile overrides from a nominally identical A/B.
    for key in list(env):
        if key in ('RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS') or key.startswith('CARGO_PROFILE_RELEASE_') and key not in ('CARGO_PROFILE_RELEASE_CODEGEN_UNITS','CARGO_PROFILE_RELEASE_INCREMENTAL'):
            env.pop(key)
    rust=subprocess.run(['rustc','--version'],check=True,text=True,capture_output=True,timeout=10).stdout.strip()
    sdk=subprocess.run(['xcrun','--sdk','macosx','--show-sdk-version'],check=True,text=True,capture_output=True,timeout=10).stdout.strip()
    with (output/'translator-build.log').open('w') as log:
        if run_owned(command,log,600,env): raise ValueError('translator build failed')
    if git('HEAD') != commit or inputs != {p:sha(source/p) for p in files}: raise ValueError('source changed during build')
    binary=output/'libnvmtl_translate.dylib'
    shutil.copyfile(target/'x86_64-apple-darwin/release/libnvmtl_translate.dylib',binary)
    proof=dict(source_commit=commit,source_tree=tree,input_sha256=inputs,binary_sha256=sha(binary),
               build_succeeded=True,command=command,rust=rust,sdk=sdk,opt_level=3,codegen_units=16,incremental=False,jobs=1)
    (output/'translator-proof.json').write_text(json.dumps(proof,indent=2)+'\n')


def execute(args):
    if any(k.startswith('DYLD_') for k in os.environ): raise ValueError('inherited DYLD overrides refused')
    fixture_proof=json.loads(args.metallib.with_name('fixture-proof.json').read_text())
    if fixture_proof.get('source_sha256') != sha(FIXTURE) or fixture_proof.get('metallib_sha256') != sha(args.metallib): raise ValueError('owned fixture proof mismatch')
    arms={}; dependency_hashes={}; proofs={}
    for name,path in [('baseline',args.baseline_plugin),('candidate',args.candidate_plugin)]:
        arms[name],hashes,proofs[name]=artifact(path); dependency_hashes.update(hashes)
    if arms['baseline']['icd'] != arms['candidate']['icd'] or arms['baseline']['llvm'] != arms['candidate']['llvm']:
        raise ValueError('A/B requires identical retained ICD and AIR runtime')
    if proofs['baseline']['source_sha256'] != proofs['candidate']['source_sha256']: raise ValueError('plugin inputs differ in translator-only A/B')
    if proofs['baseline'].get('source_commit') != args.baseline_commit or proofs['candidate'].get('source_commit') != args.candidate_commit:
        raise ValueError('pinned source commit mismatch')
    for field in ('rust','sdk','opt_level','codegen_units','incremental','jobs'):
        if field not in proofs['baseline']['translator_build'] or proofs['baseline']['translator_build'][field] != proofs['candidate']['translator_build'].get(field):
            raise ValueError('baseline/candidate build settings differ: '+field)
    dependency_hashes[str(args.metallib.resolve())]=sha(args.metallib)
    manifest=json.loads(args.dependency_manifest.read_text())
    if manifest.get('reviewed') is not True or not isinstance(manifest.get('files'),dict):
        raise ValueError('reviewed non-system dependency closure manifest required')
    for path,digest in manifest['files'].items():
        if str(Path(path).resolve()) != path or sha(path) != digest: raise ValueError('dependency manifest mismatch')
        if path in dependency_hashes and dependency_hashes[path] != digest: raise ValueError('conflicting dependency hash')
        dependency_hashes[path]=digest
    dependency_hashes[str(args.dependency_manifest.resolve())]=sha(args.dependency_manifest)
    args.output.mkdir(mode=0o700,parents=True,exist_ok=False)
    exe=args.output/'graphics-probe'; obj=args.output/'binding.o'
    commands=[['xcrun','clang','-arch','x86_64','-fobjc-arc','-O1','-Wall','-Wextra','-Werror','-DGA102_BINDING_ONLY=1','-DGA102_PERFORMANCE=1','-c',str(ROOT/'tools/ga102_isolated_plugin_probe.m'),'-o',str(obj)],
              ['xcrun','swiftc','-O','-module-cache-path',str(args.output/'modules'),str(ROOT/'tools/ga102_perf/graphics.swift'),str(obj),'-framework','IOKit','-o',str(exe)]]
    for i,cmd in enumerate(commands):
        with (args.output/f'probe-build-{i}.log').open('w') as log:
            if run_owned(cmd,log,90): raise ValueError('probe compilation failed')
    exe_hash=sha(exe); rows=[]; qualification={}
    approved_images=set(dependency_hashes)|{str(exe.resolve())}
    for pair in range(args.pairs+1):
        order=['baseline','candidate'] if pair%2==0 else ['candidate','baseline']
        for arm in order:
            root,token=new_cache(args.output)
            for condition in ('cold','reuse'):
                verify_cache(root,token); before_cache=cache_snapshot(root)
                if condition=='cold' and any(v['files'] for v in before_cache.values()): raise ValueError('cold root not empty')
                for path,digest in dependency_hashes.items():
                    if sha(path)!=digest: raise ValueError('candidate/dependency changed before launch')
                env={k:v for k,v in os.environ.items() if not k.startswith(('GA102_','MESA_','XDG_CACHE_','NVMTL_','NVK_','NVRM_','NAK_','VK_'))}
                env.update(GA102_PLUGIN_IMAGE=arms[arm]['plugin'],GA102_PLUGIN_NAMESPACE='NVMTLGA102_',
                    GA102_PLUGIN_TRANSLATOR=arms[arm]['translator'],GA102_PLUGIN_LOWER_PROBE='1',GA102_TEST_ICD=arms[arm]['icd'],
                    GA102_TEST_LLVM=arms[arm]['llvm'],GA102_TEST_CACHE=str(root),GA102_TEST_TOKEN=token)
                env['GA102_TEST_SAMPLER_FIRST']=args.sampler_first
                if pair==0: env['GA102_TEST_CAPTURE']='1'
                paths={**arms[arm],'cache':str(root)}
                log_path=args.output/f'{pair}-{arm}-{condition}.private.log'
                with log_path.open('w') as log:
                    rc=run_owned([str(exe),str(args.metallib.resolve())],log,45,env)
                for path,digest in dependency_hashes.items():
                    if sha(path)!=digest: raise ValueError('candidate/dependency changed during execution')
                if sha(exe)!=exe_hash: raise ValueError('probe binary changed')
                verify_cache(root,token)
                lines=log_path.read_text().splitlines(); results=[json.loads(x[8:]) for x in lines if x.startswith('result: ')]
                if rc or len(results)!=1 or any(lines.count(x)!=1 for x in ('binding_verified: true','binding_namespace_verified: true','binding_translator_verified: true','binding_lowering_verified: true')) or any('duplicate' in x.lower() and 'class' in x.lower() for x in lines):
                    raise ValueError('child or independent provenance marker failed: '+str(log_path))
                if results[0].get('schema_version')!=2 or results[0].get('sampler_first')!=args.sampler_first:
                    raise ValueError('requested diagnostic profile/order not executed')
                differences=validate_record(results[0],condition,paths)
                verify_inventory(results[0]['provenance']['inventory'],approved_images)
                row=dict(pair=pair,arm=arm,condition=condition,qualification=pair==0,records=results[0]['records'],
                         cache_before=before_cache,cache_after=cache_snapshot(root),differences=differences)
                rows.append(row)
                if pair==0:
                    qualification[arm,condition]=captures(root)
                    # Keep captured artifacts for evidence; move to an owned leaf so
                    # the reuse capture has an independent multiset.
                    keep=root/f'capture-{condition}'; (root/'capture').rename(keep); (root/'capture').mkdir(mode=0o700)
        if pair==0:
            for condition in ('cold','reuse'):
                if qualification['baseline',condition] != qualification['candidate',condition]: raise ValueError('baseline/candidate SPIR-V differs')
    stats={}
    for arm in arms:
        for condition in ('cold','reuse'):
            for label in LABELS:
                selected=[r for r in rows if not r['qualification'] and r['arm']==arm and r['condition']==condition]
                for event in ('air_extract','reflect','rust','sampler_abi','lower','vk_pipeline','pipeline_total','sampler_bind','local_lookup','device_lookup'):
                    values=[r['differences'][label][event]['ns'] for r in selected if r['differences'][label][event]['count']]
                    if values: stats[f'{arm}:{condition}:{label}:{event}']=summary(values)
    # Raw paths/image inventories stay only in private logs. Preserve raw timings.
    report=dict(status='PASS',scope='owned offscreen graphics only',sampler_first=args.sampler_first,fixture_sha256=sha(args.metallib),fixture_source_sha256=sha(FIXTURE),
                source_commits={k:proofs[k]['source_commit'] for k in arms},paired_statistics=paired_statistics(rows),
                dependency_hashes={arm:{kind:sha(arms[arm][kind]) for kind in ('plugin','translator','icd','llvm')} for arm in arms},probe_sha256=exe_hash,rows=rows,statistics=stats,
                limits=['Internal sampler reflection is included in sampler ABI time.','Mesa file persistence is not driver cache-hit attribution.',
                        'Owned-cache cold only; Apple/OS/internal driver caches and GPU clocks are uncontrolled.','No desktop/FPS/scanout conclusion.'])
    (args.output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__); commands=p.add_subparsers(dest='command',required=True)
    prep=commands.add_parser('prepare-metallib'); prep.add_argument('--output',type=Path,required=True)
    translator=commands.add_parser('prepare-translator'); translator.add_argument('--source-root',type=Path,required=True)
    translator.add_argument('--output',type=Path,required=True); translator.add_argument('--target-dir',type=Path,required=True)
    run=commands.add_parser('run'); run.add_argument('--baseline-plugin',type=Path,required=True); run.add_argument('--candidate-plugin',type=Path,required=True)
    run.add_argument('--metallib',type=Path,required=True); run.add_argument('--output',type=Path,required=True)
    run.add_argument('--baseline-commit',required=True); run.add_argument('--candidate-commit',required=True)
    run.add_argument('--dependency-manifest',type=Path,required=True,help='Reviewed canonical non-system image paths and SHA256 closure; no runtime auto-acceptance')
    run.add_argument('--pairs',type=int,choices=range(1,11),default=1); run.add_argument('--execute-reviewed',action='store_true')
    run.add_argument('--sampler-first',choices=('nearest','linear'),default='nearest',help='Use separate matched sessions for each order to control first-variant effects')
    args=p.parse_args()
    if sys.platform!='darwin': p.error('NEEDS MACOS VALIDATION: this command cannot execute on Linux')
    if args.command=='run' and not args.execute_reviewed: p.error('BLOCKED: reviewed execution authorization flag required')
    try:
        if args.command=='prepare-metallib': prepare_metallib(args.output)
        elif args.command=='prepare-translator': prepare_translator(args.source_root,args.output,args.target_dir)
        else: execute(args)
    except (ValueError,OSError,subprocess.SubprocessError) as error:
        print('FAIL/BLOCKED: '+str(error),file=sys.stderr); return 1
    return 0

if __name__=='__main__': raise SystemExit(main())
