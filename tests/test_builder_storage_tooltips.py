from pathlib import Path
from types import SimpleNamespace
import cv2
import unittest
from coc_bot.builder_base.vision import BuilderReader
from coc_bot.runtime.resource_farming import decide

ROOT=Path(__file__).parent/'fixtures/resource_visits'

class BuilderStorageTooltipTests(unittest.TestCase):
    def test_real_tooltips_read_exact_resource_and_do_not_borrow_neighbor(self):
        reader=BuilderReader()
        for name,expected in [('gold',1250000),('elixir',1500000)]:
            with self.subTest(resource=name):
                frame=cv2.imread(str(ROOT/f'builder-{name}-tooltip-1920.png'))
                self.assertTrue(reader.home(frame))
                self.assertEqual(reader.storage_capacity(frame,name),expected)
                other='elixir' if name=='gold' else 'gold'
                self.assertIsNone(reader.storage_capacity(frame,other))
                x,y=reader.storage_tooltip_anchors(frame,name)[0]
                frame[y-20:y+22,x+34:]=0
                self.assertTrue(reader.storage_tooltip_visible(frame,name))
                self.assertIsNone(reader.storage_capacity(frame,name))

    def test_two_verified_tooltips_are_closed_and_low_resources_allow_attack(self):
        frames={r:cv2.imread(str(ROOT/f'builder-{r}-tooltip-1920.png')) for r in ('gold','elixir')}
        clean=frames['gold'].copy();clean[85:300,1390:1905]=0
        reader=BuilderReader();reader.home=lambda _:True
        state={'open':None};taps=[]
        def tap(point):
            resource='gold' if point[1]==round(1080*.055) else 'elixir'
            state['open']=None if state['open']==resource else resource;taps.append(resource)
        runner=SimpleNamespace(frame=lambda:frames.get(state['open'],clean),tap=tap,wait=lambda _:None,stop=lambda:False)
        capacities=reader.storage_capacities(runner)
        self.assertEqual(capacities,{'gold':1250000,'elixir':1500000})
        self.assertIsNone(state['open'])
        self.assertEqual(taps,['gold','gold','elixir','elixir'])
        decision=decide({'resources':['gold','elixir'],'balances':{'gold':755325,'elixir':329926},
                         'capacities':capacities},{},start=75,stop=95)
        self.assertTrue(decision.attack)
        self.assertEqual(decision.status,'refilling')
