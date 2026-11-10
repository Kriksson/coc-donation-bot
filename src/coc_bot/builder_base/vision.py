"""Builder Base anchors and the inspected English landscape layout."""
from pathlib import Path
import re

import cv2
import numpy as np

from coc_bot.upgrades.vision import UpgradeReader, compact, crop, resource_amount

ASSETS = Path(__file__).with_name('assets')


class BuilderReader(UpgradeReader):
    def __init__(self, stop=None):
        super().__init__(stop)
        self.templates = {}

    def find(self, frame, name, box=(0, 0, 1, 1), threshold=.88, brightness=.78):
        if name not in self.templates:
            self.templates[name] = cv2.imread(str(ASSETS / (name+'.png')))
        template = self.templates[name]
        if template is None:
            return None
        h, w = frame.shape[:2]
        if not 1.6 < w/h < 1.95:
            return None
        region = crop(frame, box)
        best = None
        for factor in (.96, 1, 1.04):
            scale = w/1853*factor
            ref = cv2.resize(template, None, fx=scale, fy=scale)
            rh, rw = ref.shape[:2]
            if region.shape[0] < rh or region.shape[1] < rw:
                continue
            _, score, _, point = cv2.minMaxLoc(cv2.matchTemplate(region, ref, cv2.TM_CCOEFF_NORMED))
            observed = region[point[1]:point[1]+rh, point[0]:point[0]+rw]
            bright = observed.mean() >= ref.mean()*brightness
            if bright and score >= threshold and (best is None or score > best[0]):
                best = (score, (round(w*box[0])+point[0]+rw//2,
                                round(h*box[1])+point[1]+rh//2))
        return best[1] if best else None

    def home(self, frame):
        # Current native Builder captures have a measured 178-per-channel
        # ceiling. Keep this local tolerance limited to the two independent
        # village identity anchors; other controls retain default brightness.
        return bool(self.find(frame, 'builder_gold', (.94, 0, 1, .09), brightness=.66)
                    and self.find(frame, 'builder_axes', (0, .80, .13, .98), brightness=.66))

    def boat_target(self, frame, *, returning, box=(.14,.12,.90,.80), threshold=.86):
        """Require the matched boat's striped sail colors before it can be tapped.

        Small Home action buttons can correlate with the tiny boat template.
        The actual boat has aligned red and white sail bands, so validate those
        colors in the exact match window. Keep the existing template threshold,
        search region, and coordinates unchanged.
        """
        name='boat_return' if returning else 'boat'
        # The boat is rendered over dark water and can average well below the
        # same template's brightness; color identity below gates the candidate.
        point=self.find(frame,name,box,threshold=threshold,brightness=.65)
        if point is None:return None
        template=self.templates.get(name)
        if template is None:return None
        h,w=frame.shape[:2]
        width=max(1,round(template.shape[1]*w/1853))
        height=max(1,round(template.shape[0]*w/1853))
        x,y=point
        x0=x-width//2;y0=y-height//2
        x1=x0+width;y1=y0+height
        if x0<0 or y0<0 or x1>w or y1>h:return None
        observed=cv2.resize(frame[y0:y1,x0:x1],(template.shape[1],template.shape[0]))
        to_hsv=cv2.cvtColor(template,cv2.COLOR_BGR2HSV)
        observed_hsv=cv2.cvtColor(observed,cv2.COLOR_BGR2HSV)
        red=lambda hsv: ((cv2.inRange(hsv,(0,90,70),(12,255,255))
                          | cv2.inRange(hsv,(168,90,70),(180,255,255)))>0)
        white=lambda hsv: (cv2.inRange(hsv,(0,0,150),(180,70,255))>0)
        expected_red=red(to_hsv);expected_white=white(to_hsv)
        observed_red=red(observed_hsv);observed_white=white(observed_hsv)
        if (expected_red.sum()<8 or expected_white.sum()<8
                or observed_red[expected_red].mean()<.50
                or observed_white[expected_white].mean()<.50):
            return None
        return point

    def daily_reward_close(self, frame):
        """Only close the inspected daily calendar; never select its rewards."""
        footer=self.find(frame,'daily_reward_footer',(.30,.88,.70,.94),threshold=.97)
        if not footer:
            # The gold panel's background changes with the village behind it.
            # Match its complete native lettering, retaining the independent
            # bright title and Close checks below. Never lower all templates.
            ref=self.templates.get('daily_reward_footer')
            if ref is not None:
                mask=lambda a:cv2.inRange(cv2.cvtColor(a,cv2.COLOR_BGR2HSV),(0,0,200),(180,80,255))
                region=mask(cv2.resize(frame,(1853,1048))[922:985,555:1297])
                footer=cv2.minMaxLoc(cv2.matchTemplate(region,mask(ref),cv2.TM_CCOEFF_NORMED))[1]>=.97
        if (self.find(frame,'daily_reward_title',(.38,.12,.60,.19),threshold=.97) and footer):
            return (self.find(frame,'daily_reward_close_ready',(.82,.10,.87,.18),threshold=.97)
                    or self.find(frame,'daily_reward_close',(.82,.10,.87,.18),threshold=.97))
        return None

    def daily_reward_claim(self, frame):
        """The free calendar's whole green Claim button, excluding gray Claimed."""
        if self.daily_reward_close(frame) is None:return None
        return self.find(frame,'daily_reward_claim',(.13,.37,.86,.87),threshold=.97)

    def free_boat_confirmation(self, frame):
        if (self.find(frame,'setup_boat_title',(.37,.06,.64,.16),threshold=.94)
            and self.find(frame,'setup_boat_description',(.33,.59,.67,.68),threshold=.94)
            and self.find(frame,'setup_boat_free',(.93,.105,.99,.89),threshold=.94)):
            label=self.find(frame,'setup_boat_rebuild',(.40,.76,.61,.88),threshold=.94)
            if label:
                green=cv2.inRange(cv2.cvtColor(crop(frame,(.416,.754,.584,.875)),cv2.COLOR_BGR2HSV),
                                  (30,90,140),(90,255,255)).mean()/255
                if green>.55:return label
        return None

    def setup_boat_target(self,frame):
        """Locate the tutorial boat to inspect its actions, not to infer readiness."""
        from coc_bot.vision.battle_menu import home_build_control_visible
        if not home_build_control_visible(frame) or self.home(frame):return None
        point=self.find(frame,'setup_ready_boat',(.14,.12,.90,.80),threshold=.96)
        if point is None:return None
        h,w=frame.shape[:2];x,y=point
        box=(max(0,x/w-.055),max(0,y/h-.18),min(1,x/w+.055),max(0,y/h-.035))
        arrow=self.find(frame,'setup_ready_arrow',box,threshold=.96)
        if arrow is None:
            # The tutorial arrow stretches while bobbing. Its silhouette stays
            # the same; require that shape directly above the verified boat.
            reference=self.templates.get('setup_ready_arrow')
            def orange(image):return cv2.inRange(cv2.cvtColor(image,cv2.COLOR_BGR2HSV),(10,145,180),(36,255,255))
            def silhouette(contour,mask):
                a,b,bw,bh=cv2.boundingRect(contour);filled=np.zeros_like(mask)
                cv2.drawContours(filled,[contour],-1,255,-1)
                return cv2.resize(filled[b:b+bh,a:a+bw],(96,96),interpolation=cv2.INTER_NEAREST)>0
            if reference is not None:
                target=orange(reference);contours,_=cv2.findContours(target,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
                expected=silhouette(max(contours,key=cv2.contourArea),target) if contours else None
                region=orange(crop(frame,box));contours,_=cv2.findContours(region,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
                scale=w/1853
                for contour in contours:
                    a,b,bw,bh=cv2.boundingRect(contour)
                    if expected is None or not 60*scale<bw<150*scale or not 50*scale<bh<140*scale or cv2.contourArea(contour)<1800*scale*scale:continue
                    observed=silhouette(contour,region)
                    if (observed&expected).sum()/(observed|expected).sum()>=.94:
                        arrow=(round(w*box[0])+a+bw//2,round(h*box[1])+b+bh//2);break
        return point if arrow and abs(arrow[0]-x)<w*.025 and h*.045<y-arrow[1]<h*.18 else None

    def selected_boat_rebuild(self,frame):
        from coc_bot.vision.battle_menu import home_build_control_visible
        if not home_build_control_visible(frame):return None
        if (self.find(frame,'setup_selected_boat',(.43,.63,.56,.70),threshold=.96)
            and self.find(frame,'setup_selected_boat_free',(.45,.69,.55,.75),threshold=.96)):
            return self.find(frame,'setup_selected_boat_rebuild',(.44,.80,.55,.86),threshold=.96)
        return None

    def battle(self, frame):
        return bool(self.find(frame, 'defender', (.045, .012, .145, .06))
                    and self.find(frame, 'attacker', (.875, .012, .97, .06))
                    and (self.find(frame, 'battle_starts', (.43, .012, .57, .055))
                         or self.find(frame, 'battle_ends', (.43, .012, .57, .055))))

    def attack_menu(self, frame):
        # The inspected 1920x1080 Builder menu scales its title differently
        # from older captures; keep the low title threshold gated by the bright
        # Find Now button at a high threshold in its fixed, separate region.
        return bool(self.find(frame, 'start_attack', (.38, .14, .66, .24), threshold=.82, brightness=.65)
                    and self.find(frame, 'find_now', (.65, .60, .84, .72), threshold=.93, brightness=.65))

    def supported_army(self, frame):
        return self.supported_army_kind(frame) is not None

    def supported_army_kind(self, frame):
        """Accept only the inspected Night Witch or four single Baby Dragon camps."""
        if (not self.attack_menu(frame)
            or not self.find(frame, 'menu_machine', (.17,.39,.224,.48),brightness=.65)):
            return None
        if all(self.find(frame, 'menu_witch', (x,.39,x+.055,.48))
               for x in (.227,.286,.345,.404,.463,.522)):
            return 'night_witch'
        boxes=((.227,.39,.284,.49),(.283,.39,.340,.49),
               (.339,.39,.396,.49),(.395,.39,.461,.49))
        singles=((.227,.38,.248,.42),(.283,.38,.304,.42),
                 (.339,.38,.360,.42),(.395,.38,.416,.42))
        if (all(self.find(frame,'menu_baby_dragon',box,threshold=.96) for box in boxes)
            and all(self.find(frame,'menu_baby_dragon_one',box,threshold=.94) for box in singles)
            and not self.find(frame,'menu_baby_dragon',(.451,.39,.508,.49),threshold=.96)):
            return 'baby_dragon'
        return None

    def battle_army_ready(self, army):
        """Require verified troop art; abilities remain independently gated by live readiness."""
        if army=='night_witch':
            return True
        if army!='baby_dragon':
            return False
        return (ASSETS/'baby_dragon.png').is_file()

    def reward_button(self, frame):
        from coc_bot.vision.notices import home_star_bonus_button
        return home_star_bonus_button(frame)

    def menu_kind(self, frame):
        # The square Builder Gold icon distinguishes this from the identical
        # Home Village heading. Never infer village identity from that heading.
        if not self.find(frame, 'builder_gold', (.68, .02, .72, .08)):
            return None
        return super().menu_kind(frame)

    def research_sorting(self,frame):
        """The inspected Star Laboratory popup sorts rows; it has no filters."""
        return bool(self.find(frame,'research_sorting_title',(.47,.125,.61,.185),threshold=.98)
                    and self.find(frame,'research_sort_cost_max',(.49,.20,.60,.275),threshold=.98)
                    and self.find(frame,'research_sort_cost_min',(.64,.20,.75,.275),threshold=.98))

    def availability(self, frame, kind):
        from coc_bot.upgrades.digits import read_digits
        if self.menu_kind(frame) != kind:
            return None
        box = {'buildings': (.775, .945, .81, .977),
               'research': (.915, .944, .954, .975)}.get(kind)
        if box is None:
            return None
        from coc_bot.upgrades.vision import text
        from coc_bot.progression.reader import counter_digit_variants
        raw = (read_digits(crop(frame, box), fraction=True)
               or read_digits(crop(frame, box), fraction=True,extra_templates=counter_digit_variants())
               or text(crop(frame, box), fraction=True, stop=self.stop))
        match = re.fullmatch(r'([0-3])/([123])' if kind == 'buildings' else r'([01])/(1)', raw)
        if not match:
            return None
        free, total = map(int, match.groups())
        return (free, total) if free <= total else None

    def balances(self, frame):
        return {key: resource_amount(crop(frame, box), self.stop) for key, box in {
            'gold': (.56, .033, .679, .073),
            'elixir': (.56, .104, .679, .143),
        }.items()}

    def storage_tooltip_anchors(self, frame, resource):
        Y = {'gold':.055,'elixir':.12,'dark_elixir':.19}
        if resource not in Y:return None
        top = Y[resource]+.03
        # Max labels for adjacent resources are only ~70px apart. A broad
        # search can mistake an already-open elixir tooltip for gold.
        box = (.68, top, .99, top+.075)
        for max_name,production_name in (('storage_max','storage_production'),
                                         ('home_storage_max','home_storage_production')):
            maximum=self.find(frame,max_name,box,threshold=.95)
            production=self.find(frame,production_name,(.68,top+.02,.99,top+.13),threshold=.94)
            if maximum is not None and production is not None:return maximum,production
        maximum=self._storage_lettering(frame,'builder_storage_max_native',box)
        production=self._storage_lettering(frame,'builder_storage_production_native',(.68,top+.02,.99,top+.13))
        if maximum is not None and production is not None:return maximum,production
        # The tooltip is translucent: village details behind the lettering
        # change every time the map moves. Match the white lettering only,
        # retaining two separate labels and a narrow resource-specific row.
        maximum=self._storage_lettering(frame,'home_storage_max',box)
        production=self._storage_lettering(frame,'home_storage_production',(.68,top+.02,.99,top+.13))
        return (maximum,production) if maximum is not None and production is not None else None

    def _storage_lettering(self, frame, name, box):
        template=self.templates.get(name)
        if template is None:
            template=cv2.imread(str(ASSETS/(name+'.png')))
            self.templates[name]=template
        if template is None:return None
        h,w=frame.shape[:2]
        if not 1.6<w/h<1.95:return None
        if name.endswith('_native'):
            # Match lettering at the inspected native resolution. Scaling a
            # binary glyph twice loses its thin strokes near the white cutoff.
            image=cv2.resize(frame,(1920,1080))
            clean=lambda a:cv2.inRange(cv2.cvtColor(a,cv2.COLOR_BGR2HSV),(0,0,200),(180,70,255))
            region=clean(crop(image,box));ref=clean(template)
            if any(a<b for a,b in zip(region.shape,ref.shape)):return None
            _,score,_,point=cv2.minMaxLoc(cv2.matchTemplate(region,ref,cv2.TM_CCOEFF_NORMED))
            if score<.96:return None
            return (round((round(1920*box[0])+point[0]+ref.shape[1]/2)*w/1920),
                    round((round(1080*box[1])+point[1]+ref.shape[0]/2)*h/1080))
        mask=lambda a:cv2.inRange(cv2.cvtColor(a,cv2.COLOR_BGR2HSV),(0,0,200),(180,70,255))
        region=mask(crop(frame,box));best=None
        for factor in (.96,1,1.04):
            scale=w/1853*factor
            ref=mask(cv2.resize(template,None,fx=scale,fy=scale))
            rh,rw=ref.shape
            if region.shape[0]<rh or region.shape[1]<rw:continue
            _,score,_,point=cv2.minMaxLoc(cv2.matchTemplate(region,ref,cv2.TM_CCOEFF_NORMED))
            if score >= (.96 if name.endswith('_native') else .90 if name.endswith('_max') else .85) and (best is None or score>best[0]):
                best=(score,(round(w*box[0])+point[0]+rw//2,round(h*box[1])+point[1]+rh//2))
        return best[1] if best else None

    def storage_capacity(self, frame, resource):
        """Read the game's Max tooltip, with its resource-specific vertical position."""
        if resource not in ('gold','elixir') or not self.home(frame):return None
        anchors=self.storage_tooltip_anchors(frame,resource)
        if anchors is None:return None
        scale=frame.shape[1]/1853;x,y=anchors[0]
        area=frame[round(y-19*scale):round(y+20*scale),round(x+32*scale):round(frame.shape[1]*.978)]
        from coc_bot.progression.reader import balance_amount
        value=balance_amount(area,self.stop)
        return value if type(value) is int and 0<value<=20_000_000 else None

    def storage_tooltip_visible(self, frame, resource):
        return self.home(frame) and self.storage_tooltip_anchors(frame,resource) is not None

    def storage_capacities(self, runner):
        from loguru import logger
        result={};rows={'gold':.055,'elixir':.12}
        def close_known(frame):
            for other,oy in rows.items():
                if self.storage_tooltip_visible(frame,other):
                    runner.tap((round(frame.shape[1]*.87),round(frame.shape[0]*oy)))
                    runner.wait(.25)
                    return runner.frame()
            return frame
        try:
            for resource,y in rows.items():
                logger.info('Проверяю хранилище {} в деревне строителя', 'золота' if resource=='gold' else 'эликсира')
                frame=runner.frame()
                if not self.home(frame):return result
                if not self.storage_tooltip_visible(frame,resource):
                    frame=close_known(frame)
                    runner.tap((round(frame.shape[1]*.87),round(frame.shape[0]*y)))
                    runner.wait(.25)
                frame=runner.frame()
                if not self.storage_tooltip_visible(frame,resource):return result
                first=self.storage_capacity(frame,resource)
                second=self.storage_capacity(runner.frame(),resource)
                if first is not None and first==second:
                    result[resource]=first
                    logger.info('Вместимость хранилища {} подтверждена: {}', 'золота' if resource=='gold' else 'эликсира',f'{first:,}'.replace(',',' '))
                frame=close_known(runner.frame())
                if self.storage_tooltip_visible(frame,resource):return result
            return result
        finally:
            if not (runner.stop and runner.stop()):close_known(runner.frame())

    def detail_close(self, frame, candidate=None):
        # Match UpgradeReader's shared transaction interface. Builder dialogs
        # have their own independently verified title and close landmarks.
        # The running research modal has a wider title and its X sits farther
        # left than the confirmation panel. Require both native landmarks.
        if self.find(frame, 'research_units_native_title', (.38, .03, .64, .11), threshold=.97):
            point = self.find(frame, 'research_units_native_close', (.79, .02, .87, .12), threshold=.97)
            if point:
                return point
        title = compact(self.label(frame, (.30, .035, .72, .09)))
        # The native outlined 5 can read as S. This correction locates only
        # the non-spending close control; independent payment checks remain.
        if title in ('upgradetolevels','upgrradetolevels') and (
            self.find(frame,'upgrade_benefits',(.48,.12,.81,.18),threshold=.97)
            or self.find(frame,'upgrade_level_five_heading',(.30,.025,.65,.11),threshold=.97)):
            title = 'upgradetolevel'
        if title not in ('upgradetolevel','upgradeunits'):
            return None
        hsv = cv2.cvtColor(crop(frame, (.816, .025, .866, .11)), cv2.COLOR_BGR2HSV)
        red = cv2.bitwise_or(cv2.inRange(hsv, (0, 110, 120), (10, 255, 255)),
                            cv2.inRange(hsv, (170, 110, 120), (180, 255, 255)))
        if red.mean()/255 < .25:
            return None
        return round(frame.shape[1]*.839), round(frame.shape[0]*.064)

    def confirmation(self, frame, candidate):
        if self.detail_close(frame) is None:
            return None
        if compact(candidate.name) in ('nightwitch','sneakyarcher','ragedbarbarian'):
            return self.research_confirmation(frame,candidate)
        observed_name=compact(self.white_text(crop(frame, (.17, .14, .41, .19))))
        # The outlined native Star Laboratory heading is consistently read as
        # "Star LaboRa LORY" on its level-up dialog. Correct only that complete
        # observed title; price, resource, green control, and close remain
        # independently verified below and in detail_close.
        if observed_name in ('starlaboralory','starlabooraory'):
            observed_name='starlaboratory'
        named=observed_name==compact(candidate.name)
        if not named and compact(candidate.name)=='starlaboratory':
            named=self.find(frame,'upgrade_star_laboratory_title',(.17,.14,.41,.19),threshold=.97) is not None
        if not named and compact(candidate.name)=='builderbarracks':
            named=self.find(frame,'upgrade_builder_barracks_title',(.17,.14,.41,.19),threshold=.97) is not None
        if not named and compact(candidate.name)=='elixircollector':
            named=self.find(frame,'upgrade_elixir_collector_title',(.17,.14,.41,.19),threshold=.97) is not None
        if not named:
            return None
        # Builder building dialog has a single resource button, no Confirm text.
        price = resource_amount(crop(frame, (.415, .842, .543, .925)), self.stop)
        from coc_bot.upgrades.vision import currency
        if price != candidate.cost or candidate.currency not in ('gold','elixir'):
            return None
        if currency(crop(frame,(.546,.83,.597,.92))) != candidate.currency:
            return None
        green = cv2.inRange(cv2.cvtColor(crop(frame, (.418, .83, .59, .93)), cv2.COLOR_BGR2HSV),
                            (30, 70, 140), (90, 255, 255))
        if green.mean()/255 < .3:
            return None
        return {'point': (round(frame.shape[1]*.504), round(frame.shape[0]*.875)),
                'name': candidate.name, 'cost': price, 'currency': candidate.currency}

    def active_names(self, frame, kind=None):
        names=super().active_names(frame,kind)
        if self.menu_kind(frame)=='research':
            # Native Sneaky Archer timer lettering can lose this one e in OCR.
            # Correct this complete known name only, never an arbitrary unit.
            return ['sneakyarcher' if n=='snakyarcher' else n for n in names]
        return names

    def research_confirmation(self, frame, candidate):
        if compact(candidate.name)=='sneakyarcher':
            heading=self.white_text(crop(frame,(.35,.04,.65,.095)))
            level=re.fullmatch(r'(?i)\s*upgrade\s+to\s+level\s+(\d{1,2})\s*\??\s*',heading)
            if (candidate.currency!='elixir' or level is None or not 2<=int(level[1])<=30
                or not self.find(frame,'research_sneaky_archer',(.24,.25,.42,.63),threshold=.96)):
                return None
            target=int(level[1])
            if target==2:
                if compact(self.label(frame,(.585,.256,.80,.292)))!='unlocksspecialabilitycloak':return None
            elif compact(self.white_text(crop(frame,(.215,.73,.34,.78))))!='cloak':return None
            # Higher levels have longer prices extending left of the old crop.
            # The portrait AND native ability identify this otherwise unnamed unit.
            price=resource_amount(crop(frame,(.68,.845,.787,.89)),self.stop)
            from coc_bot.upgrades.vision import currency
            if price!=candidate.cost or currency(crop(frame,(.788,.825,.824,.90)))!='elixir':return None
            green=cv2.inRange(cv2.cvtColor(crop(frame,(.675,.81,.832,.925)),cv2.COLOR_BGR2HSV),
                             (30,70,140),(90,255,255)).mean()/255
            if green<.3:return None
            return {'point':(round(frame.shape[1]*.751),round(frame.shape[0]*.87)),
                    'name':candidate.name,'cost':price,'currency':'elixir','target_level':target}
        # This dialog does not print the troop's name. Require its distinctive
        # portrait AND ability title; a background menu row cannot prove identity.
        if (candidate.currency != 'elixir' or compact(candidate.name) != 'nightwitch'
                or not self.find(frame,'research_night_witch',(.20,.26,.33,.46))
                or not self.find(frame,'research_bat_swarm',(.20,.73,.34,.78))):
            return None
        price=resource_amount(crop(frame,(.68,.845,.787,.89)),self.stop)
        if price != candidate.cost or not self.find(frame,'research_elixir',(.788,.825,.824,.90)):
            return None
        green=cv2.inRange(cv2.cvtColor(crop(frame,(.675,.81,.832,.925)),cv2.COLOR_BGR2HSV),
                          (30,70,140),(90,255,255)).mean()/255
        if green < .3:
            return None
        return {'point':(round(frame.shape[1]*.751),round(frame.shape[0]*.87)),
                'name':candidate.name,'cost':price,'currency':candidate.currency}

    def running_detail(self, frame, candidate):
        # Closing a recognized research detail is safe even if its transition
        # has not finished. Only the menu timer and occupied lab confirm success.
        if compact(candidate.name) in ('sneakyarcher','ragedbarbarian'):
            # This only authorizes closing the verified X, never another
            # payment. The active research timer/lab occupancy proves success.
            return self.detail_close(frame) is not None
        if compact(candidate.name)=='nightwitch':
            heading=compact(self.label(frame,(.30,.035,.72,.09)))
            unit=compact(self.label(frame,(.335,.18,.60,.23)))
            # This observed timer font can read "levels" as "cevels". Correct
            # only that exact native OCR error after the troop's full name.
            unit=unit.replace('nightwitchcevels','nightwitchlevels')
            return bool(self.detail_close(frame) and heading=='upgradeunits'
                        and unit.startswith(compact(candidate.name)+'level'))
        return super().running_detail(frame,candidate)

    def white_text(self, image):
        from coc_bot.upgrades.vision import text
        white = cv2.inRange(cv2.cvtColor(image, cv2.COLOR_BGR2HSV), (0, 0, 190), (180, 75, 255))
        return text(255-white, stop=self.stop)

    def candidates(self, frame):
        from coc_bot.upgrades.vision import Candidate
        from coc_bot.progression.reader import ProgressionReader
        if self.menu_kind(frame) not in ('buildings','research'):
            return [], False
        # Early villages often put the lab/storage under Other upgrades and
        # have no Suggested research section at all. Read existing white-name
        # rows in either section; green New entries require a placement flow.
        parser=ProgressionReader(self.stop)
        parser.row_min_value=110;parser.row_close_pixels=3;parser.row_background_fraction=.40
        # Reuse the shared native row geometry, but retain Builder resource
        # identity: the otherwise identical Home menu must never qualify.
        parser.menu_kind=self.menu_kind
        h,w=frame.shape[:2];result=[]
        for row in parser.rows(frame):
            x,y,bw,bh=row['box']
            title=frame[y+3:min(y+bh,y+round(h*.035)),round(w*.775):round(w*.925)]
            green=cv2.inRange(cv2.cvtColor(title,cv2.COLOR_BGR2HSV),(35,80,170),(90,255,255))
            if row['new'] or np.count_nonzero(green)>max(12,title.size//400):continue
            if row['name'] and type(row['cost']) is int and row['cost']>0 and row['currency'] in ('gold','elixir'):
                result.append(Candidate(row['name'],row['cost'],row['currency'],row['point']))
        # Prioritize the lab, then army unlocks and storage. This ordering never
        # makes a locked/new row eligible or claims the entire hall is maxed.
        order={'starlaboratory':0,'builderbarracks':1,'goldstorage':2,'elixirstorage':2}
        if self.menu_kind(frame)=='buildings':
            result.sort(key=lambda c:order.get(compact(c.name),3))
        return result, False

    def cards(self, frame, army='night_witch'):
        """Read cards for the army already verified in the attack menu.

        Baby Dragon cards are recognized from their own live artwork. A menu
        receipt cannot identify a battle card after stage transitions.
        """
        if army not in ('night_witch','baby_dragon') or not self.battle(frame):
            return []
        if army=='baby_dragon' and not (ASSETS/'baby_dragon.png').is_file():
            return []
        h, w = frame.shape[:2]
        result = []
        for index, cx in enumerate((.10, .189, .268, .347, .426, .505, .584, .663, .742, .821)):
            box = (cx-.036, .80, cx+.036, .99)
            unit = ('battle_machine' if index == 0 else
                    'baby_dragon' if army=='baby_dragon' else 'night_witch')
            if index == 0 and self.find(frame, 'battle_copter', box, threshold=.86):
                unit = 'battle_copter'
            variants = [unit] + (['night_witch_active', 'night_witch_survivor'] if unit == 'night_witch'
                                else ['battle_machine_active'] if unit == 'battle_machine' else [])
            found = any(self.find(frame, name, box, threshold=.86) for name in variants)
            # Deployed Baby Dragon cards rise and show a bright green health
            # strip. Their face art changes slightly in that state, lowering
            # the inspected head-only template score from ~.99 to ~.78. Keep
            # the relaxed face threshold behind both independent live UI cues;
            # it cannot relabel an empty, spent-gray, or different troop slot.
            deployed_card = False
            if unit == 'baby_dragon':
                band = cv2.cvtColor(crop(frame, (cx-.01, .796, cx+.025, .822)), cv2.COLOR_BGR2HSV)
                health = cv2.cvtColor(crop(frame, (cx-.025, .831, cx+.025, .858)), cv2.COLOR_BGR2HSV)
                blue_band = cv2.inRange(band, (90, 100, 180), (170, 255, 255)).mean()/255
                green_health = cv2.inRange(health, (10, 120, 160), (85, 255, 255)).mean()/255
                deployed_card = blue_band > .90 and green_health > .55
                if not found and deployed_card:
                    found = self.find(frame, unit, box, threshold=.75) is not None
            if not found:
                continue
            # Raised cards (number band at y=.79) are deployed. Health can be
            # green, yellow or red; second-stage survivors have health while
            # still waiting to deploy, so color alone is insufficient.
            band = crop(frame, (cx-.01, .796, cx+.025, .822))
            hsv = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
            deployed = deployed_card or cv2.inRange(hsv, (90, 100, 180), (170, 255, 255)).mean()/255 > .6
            health = cv2.cvtColor(crop(frame, (cx-.025, .831, cx+.025, .858)), cv2.COLOR_BGR2HSV)
            deployed |= cv2.inRange(health, (10, 120, 160), (85, 255, 255)).mean()/255 > .12
            if index == 0:
                health = cv2.cvtColor(crop(frame, (cx-.025, .792, cx+.025, .811)), cv2.COLOR_BGR2HSV)
                deployed = cv2.inRange(health, (10, 120, 160), (85, 255, 255)).mean()/255 > .12
            art = cv2.cvtColor(crop(frame, (cx-.02, .90, cx+.02, .96)), cv2.COLOR_BGR2HSV)
            if (art[:, :, 1] > 60).mean() < .15:
                continue
            result.append({'slot': index, 'unit': unit, 'point': (round(w*cx), round(h*.90)),
                           'deployed': bool(deployed),
                           'ability_ready': bool(unit=='baby_dragon' and
                               self.find(frame,'baby_dragon_ability_ready',box,threshold=.96))})
        return result

    def result_button(self, frame):
        # Added from the inspected results layout; both text anchors required.
        if self.battle(frame):
            return None
        point = self.find(frame, 'return_home', (.25, .65, .75, 1))
        return point if point and self.find(frame, 'result_heading', (.20, .05, .80, .60)) else None
