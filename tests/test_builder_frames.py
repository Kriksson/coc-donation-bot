import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from coc_bot.builder_base.frames import BuilderFrameCapture, normalize_builder_frame
from coc_bot.builder_base.runner import BuilderBaseRunner
from coc_bot.builder_base.upgrades import BuilderUpgradeRunner
from coc_bot.builder_base.vision import BuilderReader
from coc_bot.config import BotConfig
from coc_bot.upgrades.vision import Candidate, crop


FIXTURES = Path(__file__).parent / 'fixtures' / 'builder_base'


class _Capture:
    def __init__(self, frame):
        self.frame = frame
        self.calls = 0

    def screenshot(self):
        self.calls += 1
        return self.frame.copy()


def _config(data_dir):
    return BotConfig('test', 'test.package', .9, .9, [], 0, (0, 0), (0, 0),
                      0, 0, 0, data_dir=Path(data_dir))


class BuilderFrameNormalizationTests(unittest.TestCase):
    def frame(self, name):
        result = cv2.imread(str(FIXTURES / name))
        self.assertIsNotNone(result, name)
        return result

    def test_native_builder_home_battle_result_and_selected_modal_normalize(self):
        reader = BuilderReader()
        cases = (
            ('home-dark-scene.png', 'home'),
            ('village-capped.png', 'home'),
            ('battle-baby-dragon-predeploy-capped.png', 'battle'),
            ('result-capped.png', 'result'),
        )
        for filename, screen in cases:
            with self.subTest(filename=filename):
                raw = self.frame(filename)
                before = raw.copy()
                normalized = normalize_builder_frame(raw)
                self.assertFalse(np.array_equal(raw, normalized))
                self.assertEqual(raw.shape, normalized.shape)
                self.assertTrue(np.array_equal(raw, before), 'normalization mutated source evidence')
                self.assertEqual(int(normalized.max()), 255)
                if screen == 'home':
                    self.assertTrue(reader.home(normalized))
                elif screen == 'battle':
                    self.assertTrue(reader.battle(normalized))
                else:
                    self.assertIsNotNone(reader.result_button(normalized))

    def test_capped_village_labels_become_ocr_usable_but_panel_is_not_payment(self):
        raw = self.frame('village-capped.png')
        normalized = normalize_builder_frame(raw)
        box = (.28, .22, .48, .30)
        reader = BuilderReader()
        self.assertNotEqual(reader.white_text(crop(raw, box)), 'Star Laboratory')
        self.assertEqual(reader.white_text(crop(normalized, box)), 'Star Laboratory')
        # This is a selected-building action panel, not a payment confirmation.
        candidate = Candidate('Star Laboratory', 700_000, 'elixir', (1, 1))
        self.assertIsNone(reader.confirmation(normalized, candidate))

    def test_dimmed_background_stays_rejected_when_panel_foreground_normalizes(self):
        raw = self.frame('village-capped.png')
        composite = cv2.convertScaleAbs(raw, alpha=.5)
        # Retain the actual selected-building panel as a capped foreground.
        h, w = raw.shape[:2]
        x0, x1 = round(w * .27), round(w * .73)
        y0, y1 = round(h * .64), round(h * .93)
        composite[y0:y1, x0:x1] = raw[y0:y1, x0:x1]
        title_x0, title_x1 = round(w * .25), round(w * .55)
        title_y0, title_y1 = round(h * .20), round(h * .31)
        composite[title_y0:title_y1, title_x0:title_x1] = raw[title_y0:title_y1, title_x0:title_x1]
        normalized = normalize_builder_frame(composite)
        self.assertFalse(np.array_equal(normalized, composite))
        self.assertEqual(BuilderReader().white_text(crop(normalized, (.28, .22, .48, .30))),
                         'Star Laboratory')
        # The foreground text remains usable, but dim village anchors do
        # not regain Builder-home brightness and cannot authorize actions.
        self.assertFalse(BuilderReader().home(normalized))
        self.assertIsNone(BuilderReader().confirmation(
            normalized, Candidate('Star Laboratory', 700_000, 'elixir', (1, 1))))

    def test_android_popup_half_bright_unknown_home_and_malformed_frames_stay_unchanged(self):
        reader = BuilderReader()
        popup = self.frame('os-popup-builder.png')
        self.assertIs(normalize_builder_frame(popup), popup)
        self.assertFalse(reader.home(normalize_builder_frame(popup)))

        native = self.frame('home-dark-scene.png')
        half = cv2.convertScaleAbs(native, alpha=.5)
        self.assertIs(normalize_builder_frame(half), half)
        self.assertEqual(int(half.max()), 89)

        home = cv2.imread(str(Path(__file__).parent / 'fixtures' / 'resource_visits' / 'home-gold-capacity.png'))
        self.assertIs(normalize_builder_frame(home), home)
        unknown = np.zeros((1080, 1920, 3), dtype=np.uint8)
        unknown[::2, ::2] = 178
        self.assertIs(normalize_builder_frame(unknown), unknown)

        for malformed in (None, np.empty((0, 0, 3), np.uint8), np.zeros((12, 12), np.uint8)):
            with self.subTest(shape=None if malformed is None else malformed.shape):
                self.assertIs(normalize_builder_frame(malformed), malformed)

    def test_navigation_strip_does_not_hide_capped_result_signature(self):
        raw = self.frame('result-capped.png')
        with_nav = raw.copy()
        with_nav[-20:, :] = 255
        normalized = normalize_builder_frame(with_nav)
        self.assertIsNot(normalized, with_nav)
        self.assertTrue(BuilderReader().result_button(normalized))
        self.assertTrue(np.array_equal(with_nav[-20:, :], normalized[-20:, :]))

    def test_proxy_and_both_runner_constructors_wrap_once_and_retain_raw(self):
        capped = self.frame('home-dark-scene.png')
        source = _Capture(capped)
        proxy = BuilderFrameCapture(source)
        self.assertIs(BuilderFrameCapture(proxy), proxy)

        with tempfile.TemporaryDirectory() as tmp:
            config = _config(tmp)
            base = BuilderBaseRunner(config, source, object(), object(), object())
            self.assertIsInstance(base.capture, BuilderFrameCapture)
            view = base.frame()
            self.assertTrue(base.reader.home(view))
            raw = base.capture.raw_for(view)
            self.assertIsNotNone(raw)
            self.assertTrue(np.array_equal(raw, capped))
            base.evidence(view, 'normalized-home')
            files = list(base.folder.glob('*.png'))
            self.assertEqual({p.name for p in files}, {
                '001-normalized-home.png', '001-normalized-home-raw.png'})
            raw_path = base.folder / '001-normalized-home-raw.png'
            self.assertTrue(np.array_equal(cv2.imread(str(raw_path)), capped))

            upgrades = BuilderUpgradeRunner(config, source, object(), object())
            self.assertIsInstance(upgrades.capture, BuilderFrameCapture)
            view = upgrades.capture.screenshot()
            self.assertTrue(upgrades.reader.home(view))
            self.assertIsNotNone(upgrades.capture.raw_for(view))
        self.assertGreaterEqual(source.calls, 2)


if __name__ == '__main__':
    unittest.main()
