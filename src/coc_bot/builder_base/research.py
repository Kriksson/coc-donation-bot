"""Shared identity and level policy for Builder progression research."""
from coc_bot.upgrades.vision import compact


def supports_progression_research(row):
    """Accept only the existing Night Witch flow or a verified Archer level.

    Night Witch keeps its established portrait/ability confirmation. Sneaky
    Archer rows are usable only when the native level badge was read; the
    confirmation dialog independently verifies that same supported level
    range, exact Elixir price, resource, and enabled button.
    """
    if not isinstance(row, dict) or row.get('currency') != 'elixir':
        return False
    name = compact(row.get('name', ''))
    if name == 'nightwitch':
        return True
    level = row.get('target_level')
    return name == 'sneakyarcher' and type(level) is int and 2 <= level <= 30
