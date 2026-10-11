import unittest
from ga102_query_analysis import analyze

class QueryTests(unittest.TestCase):
    def fixture(self):return [dict(index=i,latency_ms=18 if i==0 else 0.3,available=True,on_console=True) for i in range(12)]
    def test_first_call_and_scope(self):
        r=analyze(self.fixture(),0);self.assertEqual(r['session_query_measurements'],'PASS')
        self.assertEqual(r['first_invocation_ms'],18);self.assertEqual(r['subsequent_invocations']['samples'],11)
        self.assertEqual(r['desktop_causality'],'NOT VERIFIED')
    def test_missing_and_inactive_cannot_pass(self):
        self.assertEqual(analyze(self.fixture()[:-1],0)['session_query_measurements'],'NOT VERIFIED')
        rows=self.fixture();rows[0]['on_console']=False
        self.assertEqual(analyze(rows,0)['session_query_measurements'],'NOT VERIFIED')
    def test_invalid_timing_and_execution_fail(self):
        for value in (float('nan'),-1,True):
            rows=self.fixture();rows[1]['latency_ms']=value
            self.assertEqual(analyze(rows,0)['session_query_measurements'],'FAIL')
        self.assertEqual(analyze(self.fixture(),124)['session_query_measurements'],'FAIL')

if __name__=='__main__':unittest.main()
