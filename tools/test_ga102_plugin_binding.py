import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import ga102_run_metal as runner


class PluginBindingTests(unittest.TestCase):
    def test_snapshot_keeps_original_bytes_and_shadows_only_enumeration(self):
        source = b'import Metal\nlet devices = MTLCopyAllDevices()\n'
        snapshot = runner.isolated_source(source)
        self.assertTrue(snapshot.endswith(source))
        self.assertIn(b'ga102_bound_device', snapshot)
        for bad in (b'no enumeration', source + source, source+b'MTLCreateSystemDefaultDevice()'):
            with self.assertRaises(ValueError): runner.isolated_source(bad)

    def test_unisolated_binding_is_rejected_before_launch(self):
        for probe in ('ga102_metal_present','ga102_metal_composite','ga102_metal_crossprocess','ga102_metal_benchmark'):
            with self.subTest(probe=probe), \
                 patch('sys.argv', ['runner', probe, '--plugin', '/missing/NVMTLDriver']), \
                 patch.object(runner, 'run_owned') as child, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit): runner.main()
                child.assert_not_called()

    def run_probe(self, marker=True, mutate=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); scratch=root/'scratch'; scratch.mkdir()
            plugin=root/'NVMTLDriver'; plugin.write_bytes(b'owned fixture')
            result=root/'result.json'
            def child(command, log, *args):
                if command[0] != 'xcrun':
                    log.write('result: '+json.dumps({'probe':'compute', 'values':[2,4,6,8], 'checked_elements':4})+'\n')
                    if marker: log.write('binding_verified: true\n')
                    if mutate: plugin.write_bytes(b'changed fixture')
                return 0
            with patch.object(runner.tempfile, 'mkdtemp', return_value=str(scratch)), \
                 patch.object(runner, 'run_owned', side_effect=child), \
                 patch('sys.argv', ['runner', 'ga102_metal_smoketest', '--plugin', str(plugin), '--result-json', str(result)]), \
                 contextlib.redirect_stdout(io.StringIO()):
                code=runner.main()
            return code,json.loads(result.read_text())

    def test_provenance_is_required_even_when_gpu_record_is_correct(self):
        code, report=self.run_probe(marker=False)
        self.assertEqual(code,1)
        self.assertEqual(report['automated_core_validation'],'FAIL')
        self.assertEqual(report['runs'][0]['exit_code'],1)

    def test_binary_change_invalidates_the_run(self):
        code, report=self.run_probe(mutate=True)
        self.assertEqual(code,1)
        self.assertEqual(report['automated_core_validation'],'FAIL')

    def test_report_has_binary_identity_and_no_private_path(self):
        code, report=self.run_probe()
        self.assertEqual(code,0)
        self.assertEqual(report['automated_core_validation'],'PASS')
        self.assertFalse(report['runtime']['installed_driver_changed'])
        self.assertEqual(len(report['runtime']['plugin_sha256']),64)
        self.assertNotIn('NVMTLDriver',json.dumps(report))
