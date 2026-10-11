"""Production C cache-policy tests without loading Metal or modifying real caches."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


class MesaCacheTests(unittest.TestCase):
    def test_production_cache_directory_selection(self):
        self.assertNotEqual(os.geteuid(), 0, "Run as the ordinary user so permission checks are meaningful")
        with tempfile.TemporaryDirectory(prefix="ga102-cache-test-") as directory:
            folder = Path(directory)
            home, darwin = folder / "home", folder / "darwin"
            (home / "Library" / "Caches").mkdir(parents=True, mode=0o700)
            darwin.mkdir(mode=0o700)
            executable = folder / "cache-test"
            built = subprocess.run(["cc", "-std=c11", "-D_DARWIN_C_SOURCE", "-Wall", "-Wextra", "-Werror",
                                    "-fsanitize=address,undefined", "-I", str(ROOT / "plugin"),
                                    str(ROOT / "tools" / "mesa_cache_tests" / "main.c"), "-o", str(executable)],
                                   capture_output=True, text=True, timeout=30)
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run([str(executable), str(home), str(darwin)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("production Mesa cache assertions", result.stdout)
            self.assertNotIn("runtime error", result.stderr)
            print(result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
