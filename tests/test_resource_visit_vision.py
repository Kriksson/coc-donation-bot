"""Current-UI native fixtures from the supervised resource/wall pilot."""
import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import cv2
import numpy as np
from coc_bot.progression.resources import HomeResources
from coc_bot.progression.bulk_walls import selection,confirmation,control
from coc_bot.accounts.clan import native_clan_tag,clan_tab

ROOT=Path(__file__).parent/'fixtures/resource_visits'


class ResourceNativeTests(unittest.TestCase):
    def test_translucent_storage_labels_read_each_native_resource_only(self):
        nav=Mock();nav._stopping=lambda:False
        reader=HomeResources(nav);reader.home=lambda _:True
        for name,resource,expected in [('gold','gold',6253000),('elixir','elixir',6262000),
                                        ('dark','dark_elixir',85000)]:
            frame=cv2.imread(str(ROOT/f'home-{name}-tooltip-1920.png'))
            with self.subTest(resource=resource):
                self.assertEqual(reader.storage_capacity(frame,resource),expected)
                for other in ('gold','elixir','dark_elixir'):
                    if other!=resource:self.assertIsNone(reader.storage_capacity(frame,other))
                x,y=reader._storage_anchors(frame,resource)[0]
                frame[y-20:y+22,x+34:]=0
                self.assertTrue(reader.storage_tooltip_visible(frame,resource))
                self.assertIsNone(reader.storage_capacity(frame,resource))

    def test_balance_only_observation_needs_two_clean_agreeing_frames(self):
        nav=Mock();nav._stopping=lambda:False
        nav.capture.screenshot.return_value=np.zeros((1080,1920,3),dtype=np.uint8)
        reader=HomeResources(nav);reader.home=lambda _:True
        reader.storage_tooltip_visible=Mock(return_value=False)
        reader.storage_capacity=Mock(side_effect=AssertionError('capacity must not be read'))
        reader.balances=Mock(side_effect=[{'gold':10,'elixir':20,'dark_elixir':30},
                                        {'gold':10,'elixir':21,'dark_elixir':30}])
        original=nav.capture
        with patch('coc_bot.progression.home.ensure_home',return_value=True):
            result=reader.observe_balances(SimpleNamespace(account_town_hall=9))
        self.assertEqual(result['balances'],{'gold':10,'dark_elixir':30})
        self.assertEqual(result['capacities'],{})
        nav.input.tap.assert_not_called()
        self.assertIs(nav.capture,original)

    def test_balance_only_observation_rejects_overlay_and_hides_early_hall_gems(self):
        nav=Mock();nav._stopping=lambda:False
        nav.capture.screenshot.return_value=np.zeros((1080,1920,3),dtype=np.uint8)
        reader=HomeResources(nav);reader.home=lambda _:True
        reader.storage_tooltip_visible=Mock(return_value=True)
        reader.balances=Mock(return_value={'gold':10,'elixir':20,'dark_elixir':999})
        with patch('coc_bot.progression.home.ensure_home',return_value=True):
            self.assertEqual(reader.observe_balances(SimpleNamespace(account_town_hall=5)),{})
            reader.balances.assert_not_called()
            reader.storage_tooltip_visible.return_value=False
            result=reader.observe_balances(SimpleNamespace(account_town_hall=5))
        self.assertEqual(result['resources'],['gold','elixir'])
        self.assertEqual(result['balances'],{'gold':10,'elixir':20})

    def test_full_gold_bar_reads_large_and_starter_balances(self):
        nav=Mock();nav._stopping=lambda:False
        reader=HomeResources(nav);reader.home=lambda _:True
        for name,expected in (('full-gold-hud.png',30500000),('home-gold-capacity.png',19480884),
                              ('starter-gold-capacity.png',2140)):
            frame=cv2.imread(str(ROOT/name))
            with self.subTest(name=name):self.assertEqual(reader.balances(frame)['gold'],expected)

    def test_gold_bar_cannot_borrow_a_value_from_its_coin_or_elixir(self):
        nav=Mock();nav._stopping=lambda:False
        reader=HomeResources(nav);reader.home=lambda _:True
        frame=cv2.imread(str(ROOT/'full-gold-hud.png'))
        frame[34:76,1565:1770]=0  # Remove only the gold numerals, retaining its coin.
        observed=reader.balances(frame)
        self.assertIsNone(observed['gold']);self.assertEqual(observed['elixir'],18839463)

    def test_main_army_housing_retains_three_digits_and_excludes_red_alert(self):
        from coc_bot.progression.preparation import capacity
        self.assertEqual(capacity(cv2.imread(str(ROOT/'main-army-330-340.png'))),(330,340))
    def test_resource_buttons_are_found_after_horizontal_reflow(self):
        import numpy as np
        from coc_bot.progression.bulk_walls import payments
        original=cv2.imread(str(ROOT/'wall-bulk-one.png'))
        frame=np.zeros_like(original)
        frame[748:914,894:1061]=original[748:914,894:1061]
        frame[748:914,694:861]=original[748:914,894:1061]
        result=payments(frame)
        self.assertEqual(sorted(v['pay'][0] for v in result),[776,976])
        self.assertTrue(all(v['currency']=='gold' and v['price']==1000 for v in result))
    def test_both_short_and_long_gold_capacities_are_exact(self):
        nav=Mock();nav._stopping=lambda:False
        reader=HomeResources(nav);reader.home=lambda _:True
        for name,expected in (('starter-gold-capacity.png',8500),('home-gold-capacity.png',30500000)):
            frame=cv2.imread(str(ROOT/name))
            self.assertEqual(reader.storage_capacity(frame,'gold'),expected)
            self.assertIsNone(reader.storage_capacity(frame,'elixir'))
        elixir=cv2.imread(str(ROOT/'starter-elixir-capacity.png'))
        self.assertEqual(reader.storage_capacity(elixir,'elixir'),8500)
        self.assertIsNone(reader.storage_capacity(elixir,'gold'))

    def test_tooltip_identity_does_not_depend_on_numeric_capacity_ocr(self):
        nav=Mock();nav._stopping=lambda:False
        reader=HomeResources(nav);reader.home=lambda _:True
        frame=cv2.imread(str(ROOT/'home-gold-capacity.png'))
        self.assertTrue(reader.storage_tooltip_visible(frame,'gold'))
        # Erase only the digits beside Max; the two independent label anchors
        # still identify the overlay while capacity becomes unreadable.
        maximum=reader.find(frame,'storage_max',(.68,.085,.99,.16),threshold=.95)
        self.assertIsNotNone(maximum)
        x,y=maximum;bad=frame.copy();bad[y-20:y+22,x+30:]=0
        self.assertTrue(reader.storage_tooltip_visible(bad,'gold'))
        self.assertIsNone(reader.storage_capacity(bad,'gold'))

    def test_builder_village_controls_do_not_establish_home_identity(self):
        nav=Mock();nav._stopping=lambda:False
        nav.classifier._open_chat_icon_visible.return_value=True
        reader=HomeResources(nav)
        frame=cv2.imread(str(ROOT/'home-gold-capacity.png'))
        with patch('coc_bot.progression.resources.home_build_control_visible',return_value=True), \
             patch.object(reader,'find',side_effect=lambda f,n,*a,**k: (1,1) if n in ('builder_gold','builder_axes') else None):
            self.assertFalse(reader.home(frame))

    def test_unreadable_numeric_capacity_closes_each_tooltip_before_clean_hud_read(self):
        class FakeNav:
            def __init__(self):
                self.open_tooltip=None;self._stopping=lambda:False
                self.classifier=Mock();self.classifier._open_chat_icon_visible.return_value=True
                self.input=Mock();self.capture=Mock();self.ensure_clan_chat=Mock()
                self.capture.screenshot.side_effect=lambda:np.full((1080,1920,3),
                    {'gold':40,'elixir':80,None:0}[self.open_tooltip],dtype=np.uint8)
            def tap(self,x,y,jitter=0):
                row='gold' if y==round(1080*.055) else 'elixir'
                self.open_tooltip=None if self.open_tooltip==row else row

        nav=FakeNav();reader=HomeResources(nav);reader.home=lambda _:True
        nav.input.tap.side_effect=nav.tap
        reader.storage_tooltip_visible=lambda f,r: int(f[0,0,0])==({'gold':40,'elixir':80}[r])
        reader.storage_capacity=Mock(return_value=None)
        def clean_balances(frame):
            if nav.open_tooltip is not None:raise AssertionError('HUD read while tooltip is open')
            return {'gold':5253000,'elixir':6253000}
        reader.balances=Mock(side_effect=clean_balances)
        with patch('coc_bot.progression.home.ensure_home',return_value=True), \
             patch('coc_bot.stop.interrupted_sleep'):
            result=reader.observe(SimpleNamespace(account_town_hall=5))
        self.assertIsNone(nav.open_tooltip)
        self.assertEqual(result['balances'],{'gold':5253000,'elixir':6253000})
        self.assertEqual(result['capacities'],{})
        self.assertEqual(nav.input.tap.call_count,4)
        self.assertEqual(reader.storage_capacity.call_count,4)

    def test_unidentified_or_uncleared_overlay_never_publishes_hud(self):
        class FakeNav:
            def __init__(self):
                self._stopping=lambda:False;self.classifier=Mock()
                self.classifier._open_chat_icon_visible.return_value=True
                self.input=Mock();self.capture=Mock();self.ensure_clan_chat=Mock()
                self.capture.screenshot.return_value=np.zeros((1080,1920,3),dtype=np.uint8)
            def tap(self,*args,**kwargs):pass
        for identify in (False,):
            nav=FakeNav();reader=HomeResources(nav);reader.home=lambda _:True
            reader.storage_tooltip_visible=lambda f,r:identify
            reader.balances=Mock(return_value={'gold':999,'elixir':999})
            with patch('coc_bot.progression.home.ensure_home',return_value=True), \
                 patch('coc_bot.stop.interrupted_sleep'):
                result=reader.observe(SimpleNamespace(account_town_hall=5))
            self.assertEqual(result['balances'],{})
            reader.balances.assert_not_called()

        nav=FakeNav();reader=HomeResources(nav);reader.home=lambda _:True
        # Keep a verified gold tooltip present even after the bounded close tap.
        reader.storage_tooltip_visible=lambda f,r:r=='gold'
        reader.storage_capacity=Mock(return_value=None)
        reader.balances=Mock(return_value={'gold':999,'elixir':999})
        with patch('coc_bot.progression.home.ensure_home',return_value=True), \
             patch('coc_bot.stop.interrupted_sleep'):
            result=reader.observe(SimpleNamespace(account_town_hall=5))
        self.assertEqual(result['balances'],{})
        reader.balances.assert_not_called()

    def test_different_tooltip_opening_after_close_blocks_hud_read(self):
        class FakeNav:
            def __init__(self):
                self.open_tooltip=None;self._stopping=lambda:False;self.classifier=Mock()
                self.classifier._open_chat_icon_visible.return_value=True
                self.input=Mock();self.capture=Mock();self.ensure_clan_chat=Mock()
                self.capture.screenshot.side_effect=lambda:np.full((1080,1920,3),
                    {'gold':40,'elixir':80,None:0}[self.open_tooltip],dtype=np.uint8)
            def tap(self,x,y,jitter=0):
                row='gold' if y==round(1080*.055) else 'elixir'
                self.open_tooltip=None if self.open_tooltip==row else row
        nav=FakeNav();nav.input.tap.side_effect=nav.tap
        reader=HomeResources(nav);reader.home=lambda _:True
        reader.storage_tooltip_visible=lambda f,r:int(f[0,0,0])==({'gold':40,'elixir':80}[r])
        reader.storage_capacity=Mock(return_value=1000)
        reader.balances=Mock(side_effect=AssertionError('balances must not read any open tooltip'))
        # Immediately after closing gold, a different (elixir) tooltip appears.
        # Gold's own absence is therefore insufficient to authorize HUD OCR.
        original_capture=nav.capture.screenshot.side_effect
        def screenshot():
            frame=original_capture()
            if nav.open_tooltip is None and nav.input.tap.call_count==4:
                nav.open_tooltip='gold'
                frame=np.full_like(frame,40)
            return frame
        nav.capture.screenshot.side_effect=screenshot
        with patch('coc_bot.progression.home.ensure_home',return_value=True), \
             patch('coc_bot.stop.interrupted_sleep'):
            result=reader.observe(SimpleNamespace(account_town_hall=5))
        self.assertEqual(result['balances'],{})
        reader.balances.assert_not_called()

    @unittest.skipUnless(shutil.which('tesseract'),'Tesseract is required')
    def test_native_bulk_counts_and_white_red_prices(self):
        for name,count,price,red in (('wall-bulk-one.png',1,1000,False),
                                     ('wall-bulk-two.png',2,2000,False),('wall-bulk-red.png',3,3000,True)):
            observed=selection(cv2.imread(str(ROOT/name)),'gold')
            self.assertIsNotNone(observed,name)
            self.assertEqual((observed['count'],observed['price'],observed['red']),(count,price,red))
            self.assertIsNone(selection(cv2.imread(str(ROOT/name)),'elixir'))

    @unittest.skipUnless(shutil.which('tesseract'),'Tesseract is required')
    def test_bulk_confirmation_never_accepts_wrong_price_or_resource(self):
        frame=cv2.imread(str(ROOT/'wall-confirm.png'))
        self.assertIsNotNone(confirmation(frame,2000,'gold'))
        for price,resource in ((1000,'gold'),(3000,'gold'),(2000,'elixir'),(2000,'gems')):
            self.assertIsNone(confirmation(frame,price,resource))
        self.assertIsNone(confirmation(cv2.imread(str(ROOT/'wall-bulk-red.png')),2000,'gold'))

    @unittest.skipUnless(shutil.which('tesseract'),'Tesseract is required')
    def test_clan_tag_requires_membership_context_not_player_settings(self):
        own=cv2.imread(str(ROOT/'own-clan.png'));settings=cv2.imread(str(ROOT/'settings.png'))
        self.assertEqual(native_clan_tag(own,lambda:False),'#8Y298U8')
        self.assertIsNone(native_clan_tag(settings,lambda:False))
        self.assertIsNotNone(clan_tab(own,lambda:False));self.assertIsNotNone(clan_tab(settings,lambda:False))

    def test_current_builder_max_and_production_lettering_are_both_required(self):
        from coc_bot.builder_base.vision import BuilderReader
        reader=BuilderReader()
        frame=cv2.imread(str(ROOT/'builder-gold-tooltip-native.png'))
        original=frame.copy()
        self.assertTrue(reader.storage_tooltip_visible(frame,'gold'))
        self.assertEqual(reader.storage_capacity(frame,'gold'),1250000)
        self.assertIsNone(reader.storage_capacity(frame,'elixir'))
        self.assertTrue(np.array_equal(original,frame))
        for box in ((1628,108,1706,147),(1425,147,1717,183)):
            broken=frame.copy();x0,y0,x1,y1=box;broken[y0:y1,x0:x1]=0
            self.assertFalse(reader.storage_tooltip_visible(broken,'gold'))
            self.assertIsNone(reader.storage_capacity(broken,'gold'))
        broken=frame.copy();broken[110:146,1708:1890]=0
        self.assertTrue(reader.storage_tooltip_visible(broken,'gold'))
        self.assertIsNone(reader.storage_capacity(broken,'gold'))

    def test_native_builder_gold_tooltip_survives_brightness_normalization(self):
        from coc_bot.builder_base.vision import BuilderReader
        from coc_bot.builder_base.frames import normalize_builder_frame
        frame=cv2.imread(str(ROOT/'builder-gold-tooltip-native.png'))
        capped=np.rint(frame.astype(np.float32)*(178/255)).astype(np.uint8)
        restored=normalize_builder_frame(capped)
        reader=BuilderReader()
        self.assertEqual(reader.storage_capacity(restored,'gold'),1250000)
        self.assertIsNone(reader.storage_capacity(restored,'elixir'))
