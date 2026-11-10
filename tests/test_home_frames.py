import unittest
from pathlib import Path

import cv2
import numpy as np

from coc_bot.builder_base.frames import BuilderFrameCapture
from coc_bot.builder_base.vision import BuilderReader
from coc_bot.progression.reader import ProgressionReader
from coc_bot.upgrades.vision import UpgradeReader
from coc_bot.vision.home_frames import HomeFrameCapture, normalize_home_frame
from coc_bot.vision.matcher import TemplateMatcher


FIXTURES = Path(__file__).parent / 'fixtures' / 'progression'
BUILDER_FIXTURES = Path(__file__).parent / 'fixtures' / 'builder_base'


class _Capture:
    def __init__(self, frame):
        self.frame = frame

    def screenshot(self):
        return self.frame.copy()


class _HomeClassifier:
    """Use the saved, known-visible Home chat control as the real template."""
    def __init__(self, frame):
        h, w = frame.shape[:2]
        self.chat = frame[int(h * .43):int(h * .58), int(w * .014):int(w * .094)].copy()
        self.matcher = TemplateMatcher(scale_range=[.95, 1.0, 1.05])

    def _load(self, name):
        return self.chat if name == 'open_chat' else None

    def _open_chat_icon_visible(self, frame):
        return self.matcher.find(frame, self.chat) is not None


class _Navigator:
    def __init__(self, frame):
        self.classifier = _HomeClassifier(frame)


class HomeFrameNormalizationTests(unittest.TestCase):
    def frame(self, name, directory=FIXTURES):
        result = cv2.imread(str(directory / name))
        self.assertIsNotNone(result, name)
        return result

    def test_capped_home_build_menu_normalizes_and_preserves_coordinates(self):
        raw = self.frame('home-build-menu-capped.png')
        for name, candidate in (
                ('home-build-menu-capped.png', raw),
                ('home-build-menu-live-capped.png', self.frame('home-build-menu-live-capped.png'))):
            with self.subTest(name=name):
                before = candidate.copy()
                normalized = normalize_home_frame(candidate)
                self.assertIsNot(normalized, candidate)
                self.assertEqual(normalized.shape, candidate.shape)
                self.assertEqual(int(normalized.max()), 255)
                self.assertTrue(np.array_equal(candidate, before), 'source evidence was mutated')
                self.assertEqual(UpgradeReader().menu_kind(normalized), 'buildings')

        proxy=HomeFrameCapture(_Capture(raw))
        self.assertIs(HomeFrameCapture(proxy),proxy)
        # Supply the village context on a later idempotent wrap; it must update
        # the existing proxy rather than silently preserving a missing context.
        nav=_Navigator(self.frame('home-village-capped.png'))
        self.assertIs(HomeFrameCapture(proxy,nav),proxy)
        view=proxy.screenshot()
        self.assertTrue(proxy.was_normalized(view))
        self.assertTrue(np.array_equal(proxy.raw_for(view),raw))

    def test_capped_home_village_needs_build_and_bright_chat_anchor(self):
        raw = self.frame('home-village-capped.png')
        nav = _Navigator(raw)
        normalized = normalize_home_frame(raw, nav)
        self.assertIsNot(normalized, raw)
        self.assertTrue(nav.classifier._open_chat_icon_visible(normalized))
        self.assertFalse(BuilderReader().home(normalized))

        # Correlation alone would still match a dimmed copy; the measured
        # brightness condition prevents a foreground modal from restoring it.
        dim = cv2.convertScaleAbs(raw, alpha=.5)
        self.assertIs(normalize_home_frame(dim, nav), dim)

    def test_normal_brightness_builder_and_unknown_frames_stay_scoped(self):
        capped = self.frame('home-build-menu-capped.png')
        ordinary = cv2.convertScaleAbs(capped, alpha=255 / 178)
        self.assertIs(normalize_home_frame(ordinary), ordinary)

        builder = self.frame('village-capped.png', BUILDER_FIXTURES)
        nav = _Navigator(self.frame('home-village-capped.png'))
        self.assertIs(normalize_home_frame(builder, nav), builder)
        composed = BuilderFrameCapture(_Capture(builder), nav).screenshot()
        self.assertIsNot(composed, builder)
        self.assertTrue(BuilderReader().home(composed))

        unknown = np.zeros_like(capped)
        unknown[::2, ::2] = 178
        self.assertIs(normalize_home_frame(unknown, nav), unknown)
        popup = self.frame('os-popup-builder.png', BUILDER_FIXTURES)
        popup_proxy=BuilderFrameCapture(_Capture(popup), nav)
        popup_after=popup_proxy.screenshot()
        self.assertTrue(np.array_equal(popup_after,popup))
        self.assertFalse(popup_proxy.was_normalized(popup_after))

    def test_capped_menu_modal_over_dim_home_does_not_restore_hidden_hud(self):
        raw = self.frame('home-build-menu-capped.png')
        h, w = raw.shape[:2]
        composite = cv2.convertScaleAbs(raw, alpha=.5)
        # The foreground menu/title/X remains capped while the Home HUD behind
        # it is at 89. Menu identity must fail because both HUD icons are dim.
        x = round(w * .73)
        composite[:, x:] = raw[:, x:]
        self.assertTrue(np.array_equal(composite[:int(h * .94)].max(axis=(0, 1)),
                                       np.full(3, 178, np.uint8)))
        self.assertIs(normalize_home_frame(composite), composite)

        composed = BuilderFrameCapture(_Capture(composite)).screenshot()
        self.assertTrue(np.array_equal(composed,composite))

    def test_home_filter_dialog_normalizes_without_weakening_hud_gate(self):
        raw = self.frame('home-filter-panel-capped.png')
        before = raw.copy()
        normalized = normalize_home_frame(raw)
        self.assertIsNot(normalized, raw)
        self.assertTrue(np.array_equal(raw, before), 'source evidence was mutated')
        reader = ProgressionReader()
        self.assertTrue(reader.filters_open(normalized))
        self.assertIsNone(reader.selected_filter(normalized))
        self.assertIsNone(UpgradeReader().menu_kind(normalized))
        self.assertEqual(UpgradeReader().label(normalized, (.79, .012, .96, .05)).replace('€', '&').replace(' ', ''), 'Buildings&Heroes')

        # The overlay's foreground cap cannot make an arbitrary dim Home HUD
        # look like the ordinary village or Build menu.
        dim = cv2.convertScaleAbs(raw, alpha=.55)
        self.assertIs(normalize_home_frame(dim), dim)

        selected = self.frame('home-filter-panel-cost-max-selected-capped.png')
        selected_view = normalize_home_frame(selected)
        self.assertIsNot(selected_view, selected)
        self.assertEqual(reader.selected_filter(selected_view), (round(.418 * selected.shape[1]), round(.65 * selected.shape[0])))


if __name__ == '__main__':
    unittest.main()
