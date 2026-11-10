import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from coc_bot.vision import ocr
from coc_bot.runtime.processes import ProcessStopped


class LabelOCRBudgetTests(unittest.TestCase):
    def setUp(self):
        ocr._LABEL_CACHE.clear()
        self.addCleanup(ocr._LABEL_CACHE.clear)
        self.image=np.full((24,80,3),180,np.uint8)
        self.clock=0.0

    def test_tiny_remaining_budget_does_not_start_another_process(self):
        def run(*args,**kwargs):
            self.clock=1.8
            return SimpleNamespace(stdout='Confirm')
        with patch.object(ocr.shutil,'which',return_value='/usr/bin/tesseract'), \
             patch.object(ocr.time,'monotonic',side_effect=lambda:self.clock), \
             patch.object(ocr,'run_process',side_effect=run) as process:
            self.assertEqual(ocr.read_short_label(self.image),'confirm')
            self.assertEqual(process.call_count,1)
            self.assertGreater(process.call_args.kwargs['timeout'],.35)

    def test_late_timeout_retains_earlier_text_and_caches_result(self):
        with patch.object(ocr.shutil,'which',return_value='/usr/bin/tesseract'), \
             patch.object(ocr,'run_process',side_effect=[SimpleNamespace(stdout='Confirm'),
                 subprocess.TimeoutExpired('tesseract',1)]) as process:
            self.assertEqual(ocr.read_short_label(self.image),'confirm')
            self.assertEqual(ocr.read_short_label(self.image.copy()),'confirm')
            self.assertEqual(process.call_count,2)

    def test_unreadable_timeout_is_cached_only_briefly(self):
        with patch.object(ocr.shutil,'which',return_value='/usr/bin/tesseract'), \
             patch.object(ocr.time,'monotonic',side_effect=lambda:self.clock), \
             patch.object(ocr,'run_process',side_effect=subprocess.TimeoutExpired('tesseract',2)) as process:
            self.assertIsNone(ocr.read_short_label(self.image))
            self.assertIsNone(ocr.read_short_label(self.image.copy()))
            self.assertEqual(process.call_count,1)
            self.clock=1.1
            self.assertIsNone(ocr.read_short_label(self.image))
            self.assertEqual(process.call_count,2)

    def test_stop_does_not_cache_partial_text(self):
        with patch.object(ocr.shutil,'which',return_value='/usr/bin/tesseract'), \
             patch.object(ocr,'run_process',side_effect=[SimpleNamespace(stdout='Confirm'),ProcessStopped('stop')]):
            self.assertIsNone(ocr.read_short_label(self.image))
        self.assertEqual(len(ocr._LABEL_CACHE),0)
