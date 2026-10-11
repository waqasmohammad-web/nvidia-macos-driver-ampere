"""Exercise the actual publication rollback without privileged/system writes."""
from pathlib import Path
import tempfile
import unittest
from tools.ga102_deploy_framebuffer import publish, matching_uuid


class PublicationTests(unittest.TestCase):
    def test_uuid_must_match_the_exact_component(self):
        for separator in ['\t', '\\t']:
            lines = ['com.nullmoth.NVRMFB' + separator + '0.1' + separator + '(EXPECTED-UUID)']
            self.assertTrue(matching_uuid(lines, 'com.nullmoth.NVRMFB', 'EXPECTED-UUID'))
            self.assertFalse(matching_uuid(lines, 'com.nullmoth.NVRM', 'EXPECTED-UUID'))
            self.assertFalse(matching_uuid(lines, 'com.nullmoth.NVRMFB', 'WRONG-UUID'))

    def exercise(self, failure=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target, candidate, job = root / 'live', root / 'candidate', root / 'job'
            for path in [target, candidate, job]:
                path.mkdir()
            (target / 'pixels').write_bytes(b'original-driver')
            (candidate / 'pixels').write_bytes(b'candidate-driver')
            cache, new_cache = root / 'cache', root / 'new-cache'
            cache.write_bytes(b'original-collection')
            new_cache.write_bytes(b'candidate-collection')
            def checkpoint(stage):
                if stage == failure:
                    raise RuntimeError('Injected publication failure')
            if failure:
                with self.assertRaisesRegex(RuntimeError, 'Injected'):
                    publish(target, candidate, cache, new_cache, job, checkpoint)
                self.assertEqual((target / 'pixels').read_bytes(), b'original-driver')
                self.assertEqual(cache.read_bytes(), b'original-collection')
            else:
                publish(target, candidate, cache, new_cache, job)
                self.assertEqual((target / 'pixels').read_bytes(), b'candidate-driver')
                self.assertEqual(cache.read_bytes(), b'candidate-collection')
                self.assertEqual((job / 'OriginalNVRMFB.kext/pixels').read_bytes(), b'original-driver')
            self.assertEqual((job / 'OriginalAuxiliaryKernelExtensions.kc').read_bytes(), b'original-collection')

    def test_success_preserves_both_originals(self):
        self.exercise()

    def test_failure_after_original_save(self):
        self.exercise('original_saved')

    def test_failure_after_bundle_publication(self):
        self.exercise('candidate_published')

    def test_failure_after_collection_publication(self):
        self.exercise('collection_published')
