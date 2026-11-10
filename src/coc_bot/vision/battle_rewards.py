"""Optional result metadata from the inspected completed-battle layouts only."""
from functools import lru_cache
from pathlib import Path
import cv2
import numpy as np


@lru_cache(maxsize=16)
def reference(name):
    return cv2.imread(str(Path(__file__).with_name('assets')/(name+'.png')))


def match(frame,name,box):
    ref=reference(name)
    x,y,u,v=box;region=frame[y:v,x:u]
    if ref is None or any(a<b for a,b in zip(region.shape[:2],ref.shape[:2])):return False
    _,score,_,point=cv2.minMaxLoc(cv2.matchTemplate(region,ref,cv2.TM_CCOEFF_NORMED))
    observed=region[point[1]:point[1]+ref.shape[0],point[0]:point[0]+ref.shape[1]]
    return score>=.96 and observed.mean()>=ref.mean()*.85


def results(frame,village,stop=None):
    if (not isinstance(frame,np.ndarray) or frame.dtype!=np.uint8 or frame.ndim!=3
            or frame.shape[2]!=3 or not 1.6<frame.shape[1]/frame.shape[0]<1.95
            or stop and stop()):return {}
    from coc_bot.vision.home_frames import has_exact_cap_178,restore_cap_178
    if has_exact_cap_178(frame):frame=restore_cap_178(frame)
    frame=cv2.resize(frame,(1920,1080))
    from coc_bot.progression.reader import balance_amount
    if village=='builder':
        if not (match(frame,'builder_reward_title',(1110,550,1340,635))
                and match(frame,'builder_reward_gold',(1290,625,1380,710))):return {}
        value=balance_amount(frame[650:691,1147:1290],stop)
        loot={'gold':value} if type(value) is int and 0<=value<=10_000_000 else None
        damage=balance_amount(frame[440:513,849:1008],stop)
        boxes=[(645,212,851,425),(834,110,1085,365),(1066,212,1278,425)]
    elif village=='home':
        if not match(frame,'home_reward_title',(880,410,1040,480)):return {}
        loot={}
        for resource,box,area in [('gold',(990,450,1100,540),(800,473,1008,520)),
                ('elixir',(990,520,1100,615),(800,544,1008,592)),
                ('dark_elixir',(990,595,1100,690),(800,615,1008,665))]:
            if not match(frame,'home_reward_'+resource,box):continue
            x,y,u,v=area;value=balance_amount(frame[y:v,x:u],stop)
            if type(value) is int and 0<=value<=100_000_000:loot[resource]=value
        damage=100 if match(frame,'home_damage_100',(880,135,1040,220)) else None
        boxes=[(685,132,877,313),(835,40,1086,280),(1045,132,1238,313)]
    else:return {}
    result={}
    if loot:result['loot']=loot
    if type(damage) is int and 0<=damage<=100:result['damage_percent']=damage
    # Each earned star is independently measured. An uninspected gray/star
    # layout remains unknown instead of inferring a count from destruction.
    all_earned=True
    for index,(x,y,u,v) in enumerate(boxes):
        ref=reference(f'{village}_earned_star_{index}')
        if ref is None:all_earned=False;break
        mask=lambda a:(cv2.inRange(cv2.cvtColor(a,cv2.COLOR_BGR2HSV),(10,100,130),(38,255,255))
                       if village=='builder' else cv2.inRange(cv2.cvtColor(a,cv2.COLOR_BGR2HSV),(0,0,220),(180,65,255)))
        expected=mask(ref)>0;observed=mask(frame[y:v,x:u])>0
        if not expected.any() or float(observed[expected].mean())<.90:all_earned=False
    if all_earned:result['stars']=3
    return result


def agreeing_results(first,second,village,stop=None):
    a=results(first,village,stop);b=results(second,village,stop)
    result={key:value for key,value in a.items() if key!='loot' and value==b.get(key)}
    loot={key:value for key,value in a.get('loot',{}).items() if value==b.get('loot',{}).get(key)}
    if loot:result['loot']=loot
    return result
