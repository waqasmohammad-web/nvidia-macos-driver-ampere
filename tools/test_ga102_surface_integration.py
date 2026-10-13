"""Portable wiring checks; actual Foundation concurrency probes remain Darwin-only."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SurfaceIntegration(unittest.TestCase):
    def test_all_encoder_imports_use_ownership(self):
        source = (ROOT/'plugin/NVMTLObjects.m').read_text()
        # Direct imports are confined to the helper and synchronous texture CPU APIs.
        encoder = source[source.index('static NSDictionary *nvmtl_pixel_sampler_norm'):]
        self.assertNotIn(' nvmtlSurfaceIn]', encoder)
        self.assertEqual(encoder.count('nvmtl_surface_overwrite_recorded('), 2)
        self.assertNotIn('sr->_surfSynced = YES', encoder)

    def test_cache_publishes_initialized_backing(self):
        source = (ROOT/'plugin/NVMTLDevice.m').read_text()
        source = source[source.index('- (id<MTLTexture>)nvmtlNewSurfaceTexture:'):]
        source = source[:source.index('- (id<MTLLibrary>)')]
        self.assertLess(source.index('t->_surf = surf'), source.index('[cache setObject:t'))
        self.assertLess(source.index('t->_usage = d.usage'), source.index('[cache setObject:t'))
        self.assertIn('strongToWeakObjectsMapTable', (ROOT/'plugin/NVMTLDevice.m').read_text())
        self.assertIn('alias->_viewParent = nil', source)

    def test_committed_registration_and_completion_cleanup(self):
        source = (ROOT/'plugin/NVMTLEventSync.m').read_text()
        submit = source[source.index('- (void)nvmtlSubmitWithEvents'):]
        self.assertLess(submit.index('_committed = YES'), submit.index('nvmtl_surface_register_writes(self)'))
        self.assertLess(submit.index('nvmtl_surface_register_writes(self)'), submit.index('nvmtl_pump_buffers()'))
        self.assertIn('nvmtl_surface_finish_writes(self);', source)
        self.assertIn('__weak NVMTLCommandBuffer *buffer', source)

    def test_shared_monitor_wraps_import_and_publication(self):
        source = (ROOT/'plugin/NVMTLObjects.m').read_text()
        self.assertEqual(source.count('@synchronized (nvmtl_surface_sync(r))'), 2)
        self.assertIn('strongToWeakObjectsMapTable', source)


if __name__ == '__main__':
    unittest.main()
