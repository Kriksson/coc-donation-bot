from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock
import cv2
from coc_bot.accounts.store import read
from coc_bot.progression.construction import Construction,controls
from coc_bot.progression.reader import balance_amount
from coc_bot.progression.resources import HUD
from coc_bot.upgrades.vision import crop

class ConstructionCounterTests(TestCase):
 def frame(self):return cv2.imread(str(Path(__file__).parent/'fixtures/progression/workshop-legal-placement.png'))
 def runner(self,root,balance=4864686):
  frame=self.frame();row={'name':'Workshop','new':True,'cost':1200000,'currency':'elixir','point':(1594,599)}
  balances={'gold':5259842,'elixir':balance,'dark_elixir':103100}
  r=SimpleNamespace(config=SimpleNamespace(data_dir=Path(root)),stop=None,path=Path(root)/'upgrades/state.json',
    find_row=Mock(return_value=(row,frame)),reader=Mock(),eligibility=Mock(return_value=None),
    stopped=Mock(return_value=False),input=SimpleNamespace(tap=Mock()),wait=Mock(return_value=False),
    capture=SimpleNamespace(screenshot=Mock(return_value=frame)))
  r.reader.balances.return_value=balances;r.reader.availability.return_value=(3,4);r.state=lambda:read(r.path,{})
  c=Construction(r);c.locate_space=Mock(return_value=controls(frame))
  return r,c,row,{'balances':balances}
 def test_native_legal_preview_reads_complete_elixir_counter(self):
  f=self.frame()
  self.assertIsNone(balance_amount(crop(f,(.87,.103,.953,.14))))
  self.assertEqual(balance_amount(crop(f,HUD['elixir'])),4864686)
  self.assertEqual(balance_amount(crop(f,HUD['gold'])),5259842)
  self.assertEqual(controls(f)['confirm'],(964,206))
 def test_verified_full_counter_reaches_one_journalled_payment(self):
  with TemporaryDirectory() as root:
   r,c,row,before=self.runner(root);r.wait.side_effect=[False,True]
   def tap(x,y,**kwargs):
    if (x,y)==(964,206):
     saved=read(r.path)['pending'];self.assertEqual(saved['balance_before'],4864686)
     self.assertEqual((saved['cost'],saved['currency']),(1200000,'elixir'))
   r.input.tap.side_effect=tap
   result=c.start(row,before)
   self.assertEqual(result['status'],'needs_review') # simulated stop AFTER the one payment
   self.assertEqual(r.input.tap.call_count,2)
   self.assertEqual(read(r.path)['pending']['phase'],'confirming')
 def test_changed_resource_still_blocks_payment(self):
  with TemporaryDirectory() as root:
   r,c,row,before=self.runner(root,balance=4864685)
   result=c.start(row,before)
   self.assertEqual(result['status'],'changed');self.assertFalse(r.path.exists())
   self.assertNotIn((964,206),[call.args for call in r.input.tap.call_args_list])
 def test_changed_placement_still_blocks_payment(self):
  with TemporaryDirectory() as root:
   r,c,row,before=self.runner(root)
   c.locate_space.return_value=controls(self.frame())|{'confirm':(969,206)}
   result=c.start(row,before)
   self.assertEqual(result['status'],'changed');self.assertFalse(r.path.exists())
   self.assertNotIn((969,206),[call.args for call in r.input.tap.call_args_list])
