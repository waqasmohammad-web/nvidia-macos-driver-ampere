"""Bounded tests of the exact production poll helper, without a loaded kext."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parent.parent
class FlipWaitTests(unittest.TestCase):
    def test_completion_contract(self):
        with tempfile.TemporaryDirectory(prefix='ga102-flip-wait-') as scratch:
            exe = Path(scratch) / 'test'
            built = subprocess.run(['clang++','-std=c++11','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I'+str(ROOT/'kexts/NVRMFB/fb'),
                str(ROOT/'tools/flip_wait_tests/main.cpp'),'-o',str(exe)],capture_output=True,text=True,timeout=30)
            self.assertEqual(built.returncode,0,built.stderr)
            result = subprocess.run([str(exe)],capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('39 production flip-wait assertions',result.stdout)
            print(result.stdout.strip())
