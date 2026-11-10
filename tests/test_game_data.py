import re
import unittest
from pathlib import Path

from coc_bot.game_data import load_units
from coc_bot.progression.profiles import HOME_PROFILES


ROOT=Path(__file__).resolve().parents[1]
ICON_ROOT=ROOT/'data'/'icons'


class GameDataTests(unittest.TestCase):
    def test_canonical_icon_ids_keep_their_verified_metadata(self):
        units=load_units()
        expected={
            'baby_dragon':('Baby Dragon','troop',10),
            'battle_blimp':('Battle Blimp','siege',1),
            'flame_flinger':('Flame Flinger','siege',1),
            'furnace':('Furnace','troop',18),
            'lava_hound':('Lava Hound','troop',30),
            'minion':('Minion','troop',2),
            'siege_barracks':('Siege Barracks','siege',1),
            'stone_slammer':('Stone Slammer','siege',1),
            'troop_launcher':('Troop Launcher','siege',1),
            'valkyrie':('Valkyrie','troop',8),
            'wall_wrecker':('Wall Wrecker','siege',1),
            'witch':('Witch','troop',12),
        }
        for unit_id,(name,category,housing) in expected.items():
            with self.subTest(unit_id=unit_id):
                self.assertEqual((units[unit_id].name,units[unit_id].category,units[unit_id].housing),
                                 (name,category,housing))

    def test_every_bundled_icon_has_metadata_without_raw_baby_dragon_alias(self):
        units=load_units()
        icon_ids={path.stem for path in ICON_ROOT.rglob('*.webp')}
        self.assertGreater(len(icon_ids),0)
        self.assertLessEqual(icon_ids,set(units))
        self.assertNotIn('babydragon',units)

    def test_home_profile_troops_resolve_to_canonical_metadata(self):
        units=load_units()
        for profile in HOME_PROFILES:
            for unit_id,_ in profile.troops:
                with self.subTest(profile=profile.id,unit_id=unit_id):
                    self.assertIn(unit_id,units)

    def test_catalog_has_no_duplicate_normalized_display_names(self):
        units=load_units()
        names=[re.sub(r'[^a-z0-9]','',unit.name.casefold()) for unit in units.values()]
        self.assertEqual(len(names),len(set(names)))


if __name__=='__main__':
    unittest.main()
