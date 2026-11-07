"""Shared portrait identities, never shared levels, readiness or attack plans."""
from functools import lru_cache
import json
from pathlib import Path
import re

import cv2
import numpy as np

from coc_bot.attack.army import ArmyCard, UnitCatalog


@lru_cache(maxsize=1)
def standard_portraits():
    with np.load(Path(__file__).with_name('assets')/'hero_portraits.npz',
                 allow_pickle=False) as archive:
        return tuple((name,archive[name]) for name in archive.files)


def profile_data_roots(data_dir):
    """Use only the installation's registered profiles, never backup snapshots."""
    from coc_bot.accounts.store import AccountStore, IDENT
    current = Path(data_dir).resolve()
    base = current
    if (current.name == 'data' and IDENT.fullmatch(current.parent.name)
            and current.parent.parent.name == 'profiles'
            and current.parent.parent.parent.name == 'accounts'):
        base = current.parents[3]
    if not (base/'accounts/registry.json').is_file():
        return [current]
    store = AccountStore(base.parent)
    roots = [(store.profile(account)/'data').resolve()
             for account in store.load()['accounts']]
    return roots if current in roots else [current]


def add_shared_heroes(config, catalog, *, unit_ids=None):
    """A reviewed skin learned on one account is available to all accounts.

    Existing files stay in their source profiles for backup/restore. Only their
    portrait identities are shared; no observation, count or device state is.
    Explicit saved plans retain their reviewed custom names.
    """
    standards = UnitCatalog(Path('missing-hero-icons'))

    def add(target, name, image):
        h,w = image.shape[:2]
        target.add_references(image,[ArmyCard('shared-hero',(0,0,w,h),name,
                                             'hero',1,confirmed=True)])

    for name,image in standard_portraits():
        add(standards,name,image)
        if unit_ids is None or name in unit_ids:
            add(catalog,name,image)
    seen = set()
    for root in profile_data_roots(config.data_dir):
        for path in sorted((root/'attack-planner/units').glob('*.json')):
            try:
                image_path = path.with_suffix('.png')
                if (not path.resolve().is_relative_to(root)
                        or not image_path.resolve().is_relative_to(root)):
                    continue
                value = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(value,dict) or value.get('kind') != 'hero':continue
                name = value.get('unit_id')
                if not isinstance(name,str) or not re.fullmatch(r'[a-z0-9_]{1,80}',name):continue
                if unit_ids is not None and name not in unit_ids:continue
                image = cv2.imread(str(image_path))
                if image is None or not all(40 <= n <= 600 for n in image.shape[:2]):continue
                # A standard portrait previously saved as e.g. "hero_1" must
                # not compete against its own canonical name in automatic mode.
                if unit_ids is None:
                    match = standards.identify_reference(image,kind='hero')
                    if match:
                        if name in dict(standard_portraits()) and name != match[0]:continue
                        name = match[0]
                key = (name,image.shape,image.tobytes())
                if key in seen:continue
                seen.add(key)
                add(catalog,name,image)
            except (OSError,ValueError,TypeError,cv2.error):
                continue
