#!/usr/bin/env python3
"""Compare the actual Linux NVMTL translator ABI on existing owned shader fixtures.

Build the wrapper with cargo build --lib (no source-built validator dependency).
Pass explicit baseline/candidate shared libraries; this invokes no Vulkan/GPU APIs.
"""
import argparse
import ctypes
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
TEXTURES = 'translator/translator/src/native/tests/textures.rs'
INTERFACE = 'translator/translator/src/native/tests/interface.rs'
MISC = 'translator/translator/src/native/tests/misc.rs'
THREADGROUP = 'translator/translator/src/native/tests/threadgroup.rs'


def fixture(path, owner, variable='ll', constant=False):
    text = (ROOT / path).read_text()
    if constant:
        pattern = rf'const {re.escape(owner)}: &str = r#"(.*?)"#;'
    else:
        start = text.index('fn ' + owner + '(')
        end = text.find('\n#[test]', start)
        text = text[start:end if end >= 0 else len(text)]
        pattern = rf'let {re.escape(variable)} = r#"(.*?)"#;'
    match = re.search(pattern, text, re.S)
    if not match:
        raise ValueError(f'owned fixture missing: {path}:{owner}')
    return match.group(1).encode()


def state(filter_name='Nearest', coordinates='Pixel'):
    return dict(min_filter=filter_name, mag_filter=filter_name, mip_filter='None',
                address_mode_s='ClampToEdge', address_mode_t='ClampToEdge',
                address_mode_r='ClampToEdge', coordinates=coordinates,
                compare_function='None', max_anisotropy=1, lod_min_clamp=0.0,
                lod_max_clamp=65504.0, border_color='TransparentBlack',
                reduction='WeightedAverage', lod_bias=0.0)


class Translator:
    def __init__(self, path):
        self.path = path.resolve()
        self.lib = ctypes.CDLL(str(self.path))
        self.lib.nvmtl_translate_set_caps.argtypes = [ctypes.c_uint32]
        self.lib.nvmtl_translate_set_caps.restype = None
        self.call = self.lib.nvmtl_translate_samplers
        self.call.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
                              ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_size_t),
                              ctypes.c_void_p, ctypes.c_size_t]
        self.call.restype = ctypes.c_int
        self.lib.nvmtl_translate_free.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        self.lib.nvmtl_translate_free.restype = None
        self.lib.nvmtl_translate_set_threadgroup_lengths.argtypes = [ctypes.POINTER(ctypes.c_uint32), ctypes.c_uint32]
        self.lib.nvmtl_translate_set_threadgroup_lengths.restype = None

    def threadgroup_lengths(self, lengths):
        values=(ctypes.c_uint32*len(lengths))(*lengths)
        self.lib.nvmtl_translate_set_threadgroup_lengths(values,len(lengths))

    def translate(self, ll, stage, config, caps=3):
        self.lib.nvmtl_translate_set_caps(caps)
        out, size = ctypes.c_void_p(), ctypes.c_size_t()
        error = ctypes.create_string_buffer(2048)
        start = time.perf_counter_ns()
        rc = self.call(ll, stage.encode(), config, ctypes.byref(out), ctypes.byref(size), error, len(error))
        elapsed = time.perf_counter_ns() - start
        if rc:
            return None, error.value.decode(), elapsed
        try:
            return ctypes.string_at(out, size.value), None, elapsed
        finally:
            self.lib.nvmtl_translate_free(out, size.value)


def config(samplers, constants=None):
    return json.dumps(dict(samplers=samplers, constants=constants or {}), sort_keys=True).encode()


def validate(data, output, name):
    path = output / (name + '.spv')
    path.write_bytes(data)
    subprocess.run(['spirv-val', '--target-env', 'vulkan1.2', '--scalar-block-layout', str(path)],
                   check=True, capture_output=True)


