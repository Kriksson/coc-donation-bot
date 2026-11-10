from pathlib import Path
import shutil
import unittest

import cv2
import numpy as np

from coc_bot.progression.reader import unreadable_building_title
from coc_bot.upgrades.vision import Candidate, UpgradeReader
from coc_bot.vision.battle_completion import BattleCompletionDetector


@unittest.skipUnless(shutil.which('tesseract'), 'Tesseract is required')
class HeroHallTitleTests(unittest.TestCase):
    def test_observed_title_and_other_buildings(self):
        fixtures = Path(__file__).parent / 'fixtures' / 'progression'
        for name in ('hero-hall', 'barbarian-king', 'elixir-collector', 'barracks'):
            with self.subTest(name=name):
                image = cv2.imread(str(fixtures / (name + '.png')))
                hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
                letters = (cv2.inRange(hsv, (0, 0, 205), (180, 80, 255)) |
                           cv2.inRange(hsv, (35, 80, 170), (90, 255, 255)))
                self.assertEqual(unreadable_building_title(image, letters),
                                 'Hero Hall' if name == 'hero-hall' else '')

    def test_clipped_title_is_not_accepted(self):
        image = np.zeros((35, 130, 3), dtype=np.uint8)
        mask = np.zeros((35, 130), dtype=np.uint8)
        mask[8:28, 119:130] = 255
        self.assertEqual(unreadable_building_title(image, mask), '')

    def test_laboratory_confirmation_checks_name_price_and_currency(self):
        path = Path(__file__).parent / 'fixtures/progression/laboratory-confirmation.png'
        image = cv2.imread(str(path))
        reader = UpgradeReader()
        self.assertIsNotNone(reader.confirmation(image, Candidate('Laboratory', 400000, 'elixir', (0, 0))))
        for name, price, currency in (('Laboratory', 800000, 'elixir'),
                                      ('Laboratory', 400000, 'gems'),
                                      ('Barracks', 400000, 'elixir')):
            with self.subTest(name=name, price=price, currency=currency):
                self.assertIsNone(reader.confirmation(image, Candidate(name, price, currency, (0, 0))))

    def test_laboratory_running_timer_and_builder_count(self):
        path = Path(__file__).parent / 'fixtures/progression/laboratory-running.png'
        image = cv2.imread(str(path))
        reader = UpgradeReader()
        self.assertIn('laboratory', reader.active_names(image))
        self.assertEqual(reader.availability(image, 'buildings'), (0, 4))

    def test_battle_result_requires_both_visible_labels(self):
        path = Path(__file__).parent / 'fixtures/progression/battle-results.png'
        image = cv2.imread(str(path))
        detector = BattleCompletionDetector()
        self.assertIsNotNone(detector.detect(image))
        without_label = image.copy()
        without_label[690:735, 820:1100] = 0
        self.assertIsNone(detector.detect(without_label))
        without_button = image.copy()
        without_button[865:1000, 820:1100] = 0
        self.assertIsNone(detector.detect(without_button))
