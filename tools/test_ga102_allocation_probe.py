import copy
import unittest
from tools.ga102_allocation_probe import validate_stress, validate_fragments, validate_uploads
from tools import ga102_graphics_perf as perf


class AllocationAcceptanceTests(unittest.TestCase):
    def control(self):
        # Policy-only records; never passed off as physical GPU evidence.
        base=dict(pools=2,reserved_sets=4352,live_sets=0,allocated_sets=1600,
                  freed_sets=1600,free_failures=0,buffer_live=10,host_pool_bytes=32<<20,
                  host_pool_blocks=1,dummy_heap_bytes=32<<20)
        blank={k:dict(count=0,ns=0,failures=0) for k in perf.DIAGNOSTIC_EVENTS}
        after=copy.deepcopy(blank);after['local_hit']['count']=1536
        return dict(growth=[dict(round=i,draws=1536,checked_pixels=1024,
                                before=base,held={**base,'live_sets':1568},after=base,
                                metrics_before=blank,metrics_after=after) for i in range(3)],
                    buffers=[dict(round=i,buffer_count=128,bytes_verified=64<<20,
                                  before=base,held={**base,'buffer_live':138,'host_pool_bytes':160<<20},
                                  after={**base,'host_pool_bytes':96<<20,'host_pool_blocks':3},
                                  allocation_samples_ns=[1]*128) for i in range(3)])

    def test_valid_policy_control(self):validate_stress(self.control())

    def test_growth_cannot_be_claimed_by_draw_count(self):
        result=self.control();result['growth'][0]['held']['live_sets']=32
        with self.assertRaises(ValueError):validate_stress(result)

    def test_retirement_and_reuse_required(self):
        for field,value in [('live_sets',32),('freed_sets',1599),('free_failures',1)]:
            result=self.control();result['growth'][0]['after']={**result['growth'][0]['after'],field:value}
            with self.assertRaises(ValueError):validate_stress(result)

    def test_buffer_lifetime_and_checked_size_required(self):
        for field,value in [('buffer_live',11),('host_pool_bytes',128<<20)]:
            result=self.control();result['buffers'][0]['after']={**result['buffers'][0]['after'],field:value}
            with self.assertRaises(ValueError):validate_stress(result)
        result=self.control();result['buffers'][0]['bytes_verified']=4
        with self.assertRaises(ValueError):validate_stress(result)


class FragmentationAcceptanceTests(unittest.TestCase):
    def control(self):
        # Acceptance-policy control only, never GPU evidence.
        return [dict(round=i,bytes_verified=31<<20,allocation_ns=1,
                     before=dict(buffer_live=10),after=dict(buffer_live=10,free_failures=0),
                     filled=dict(buffer_live=41),holes=dict(buffer_live=38),held=dict(buffer_live=39),
                     trace_before=dict(requests=31,failures=0,request_ns=1,lock_wait_ns=0,growths=3,growth_ns=1,fragmented_growths=0),trace_after=dict(requests=32,failures=0,request_ns=2,lock_wait_ns=0,growths=3,growth_ns=1,fragmented_growths=0)) for i in range(3)]

    def test_checked_size_and_lifetime_required(self):
        validate_fragments(self.control())
        for key,value in [('bytes_verified',1),('allocation_ns',0)]:
            rows=self.control();rows[0][key]=value
            with self.assertRaises(ValueError):validate_fragments(rows)
        rows=self.control();rows[0]['after']['buffer_live']=11
        with self.assertRaises(ValueError):validate_fragments(rows)

    def test_live_joined_range_and_monotonic_trace_required(self):
        rows=self.control();rows[0]['held']['buffer_live']=38
        with self.assertRaises(ValueError):validate_fragments(rows)
        rows=self.control();rows[0]['holes']['buffer_live']=41
        with self.assertRaises(ValueError):validate_fragments(rows)
        rows=self.control();rows[0]['trace_after']['growths']=2
        with self.assertRaises(ValueError):validate_fragments(rows)


class UploadAcceptanceTests(unittest.TestCase):
    def control(self):
        # Synthetic acceptance-policy controls; physical evidence stays separate.
        def row(w,h):return dict(width=w,height=h,source_row_bytes=w*4+256,bytes_verified=w*h*4,encode_ns=1,completion_ns=1)
        rows=[dict(worker=w,trial=t,**row((64,128,256,512)[(w+t)%4],128)) for w in range(4) for t in range(8)]
        return rows+[dict(large=row(4096,2049),small_after_large=row(256,128))]

    def test_requires_all_workers_and_unique_trials(self):
        validate_uploads(self.control())
        for rows in [self.control()[:-1],self.control()[1:32]+[self.control()[31],self.control()[-1]]]:
            with self.assertRaises((ValueError,KeyError)):validate_uploads(rows)

    def test_requires_real_pitched_bytes_and_positive_timing(self):
        for field,value in [('source_row_bytes',256),('bytes_verified',1),('completion_ns',0),('encode_ns',float('nan'))]:
            rows=self.control();rows[0][field]=value
            with self.assertRaises(ValueError):validate_uploads(rows)

    def test_requires_large_and_subsequent_small_import(self):
        rows=self.control();rows[-1]['large']['bytes_verified']=32<<20
        with self.assertRaises(ValueError):validate_uploads(rows)
        rows=self.control();del rows[-1]['small_after_large']
        with self.assertRaises(KeyError):validate_uploads(rows)