def stats(samples):
    values = sorted(samples)
    quartiles = statistics.quantiles(values, n=4, method='inclusive')
    return dict(n=len(values), median_ns=statistics.median(values),
                p95_ns=values[math.ceil(.95 * len(values)) - 1], min_ns=min(values), max_ns=max(values),
                iqr_ns=quartiles[2]-quartiles[0],
                cv_percent=100*statistics.pstdev(values)/statistics.mean(values), samples_ns=samples)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rounds', type=int, default=10)
    parser.add_argument('--samples', type=int, default=10)
    args = parser.parse_args()
    if not 2 <= args.rounds <= 20 or not 2 <= args.samples <= 100:
        parser.error('bounded rounds 2..20 and samples 2..100 required')
    args.output.mkdir(parents=True, exist_ok=False)
    libs = dict(baseline=Translator(args.baseline), candidate=Translator(args.candidate))
    fs = fixture(TEXTURES, 'runtime_sampler_specialization_uses_fragment_metal_index_not_descriptor_binding')
    vs = fixture(INTERFACE, 'caller_selected_layout_separates_independently_translated_vertex_and_fragment_resources', 'vertex')
    cs = fixture(TEXTURES, 'RUNTIME_STORAGE_IMAGE_WRITE_PAIR_LL', constant=True)
    workloads = [
        ('fragment-nearest', fs, 'fragment', config({'3': state()})),
        ('fragment-linear', fs, 'fragment', config({'3': state('Linear')})),
        ('fragment-normalized', fs, 'fragment', config({'3': state('Linear', 'Normalized')})),
        ('vertex-unused-sampler', vs, 'vertex', config({'3': state()})),
        ('storage-write-unused-sampler', cs, 'kernel', config({'3': state()})),
    ]
    reference = {}
    for name, ll, stage, cfg in workloads:
        reference[name] = {}
        for variant, lib in libs.items():
            for _ in range(5):
                data, error, _ = lib.translate(ll, stage, cfg)
                assert data is not None, (name, variant, error)
            validate(data, args.output, name+'-'+variant)
            reference[name][variant] = data
        assert reference[name]['baseline'] == reference[name]['candidate'], name
    assert reference['fragment-nearest']['candidate'] != reference['fragment-linear']['candidate'], 'filter state must affect the emitted program'
    assert reference['fragment-linear']['candidate'] != reference['fragment-normalized']['candidate'], 'pixel/normalized coordinate semantics must differ'
    controls = []
    for caps in [0, 1, 2, 3]:
        for label, ll, stage, cfg in workloads:
            results = [lib.translate(ll, stage, cfg, caps)[:2] for lib in libs.values()]
            assert results[0] == results[1], (label, caps, results)
            assert results[0][0] is not None, (label, caps, results[0][1])
            validate(results[0][0], args.output, f'caps-{caps}-{label}')
            controls.append(f'caps={caps}:{label}')
    invalid = state(); invalid['mag_filter'] = 'Linear'
    for cfg in [config({'3': invalid}), config({'3': state()}, {'not-an-index': [0]})]:
        results = [lib.translate(fs, 'fragment', cfg)[:2] for lib in libs.values()]
        assert results[0] == results[1] and results[0][0] is None and results[0][1], results
        controls.append('identical explicit invalid-state/constant error')
    for lib in libs.values():
        data, error, _ = lib.translate(fs, 'fragment', config({'3': state(), '7': invalid}))
        assert not error and data == reference['fragment-nearest']['candidate'], 'undeclared bound sampler must be ignored before state validation'
    controls.append('undeclared sampler does not change output')
    results = [lib.translate(b'not LLVM IR', 'fragment', config({'3': state()}))[:2]
               for lib in libs.values()]
    assert results[0] == results[1] and results[0][0] is None and results[0][1], results
    controls.append('identical explicit malformed AIR error')
    fc=fixture(MISC,'air_level_function_constant_specialization_selects_cfg_before_emission')
    fc_outputs=[]
    for enabled in (0,1,0):
        results=[lib.translate(fc,'fragment',config({'3':state()}, {'0':[enabled]}))[:2] for lib in libs.values()]
        assert results[0]==results[1] and results[0][0] is not None, results
        validate(results[0][0],args.output,f'function-constant-{enabled}')
        fc_outputs.append(results[0][0])
    assert fc_outputs[0]!=fc_outputs[1] and fc_outputs[0]==fc_outputs[2], 'function constants must change the program without retaining previous values'
    controls.append('positive function-constant specialization and call independence')
    tg=fixture(THREADGROUP,'kernel_threadgroup_array_length_follows_the_caller')
    tg_outputs=[]
    try:
        for length in (0,4352,2,0):
            results=[]
            for lib in libs.values():
                lib.threadgroup_lengths([length])
                results.append(lib.translate(tg,'kernel',config({'3':state()}))[:2])
            assert results[0]==results[1], results
            if length==2:
                assert results[0][0] is None and 'less than one 4-byte element' in results[0][1], results
            else:
                assert results[0][0] is not None, results
                validate(results[0][0],args.output,f'threadgroup-length-{length}')
                tg_outputs.append(results[0][0])
        assert tg_outputs[0]!=tg_outputs[1] and tg_outputs[0]==tg_outputs[2], 'unused-sampler fallback must apply and clear threadgroup lengths'
    finally:
        for lib in libs.values(): lib.threadgroup_lengths([])
    controls.append('unused-sampler fallback preserves threadgroup lengths, error and clearing')
    malformed = args.output / 'invalid-header.spv'
    malformed.write_bytes(b'\x00\x00\x00\x00' + reference['fragment-nearest']['candidate'][4:])
    rejection = subprocess.run(['spirv-val', '--target-env', 'vulkan1.2', str(malformed)],
                               capture_output=True)
    assert rejection.returncode != 0 and rejection.stderr, 'real validator must reject invalid SPIR-V magic'
    controls.append('real validator rejects malformed SPIR-V header')
    measurements = {name: {'baseline': [], 'candidate': []} for name, *_ in workloads}
    paired = {name: [] for name, *_ in workloads}
    paired_saved = {name: [] for name, *_ in workloads}
    for round_index in range(args.rounds):
        batch = {name: {} for name, *_ in workloads}
        for variant in (['baseline', 'candidate'] if round_index % 2 == 0 else ['candidate', 'baseline']):
            lib = libs[variant]
            for name, ll, stage, cfg in workloads:
                samples = []
                for _ in range(args.samples):
                    data, error, elapsed = lib.translate(ll, stage, cfg)
                    assert not error and data == reference[name][variant], (name, variant, error)
                    samples.append(elapsed)
                measurements[name][variant].extend(samples)
                batch[name][variant] = statistics.median(samples)
        for name in paired:
            paired[name].append(100*(1-batch[name]['candidate']/batch[name]['baseline']))
            paired_saved[name].append(batch[name]['baseline']-batch[name]['candidate'])
    results = []
    for name, ll, stage, cfg in workloads:
        row = dict(workload=name, stage=stage, source_sha256=hashlib.sha256(ll).hexdigest(),
                   config_sha256=hashlib.sha256(cfg).hexdigest(), spirv_sha256=hashlib.sha256(reference[name]['candidate']).hexdigest(),
                   spirv_bytes=len(reference[name]['candidate']), byte_identical=True,
                   baseline=stats(measurements[name]['baseline']), candidate=stats(measurements[name]['candidate']),
                   paired_reductions_percent=paired[name],paired_saved_ns=paired_saved[name],
                   paired_median_reduction_percent=statistics.median(paired[name]),
                   paired_median_saved_ns=statistics.median(paired_saved[name]),
                   faster_batches=sum(value>0 for value in paired_saved[name]))
        row['median_reduction_percent'] = 100*(1-row['candidate']['median_ns']/row['baseline']['median_ns'])
        results.append(row)
        print(name, 'median ms', row['baseline']['median_ns']/1e6, '->', row['candidate']['median_ns']/1e6,
              'reduction %', row['median_reduction_percent'], flush=True)
    report = dict(results=results, controls=controls, source_fixture_owners=[TEXTURES+':runtime_sampler_specialization_uses_fragment_metal_index_not_descriptor_binding',
        INTERFACE+':caller_selected_layout_separates_independently_translated_vertex_and_fragment_resources', TEXTURES+':RUNTIME_STORAGE_IMAGE_WRITE_PAIR_LL'],
        rounds=args.rounds, warmup_calls_per_variant_per_workload=5,
        samples_per_variant_per_workload=args.rounds*args.samples,
        method='Actual nvmtl_translate_samplers C ABI; alternating paired batches after warmup, no concurrent builds; copying/freeing/validation excluded from timer; caps=3 as set by NVMTL loader.',
        limitation='Owned representative texture sampling/position/storage fixtures, not captured WindowServer shaders; Objective-C caches, AIR bitcode reading and NVK compilation not executed.',
        baseline_library_sha256=hashlib.sha256(args.baseline.read_bytes()).hexdigest(), candidate_library_sha256=hashlib.sha256(args.candidate.read_bytes()).hexdigest())
    (args.output/'results.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
