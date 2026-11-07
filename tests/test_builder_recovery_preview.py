"""A rejected research preview must retain a safe, non-spending exit."""
import shutil
import unittest
from unittest.mock import Mock, patch
from pathlib import Path
import cv2
from coc_bot.builder_base.vision import BuilderReader
from coc_bot.builder_base.progression import BuilderProgressionRunner
from coc_bot.builder_base.upgrades import BuilderUpgradeRunner
from coc_bot.upgrades.vision import Candidate


class BuilderPlacementRecoveryTests(unittest.TestCase):
    def test_native_preview_cancels_only_after_matching_frames_and_no_payment(self):
        runner = BuilderProgressionRunner.__new__(BuilderProgressionRunner)
        runner.reader = Mock()
        runner.reader.home.return_value = True
        runner.capture = Mock()
        runner.input = Mock()
        runner.stopped = Mock(return_value=False)
        runner.state = Mock(return_value={})
        runner.wait = Mock(return_value=False)
        runner.construction_controls = Mock(return_value=None)
        runner._native_preview_cancel = Mock(side_effect=[(642, 463), (642, 463), None])
        with patch.object(BuilderUpgradeRunner, 'close'):
            runner.close()
            runner.input.tap.assert_called_once_with(642, 463, jitter=0)
            runner.input.reset_mock()
            runner.state.return_value = {'pending': {'kind': 'construction'}}
            runner.close()
            runner.input.tap.assert_not_called()


@unittest.skipUnless(shutil.which('tesseract'),'Tesseract is required')
class BuilderPreviewRecoveryTests(unittest.TestCase):
    def test_level_five_ocr_confusion_can_close_but_does_not_authorize_payment(self):
        frame=cv2.imread(str(Path(__file__).parent/'fixtures/builder_base/rejected-level-five-preview.png'))
        reader=BuilderReader()
        self.assertEqual(reader.detail_close(frame),(1555,67))
        with patch.object(reader,'label',return_value='UpgrRade to level S?'):
            self.assertEqual(reader.detail_close(frame),(1555,67))
        self.assertIsNone(reader.confirmation(frame,Candidate('Night Witch',100000,'elixir',(0,0))))
        self.assertIsNone(reader.confirmation(frame,Candidate('Sneaky Archer',999,'elixir',(0,0))))
        missing=frame.copy();missing[25:116,1512:1605]=0
        self.assertIsNone(reader.detail_close(missing))
        missing=frame.copy();missing[125:189,880:1502]=0
        self.assertIsNone(reader.detail_close(missing))
