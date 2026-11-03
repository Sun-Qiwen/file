"""Exercise real session formatting with accelerator execution substituted in RAM."""
from pathlib import Path
import builtins
import importlib.util
import sys
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / 'board/runtime/application'
sys.path.insert(0, str(APP))
from engine_runtime import Engine


class MemoryEngine(Engine):
    def __init__(self):
        self.configure(APP)
        self.arena = np.zeros(self.exp['total_bytes'] // 8, np.uint64)
        self.calls = []

    def invoke(self, first, last):
        self.calls.append((first, last))
        self.history.append({'board_measured': False})
        if (first, last) == (169, 214):
            output = self.arena.view(np.uint8)[5652480:5652480 + 4609 * 4].view(np.float32)
            output[:4608] = 2.5
            output[4608] = -0.75


class HardwareSessionTests(unittest.TestCase):
    def test_explicit_cnn_id_executes_cnn_range_and_returns_float_outputs(self):
        engine = MemoryEngine()
        heat, valid = engine.factory('cnn').run(None, {'image': np.zeros((1, 1, 96, 96), np.float32)})
        self.assertEqual(engine.calls, [(169, 214)])
        self.assertEqual(heat.shape, (1, 2, 48, 48))
        self.assertTrue(np.all(heat == 2.5))
        self.assertEqual(float(valid[0, 0]), -0.75)

    def test_unknown_model_is_rejected_instead_of_executing_detector(self):
        engine = MemoryEngine()
        with self.assertRaises(ValueError):
            engine.factory('unknown')
        self.assertEqual(engine.calls, [])

    def test_pipeline_import_and_hardware_execution_need_no_optional_backend(self):
        original_import = builtins.__import__

        def required_import(name, *args, **kwargs):
            if name.split('.')[0] in ('motion', 'onnxruntime'):
                raise ImportError('optional backend is unavailable: ' + name)
            return original_import(name, *args, **kwargs)

        spec = importlib.util.spec_from_file_location('standalone_pipeline', APP / 'board_pipeline.py')
        module = importlib.util.module_from_spec(spec)
        with patch('builtins.__import__', side_effect=required_import):
            spec.loader.exec_module(module)
            engine = MemoryEngine()
            pipeline = module.Pipeline(APP, session_factory=engine.factory)
            result = pipeline.run_frame(np.full((480, 640, 3), 128, np.uint8), timestamp=1.)
        self.assertEqual(engine.calls, [(0, 169), (169, 214)])
        self.assertTrue(result['cnn_ran'])
        self.assertIsNone(result['angle_degrees'])


if __name__ == '__main__':
    unittest.main()
