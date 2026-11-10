"""Read the inspected landscape Build menu; unknown layouts fail closed."""
from dataclasses import dataclass, asdict
from pathlib import Path
import re
import tempfile
import csv
import io
import unicodedata
from functools import lru_cache

import cv2
import numpy as np

from coc_bot.runtime.processes import run_process


@lru_cache(maxsize=3)
def _goblin_counter(kind, native=False):
    name=('goblin-research-counter-native.png' if native else
          'goblin-research-counter.png' if kind=='research' else 'goblin-counter.png')
    return cv2.imread(str(Path(__file__).with_name('assets')/name))


def compact(text):
    return re.sub(r"[^a-z]", "", text.lower())


PET_NAMES = {compact(name): name for name in (
    'L.A.S.S.I', 'Electro Owl', 'Mighty Yak', 'Unicorn', 'Frosty', 'Diggy',
    'Poison Lizard', 'Phoenix', 'Spirit Fox', 'Angry Jelly', 'Sneezy', 'Greedy Raven',
)}


def _pet_ocr(value):
    # The game's dotted L.A.S.S.I title has S/5 and I/1/bracket ambiguities.
    # Correct only the complete known name, never prices or arbitrary words.
    return re.sub(r'(?i)\bl[. :\-]*a[. :\-]*[s5]\$?[. :\-]*[s5][. :\-]*[i1l|!\]]','LASSI',value)


def pet_name(value):
    value=re.sub(r'(?i)\s+(?:[0-9Il|]+[dhwm]\s*)+$','',value.strip())
    return PET_NAMES.get(compact(_pet_ocr(value)))


def upgrade_heading(value, candidate):
    value=unicodedata.normalize('NFKD', value)
    if compact(candidate.name)=='lassi':
        value=_pet_ocr(value)
    if compact(candidate.name) in ('barracks','darkbarracks'):
        # The inspected outlined heading can duplicate one R. Correct only the
        # full known building word; never alter levels, prices or other names.
        value=re.sub(r'(?i)\bbar{3}acks\b','Barracks',value)
    if compact(candidate.name)=='clancastle':
        # The inspected outlined title joins the t/l as "til" in OCR.
        # Correct only this complete known building name, never any price.
        value=re.sub(r'(?i)\bclan\s+castile\b','Clan Castle',value)
    return re.sub(r'^up+(?=grad)','up',compact(value))


def crop(frame, box):
    h, w = frame.shape[:2]
    a, b, c, d = box
    return frame[round(b*h):round(d*h), round(a*w):round(c*w)]


def text(image, *, digits=False, fraction=False, stop=None, psm=7):
    if image is None or not image.size:
        return ""
    if stop and stop():
        return ""
    if (digits or fraction) and image.ndim==3:
        hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
        gray=cv2.bitwise_not(cv2.inRange(hsv,(0,0,170),(180,75,255)))
        gray=cv2.copyMakeBorder(gray,8,8,8,8,cv2.BORDER_CONSTANT,value=255)
    else:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)/"label.png"
        cv2.imwrite(str(path), gray)
        command = ["tesseract", str(path), "stdout", "--psm", str(psm), "-l", "eng"]
        if digits or fraction:
            command += ["-c", "tessedit_char_whitelist=0123456789" + ("/" if fraction else "")]
        result = run_process(command, text=True, timeout=4, stop_check=stop)
        return (result.stdout or "").strip() if result.returncode == 0 else ""


def amount(image, stop=None):
    from coc_bot.upgrades.digits import read_digits
    raw = read_digits(image) or ''
    if not re.fullmatch(r"[\d\s]+", raw):
        return None
    value = int(re.sub(r"\s", "", raw))
    return value if 0 <= value <= 500_000_000 else None


def resource_amount(image, stop=None):
    """Separate bright resource text from scenery in a partly empty bar."""
    original=amount(image,stop)
    if image is None or not image.size:
        return None
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    bright=cv2.inRange(hsv,(0,0,230),(180,75,255))
    isolated=amount(cv2.cvtColor(bright,cv2.COLOR_GRAY2BGR),stop)
    # Both reads retain the strict glyph threshold. Conflicting numbers block
    # spending; uncertain labels are never replaced with a guessed OCR result.
    if original is not None and isolated is not None and original != isolated:
        return None
    return original if original is not None else isolated


