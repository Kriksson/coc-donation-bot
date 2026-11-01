from pathlib import Path
from unittest import TestCase
from types import SimpleNamespace
from unittest.mock import Mock
import tempfile
import cv2
from coc_bot.upgrades.vision import UpgradeReader
from coc_bot.upgrades.runner import UpgradeRunner

ROOT=Path(__file__).parent/'fixtures/upgrades'


class GoblinCounterTests(TestCase):
    def test_paid_goblin_is_excluded_from_builder_and_lab_free_counts(self):
        reader=UpgradeReader()
        for name,kind,expected in (('goblin-builder-counter.png','buildings',(0,5)),
                                   ('goblin-research-counter.png','research',(0,1))):
            frame=cv2.imread(str(ROOT/name))
            self.assertEqual(reader.availability(frame,kind),expected)
            self.assertIn(reader.availability(cv2.resize(frame,(1280,724)),kind),(None,expected))

    def test_normal_builder_fraction_is_unchanged(self):
        reader=UpgradeReader()
        frame=cv2.imread(str(ROOT/'goblin-research-counter.png'))
        self.assertEqual(reader.availability(frame,'buildings'),(1,5))

    def test_real_second_camp_receipt_reconciles_without_another_spending_tap(self):
        frame=cv2.imread(str(ROOT/'goblin-builder-counter.png'))
        with tempfile.TemporaryDirectory() as folder:
            config=SimpleNamespace(data_dir=Path(folder))
            runner=UpgradeRunner(config,Mock(),Mock(),Mock())
            state={'pending':{'kind':'buildings','name':'ARMY Camp','cost':13000000,'currency':'elixir',
                              'free_before':1,'active_before':0,'phase':'confirming'}}
            # Native slot proof is real; OCR timer names are covered separately
            # by the current-UI fixtures and rechecked on the server.
            runner.reader.active_names=Mock(return_value=['darkbarracks','goldstorage','armycamp','armycamp','armycamp'])
            self.assertTrue(runner._verify_pending(state,'buildings',frame))
            self.assertNotIn('pending',state);runner.input.tap.assert_not_called()
