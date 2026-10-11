"""Scoped public session-query measurements; no desktop-performance PASS claim."""
import math
try:
    from .ga102_delivery_analysis import distribution
except ImportError:
    from ga102_delivery_analysis import distribution


def analyze(rows,exit_code):
    complete=len(rows)==12 and [r.get('index') for r in rows]==list(range(12))
    valid=all(isinstance(r.get('latency_ms'),(int,float)) and not isinstance(r['latency_ms'],bool) and math.isfinite(r['latency_ms']) and r['latency_ms']>=0 for r in rows)
    status='FAIL' if exit_code or not valid else 'PASS' if complete and all(r.get('available') is True and r.get('on_console') is True for r in rows) else 'NOT VERIFIED'
    values=[r['latency_ms'] for r in rows] if valid else []
    return {'session_query_measurements':status,'samples':len(rows),'all_invocations':distribution(values),
            'first_invocation_ms':values[0] if values else None,'subsequent_invocations':distribution(values[1:]),
            'desktop_causality':'NOT VERIFIED','physical_scanout':'NOT VERIFIED',
            'note':'API roundtrip wall time includes initialization/IPC/scheduling; first call retained separately; sparse p99 is near maximum'}
