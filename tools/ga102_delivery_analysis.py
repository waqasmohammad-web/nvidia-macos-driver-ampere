"""Relative per-ID delivery correlations; never infer panel loss from SCK absence."""
import math


def distribution(values):
    values=sorted(v for v in values if isinstance(v,(int,float)) and math.isfinite(v))
    if not values:return {'samples':0,'p50_ms':None,'p95_ms':None,'p99_ms':None,'max_ms':None}
    return {'samples':len(values),**{f'p{p}_ms':values[max(0,math.ceil(len(values)*p/100)-1)] for p in (50,95,99)},'max_ms':values[-1]}


def analyze(metrics):
    metal=metrics.get('probe')=='visual'
    rows=metrics.get('frame_trace',[]) if metal else metrics.get('samples',[])
    key='draw_start_ms' if metal else 'transaction_start_ms'
    starts=[r[key] for r in rows if key in r]
    submitted={int(r['frame']) for r in rows}
    captured={int(r['frame']) for r in metrics.get('stream_analysis',{}).get('captured_changes',[])}
    presented={int(r['frame']) for r in rows if 'reported_presented_ms' in r}
    expected=set(range(metrics.get('frames',120)))
    intervals=[b-a for a,b in zip(starts,starts[1:])]
    stages=('acquisition_ms','encode_ms','commit_call_ms','commit_to_scheduled_callback_ms','commit_to_completion_callback_ms','completion_callback_to_actor_ms','commit_to_completed_ms','gpu_ms','cpu_reference_readback_ms','eligibility_and_stream_start_ms') if metal else ('transaction_ms','visibility_ms','capture_roundtrip_ms')
    steady_starts=[r[key] for r in rows if key in r and r['frame']>=10]
    result={'submission_intervals_all_including_initial_hold':distribution(intervals),
            'submission_intervals':distribution([b-a for a,b in zip(steady_starts,steady_starts[1:])]), 'stage_costs':{k:distribution([r.get(k) for r in rows[10:]]) for k in stages},
            'not_submitted_ids':sorted(expected-submitted),'submitted_without_capture_ids':sorted(submitted-captured),
            'captured_without_submission_ids':sorted(captured-submitted),
            'submitted_late_after_ids':[int(rows[i]['frame']) for i,v in enumerate(intervals) if v>25],
            'capture_loss_is_panel_loss':'NOT VERIFIED','physical_scanout':'NOT VERIFIED'}
    if metal:
        required=('commit_ms','completed_callback_ms','completed_ms','scheduled_callback_ms','commit_return_ms')
        complete=bool(rows) and all(all(isinstance(r.get(k),(int,float)) and math.isfinite(r[k]) for k in required) for r in rows)
        invalid=complete and any(r['completed_callback_ms']<r['commit_ms'] or r['completed_ms']<r['completed_callback_ms'] for r in rows)
        result['callback_trace_collection']='FAIL' if invalid else 'PASS' if complete else 'NOT VERIFIED'
        result['long_client_completion_observations']=[{
            'frame':int(r['frame']),'callback_after_commit_ms':r.get('commit_to_completion_callback_ms'),
            'actor_after_callback_ms':r.get('completion_callback_to_actor_ms'),'gpu_ms':r.get('gpu_ms'),
            'classification':'actor_resumption_delay' if r.get('commit_to_completion_callback_ms',float('inf'))<=2 and r.get('completion_callback_to_actor_ms',0)>2 else 'callback_or_unclassified_delay'}
            for r in rows if r['frame']>=10 and r.get('commit_to_completed_ms',0)>5]
        ordered=[r for r in rows if 'reported_presented_ms' in r and r['frame']>=10]
        gaps=[b['reported_presented_ms']-a['reported_presented_ms'] for a,b in zip(ordered,ordered[1:])]
        result.update({'reported_presentation_intervals':distribution(gaps),
                       'reported_presented_without_capture_ids':sorted(presented-captured),
                       'submitted_without_positive_presentation_ids':sorted(submitted-presented),
                       'presentation_intervals_above_25ms':sum(v>25 for v in gaps)})
    else:result['gpu_completion_and_presentation']='NOT VERIFIED: CALayer client does not expose a drawable/fence timestamp'
    return result
