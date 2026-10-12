import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from build import build_isolated_plugin as builder
from build.ga102_perf_instrumentation import instrument, once
from tools import ga102_graphics_perf as perf


class GraphicsPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Exercise the real source-pinning gate even when developing in a dirty
        # checkout. The integration fixture uses committed production inputs.
        cls.source_parent=tempfile.TemporaryDirectory()
        cls.pinned_source=Path(cls.source_parent.name)/'pinned'
        subprocess.run(['git','-C',str(perf.ROOT),'worktree','add','--detach',str(cls.pinned_source),'HEAD'],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):
        subprocess.run(['git','-C',str(perf.ROOT),'worktree','remove',str(cls.pinned_source)],check=True,capture_output=True)
        cls.source_parent.cleanup()

    def test_owned_cache_rejects_tokens_permissions_and_symlinks(self):
        with tempfile.TemporaryDirectory() as parent:
            root,token=perf.new_cache(parent)
            perf.verify_cache(root,token)
            with self.assertRaises(ValueError): perf.verify_cache(root,'0'*64)
            (root/'air').chmod(0o755)
            with self.assertRaises(ValueError): perf.verify_cache(root,token)
            (root/'air').chmod(0o700)
            (root/'air'/'escape').symlink_to(parent)
            with self.assertRaises(ValueError): perf.verify_cache(root,token)

    def test_descriptor_pool_comparison_keeps_other_source_gates(self):
        a={'nvmtl_vk.c':'a','NVMTLObjects.m':'b'}
        b={**a,'nvmtl_vk.c':'c'}
        perf.verify_plugin_inputs(a,a)
        with self.assertRaises(ValueError): perf.verify_plugin_inputs(a,b)
        perf.verify_plugin_inputs(a,b,True)
        for bad in ({**b,'NVMTLObjects.m':'d'}, {'nvmtl_vk.c':'c'}, {**b,'extra.c':'e'}):
            with self.assertRaises(ValueError): perf.verify_plugin_inputs(a,bad,True)

    def test_real_portable_C_cache_metrics_and_capture_controls(self):
        with tempfile.TemporaryDirectory() as parent:
            base=Path(parent); root,token=perf.new_cache(base)
            unit=base/'proof.c'
            unit.write_text('#include "'+str(perf.ROOT/'tools/ga102_perf/metrics.h')+'"\n'+r'''
#include <pthread.h>
static void *worker(void *p) { (void)p; for(int i=0;i<1000;++i)ga102_hit(GA102_LOCAL_HIT); return NULL; }
int main(void) {
    ga102_owned_air(); ga102_owned_mesa();
    uint64_t t=ga102_tick(); ga102_record(GA102_VK_PIPELINE,ga102_tick()-t,0);
    ga102_record(GA102_PIPELINE_TOTAL,ga102_tick()-t,0);
    pthread_t threads[4];
    for(int i=0;i<4;++i)if(pthread_create(&threads[i],NULL,worker,NULL))return 2;
    for(int i=0;i<4;++i)if(pthread_join(threads[i],NULL))return 3;
    // Exercises capture I/O only; deliberately not a shader/validator fixture.
    uint8_t bytes[20]={0}; ga102_capture(GA102_RUST,bytes,sizeof bytes);
    puts(ga102_metrics_json()); return 0;
}
''')
            exe=base/'proof'
            # Darwin hides O_NOFOLLOW under strict XSI feature selection. Keep
            # the no-symlink checks enabled in the actual sanitized C proof.
            feature_flags=['-D_XOPEN_SOURCE=700']
            if perf.sys.platform == 'darwin': feature_flags.append('-D_DARWIN_C_SOURCE')
            compiled=subprocess.run(['cc','-std=c11',*feature_flags,'-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined',str(unit),'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            env={**os.environ,'GA102_TEST_CACHE':str(root),'GA102_TEST_TOKEN':token}
            env.pop('MESA_SHADER_CACHE_DISABLE',None)
            output=subprocess.run([str(exe)],env=env,capture_output=True,text=True,check=True)
            m=json.loads(output.stdout); perf.metrics(m)
            self.assertEqual(m['local_hit']['count'],4000)
            self.assertEqual(m['vk_pipeline']['count'],1)
            self.assertEqual(m['pipeline_total']['count'],1)
            self.assertGreaterEqual(m['pipeline_total']['ns'],m['vk_pipeline']['ns'])
            self.assertEqual(list((root/'capture').iterdir()),[])
            captured=subprocess.run([str(exe)],env={**env,'GA102_TEST_CAPTURE':'1'},capture_output=True,text=True)
            self.assertEqual(captured.returncode,0,captured.stderr)
            self.assertEqual(len(list((root/'capture').glob('*.spv'))),1)
            for change in ({'GA102_TEST_TOKEN':'1'*64},{'MESA_SHADER_CACHE_DISABLE':'true'},{'GA102_TEST_CACHE':str(base)},{'NVMTL_VENDOR_COMPILER':'1'}):
                out=subprocess.run([str(exe)],env={**env,**change},capture_output=True,text=True)
                self.assertNotEqual(out.returncode,0)
                self.assertIn('GA102 isolation failure',out.stderr)
            (root/'spvcache').rmdir(); (root/'spvcache').symlink_to(base)
            out=subprocess.run([str(exe)],env=env,capture_output=True,text=True)
            self.assertNotEqual(out.returncode,0); self.assertIn('GA102 isolation failure',out.stderr)

    def test_prepare_only_transforms_actual_sites_without_changing_production(self):
        originals={p.name:perf.sha(p) for p in (perf.ROOT/'plugin').iterdir() if p.is_file()}
        with tempfile.TemporaryDirectory() as parent:
            out=Path(parent)/'snapshot'
            with patch('sys.argv',['builder','--source-root',str(self.pinned_source),'--prepare-only','--graphics-performance','--output',str(out),'--translator','/owned/translator.dylib','--icd','/retained/nvk.dylib','--air-runtime','/retained/runtime']):
                builder.main()
            proof=json.loads((out/'preparation-proof.json').read_text())
            self.assertIsNone(proof['binary_sha256']); self.assertFalse(proof['runtime_executed'])
            source=out/'source'; library=(source/'NVMTLLibraryLoad.m').read_text(); objects=(source/'NVMTLObjects.m').read_text(); vk=(source/'nvmtl_vk.c').read_text()
            cache_function=library.split('static NSString *nvmtl_aircache_dir(void) {')[1].split('static _Atomic unsigned long gSpvHit')[0]
            self.assertIn('ga102_owned_air()',cache_function)
            self.assertNotIn('NVMTL_AIRCACHE',cache_function)
            # The actual production environment/config constructor is byte-identical
            # after namespace conversion; this profile does not edit its safety policy.
            original=(perf.ROOT/'plugin/NVMTLObjects.m').read_text()
            def constructor(s): return s.split('__attribute__((constructor)) static void nvmtl_conf_knobs(void)')[1].split('static int nvmtl_dontcare_clears')[0]
            self.assertEqual(constructor(original),constructor(objects))
            self.assertIn('ga102_hit(selected ? GA102_LOCAL_HIT : GA102_LOCAL_MISS)',objects)
            self.assertIn('ga102_hit(selected ? GA102_DEVICE_HIT : GA102_DEVICE_MISS)',objects)
            self.assertIn('ga102_actual_sampler(',library)
            self.assertIn('ga102_record(GA102_VK_PIPELINE',vk)
            self.assertIn('ga102_record(GA102_PIPELINE_TOTAL',vk)
            self.assertEqual(proof['performance']['profile'],'ga102-graphics-v2')
            self.assertIn('loader fallback prohibited',vk)
            self.assertIn('in-memory AIR extraction failed; fallback prohibited',library)
            with self.assertRaises(ValueError): instrument(source,Path('/x'),Path('/y'))
        self.assertEqual(originals,{p.name:perf.sha(p) for p in (perf.ROOT/'plugin').iterdir() if p.is_file()})
        for text in ('absent','site site'):
            with self.assertRaises(ValueError): once(text,'site','new')

    def test_descriptor_breakdown_is_opt_in_and_uses_actual_initialization(self):
        with tempfile.TemporaryDirectory() as parent:
            for enabled in (False,True):
                out=Path(parent)/str(enabled)
                args=['builder','--source-root',str(self.pinned_source),'--prepare-only','--graphics-performance','--output',str(out),'--translator','/owned/translator.dylib','--icd','/retained/nvk.dylib','--air-runtime','/retained/runtime']
                if enabled: args.append('--preparation-breakdown')
                with patch('sys.argv',args): builder.main()
                proof=json.loads((out/'preparation-proof.json').read_text())
                self.assertEqual(proof['performance']['preparation_breakdown'],enabled)
                vk=(out/'source/nvmtl_vk.c').read_text()
                self.assertEqual('ga102_preparation:' in vk,enabled)
                if enabled:
                    body=vk.split('static int ensure_descriptors_locked(void)')[1].split('static int ensure_descriptors(void)')[0]
                    self.assertLess(body.index('if (g_descriptor_state)'),body.index('descriptorT=ga102_tick()'))
                    self.assertLess(body.index('poolT=ga102_tick()'),body.index('nvmtl_desc_pool_open()'))
                    self.assertLess(body.index('nvmtl_desc_pool_open()'),body.index('poolNS=ga102_tick()-poolT'))
                    self.assertLess(body.index('nvmtl_sampler_acquire'),body.index('resourceNS=ga102_tick()-resourceT'))
                    self.assertLess(body.index('zeroT=ga102_tick()'),body.index('nvmtl_vk_zero_dummies();'))
                    self.assertLess(body.index('nvmtl_vk_zero_dummies();'),body.index('zeroNS=ga102_tick()-zeroT'))
                    self.assertLess(body.index('heapT=ga102_tick()'),body.index('if (g_bindless)'))
                    self.assertLess(body.index('pvkUpdateDescriptorSets'),body.index('heapNS=ga102_tick()-heapT'))
                    self.assertLess(body.index('g_descriptor_state = 1;'),body.index('ga102_preparation:'))

    @staticmethod
    def fixture(condition='cold'):
        def blank():return {k:dict(count=0,ns=0,failures=0) for k in perf.EVENTS}
        state=blank(); rows=[]
        for label in perf.LABELS:
            before=copy.deepcopy(state); counts={}
            if label=='library':counts={'air_miss':1,'air_extract':1} if condition=='cold' else {'index_disk_hit':1}
            elif label.startswith('pipeline-'):
                counts={'vk_pipeline':1}
                if label=='pipeline-initial':counts.update({'rust':2,'spv_miss':2} if condition=='cold' else {'spv_hit':2})
            else:
                counts={'sampler_bind':1,'local_lookup':1,'local_miss':1,'device_lookup':1,'device_miss':1,'variant_build':1,'sampler_abi':1,'vk_pipeline':1}
                if label.endswith('local-hit'):counts={'sampler_bind':1,'local_lookup':1,'local_hit':1}
                elif label.endswith('device-hit'):counts={'sampler_bind':1,'local_lookup':1,'local_miss':1,'device_lookup':1,'device_hit':1}
            for k,n in counts.items():state[k]['count']+=n; state[k]['ns']+=n*100
            row=dict(label=label,before=before,after=copy.deepcopy(state),wall_ns=100)
            if not label.startswith('pipeline') and label!='library':
                f=0 if label.startswith('nearest') else 1
                row.update(filter=f,checked_pixels=1024,max_error=0,center_rgba=[64,96,80,255] if f==0 else [56,104,80,255])
            rows.append(row)
        paths=dict(translator='/owned/xlate',icd='/retained/icd',llvm='/retained/llvm',plugin='/owned/plugin',cache='/owned/cache')
        images=[paths['translator']]*3+[paths['icd']]*2+[paths['llvm'] if condition=='cold' else None]
        result=dict(schema_version=1,records=rows,final_metrics=state,
                    provenance=dict(images=images,inventory=images+[paths['plugin']],cache=paths['cache'],mesa='/owned/cache/mesa',namespace_verified=True))
        return result,paths

    def test_acceptance_requires_actual_branches_pixels_images_and_cache_conditions(self):
        for condition in ('cold','reuse'):
            result,paths=self.fixture(condition); perf.validate_record(result,condition,paths)
            mutations=[lambda r:r['records'][2]['after']['sampler_abi'].update(count=0),
                       lambda r:r['records'][3]['after']['local_hit'].update(count=0),
                       lambda r:r['records'][7]['after']['device_hit'].update(count=0),
                       lambda r:r['records'][2].update(center_rgba=[0,0,0,0]),
                       lambda r:r['records'][2].update(max_error=3),
                       lambda r:r['provenance']['images'].__setitem__(1,'/installed/xlate'),
                       lambda r:r['provenance'].update(cache='/driver/cache'),
                       lambda r:r['records'][2]['after']['vk_pipeline'].update(failures=1),
                       lambda r:r['final_metrics']['vk_error'].update(count=1,failures=1),
                       lambda r:r['records'][2].update(encode_ns=float('nan')),
                       lambda r:r['records'].pop()]
            for mutate in mutations:
                changed=copy.deepcopy(result);mutate(changed)
                with self.assertRaises(ValueError):perf.validate_record(changed,condition,paths)
            with self.assertRaises(ValueError):perf.validate_record(result,'reuse' if condition=='cold' else 'cold',paths)

    def test_shader_is_runtime_bound_and_expected_filters_differ(self):
        shader=perf.FIXTURE.read_text()
        self.assertIn('[[sampler(3)]]',shader); self.assertNotIn('constexpr',shader)
        self.assertIn('image.sample(bound',shader)
        # Independent bilinear interpolation oracle, not just the fixture constants.
        corners=[(1,3),(2,3),(1,4),(2,4)]; weights=[.1875,.5625,.0625,.1875]
        result=[round(sum(w*(32*x if c==0 else 32*y if c==1 else 16*(x+y)) for (x,y),w in zip(corners,weights))) for c in range(3)]
        self.assertEqual(result,[56,104,80]); self.assertNotEqual(result,[64,96,80])

    def diagnostic_fixture(self,condition,first):
        result,paths=self.fixture(condition)
        result.update(schema_version=2,sampler_first=first)
        for row in result['records']:
            for name in ('before','after'):
                driver=row[name]['vk_pipeline']
                row[name]['pipeline_total']=dict(count=driver['count'],ns=driver['ns']*2,failures=0)
        driver=result['final_metrics']['vk_pipeline']
        result['final_metrics']['pipeline_total']=dict(count=driver['count'],ns=driver['ns']*2,failures=0)
        # Reconstruct a monotonic timeline after reordering the operations.
        by_label={row['label']:row for row in result['records']}
        running={k:dict(count=0,ns=0,failures=0) for k in perf.DIAGNOSTIC_EVENTS}
        rows=[]
        for label in perf.labels(first):
            row=copy.deepcopy(by_label[label]); change=perf.delta(row)
            row['before']=copy.deepcopy(running)
            for key in running:
                for field in running[key]: running[key][field]+=change[key][field]
            row['after']=copy.deepcopy(running); rows.append(row)
        result['records']=rows; result['final_metrics']=running
        return result,paths

    def test_diagnostic_orders_require_inclusive_timing_and_preserve_gates(self):
        for condition in ('cold','reuse'):
            for first in ('nearest','linear'):
                result,paths=self.diagnostic_fixture(condition,first)
                perf.validate_record(result,condition,paths)
                mutations=[lambda r:r['records'][1]['after']['pipeline_total'].update(ns=0),
                           lambda r:r['records'][1]['after']['pipeline_total'].update(count=0),
                           lambda r:r.update(sampler_first='unexpected'),
                           lambda r:r['records'][2].update(center_rgba=[0,0,0,0]),
                           lambda r:r['records'][2]['after']['pipeline_total'].update(failures=1),
                           lambda r:r['records'][2]['after'].pop('pipeline_total'),
                           lambda r:r['final_metrics']['pipeline_total'].update(count=0)]
                for mutate in mutations:
                    changed=copy.deepcopy(result); mutate(changed)
                    with self.assertRaises(ValueError): perf.validate_record(changed,condition,paths)

    def test_pairing_keeps_process_conditions_and_qualification_separate(self):
        rows=[]
        for pair in (0,1,2):
            for condition in ('cold','reuse'):
                for arm in ('baseline','candidate'):
                    result,paths=self.diagnostic_fixture(condition,'linear')
                    d=perf.validate_record(result,condition,paths)
                    if arm=='candidate':
                        for events in d.values():
                            for item in events.values(): item['ns']*=.8 if condition=='cold' else 1.1
                    rows.append(dict(pair=pair,condition=condition,arm=arm,qualification=pair==0,differences=d))
        report=perf.paired_statistics(rows)
        cold=report['cold:nearest-miss:vk_pipeline']; reuse=report['reuse:nearest-miss:vk_pipeline']
        self.assertEqual(cold['n'],2); self.assertEqual(cold['faster_pairs'],2)
        self.assertAlmostEqual(cold['paired_median_change_percent'],20)
        self.assertEqual(reuse['faster_pairs'],0); self.assertAlmostEqual(reuse['paired_median_change_percent'],-10)
        self.assertEqual([p['pair'] for p in cold['pairs']],[1,2])
        for invalid in (rows[:-1],rows+[rows[-1]]):
            with self.assertRaises(ValueError): perf.paired_statistics(invalid)

    def test_unknown_non_system_dependency_is_not_auto_accepted(self):
        perf.verify_inventory(['/usr/lib/libSystem.B.dylib','/owned/nvk'],{'/owned/nvk'})
        with self.assertRaises(ValueError):perf.verify_inventory(['/unexpected/driver'],{'/owned/nvk'})

    def test_linux_refuses_darwin_commands_before_execution(self):
        with patch('sys.platform','linux'),patch('sys.argv',['runner','prepare-metallib','--output','/not-created']),patch.object(perf,'prepare_metallib') as execute:
            with self.assertRaises(SystemExit):perf.main()
            execute.assert_not_called()

if __name__=='__main__':unittest.main()
