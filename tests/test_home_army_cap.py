import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2
import numpy as np

from coc_bot.attack.army import ArmyCard, UnitCatalog, agree_cards, card_boxes, read_army
from coc_bot.vision.battle_menu import battlefield_ready
from coc_bot.vision.capped_frames import has_exact_cap_178


FIXTURES = Path(__file__).parent / 'fixtures'


class HomeArmyCapTests(unittest.TestCase):
    def _home_battle_with_known_troop(self):
        """Pair existing native battle controls with its saved x20 card art."""
        battle = cv2.imread(str(FIXTURES / 'attack' / 'boundary-bright.png'))
        card_frame = cv2.imread(str(FIXTURES / 'progression' / 'barbarian-battle.png'))
        box = card_boxes(card_frame, 'battle')[0]
        x, y, w, h = box
        battle[y:y + h, x:x + w] = card_frame[y:y + h, x:x + w]
        return battle

    def _catalog(self, temp_dir):
        editor = cv2.imread(str(FIXTURES / 'progression' / 'army-editor.png'))
        box = card_boxes(editor, 'army_confirmation')[0]
        catalog = UnitCatalog(Path(temp_dir))
        catalog.add_references(editor, [
            ArmyCard('0', box, 'barbarian', 'troop', 20, confirmed=True)
        ])
        return catalog

    @staticmethod
    def _barbarian(cards):
        return next(card for card in cards if card.unit_id == 'barbarian')

    def test_cap_normalization_preserves_native_battle_count_and_identity(self):
        native = self._home_battle_with_known_troop()
        original = native.copy()
        capped = cv2.convertScaleAbs(native, alpha=178 / 255)
        self.assertTrue(has_exact_cap_178(capped))
        self.assertTrue(battlefield_ready(capped))

        with TemporaryDirectory() as folder:
            catalog = self._catalog(folder)
            before = agree_cards(read_army(native, 'battle', catalog),
                                 read_army(native, 'battle', catalog))
            after = agree_cards(read_army(capped, 'battle', catalog),
                                read_army(capped, 'battle', catalog))

        native_card = self._barbarian(before)
        capped_card = self._barbarian(after)
        self.assertEqual((native_card.unit_id, native_card.quantity, native_card.stable),
                         ('barbarian', 20, True))
        self.assertEqual((capped_card.unit_id, capped_card.quantity, capped_card.stable),
                         ('barbarian', 20, True))
        self.assertEqual(capped_card.box, native_card.box)
        self.assertTrue(np.array_equal(native, original), 'reading mutated the native frame')

    def test_capped_battle_card_without_two_label_battle_proof_stays_unreadable(self):
        capped = cv2.convertScaleAbs(self._home_battle_with_known_troop(), alpha=178 / 255)
        h, w = capped.shape[:2]
        # Cover the End Battle/Surrender control; remaining scenery and cards
        # retain the 178 cap, but the frame no longer proves a live Home battle.
        capped[round(h * .715):round(h * .775),
               round(w * .015):round(w * .13)] = 0
        self.assertTrue(has_exact_cap_178(capped))
        self.assertFalse(battlefield_ready(capped))

        with TemporaryDirectory() as folder:
            catalog = self._catalog(folder)
            cards = agree_cards(read_army(capped, 'battle', catalog),
                                read_army(capped, 'battle', catalog))
        card = self._barbarian(cards)
        self.assertEqual(card.unit_id, 'barbarian')
        self.assertIsNone(card.quantity)
        self.assertFalse(card.stable)

    def test_half_bright_transition_is_not_promoted_to_a_verified_battle(self):
        transition = cv2.convertScaleAbs(self._home_battle_with_known_troop(), alpha=.5)
        self.assertFalse(has_exact_cap_178(transition))
        self.assertFalse(battlefield_ready(transition))

        with TemporaryDirectory() as folder:
            catalog = self._catalog(folder)
            cards = agree_cards(read_army(transition, 'battle', catalog),
                                read_army(transition, 'battle', catalog))
        card = self._barbarian(cards)
        self.assertIsNone(card.quantity)
        self.assertFalse(card.stable)


if __name__ == '__main__':
    unittest.main()
