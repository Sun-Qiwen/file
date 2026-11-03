import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'evidence.py'


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        work = ROOT / 'validation' / 'tmp'
        work.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=work)
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)

    def run_tool(self, *args, expected=0):
        self.assertTrue(SCRIPT.is_file(), 'Evidence tool has not been implemented')
        out = self.work / 'result.json'
        result = subprocess.run([sys.executable, str(SCRIPT), *map(str, args), '--out', str(out)],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, expected, result.stderr + result.stdout)
        return json.loads(out.read_text(encoding='utf-8'))

    def arrays(self, reference, actual, *options, expected=0):
        ref, got = self.work / 'reference.npy', self.work / 'actual.npy'
        np.save(ref, reference, allow_pickle=False)
        np.save(got, actual, allow_pickle=False)
        return self.run_tool('compare', ref, got, *options, expected=expected)

    def test_int8_exact_and_first_error(self):
        r = self.arrays(np.array([-128, 0, 127], dtype='int8'),
                        np.array([-128, 1, 127], dtype='int8'), expected=1)
        self.assertEqual(r['mismatch_count'], 1)
        self.assertEqual(r['first_mismatch']['index'], [1])

    def test_large_integer_does_not_round_through_float(self):
        r = self.arrays(np.array([2**63 + 1], dtype='uint64'),
                        np.array([2**63 + 2], dtype='uint64'), expected=1)
        self.assertFalse(r['passed'])

    def test_exact_success(self):
        r = self.arrays(np.arange(8, dtype='int32'), np.arange(8, dtype='int32'))
        self.assertTrue(r['passed'])

    def test_shape_mismatch_is_not_broadcast(self):
        r = self.arrays(np.ones((2, 1), dtype='int8'), np.ones(2, dtype='int8'), expected=1)
        self.assertIn('shape', r['reason'])

    def test_dtype_mismatch(self):
        r = self.arrays(np.ones(2, dtype='int8'), np.ones(2, dtype='int16'), expected=1)
        self.assertIn('dtype', r['reason'])

    def test_float_uses_reference_relative_tolerance(self):
        r = self.arrays(np.array([10.0], dtype='float32'), np.array([10.125], dtype='float32'),
                        '--mode', 'float', '--atol', '0.125', '--rtol', '0')
        self.assertTrue(r['passed'])

    def test_nan_never_passes_as_matching_output(self):
        r = self.arrays(np.array([np.nan]), np.array([np.nan]), expected=1)
        self.assertIn('nonfinite', r['reason'])

    def test_relative_tolerance_is_relative_to_reference(self):
        self.arrays(np.array([1.0]), np.array([2.0]), '--mode', 'float', '--rtol', '0.75', expected=1)

    def test_negative_tolerance_is_invalid(self):
        self.arrays(np.array([1.0]), np.array([1.0]), '--mode', 'float', '--atol', '-1', expected=2)

    def test_empty_output_cannot_pass(self):
        self.arrays(np.array([], dtype='int8'), np.array([], dtype='int8'), expected=1)

    def rows(self):
        result = []
        for group, times in [('A1', [100, 102, 98]), ('B', [70, 71, 69]), ('A2', [99, 100, 101])]:
            for i, elapsed in enumerate([999] + times):
                result.append(dict(case='vector_add', group=group, iteration=str(i),
                                   warmup='1' if i == 0 else '0', correct='1', elapsed_ms=str(elapsed),
                                   run_id='synthetic-run', environment_id='synthetic-board-config',
                                   artifact_id='a-build' if group != 'B' else 'b-build',
                                   timing_boundary='call-entry-to-output-ready', input_id='input-v1',
                                   reference_id='reference-v1'))
        return result

    def aba(self, rows, expected=0):
        source = self.work / 'samples.csv'
        with source.open('w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)
        return self.run_tool('aba', source, expected=expected)

    def test_aba_preserves_samples_and_excludes_explicit_warmup(self):
        r = self.aba(self.rows())
        case = r['cases']['vector_add']
        self.assertEqual(case['groups']['A1']['n'], 3)
        self.assertEqual(case['groups']['A1']['warmup_n'], 1)
        self.assertEqual(case['groups']['A1']['mean_ms'], 100)
        self.assertEqual(case['conservative_saved_ms'], 30)
        self.assertEqual(r['input_rows'], 12)
        self.assertFalse(r['board_verified_by_this_tool'])

    def test_slow_valid_sample_is_not_removed(self):
        rows = self.rows(); rows[6]['elapsed_ms'] = '1000'
        r = self.aba(rows)
        self.assertEqual(r['cases']['vector_add']['groups']['B']['max_ms'], 1000)
        self.assertLess(r['cases']['vector_add']['conservative_saved_ms'], 0)

    def test_environment_change_rejected(self):
        rows = self.rows(); rows[5]['environment_id'] = 'changed-clock'
        self.aba(rows, expected=2)

    def test_restored_baseline_identity_checked(self):
        rows = self.rows(); rows[-1]['artifact_id'] = 'different-build'
        self.aba(rows, expected=2)

    def test_interleaved_groups_rejected(self):
        rows = self.rows(); rows[2], rows[6] = rows[6], rows[2]
        self.aba(rows, expected=2)

    def test_bad_result_is_not_hidden_by_speedup(self):
        rows = self.rows(); rows[5]['correct'] = '0'
        r = self.aba(rows, expected=1)
        self.assertFalse(r['data_checks_passed'])

    def test_drift_is_reported_as_failure(self):
        rows = self.rows()
        for row in rows:
            if row['group'] == 'A2' and row['warmup'] == '0': row['elapsed_ms'] = '130'
        r = self.aba(rows, expected=1)
        self.assertAlmostEqual(r['cases']['vector_add']['baseline_drift_pct'], 30)

    def test_nonfinite_sample_rejected(self):
        rows = self.rows(); rows[5]['elapsed_ms'] = 'NaN'
        self.aba(rows, expected=2)

    def test_missing_retest_group_rejected(self):
        self.aba(self.rows()[:8], expected=2)

    def test_changed_timing_boundary_rejected(self):
        rows = self.rows(); rows[5]['timing_boundary'] = 'hardware-only'
        self.aba(rows, expected=2)

    def test_duplicate_samples_rejected(self):
        rows = self.rows(); rows.insert(2, dict(rows[1]))
        self.aba(rows, expected=2)

    def test_repeated_case_with_different_input_is_rejected(self):
        rows = self.rows(); rows[5]['input_id'] = 'different-input'
        self.aba(rows, expected=2)

    def test_script_does_not_overwrite_existing_report(self):
        target = self.work / 'result.json'
        target.write_text('{"keep": true}', encoding='utf-8')
        result = self.aba(self.rows(), expected=2)
        self.assertEqual(result, {'keep': True})

    def test_artifact_hashes_and_pairing_limit(self):
        bit, hwh = self.work / 'demo.bit', self.work / 'demo.hwh'
        bit.write_bytes(b'synthetic-not-a-bitstream')
        hwh.write_bytes(b'synthetic-not-hwh')
        contract = dict(build_id='synthetic-build', artifacts={
            key: dict(path=p.name, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
            for key, p in [('bit', bit), ('hwh', hwh)]})
        path = self.work / 'contract.json'
        path.write_text(json.dumps(contract), encoding='utf-8')
        r = self.run_tool('artifacts', path)
        self.assertTrue(r['file_hashes_match'])
        self.assertEqual(r['semantic_pairing'], 'not_proven')
        (self.work / 'result.json').unlink()
        bit.write_bytes(b'changed')
        self.run_tool('artifacts', path, expected=1)


if __name__ == '__main__':
    unittest.main()
