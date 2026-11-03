"""Tcl flow validation with command stubs, not HLS synthesis or simulation."""
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HLSTemplateTests(unittest.TestCase):
    def setUp(self):
        try:
            import tkinter
            self.tcl = tkinter.Tcl()
        except (ImportError, RuntimeError) as error:
            self.skipTest('Tkinter/Tcl unavailable: ' + str(error))
        self.TclError = tkinter.TclError
        temp = ROOT / 'validation/tmp'; temp.mkdir(parents=True, exist_ok=True)
        self.work = tempfile.TemporaryDirectory(dir=temp); self.addCleanup(self.work.cleanup)
        self.dest = Path(self.work.name) / 'output with spaces'
        for key in ('VADD_PART', 'VADD_CLOCK_NS', 'VADD_OUT', 'VADD_STAGE'):
            variable = 'env(' + key + ')'
            exists = bool(int(self.tcl.call('info', 'exists', variable)))
            previous = self.tcl.getvar(variable) if exists else None
            self.addCleanup(self.restore_env, variable, previous)
            self.tcl.call('unset', '-nocomplain', variable)
        self.tcl.setvar('env(VADD_PART)', 'test-part-no-hardware')
        self.tcl.setvar('env(VADD_CLOCK_NS)', '10')
        self.tcl.setvar('env(VADD_OUT)', str(self.dest))
        self.tcl.eval('set ::calls {}')
        for name in ('set_top', 'add_files', 'open_solution', 'set_part', 'create_clock',
                     'csim_design', 'csynth_design', 'cosim_design', 'export_design', 'close_project'):
            self.tcl.eval('proc ' + name + ' {args} {lappend ::calls [linsert $args 0 ' + name + ']}')
        self.tcl.eval('proc open_project {path} {lappend ::calls [list open_project $path]; file mkdir $path}')

    def restore_env(self, variable, previous):
        if previous is None:
            self.tcl.call('unset', '-nocomplain', variable)
        else:
            self.tcl.setvar(variable, previous)

    def source(self):
        self.tcl.call('source', str(ROOT / 'examples/vector_add_hls/run_hls.tcl'))

    def calls(self):
        return [tuple(str(arg) for arg in self.tcl.splitlist(item))
                for item in self.tcl.splitlist(self.tcl.getvar('calls'))]

    def test_default_only_runs_csim(self):
        self.source()
        names = [call[0] for call in self.calls()]
        self.assertIn('csim_design', names)
        self.assertNotIn('csynth_design', names)
        self.assertNotIn('cosim_design', names)
        self.assertNotIn('export_design', names)
        self.assertEqual(names[-1], 'close_project')

    def test_stages_run_in_required_order(self):
        for stage, expected in [('synth', ['csim_design', 'csynth_design']),
                                ('cosim', ['csim_design', 'csynth_design', 'cosim_design']),
                                ('export', ['csim_design', 'csynth_design', 'cosim_design', 'export_design'])]:
            with self.subTest(stage=stage):
                self.tcl.setvar('env(VADD_STAGE)', stage)
                self.tcl.setvar('env(VADD_OUT)', str(self.dest.parent / stage))
                self.tcl.eval('set ::calls {}')
                self.source()
                self.assertEqual([c[0] for c in self.calls() if c[0].endswith('_design')], expected)

    def test_missing_part_rejected_before_project(self):
        self.tcl.call('unset', 'env(VADD_PART)')
        with self.assertRaisesRegex(self.TclError, 'VADD_PART'):
            self.source()
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.dest.exists())

    def test_invalid_period_rejected_before_project(self):
        for invalid in ('0', '-1', 'NaN', 'Inf', '-Inf', 'not-a-number'):
            with self.subTest(period=invalid):
                self.tcl.setvar('env(VADD_CLOCK_NS)', invalid)
                with self.assertRaisesRegex(self.TclError, 'positive and finite'):
                    self.source()
                self.assertEqual(self.calls(), [])
                self.assertFalse(self.dest.exists())

    def test_unknown_stage_does_not_start_tools(self):
        self.tcl.setvar('env(VADD_STAGE)', 'route')
        with self.assertRaisesRegex(self.TclError, 'VADD_STAGE'):
            self.source()
        self.assertEqual(self.calls(), [])

    def test_existing_output_preserved(self):
        self.dest.mkdir()
        marker = self.dest / 'keep.txt'; marker.write_text('retain', encoding='utf-8')
        with self.assertRaisesRegex(self.TclError, 'Output exists'):
            self.source()
        self.assertEqual(marker.read_text(encoding='utf-8'), 'retain')
        self.assertEqual(self.calls(), [])

    def test_paths_and_parameters_are_separate_arguments(self):
        self.source()
        calls = self.calls()
        opened = next(c for c in calls if c[0] == 'open_project')
        self.assertEqual(Path(opened[1]).resolve(), self.dest.resolve())
        self.assertEqual(len(opened), 2)
        self.assertIn(('set_part', 'test-part-no-hardware'), calls)
        self.assertIn(('create_clock', '-period', '10', '-name', 'default'), calls)
        for call in calls:
            if call[0] == 'add_files':
                file_arg = call[2] if call[1] == '-tb' else call[1]
                self.assertTrue(Path(file_arg).is_file())


if __name__ == '__main__':
    unittest.main()
