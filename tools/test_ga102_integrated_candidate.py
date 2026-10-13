import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('candidate', Path(__file__).with_name('ga102_integrated_candidate.py'))
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


class Publication(unittest.TestCase):
    def fixture(self, base):
        root, stage, job = base / 'root', base / 'stage', base / 'job'
        for name in candidate.TARGETS:
            for parent, value in ((root, 'original'), (stage, 'candidate')):
                path = parent / name
                if name.endswith('.bundle'):
                    path = path / 'Contents/MacOS/NVMTLDriver'
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value)
        return root, stage, job

    def test_all_failure_boundaries_restore_originals(self):
        for boundary in [prefix + name for name in candidate.TARGETS for prefix in ('saved:', 'published:')] + ['complete']:
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as tmp:
                root, stage, job = self.fixture(Path(tmp))
                original = {n: candidate.snapshot(root / n) for n in candidate.TARGETS}
                def fail(point):
                    if point == boundary:
                        raise RuntimeError('injected publication failure')
                with self.assertRaises(RuntimeError):
                    candidate.publish(root, stage, job, fail)
                self.assertEqual(original, {n: candidate.snapshot(root / n) for n in candidate.TARGETS})

    def test_success_preserves_exact_originals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, stage, job = self.fixture(Path(tmp))
            original = {n: candidate.snapshot(root / n) for n in candidate.TARGETS}
            expected = {n: candidate.snapshot(stage / n) for n in candidate.TARGETS}
            candidate.publish(root, stage, job)
            self.assertEqual(expected, {n: candidate.snapshot(root / n) for n in candidate.TARGETS})
            self.assertEqual(original, {n: candidate.snapshot(job / 'original' / n) for n in candidate.TARGETS})

    def test_existing_job_refused_before_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, stage, job = self.fixture(Path(tmp))
            original = candidate.snapshot(root)
            job.mkdir()
            with self.assertRaises(RuntimeError):
                candidate.publish(root, stage, job)
            self.assertEqual(original, candidate.snapshot(root))

    def test_reverse_publication_restores_and_preserves_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, stage, job = self.fixture(Path(tmp))
            original = {n: candidate.snapshot(root / n) for n in candidate.TARGETS}
            expected = {n: candidate.snapshot(stage / n) for n in candidate.TARGETS}
            candidate.publish(root, stage, job)
            candidate.publish(root, job / 'original', job / 'rollback')
            self.assertEqual(original, {n: candidate.snapshot(root / n) for n in candidate.TARGETS})
            self.assertEqual(expected, {n: candidate.snapshot(job / 'rollback/original' / n) for n in candidate.TARGETS})


if __name__ == '__main__':
    unittest.main()
