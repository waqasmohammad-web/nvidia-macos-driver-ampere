"""Portable diagnostic transformation contracts, without a Vulkan device."""
from pathlib import Path
import unittest
from build import ga102_pool_instrumentation as trace

ROOT = Path(__file__).resolve().parents[1]


class PoolTraceTests(unittest.TestCase):
    def test_instruments_actual_source(self):
        original = (ROOT/'plugin/nvmtl_vk.c').read_text()
        changed = trace.instrument(original)
        self.assertEqual(changed.count('static int ga102_pool_buffer_body('), 1)
        self.assertEqual(changed.count('static int pool_buffer_create_in(int vram, size_t size, nvk_buffer *out)\n{'), 1)
        self.assertIn('ga102_pool_fragmented=freeBytes>=len;', changed)
        self.assertIn('atomic_fetch_add(&ga102_pool_wait_ns,ga102_pool_wait)', changed)
        self.assertEqual(changed.count('pthread_mutex_lock(&g_pool_lock)'), original.count('pthread_mutex_lock(&g_pool_lock)'))
        self.assertEqual(changed.count('pthread_mutex_unlock(&g_pool_lock)'), original.count('pthread_mutex_unlock(&g_pool_lock)'))

    def test_refuses_missing_or_duplicate_sites(self):
        source = (ROOT/'plugin/nvmtl_vk.c').read_text()
        for malformed in ('', source+source):
            with self.assertRaises(ValueError): trace.instrument(malformed)
        with self.assertRaises(ValueError): trace.instrument(trace.instrument(source))


if __name__ == '__main__':
    unittest.main()