def currency(image):
    if not image.size:
        return None
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    masks = {
        "dark_elixir": ((110,40,35),(175,255,145)),
        "elixir": ((130,70,150),(175,255,255)),
        "gold": ((15,100,150),(34,255,255)),
    }
    scores = {key: float(cv2.inRange(hsv, lo, hi).mean())/255
              for key,(lo,hi) in masks.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > .07 else None


def confirmation_price(cell, stop=None):
    """Discounts show a green payable line above a red-struck original price."""
    h,w=cell.shape[:2]
    hsv=cv2.cvtColor(cell,cv2.COLOR_BGR2HSV)
    lower=hsv[round(h*.65):round(h*.92),round(w*.03):round(w*.80)]
    red=cv2.inRange(lower,(0,110,110),(10,255,255))|cv2.inRange(lower,(170,110,110),(180,255,255))
    strike=(red>0).mean(axis=1)>.55 if red.size else np.array([],dtype=bool)
    if strike.any():
        # Only an observed narrow horizontal strike enables the separate line.
        if strike.sum()>max(3,round(h*.08)):return None
        prices=[]
        for saturation in (180,190,195,200,210):
            mask=cv2.inRange(hsv,(35,saturation,100),(90,255,255))
            line=mask[round(h*.32):round(h*.64),round(w*.03):round(w*.80)]
            value=resource_amount(cv2.cvtColor(line,cv2.COLOR_GRAY2BGR),stop)
            if value is not None:prices.append(value)
        # Pale green button shading can contaminate the least saturated mask.
        # Two strict price reads must still agree; any valid conflict blocks.
        return prices[0] if len(prices)>=2 and len(set(prices))==1 else None
    return resource_amount(cell[round(h*.48):round(h*.91),round(w*.03):round(w*.80)],stop)


@dataclass(frozen=True)
class Candidate:
    name: str
    cost: int
    currency: str
    point: tuple[int,int]
    assigned: bool | None = None

    def public(self):
        return asdict(self)


class UpgradeReader:
    def __init__(self, stop=None):
        self.stop = stop
        self._pet_empty_reference = None

    def label(self, frame, box):
        return text(crop(frame, box), stop=self.stop)

    def menu_kind(self, frame):
        h,w = frame.shape[:2]
        if not 1.6 < w/h < 1.95:
            return None
        # Both this heading and the red close control must be present.
        close = crop(frame,(.973,.008,.997,.055))
        hsv=cv2.cvtColor(close,cv2.COLOR_BGR2HSV)
        red=cv2.bitwise_or(cv2.inRange(hsv,(0,100,100),(10,255,255)),
                           cv2.inRange(hsv,(170,100,100),(180,255,255)))
        white=cv2.inRange(hsv,(0,0,210),(180,65,255))
        if float(red.mean())/255 < .15 or float(white.mean())/255 < .08:
            return None
        title = compact(self.label(frame, (.79,.012,.96,.05)))
        if title == "armyupgrades":
            return "research"
        if title == "heropets":
            return "pets"
        if title in ("buildingsheroes", "buildingheroes"):
            return "buildings"
        return None

    def upgrade_title(self, frame, candidate=None):
        title=self.label(frame,(.26,.035,.73,.095))
        normalized=upgrade_heading(title,candidate) if candidate is not None else compact(title)
        prefixes=(('upgrade'+compact(candidate.name)+'toleve','upgrading'+compact(candidate.name)+'toleve')
                  if candidate is not None else ('upgrade','upgrading'))
        if normalized.startswith(prefixes) and 'toleve' in normalized:return title
        # Long names extend beyond the compact title region. Keep the original
        # crop for short names, where unrelated header controls can spoil OCR.
        return self.label(frame,(.14,.035,.85,.095))

    def detail_close(self, frame, candidate=None):
        capped_home = False
        if candidate is not None:
            from coc_bot.vision.capped_frames import has_exact_cap_178
            if has_exact_cap_178(frame):
                heading = self.upgrade_title(frame,candidate)
                normalized = upgrade_heading(heading, candidate)
                prefix = 'upgrade' + compact(candidate.name) + 'tolevel'
                raw_title = re.sub(r'[^a-z0-9]', '',
                                   unicodedata.normalize('NFKD', heading).lower())
                if compact(candidate.name) == 'lassi':
                    raw_title = re.sub(r'[^a-z0-9]', '', _pet_ocr(raw_title).lower())
                if compact(candidate.name) in ('barracks', 'darkbarracks'):
                    raw_title = re.sub(r'bar{3}acks', 'barracks', raw_title)
                if compact(candidate.name) == 'clancastle':
                    raw_title = raw_title.replace('clancastile', 'clancastle')
                if (not normalized.startswith(prefix)
                        or not raw_title.startswith(prefix)
                        or re.fullmatch(r'\d{1,3}', raw_title[len(prefix):]) is None):
                    return None
                capped_home = True
        close=crop(frame,(.865,.04,.907,.113))
        hsv=cv2.cvtColor(close,cv2.COLOR_BGR2HSV)
        red=cv2.bitwise_or(cv2.inRange(hsv,(0,100,100),(10,255,255)),
                           cv2.inRange(hsv,(170,100,100),(180,255,255)))
        if capped_home:
            x_mark=crop(frame,(.875,.052,.900,.096))
            x_hsv=cv2.cvtColor(x_mark,cv2.COLOR_BGR2HSV)
            white=cv2.inRange(x_hsv,(0,0,160),(180,75,178))
        else:
            white=cv2.inRange(hsv,(0,0,200),(180,65,255))
        if red.mean()/255 < .20 or white.mean()/255 < .08:
            return None
        label=re.sub(r'^up+(?=grad)','up',compact(self.upgrade_title(frame,candidate)))
        if not label.startswith(('upgrade','upgrading')) or 'toleve' not in label:
            return None
        h,w=frame.shape[:2]
        return round(w*.886),round(h*.075)

    def running_detail(self, frame, candidate):
        heading=compact(self.upgrade_title(frame,candidate))
        timer=compact(self.label(frame,(.79,.82,.895,.865)))
        return (upgrade_heading(heading,candidate).startswith('upgrading'+compact(candidate.name)+'toleve')
                and timer=='timeleft' and self.detail_close(frame,candidate) is not None)

    def availability(self, frame, kind):
        from coc_bot.upgrades.digits import read_digits
        box = {'buildings':(.739,.945,.788,.982),'research':(.808,.945,.854,.982),
               'pets':(.944,.945,.987,.982)}.get(kind)
        if box is None: return None
        raw = read_digits(crop(frame,box),fraction=True) or ''
        match = re.fullmatch(r'(\d)/(\d)',raw)
        if not match and kind in ('buildings','research'):
            from coc_bot.progression.reader import counter_digit_variants
            raw=read_digits(crop(frame,box),fraction=True,extra_templates=counter_digit_variants()) or ''
            match=re.fullmatch(r'(\d)/(\d)',raw)
        if not match:
            return None
        free,total=map(int,match.groups())
        if kind in ('buildings','research'):
            # The Goblin event adds a gem-only worker to the displayed fraction
            # when regular workers are busy. Never count it as a free builder
            # or research slot, including when reconciling a real upgrade.
            bounds=(.735,.895,.79,.947) if kind=='buildings' else (.802,.895,.86,.947)
            references=[((1853,1048),_goblin_counter(kind))]
            if kind=='research':
                references.append(((1920,1080),_goblin_counter(kind,native=True)))
            for size,reference in references:
                if reference is None:continue
                region=crop(cv2.resize(frame,size),bounds)
                if region.shape[0]<reference.shape[0] or region.shape[1]<reference.shape[1]:continue
                _,score,_,(x,y)=cv2.minMaxLoc(cv2.matchTemplate(region,reference,cv2.TM_CCOEFF_NORMED))
                observed=region[y:y+reference.shape[0],x:x+reference.shape[1]]
                if score>=.96 and observed.mean()>=reference.mean()*.85:
                    if not 0<=free<=total or total<2:return None
                    free=max(0,free-1);total-=1
                    break
        maximum=6 if kind=='buildings' else 1
        return (free,total) if 0 <= free <= total <= maximum and total>0 else None

    def balances(self, frame):
        values={key:resource_amount(crop(frame,box),self.stop) for key,box in {
            'gold':(.56,.033,.679,.073),
            'elixir':(.56,.104,.679,.143),
            'dark_elixir':(.59,.17,.685,.217),
        }.items()}
        from coc_bot.progression.reader import balance_amount
        for key,box in (('gold',(.525,.035,.679,.072)),('elixir',(.525,.103,.679,.14))):
            if values[key] is None:values[key]=balance_amount(crop(frame,box),self.stop)
        if values['dark_elixir'] is None and currency(crop(frame,(.684,.16,.719,.22)))=='dark_elixir':
            values['dark_elixir']=balance_amount(crop(frame,(.59,.17,.679,.217)),self.stop)
        return values

    def _headings(self, frame):
        """Read section labels with their positions; never infer them from color."""
        h,w=frame.shape[:2]
        strip=crop(frame,(.735,.065,.998,.892))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'panel.png'
            cv2.imwrite(str(path),cv2.resize(strip,None,fx=2,fy=2))
            result=run_process(['tesseract',str(path),'stdout','--psm','6','-l','eng','tsv'],
                               text=True,timeout=6,stop_check=self.stop)
        words=list(csv.DictReader(io.StringIO(result.stdout or ''),delimiter='\t'))
        found=[]
        for i,word in enumerate(words[:-1]):
            first=compact(word.get('text',''))
            second=compact(words[i+1].get('text',''))
            phrase=first+second
            section='suggested' if first.startswith('suggested') and 'up' in phrase else ('other' if first.startswith('other') and 'up' in phrase else None)
            if section is not None:
                top=int(word['top'])/2+round(h*.065)
                bottom=(int(word['top'])+int(word['height']))/2+round(h*.065)
                found.append((section+'upgrades',round(top),round(bottom)))
            elif first in ('assigned','unassigned'):
                top=int(word['top'])/2+round(h*.065)
                bottom=(int(word['top'])+int(word['height']))/2+round(h*.065)
                found.append((first,round(top),round(bottom)))
        return found

    def pet_candidates(self, frame):
        """Read pet rows, excluding locked/maxed entries without a real price.

        Pet order is not a Suggested ranking. Visible section headings establish
        assignment. A matching empty hero slot can carry verified unassigned
        state across a scroll; missing evidence never means unassigned.
        """
        h,w=frame.shape[:2]
        sections=sorted(((name,y0,y1) for name,y0,y1 in self._headings(frame)
                         if name in ('assigned','unassigned')),key=lambda item:item[1])
        top,bottom=round(h*.105),round(h*.89)
        strip=frame[top:bottom,round(w*.800):round(w*.977)]
        mask=cv2.inRange(cv2.cvtColor(strip,cv2.COLOR_BGR2HSV),(7,45,120),(30,190,220))
        rows=(mask.mean(axis=1)/255>.30).astype(np.uint8)
        found=[];start=None
        for y,value in enumerate(np.append(rows,0)):
            if value and start is None: start=y
            if value or start is None: continue
            a,b=top+start,top+y;start=None
            if b-a<h*.045 or a<=top or b>=bottom: continue
            height=b-a
            title=frame[a+round(height*.04):a+round(height*.48),round(w*.802):round(w*.955)]
            white=cv2.inRange(cv2.cvtColor(title,cv2.COLOR_BGR2HSV),(0,0,210),(180,75,255))
            letters=cv2.copyMakeBorder(255-white,8,8,8,8,cv2.BORDER_CONSTANT,value=255)
            name=pet_name(text(letters,stop=self.stop))
            if not name: continue
            price=resource_amount(frame[a+round(height*.46):b-round(height*.04),
                               round(w*.85):round(w*.983)],self.stop)
            resource=currency(frame[a+round(height*.30):b,round(w*.979):round(w*.996)])
            if not price or resource!='dark_elixir': continue
            preceding=[label for label,_,end in sections if end<a]
            assigned=(preceding[-1]=='assigned') if preceding else None
            slot=frame[a:b,round(w*.735):round(w*.765)]
            slot=cv2.resize(slot,(56,56),interpolation=cv2.INTER_AREA)
            if assigned is False:
                self._pet_empty_reference=slot
            elif assigned is None and self._pet_empty_reference is not None:
                error=np.abs(slot.astype(float)-self._pet_empty_reference.astype(float))
                if np.std(self._pet_empty_reference)>8 and error.mean()<8 and np.percentile(error,90)<20:
                    assigned=False
            found.append(Candidate(name,price,resource,(round(w*.86),(a+b)//2),assigned))
        return found, False

    def candidates(self, frame):
        """Read only Suggested upgrades, never silently use Other upgrades."""
        h,w=frame.shape[:2]
        top=bottom=None
        for label,y0,y1 in self._headings(frame):
            if label == 'suggestedupgrades':
                top=y1+round(h*.008)
            elif label == 'otherupgrades' and top is not None:
                bottom=y0-round(h*.003)
                break
        if top is None or bottom is None:
            return [], False
        # The narrow color strip can split a row at its white title and omit
        # valid Suggested entries. Use the full-card reader, still restricted
        # to the independently recognized Suggested section.
        from coc_bot.progression.reader import ProgressionReader
        candidates=[]
        for row in ProgressionReader(self.stop).rows(frame):
            if top<=row['point'][1]<=bottom and row['name'] and row['cost'] and row['currency']:
                candidates.append(Candidate(row['name'],row['cost'],row['currency'],row['point']))
        return candidates, bottom < round(h*.89)

    def confirmation(self, frame, candidate):
        frame=self._restore_capped_home_confirmation(frame,candidate)
        heading=self.upgrade_title(frame,candidate)
        normalized=upgrade_heading(heading,candidate)
        if not normalized.startswith('upgrade'+compact(candidate.name)+'toleve'):
            return None
        h,w=frame.shape[:2]
        x0,y0=round(w*.46),round(h*.80)
        button=frame[y0:round(h*.95),x0:round(w*.79)]
        hsv=cv2.cvtColor(button,cv2.COLOR_BGR2HSV)
        green=cv2.inRange(hsv,(35,80,130),(90,255,255))
        green=cv2.morphologyEx(green,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
        contours,_=cv2.findContours(green,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        targets=[]
        for contour in contours:
            x,y,bw,bh=cv2.boundingRect(contour)
            if bw < w*.12 or bh < h*.07:
                continue
            cell=button[y:y+bh,x:x+bw]
            label_image=cell[round(bh*.10):round(bh*.40),round(bw*.15):round(bw*.85)]
            label=text(label_image,stop=self.stop)
            if not label.strip():
                # Pale green buttons can defeat the normal line reader. Both
                # polarities of the isolated text mask must agree on the label.
                from coc_bot.vision.ocr import _button_label_variants
                variants=_button_label_variants(label_image)
                readings=[compact(text(v,stop=self.stop,psm=8)) for v in variants[:2]]
                if readings[0] == readings[1] and readings[0] in ('confirm','upgrade'):
                    label=readings[0]
            # Eight-digit prices begin close to the left edge. Keep the whole
            # number while excluding the resource icon on the right.
            # The green button shades its white text differently from the list.
            # Use the same strict contrast-isolated read as resource balances;
            # conflicting raw/isolated prices still block spending.
            price=confirmation_price(cell,self.stop)
            resource=currency(cell[round(bh*.35):round(bh*.95),round(bw*.79):round(bw*.99)])
            normalized=compact(label).replace('contirm','confirm')
            if not re.fullmatch(r'(?:ge)?(?:confirm|upgrade)',normalized):
                continue
            if price==candidate.cost and resource==candidate.currency:
                targets.append({'point':(x0+x+bw//2,y0+y+bh//2), 'level_text':heading,
                                'name':candidate.name,'cost':price,'currency':resource})
        return targets[0] if len(targets)==1 else None

    def _restore_capped_home_confirmation(self, frame, candidate):
        """Restore one exact-cap Home payment modal after its foreground is proven.

        The popup itself is rendered at the measured 178 ceiling while the
        intentionally dimmed scene behind it can remain at 89. The candidate
        title, red close with a white X, and a green button carrying the
        requested resource must all be visible before strict price parsing is
        allowed on a locally restored copy. BuilderReader overrides
        ``confirmation`` and never enters this Home-only path.
        """
        from coc_bot.vision.capped_frames import has_exact_cap_178, restore_cap_178
        if not has_exact_cap_178(frame):
            return frame
        raw_heading=self.upgrade_title(frame,candidate)
        heading = upgrade_heading(raw_heading,candidate)
        title_prefix='upgrade'+compact(candidate.name)+'tolevel'
        title_alnum=re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',raw_heading).lower())
        if compact(candidate.name)=='lassi':
            title_alnum=re.sub(r'[^a-z0-9]','',_pet_ocr(title_alnum).lower())
        if compact(candidate.name) in ('barracks','darkbarracks'):
            title_alnum=re.sub(r'bar{3}acks','barracks',title_alnum)
        if compact(candidate.name)=='clancastle':
            title_alnum=title_alnum.replace('clancastile','clancastle')
        # The normal compact helper intentionally removes digits, so retain the
        # raw alphanumeric suffix here and require one complete level number.
        if (not heading.startswith(title_prefix)
                or not title_alnum.startswith(title_prefix)
                or re.fullmatch(r'\d{1,3}',title_alnum[len(title_prefix):]) is None):
            return frame

        h,w=frame.shape[:2]
        close=crop(frame,(.865,.04,.907,.113))
        hsv=cv2.cvtColor(close,cv2.COLOR_BGR2HSV)
        red=(cv2.inRange(hsv,(0,100,100),(10,255,255))
             | cv2.inRange(hsv,(170,100,100),(180,255,255)))
        # Check the bright X separately from the red surround. V=160 is below
        # the measured cap, while the low saturation rejects the red button.
        x_mark=crop(frame,(.875,.052,.900,.096))
        x_hsv=cv2.cvtColor(x_mark,cv2.COLOR_BGR2HSV)
        white=cv2.inRange(x_hsv,(0,0,160),(180,75,178))
        if red.mean()/255 < .25 or white.mean()/255 < .12:
            return frame

        x0,y0=round(w*.46),round(h*.80)
        button=frame[y0:round(h*.95),x0:round(w*.79)]
        button_hsv=cv2.cvtColor(button,cv2.COLOR_BGR2HSV)
        green=cv2.inRange(button_hsv,(35,80,130),(90,255,255))
        green=cv2.morphologyEx(green,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
        contours,_=cv2.findContours(green,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x,y,bw,bh=cv2.boundingRect(contour)
            if bw < w*.12 or bh < h*.07:
                continue
            cell=button[y:y+bh,x:x+bw]
            resource_icon=cell[round(bh*.35):round(bh*.95),round(bw*.79):round(bw*.99)]
            if currency(resource_icon)==candidate.currency:
                return restore_cap_178(frame)
        return frame

    def active_names(self, frame, kind=None):
        """Active upgrades use green progress rows above Suggested upgrades."""
        h,w=frame.shape[:2]
        headings=self._headings(frame)
        labels=('assigned','unassigned') if kind=='pets' else ('suggestedupgrades',)
        bottom=next((y0 for label,y0,_ in headings if label in labels),None)
        if bottom is None: return []
        panel=frame[round(h*.07):bottom,round(w*.735):round(w*.998)]
        hsv=cv2.cvtColor(panel,cv2.COLOR_BGR2HSV)
        green=cv2.inRange(hsv,(35,60,65),(90,255,255))
        if kind=='pets':
            # One pet owns the slot. Its initial progress is a narrow green
            # sliver, not the full title's bounds. Read the complete row above
            # Assigned/Unassigned rather than cropping letters to that sliver.
            if np.count_nonzero(green)<h*.023: return []
            region=frame[round(h*.08):bottom-round(h*.004),round(w*.74):round(w*.93)]
            if not region.size: return []
            white=cv2.inRange(cv2.cvtColor(region,cv2.COLOR_BGR2HSV),(0,0,210),(180,75,255))
            letters=cv2.copyMakeBorder(255-white,8,8,8,8,cv2.BORDER_CONSTANT,value=255)
            name=pet_name(text(letters,stop=self.stop))
            return [compact(name)] if name else []
        # Newly started upgrades have only a thin green sliver at the left edge.
        rows=(green.mean(axis=1)/255 > .003).astype(np.uint8)
        result=[]; start=None
        for y,value in enumerate(np.append(rows,0)):
            if value and start is None: start=y
            if not value and start is not None:
                if y-start > h*.023:
                    a=start+round(h*.07); b=y+round(h*.07)
                    region=frame[a:b,round(w*.74):round(w*.93)]
                    hsv=cv2.cvtColor(region,cv2.COLOR_BGR2HSV)
                    mask=cv2.inRange(hsv,(0,0,220),(180,65,255))
                    letters=cv2.copyMakeBorder(255-mask,8,8,8,8,cv2.BORDER_CONSTANT,value=255)
                    value=text(letters,stop=self.stop)
                    name=compact(pet_name(value) or value)
                    # The observed running-timer font reads the middle O as A.
                    result.append('laboratory' if name=='laboratary' else name)
                start=None
        return result
