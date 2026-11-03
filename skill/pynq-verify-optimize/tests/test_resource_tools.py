"""Offline tests: historical report text, synthetic checkpoints, mocked PYNQ/Tcl APIs."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reports = load('check_reports')
snapshot = load('pynq_snapshot')


class ResourceTests(unittest.TestCase):
    def setUp(self):
        work = ROOT / 'validation/tmp'; work.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=work); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.report_dir = self.root / 'reports'
        shutil.copytree(ROOT / 'tests/fixtures/fc70_reports', self.report_dir)
        (self.report_dir / 'routed.dcp').write_bytes(b'SYNTHETIC CHECKPOINT HASH FIXTURE, NOT A VALID DCP')

    def inspect(self):
        return reports.inspect(self.report_dir, {'clk_fpga_0': 100})

    def change(self, name, old, new):
        p = self.report_dir / name; text = p.read_text(encoding='utf-8')
        self.assertIn(old, text); p.write_text(text.replace(old, new, 1), encoding='utf-8')

    def test_actual_saved_fc70_layout(self):
        result = self.inspect()
        self.assertEqual(result['resources']['slice'], 13217)
        self.assertEqual(result['resources']['dsp'], 212)
        self.assertEqual(result['resources']['bram36_equivalent'], 117.5)
        self.assertEqual(result['provenance_status'], 'report_snapshot_unbound_to_execution')

    def test_explicit_clock_mismatch(self):
        with self.assertRaisesRegex(ValueError, 'Clock'):
            reports.inspect(self.report_dir, {'clk_fpga_0': 125})

    def test_other_architecture_rejected(self):
        self.change('utilization.rpt', 'xc7z020clg400-1', 'xcku040')
        with self.assertRaisesRegex(ValueError, '7-series'):
            self.inspect()

    def test_missing_check_timing_is_not_zero(self):
        self.change('check_timing.rpt', 'no_clock', 'absent_clock_category')
        with self.assertRaisesRegex(ValueError, 'check_timing'):
            self.inspect()

    def test_negative_hold_is_rejected(self):
        self.change('timing.rpt', '0.010', '-0.010')
        with self.assertRaisesRegex(ValueError, 'slack'):
            self.inspect()

    def test_baseline_artifact_tamper(self):
        baseline = self.inspect(); candidate = self.inspect()
        (self.report_dir / 'routed.dcp').write_bytes(b'CHANGED SYNTHETIC FIXTURE')
        with self.assertRaisesRegex(ValueError, 'changed'):
            reports.compare(candidate, baseline)

    def test_run_seal_rejects_modified_script(self):
        script = self.root / 'run.tcl'; script.write_text('# synthetic fixture', encoding='utf-8')
        seal = self.root / 'seal.json'
        record = dict(started=1, ended=2, exit_code=0, command=['vivado', '-source', str(script)],
                      script_sha256=reports.sha(script),
                      output_sha256={name: reports.sha(self.report_dir / name) for name in reports.FILES})
        seal.write_text(json.dumps(record), encoding='utf-8')
        result = reports.inspect(self.report_dir, {'clk_fpga_0': 100}, seal)
        self.assertTrue(result['supplied_run_seal_matches'])
        script.write_text('# changed fixture', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            reports.inspect(self.report_dir, {'clk_fpga_0': 100}, seal)

    def fake_board(self):
        boot = self.root / 'boot'; boot.write_text('synthetic-boot')
        bit = self.root / 'design.bit'; bit.write_bytes(b'synthetic-bit')
        bit.with_suffix('.hwh').write_bytes(b'synthetic-hwh')
        fake = SimpleNamespace(__version__='mock-only', PL=SimpleNamespace(bitfile_name=str(bit)),
                               Clocks=SimpleNamespace(fclk0_mhz=100.0))
        return fake, boot

    def test_pynq_snapshot_read_only_mock(self):
        fake, boot = self.fake_board()
        # No Overlay/DMA APIs are provided. The observer must not need them.
        result = snapshot.snapshot(fake, boot_file=str(boot))
        self.assertEqual(result['errors'], [])
        self.assertFalse(result['overlay_pair_verified'])
        self.assertFalse(result['dma_idle_verified'])
        self.assertEqual(result['clocks_mhz']['fclk0_mhz'], 100)

    def test_missing_clock_is_unknown(self):
        fake, boot = self.fake_board()
        result = snapshot.snapshot(fake, clock_ids=(1,), boot_file=str(boot))
        self.assertIsNone(result['clocks_mhz']['fclk1_mhz'])
        self.assertTrue(result['errors'])

    def test_missing_hwh_is_not_pair_verified(self):
        fake, boot = self.fake_board()
        Path(fake.PL.bitfile_name).with_suffix('.hwh').unlink()
        result = snapshot.snapshot(fake, boot_file=str(boot))
        self.assertTrue(result['errors'])
        self.assertFalse(result['overlay_pair_verified'])

    def tcl(self, ranges):
        try:
            import tkinter
        except ImportError:
            self.skipTest('Tcl/Tk required for offline Tcl API-stub tests')
        t = tkinter.Tcl()
        t.eval('''
proc set_param {args} {}
proc open_checkpoint {args} {}
proc current_instance {args} {}
proc current_design {} {return demo}
proc get_cells {args} {return cells}
proc get_pblocks {args} {return compact}
proc close_design {} {}
proc exit {args} {}
proc get_sites {args} {
    if {[lsearch -exact $args -of_objects] >= 0} {return {SLICE_X0Y0 SLICE_X1Y0 SLICE_X3Y0}}
    return {SLICE_X0Y0 SLICE_X1Y0 SLICE_X2Y0 SLICE_X3Y0 SLICE_X0Y2}
}
proc get_property {name object} {
    if {$name eq "PART"} {return xc7z020clg400-1}
    if {$name eq "IS_SOFT"} {return 0}
    if {$name eq "GRID_RANGES"} {return $::ranges}
    error "Unexpected property"
}
''')
        t.setvar('ranges', ranges)
        output = self.root / 'sites.txt'
        t.setvar('argc', 3)
        t.setvar('argv', t.call('list', str(self.report_dir / 'routed.dcp'), str(output), 'compact'))
        return t, output

    def test_tcl_counts_real_site_union(self):
        t, output = self.tcl('SLICE_X0Y0:SLICE_X1Y1 SLICE_X1Y0:SLICE_X2Y1')
        t.eval((ROOT / 'scripts/collect_sites.tcl').read_text(encoding='utf-8'))
        values = dict(line.split('=', 1) for line in output.read_text().splitlines())
        self.assertEqual(values['device_slice_sites'], '5')
        self.assertEqual(values['allowed_slice_sites'], '3')
        self.assertEqual(values['reserved_slice_sites'], '2')
        self.assertEqual(values['occupied_outside_region'], '1')

    def test_tcl_rejects_mixed_resource_ranges(self):
        t, output = self.tcl('SLICE_X0Y0:SLICE_X1Y1 DSP48_X0Y0:DSP48_X1Y1')
        import tkinter
        with self.assertRaisesRegex(tkinter.TclError, 'Unsupported'):
            t.eval((ROOT / 'scripts/collect_sites.tcl').read_text(encoding='utf-8'))
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
