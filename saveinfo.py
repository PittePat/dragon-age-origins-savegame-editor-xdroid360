# -*- coding: utf-8 -*-
"""Read-only information from a Dragon Age: Origins savegame: quest journal and location (no GUI)."""
from collections import namedtuple

from gff4.datoolset_fields import (
    SAVEGAME_CAMPAIGN, SAVEGAME_JOURNAL, SAVEGAME_JOURNAL_ACTIVE_LIST, SAVEGAME_JOURNAL_COMPLETE_LIST,
    SAVEGAME_JOURNAL_TITLE, SAVEGAME_JOURNAL_TEXT, SAVEGAME_JOURNAL_RESREF, SAVEGAME_JOURNAL_QUEST_GROUP,
    SAVEGAME_JOURNAL_QUEST_UPDATED, CAMPAIGN_CIF_ENTRY_AREA, CAMPAIGN_CIF_ENTRY_POSITION,
    SAVEGAME_PLAYERCHAR, SAVEGAME_PLAYERCHAR_CHAR, POSITION, SAVEGAME_PLAYER_MAP_ZOOM,
    SAVEGAME_AREALIST, TAG, SAVEGAME_APPEARANCE, SAVEGAME_APPEARANCE_GENDER,
)

Quest = namedtuple('Quest', 'status resref group title_id text_id title updated')
Location = namedtuple('Location', 'area area_name position entry_position zoom visited')

def _clean(value):
    return str(value).strip('\0') if value is not None else ''

def quest_entries(root):
    """Active quests first, then completed ones. 'title' is only filled if the savegame itself carries the text;
    normally it only has the text id ('title_id') that points into the game's talk table."""
    try:
        journal = root[SAVEGAME_CAMPAIGN][SAVEGAME_JOURNAL]
    except KeyError:
        return []
    quests = []
    for status, label in (('Active', SAVEGAME_JOURNAL_ACTIVE_LIST), ('Completed', SAVEGAME_JOURNAL_COMPLETE_LIST)):
        try:
            entries = journal[label]
        except KeyError:
            continue
        for q in entries:
            title, text = q[SAVEGAME_JOURNAL_TITLE], q[SAVEGAME_JOURNAL_TEXT]
            quests.append(Quest(status, _clean(q[SAVEGAME_JOURNAL_RESREF]), _clean(q[SAVEGAME_JOURNAL_QUEST_GROUP]),
                                int(title.label), int(text.label), _clean(title.s),
                                bool(int(q[SAVEGAME_JOURNAL_QUEST_UPDATED]))))
    return quests

def _vec(v):
    return (float(v.a), float(v.b), float(v.c)) if v is not None else None

def location_info(root, names=None):
    """Current area, positions and the areas stored in the savegame. `names` maps resref -> readable name."""
    names = names or {}
    campaign = root[SAVEGAME_CAMPAIGN]
    area = _clean(campaign[CAMPAIGN_CIF_ENTRY_AREA])
    player = root[SAVEGAME_PLAYERCHAR]
    creature = player[SAVEGAME_PLAYERCHAR_CHAR]
    visited = []
    try:
        for a in root[SAVEGAME_AREALIST]:
            tag = _clean(a[TAG])
            if tag:
                visited.append((tag, names.get(tag, '')))
    except KeyError:
        pass
    return Location(area, names.get(area, ''), _vec(creature[POSITION]), _vec(campaign[CAMPAIGN_CIF_ENTRY_POSITION]),
                    float(player[SAVEGAME_PLAYER_MAP_ZOOM]), visited)

def player_is_female(root):
    """True if the player character is female (selects the '*_f.tlk' text variants)."""
    try:
        appearance = root[SAVEGAME_PLAYERCHAR][SAVEGAME_PLAYERCHAR_CHAR][SAVEGAME_APPEARANCE]
        return int(appearance[SAVEGAME_APPEARANCE_GENDER]) == 2
    except KeyError:
        return False
