from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock,patch
import cv2
from coc_bot.progression.inactive_army import inactive_clear,clear_confirmation,clear_inactive

ROOT=Path(__file__).parent/'fixtures/progression'

class InactiveArmyTests(TestCase):
 def frame(self,name):return cv2.imread(str(ROOT/name))
 def test_current_level_two_unlocks_are_read_without_changing_digit_thresholds(self):
  from coc_bot.progression.preparation import picker_boxes,picker_level
  f=self.frame('newera-troop-picker.png');found=[]
  for x,y,w,h in picker_boxes(f):
   if (990<x<1400 and y<800) or (1180<x<1190 and y>800):
    found.append(picker_level(f[y:y+h,x:x+w]))
  self.assertEqual(found,[2,2,2,2])
 def test_native_expired_army_and_troop_only_dialog(self):
  f=self.frame('inactive-super-army.png');d=self.frame('remove-troops.png')
  self.assertEqual(inactive_clear(f)[1],(320,320))
  self.assertIsNone(inactive_clear(d))
  self.assertIsNone(clear_confirmation(f))
  self.assertIsNotNone(clear_confirmation(d))
  for scale in (.75,1.25):
   self.assertIsNotNone(inactive_clear(cv2.resize(f,None,fx=scale,fy=scale)))
   self.assertIsNotNone(clear_confirmation(cv2.resize(d,None,fx=scale,fy=scale)))
 def test_changed_or_dimmed_controls_never_authorize_clear(self):
  f=self.frame('inactive-super-army.png')
  self.assertIsNone(inactive_clear(cv2.convertScaleAbs(f,alpha=.55)))
  f[369:416,815:940]=0;self.assertIsNone(inactive_clear(f))
  d=self.frame('remove-troops.png');d[460:492,570:1285]=0
  self.assertIsNone(clear_confirmation(d))
  self.assertIsNone(inactive_clear(self.frame('inactive-super-army.png'),lambda:True))
  self.assertIsNone(clear_confirmation(self.frame('remove-troops.png'),lambda:True))
 def prep(self):return SimpleNamespace(frame=Mock(return_value=self.frame('remove-troops.png')),tap=Mock(),stop=None,s=SimpleNamespace(_sleep=Mock()))
 def test_changed_second_inactive_observation_sends_nothing(self):
  p=self.prep()
  with patch('coc_bot.progression.inactive_army.inactive_clear',side_effect=[((1790,247),(320,320)),None]):
   with self.assertRaisesRegex(ValueError,'changed'):clear_inactive(p)
  p.tap.assert_not_called()
 def test_unknown_dialog_never_sends_confirmation(self):
  p=self.prep()
  with patch('coc_bot.progression.inactive_army.inactive_clear',return_value=((1790,247),(320,320))),patch('coc_bot.progression.inactive_army.clear_confirmation',return_value=None):
   with self.assertRaisesRegex(ValueError,'confirmation is unverified'):clear_inactive(p)
  p.tap.assert_called_once_with((1790,247))
 def test_uncertain_clear_never_replays_confirmation(self):
  p=self.prep()
  with patch('coc_bot.progression.inactive_army.inactive_clear',return_value=((1790,247),(320,320))),patch('coc_bot.progression.preparation.army_page',return_value=True),patch('coc_bot.progression.preparation.capacity',return_value=(320,320)):
   with self.assertRaisesRegex(ValueError,'not verified'):clear_inactive(p)
  self.assertEqual(p.tap.call_count,2)
 def test_empty_camps_required_before_replacement(self):
  p=self.prep()
  with patch('coc_bot.progression.inactive_army.inactive_clear',return_value=((1790,247),(320,320))),patch('coc_bot.progression.preparation.army_page',return_value=True),patch('coc_bot.progression.preparation.capacity',return_value=(0,320)):
   self.assertTrue(clear_inactive(p))
  self.assertEqual(p.tap.call_count,2)
