#!/usr/bin/env python3
"""Bounded installed-driver cache-path comparison; no component replacement."""
import argparse, hashlib, json, os, pathlib, statistics, subprocess
p = argparse.ArgumentParser()
p.add_argument('--probe', type=pathlib.Path, required=True)
p.add_argument('--output', type=pathlib.Path, required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=False)
keys = ('MESA_SHADER_CACHE_DIR', 'XDG_CACHE_HOME', 'MESA_SHADER_CACHE_DISABLE')
inherited_overrides = [k for k in keys if k in os.environ]
def snapshot(directory):
    files = [f for f in directory.rglob('*') if f.is_file()]
    return {'files': len(files), 'bytes': sum(f.stat().st_size for f in files)}
def run(label, cache=None):
    env = os.environ.copy()
    for key in keys:
        env.pop(key, None)
    if cache is not None:
        env['MESA_SHADER_CACHE_DIR'] = str(cache.resolve())
    out = subprocess.run([str(a.probe.resolve())], env=env, text=True,
                         capture_output=True, timeout=90)
    (a.output / (label + '.stdout')).write_text(out.stdout)
    (a.output / (label + '.stderr')).write_text(out.stderr)
    if out.returncode:
        raise SystemExit(f'{label}: probe failed ({out.returncode}); retained private output')
    lines = [s[8:] for s in out.stdout.splitlines() if s.startswith('result: ')]
    if len(lines) != 1:
        raise SystemExit(f'{label}: missing unique result')
    result = json.loads(lines[0])
    assert len(result['rows']) == 8 and all(r['correct'] for r in result['rows'])
    diagnostics = out.stdout + out.stderr
    result.update(label=label, cache_disabled_warning=('disabling' in diagnostics and 'shader cache' in diagnostics),
                  cache_permission_warning=('Permission denied' in diagnostics and 'shader cache' in diagnostics))
    if cache is not None:
        result['cache'] = snapshot(cache)
    return result
rows = []
for i in range(3):
    cache = a.output / f'owned-cache-{i}'
    cache.mkdir()
    # Alternate order to avoid giving the same arm all initial AIR warmup.
    if i % 2 == 0:
        rows.append(run(f'default-{i}'))
    rows.append(run(f'owned-cold-{i}', cache))
    rows.append(run(f'owned-reuse-{i}', cache))
    if i % 2:
        rows.append(run(f'default-{i}'))
def stats(values):
    ordered = sorted(values)
    return {'n':len(values), 'p50_ms':statistics.median(values),
            'p95_ms':ordered[min(len(ordered)-1, int(.95*(len(ordered)-1)))],
            'total_ms':sum(values)}
summary = {}
for arm in ('default', 'owned-cold', 'owned-reuse'):
    samples = [r for r in rows if r['label'].startswith(arm+'-')]
    summary[arm] = {'library_ms':[r['library_ms'] for r in samples],
                    'pipeline':stats([s['pipeline_ms'] for r in samples for s in r['rows']]),
                    'function':stats([s['function_ms'] for r in samples for s in r['rows']]),
                    'cache_disabled_runs':sum(r['cache_disabled_warning'] for r in samples),
                    'cache':[r.get('cache') for r in samples]}
evidence = {'probe_sha256':hashlib.sha256(a.probe.read_bytes()).hexdigest(),
            'runs':rows, 'summary':summary, 'cleared_child_override_names':inherited_overrides,
            'limits':['8 small owned compute kernels; 3 processes per arm',
                      'AIR/frontend caches remain in place; not a globally cold comparison',
                      'Cache files demonstrate persistence, not explicit Mesa hit counters',
                      'No WindowServer or desktop frame-pacing measurement']}
(a.output / 'results.json').write_text(json.dumps(evidence, indent=2)+'\n')
print(json.dumps(summary, indent=2))
