from pathlib import Path
from unittest import TestCase
import cv2
import numpy as np
from coc_bot.vision.battle_rewards import results,agreeing_results

ROOT=Path(__file__).parent/'fixtures/resource_visits'

class BattleRewardsTests(TestCase):
    def frame(self,village):return cv2.imread(str(ROOT/(village+'-results-native.png')))

    def test_native_home_and_builder_rewards_are_independent_and_read_only(self):
        for village,loot in [('home',{'gold':258758,'elixir':113952,'dark_elixir':2323}),('builder',{'gold':82000})]:
            with self.subTest(village=village):
                frame=self.frame(village);before=frame.copy()
                self.assertEqual(results(frame,village),{'loot':loot,'damage_percent':100,'stars':3})
                self.assertTrue(np.array_equal(frame,before))
                self.assertEqual(results(frame,'home' if village=='builder' else 'builder'),{})
                self.assertEqual(results((frame*.4).astype(np.uint8),village),{})

    def test_labels_currency_and_amount_cannot_be_borrowed_from_another_row(self):
        frame=self.frame('home');frame[431:465,915:1015]=0
        self.assertEqual(results(frame,'home'),{})
        frame=self.frame('builder');frame[649:698,1310:1357]=0
        self.assertEqual(results(frame,'builder'),{})
        frame=self.frame('home');frame[473:520,800:1008]=0
        read=results(frame,'home')['loot']
        self.assertNotIn('gold',read);self.assertEqual(read['elixir'],113952)
        frame=self.frame('home');frame[469:534,1010:1081]=0
        self.assertNotIn('gold',results(frame,'home').get('loot',{}))

    def test_two_frames_must_agree_on_each_reported_field(self):
        frame=self.frame('builder');missing=np.zeros_like(frame)
        self.assertEqual(agreeing_results(frame,missing,'builder'),{})
        second=frame.copy();second[650:691,1147:1290]=0
        read=agreeing_results(frame,second,'builder')
        self.assertNotIn('loot',read);self.assertEqual(read['damage_percent'],100)

    def test_stars_are_not_inferred_from_percent_and_stop_skips_reading(self):
        frame=self.frame('builder');frame[212:425,645:851]=0
        read=results(frame,'builder');self.assertEqual(read['damage_percent'],100)
        self.assertNotIn('stars',read)
        self.assertEqual(results(self.frame('home'),'home',lambda:True),{})

    def test_brightness_cap_is_restored_only_for_result_measurement(self):
        frame=self.frame('builder');capped=np.rint(frame.astype(np.float32)*(178/255)).astype(np.uint8)
        original=capped.copy()
        self.assertEqual(results(capped,'builder')['loot'],{'gold':82000})
        self.assertTrue(np.array_equal(capped,original))
