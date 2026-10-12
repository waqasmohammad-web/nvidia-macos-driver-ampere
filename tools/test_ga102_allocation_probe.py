import copy
import unittest
from tools.ga102_allocation_probe import validate_stress
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
