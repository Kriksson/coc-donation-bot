"""Home storage readings from native counters and Max/Production tooltips.

    No Town Hall capacity table, full-looking bars, purchase icons, or gems.
"""
from loguru import logger
from coc_bot.builder_base.vision import BuilderReader
from coc_bot.progression.reader import balance_amount
from coc_bot.upgrades.vision import crop, currency
from coc_bot.vision.battle_menu import home_build_control_visible
from coc_bot.vision.home_frames import home_capture


# Search the whole gold-bar interior: wide balances extend left of the old
# text-only crop. Keep the coin icon and adjacent resource rows outside it.
HUD = {'gold': (.775, .028, .958, .083), 'elixir': (.855, .102, .958, .140),
       'dark_elixir': (.865, .171, .958, .209)}
Y = {'gold': .055, 'elixir': .12, 'dark_elixir': .19}


class HomeResources(BuilderReader):
    def __init__(self, navigator):
        self.nav = navigator
        self.capture = home_capture(navigator.capture,navigator)
        super().__init__(navigator._stopping)

    def home(self, frame):
        # Build + chat controls also exist in Builder Village. The paired
        # Builder Base HUD anchors positively identify that village.
        return bool(home_build_control_visible(frame)
                    and self.nav.classifier._open_chat_icon_visible(frame)
                    and not super().home(frame))

    def balances(self, frame):
        if not self.home(frame):return {}
        return {resource: balance_amount(crop(frame, box), self.stop) for resource, box in HUD.items()}

    def observe_balances(self, config):
        """Read display-only balances twice without opening storage tooltips."""
        from coc_bot.progression.home import ensure_home
        original=self.nav.capture
        self.nav.capture=self.capture
        try:
            if not ensure_home(self.nav):return {}
            samples=[]
            for _ in range(2):
                if self.stop():raise InterruptedError('Resource check stopped')
                frame=self.capture.screenshot()
                if not self.home(frame):return {}
                if any(self.storage_tooltip_visible(frame,r) for r in Y):return {}
                samples.append(self.balances(frame))
            balances={r:value for r,value in samples[1].items()
                      if type(value) is int and samples[0].get(r)==value}
            hall=getattr(config,'account_town_hall',None)
            resources=['gold','elixir']
            if type(hall) is int and hall>=7:resources.append('dark_elixir')
            else:balances.pop('dark_elixir',None)
            return {'resources':resources,'balances':balances,'capacities':{}}
        finally:
            if self.nav.capture is self.capture:self.nav.capture=original

    def _storage_anchors(self, frame, resource):
        return self.storage_tooltip_anchors(frame,resource)

    def storage_capacity(self, frame, resource):
        if resource not in Y or not self.home(frame):return None
        anchors=self._storage_anchors(frame,resource)
        if anchors is None:return None
        maximum,_=anchors
        scale = frame.shape[1]/1853
        x, y = maximum
        region = frame[round(y-19*scale):round(y+20*scale), round(x+32*scale):round(frame.shape[1]*.978)]
        value = balance_amount(region, self.stop)
        return value if type(value) is int and 0 < value <= 100_000_000 else None

    def storage_tooltip_visible(self, frame, resource):
        """Identify the target Max tooltip without requiring its digits to OCR."""
        if resource not in Y or not self.home(frame):return False
        return self._storage_anchors(frame,resource) is not None

    def observe(self, config):
        # ensure_home/ensure_clan_chat and their checks capture directly from
        # Navigator. Scope the Home proxy to this observation so every such
        # check sees the same corrected pixels, then restore the shared source.
        original=self.nav.capture
        proxy=home_capture(original,self.nav)
        self.nav.capture=proxy
        try:
            return self._observe_captured(config)
        finally:
            if self.nav.capture is proxy:self.nav.capture=original

    def _observe_captured(self, config):
        from coc_bot.progression.home import ensure_home
        from coc_bot.stop import interrupted_sleep
        if not ensure_home(self.nav):return {}
        def frame():
            if self.stop():raise InterruptedError('Resource check stopped')
            result = self.capture.screenshot()
            if not self.home(result):raise ValueError('Home controls lost during resource check')
            return result
        current = frame()
        resources = ['gold', 'elixir']
        # A saved verified early Hall and absence of the DE icon establish that
        # the third counter is gems. Later Halls require the actual dark icon.
        hall = getattr(config, 'account_town_hall', None)
        # At verified early Halls this slot contains gems. Dark shadows on the
        # green gem can satisfy a loose purple-color test; never tap that slot.
        early_hall=type(hall) is int and hall<7
        dark = not early_hall and currency(crop(current, (.963, .158, .998, .225))) == 'dark_elixir'
        if dark:resources.append('dark_elixir')
        elif type(hall) is not int or hall >= 7:return {}
        capacities = {}
        unreadable_open_tooltip=False
        try:
            for resource in resources:
                logger.info('Проверяю хранилище {} в основной деревне', {'gold':'золота','elixir':'эликсира','dark_elixir':'тёмного эликсира'}[resource])
                current = frame()
                # If some recognized tooltip is already open, close only that
                # verified target before opening the requested row.
                open_resource=next((r for r in resources if self.storage_tooltip_visible(current,r)),None)
                if open_resource is not None and open_resource != resource:
                    self.nav.input.tap(round(current.shape[1]*.87),round(current.shape[0]*Y[open_resource]),jitter=0)
                    interrupted_sleep(.2,self.stop)
                    current=frame()
                if not self.storage_tooltip_visible(current,resource):
                    self.nav.input.tap(round(current.shape[1]*.87), round(current.shape[0]*Y[resource]), jitter=0)
                    interrupted_sleep(.3, self.stop)
                current=frame()
                tooltip_open=self.storage_tooltip_visible(current,resource)
                if not tooltip_open:
                    # Identity was not established after the tap. Do not tap
                    # again at an unknown location or trust possibly covered HUD.
                    unreadable_open_tooltip=True
                    return {'resources':resources,'balances':{},'capacities':capacities}
                first = self.storage_capacity(current, resource) if tooltip_open else None
                second_frame=frame()
                tooltip_still_open=self.storage_tooltip_visible(second_frame,resource)
                second = self.storage_capacity(second_frame, resource) if tooltip_still_open else None
                if first is not None and first == second:capacities[resource] = first
                # Close based on the independent visual identity, even when
                # numeric OCR failed. Confirm that the overlay went away.
                current=frame()
                if self.storage_tooltip_visible(current,resource):
                    self.nav.input.tap(round(current.shape[1]*.87),round(current.shape[0]*Y[resource]),jitter=0)
                    interrupted_sleep(.2,self.stop)
                    if self.storage_tooltip_visible(frame(),resource):
                        return {'resources':resources,'balances':{},'capacities':capacities}
                elif tooltip_open:
                    return {'resources':resources,'balances':{},'capacities':capacities}
            first_frame=frame()
            if any(self.storage_tooltip_visible(first_frame,r) for r in resources):
                return {'resources':resources,'balances':{},'capacities':capacities}
            first=self.balances(first_frame)
            second_frame=frame()
            if any(self.storage_tooltip_visible(second_frame,r) for r in resources):
                return {'resources':resources,'balances':{},'capacities':capacities}
            second=self.balances(second_frame)
            balances = {r: second.get(r) for r in resources if first.get(r) == second.get(r)}
            return {'resources': resources, 'balances': balances, 'capacities': capacities}
        finally:
            # Best-effort bounded cleanup of a tooltip whose identity was
            # proven. Never use OCR readability as the close condition.
            if unreadable_open_tooltip and not self.stop():
                for resource in resources:
                    try:
                        current=self.capture.screenshot()
                        if self.storage_tooltip_visible(current,resource):
                            self.nav.input.tap(round(current.shape[1]*.87),round(current.shape[0]*Y[resource]),jitter=0)
                            interrupted_sleep(.2,self.stop)
                            break
                    except (InterruptedError,ValueError):
                        break
            if not self.stop():self.nav.ensure_clan_chat()
