"""Bounded own-child SCStream broker and independent encoded-content analysis."""
import ctypes
import json
import math
try:
    from .ga102_capture_bridge import CaptureBroker, correct_samples
except ImportError:
    from ga102_capture_bridge import CaptureBroker, correct_samples


def analyze_stream(raw, submitted=120):
    records = raw.get('records', [])
    decoded = []
    invalid = 0
    origin = records[0].get('pts_seconds', 0) if records else 0
    for row in records:
        rgb = row.get('samples', [])
        frame = 0
        good = len(rgb) == 72
        if good:
            for cell in range(8):
                bit = rgb[cell*9:cell*9+3]
                if all(v >= 215 for v in bit): frame |= 1 << cell
                elif not all(v <= 40 for v in bit): good = False
        pts = row.get('pts_seconds')
        good = good and 0 <= frame < submitted and correct_samples(frame, rgb) and isinstance(pts, (float, int)) and math.isfinite(pts)
        if good: decoded.append({'frame': frame, 'capture_pts_ms': (pts-origin)*1000})
        else: invalid += 1
    ids = [r['frame'] for r in decoded]
    clocks = [r['capture_pts_ms'] for r in decoded]
    ordered = all(b >= a for a,b in zip(ids,ids[1:])) and all(b > a for a,b in zip(clocks,clocks[1:]))
    changes = [row for i,row in enumerate(decoded) if i==0 or row['frame'] != decoded[i-1]['frame']]
    intervals = [b['capture_pts_ms']-a['capture_pts_ms'] for a,b in zip(changes,changes[1:])]
    unique = len(set(ids))
    incomplete = not raw.get('stopped') or raw.get('failed') or raw.get('overflow')
    content = ('FAIL' if invalid or not ordered else 'NOT VERIFIED' if incomplete or unique < 3 else 'PASS')
    # A missing ID is a capture-path observation. SCStream can drop/coalesce;
    # absence cannot establish a panel/compositor drop or justify a driver fix.
    coverage = 'PASS' if content == 'PASS' and set(ids) == set(range(submitted)) else 'NOT VERIFIED'
    return {'captured_reference_contents':content,'capture_id_coverage':coverage,
            'records':len(records),'correct_records':len(decoded),'invalid_records':invalid,
            'distinct_frame_ids':unique,'frame_ids_nondecreasing':all(b>=a for a,b in zip(ids,ids[1:])),
            'capture_pts_increasing':all(b>a for a,b in zip(clocks,clocks[1:])),
            'missing_capture_ids':[i for i in range(submitted) if i not in set(ids)],
            'captured_changes':changes,'change_intervals_above_25ms':sum(x>25 for x in intervals),
            'max_change_interval_ms':max(intervals) if intervals else None,
            'stream_status_counts':raw.get('statuses',{}),'stream_stopped':bool(raw.get('stopped')),
            'stream_failed':bool(raw.get('failed')),'stream_overflow':bool(raw.get('overflow')),
            'physical_scanout':'NOT VERIFIED','desktop_smoothness':'NOT VERIFIED',
            'note':'capture PTS cadence/ID loss is capture-path evidence, not physical scanout or exclusive compositor timing'}


class StreamBroker(CaptureBroker):
    def __init__(self, library, directory):
        super().__init__(library,directory)
        self.library.ga102_stream_start.argtypes=[ctypes.c_uint,ctypes.c_int]
        self.library.ga102_stream_start.restype=ctypes.c_int
        self.library.ga102_stream_stop.restype=ctypes.c_void_p
        self.library.ga102_capture_free.argtypes=[ctypes.c_void_p]
        self.analysis=None

    def close(self):
        pointer=self.library.ga102_stream_stop()
        if pointer:
            try:
                raw=json.loads(ctypes.string_at(pointer))
                # Raw RGB/absolute PTS remain private, never returned in a report.
                (self.directory/'stream-raw.json').write_text(json.dumps(raw))
                self.analysis=analyze_stream(raw)
            finally:self.library.ga102_capture_free(pointer)

    def poll(self, child):
        request=self.directory/'request.json'
        if not request.exists():return
        data=json.loads(request.read_text());operation=data.get('operation')
        if data.get('pid') != child.pid or operation not in ('stream-start','stream-stop'):
            raise ValueError('stream request does not identify the owned child/operation')
        request.unlink()
        if operation=='stream-start':
            identity=data.get('window_id')
            code=(self.library.ga102_stream_start(identity,child.pid) if self.allowed and
                  isinstance(identity,int) and identity>0 else -4 if self.allowed else -1)
            if code != 0:self.allowed=False;self.close()
            response={'started':code==0,'code':code}
        else:
            self.close();response={'analysis':self.analysis or {'captured_reference_contents':'NOT VERIFIED'}}
        temporary=self.directory/'response.tmp';temporary.write_text(json.dumps(response))
        temporary.replace(self.directory/(operation+'.json'))
