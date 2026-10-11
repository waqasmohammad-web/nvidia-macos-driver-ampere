"""Bounded own-client run-loop/event timing; phases are wall time, not CPU attribution."""
import math
try:
    from .ga102_delivery_analysis import distribution
except ImportError:
    from ga102_delivery_analysis import distribution


def _finite(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def analyze(metrics):
    gaps=metrics.get('runloop_long_gaps',[])
    spans=metrics.get('owned_window_event_spans',[])
    application_spans=metrics.get('owned_application_event_spans',[])
    valid=all(all(_finite(g.get(k)) for k in ('start_ms','end_ms','from_activity','to_activity','from_lane','to_lane')) and
              g['end_ms']>=g['start_ms'] and g['from_activity'] in (1,2,4,32,64,128) and
              g['to_activity'] in (1,2,4,32,64,128) and g['from_lane'] in (0,1) and g['to_lane'] in (0,1) for g in gaps)
    valid=valid and all(b['start_ms']>=a['end_ms'] for a,b in zip(gaps,gaps[1:]))
    span_valid=all(all(_finite(g.get(k)) for k in ('start_ms','end_ms','subtype')) and g['end_ms']>=g['start_ms'] for g in spans)
    application_valid=all(all(_finite(g.get(k)) for k in ('start_ms','end_ms','subtype','target_is_probe')) and g['end_ms']>=g['start_ms'] and g['target_is_probe'] in (0,1) for g in application_spans)
    available=metrics.get('runloop_trace_enabled') is True and metrics.get('runloop_event_count',0)>=2
    collection='FAIL' if not valid or not span_valid or not application_valid else 'NOT VERIFIED' if not available or metrics.get('runloop_overflow') or metrics.get('owned_window_event_overflow') or metrics.get('owned_application_event_overflow') else 'PASS'
    categories={}
    categorized=[]
    if valid:
        for g in gaps:
            category=('between_runloop_invocations' if g['from_activity']==128 and g['to_activity']==1 else
                      'between_wait_notifications' if g['from_activity']==32 and g['to_activity']==64 else
                      'before_wait_observers' if g['from_activity']==g['to_activity']==32 and g['from_lane']==0 and g['to_lane']==1 else
                      'other_observer_phase' if g['from_activity']==g['to_activity'] and g['from_lane']==0 and g['to_lane']==1 else
                      'source_or_transition_interval')
            categories.setdefault(category,[]).append(g['end_ms']-g['start_ms'])
            categorized.append((g,category))
    delays=[]
    for row in metrics.get('frame_trace',[]):
        low=row.get('completed_callback_ms');high=row.get('main_queue_marker_ms')
        if not _finite(low) or not _finite(high) or high-low<=5 or row.get('frame',0)<10:continue
        overlaps=[]
        for g,category in categorized:
            overlap=max(0,min(high,g['end_ms'])-max(low,g['start_ms']))
            if overlap>0:overlaps.append({'phase':category,'overlap_ms':overlap})
        event_overlaps=[]
        if span_valid:
            for g in spans:
                overlap=max(0,min(high,g['end_ms'])-max(low,g['start_ms']))
                if overlap>0:event_overlaps.append({'subtype':g['subtype'],'handler_ms':g['end_ms']-g['start_ms'],'overlap_ms':overlap})
        application_overlaps=[]
        if application_valid:
            for g in application_spans:
                overlap=max(0,min(high,g['end_ms'])-max(low,g['start_ms']))
                if overlap>0:application_overlaps.append({'subtype':g['subtype'],'target_is_probe':g['target_is_probe'],'handler_ms':g['end_ms']-g['start_ms'],'overlap_ms':overlap})
        delays.append({'frame':row['frame'],'main_queue_delay_ms':high-low,'runloop_phase_overlaps':overlaps,'owned_window_event_overlaps':event_overlaps,'owned_application_event_overlaps':application_overlaps})
    return {'trace_collection':collection,'observed_runloop_notifications':metrics.get('runloop_event_count',0),
            'retained_long_gaps':len(gaps),'long_gap_threshold_ms':0.25,
            'retained_gap_durations_by_phase':{key:distribution(values) for key,values in categories.items()},
            'owned_framework_event_spans':spans if span_valid else [],'owned_application_event_spans':application_spans if application_valid else [],
            'application_dispatcher_instrumented':metrics.get('application_dispatcher_instrumented',False),'delayed_queue_correlations':delays,
            'physical_scanout':'NOT VERIFIED','root_cause':'NOT VERIFIED',
            'note':'relative wall-time phase/event overlap; not CPU scheduling proof, a per-frame stack trace, or WindowServer fence attribution'}
