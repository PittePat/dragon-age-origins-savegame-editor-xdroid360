# -*- coding: utf-8 -*-
"""Spells, talents, skills and skill/talent points of a Dragon Age: Origins savegame.

Pure data logic without any GUI, so it can be tested on its own.

In the savegame a creature (struct CPS1) keeps its abilities as plain lists of ability ids:
  16305 SAVEGAME_SPELLLIST, 16306 SAVEGAME_TALENTLIST, 16307 SAVEGAME_SKILLLIST
The names below map those ids to the in-game names (ids as used by the game's console command
'runscript addtalent <id>'). Unspent points are ordinary stat properties (see POINT_STATS).
"""
from collections import namedtuple

from gff4.datoolset_fields import (
    SAVEGAME_SPELLLIST as LABEL_SPELLLIST,
    SAVEGAME_TALENTLIST as LABEL_TALENTLIST,
    SAVEGAME_SKILLLIST as LABEL_SKILLLIST,
    SAVEGAME_QUICKSLOTS, SAVEGAME_QUICKSLOTS1, SAVEGAME_QUICKSLOTS2, SAVEGAME_QUICKSLOTS3, SAVEGAME_QUICKSLOTS4,
    SAVEGAME_QUICKSLOT_ABILITY as LABEL_QUICKSLOT_ABILITY,
    SAVEGAME_STATPROPERTY_INDEX as LABEL_STAT_INDEX,
    SAVEGAME_STATPROPERTY_BASE as LABEL_STAT_BASE,
)

QUICKSLOT_LISTS = (SAVEGAME_QUICKSLOTS, SAVEGAME_QUICKSLOTS1, SAVEGAME_QUICKSLOTS2,
                   SAVEGAME_QUICKSLOTS3, SAVEGAME_QUICKSLOTS4)

# which savegame list an ability kind is stored in
KIND_LABEL = {
    'spell': LABEL_SPELLLIST,
    'talent': LABEL_TALENTLIST,
    'skill': LABEL_SKILLLIST,
    'trait': LABEL_TALENTLIST,     # passive traits/immunities: assumed to live with the talents
}
KIND_TITLE = {'spell': 'Spell', 'talent': 'Talent', 'skill': 'Skill', 'trait': 'Immunity (experimental)'}

# unspent points are stat properties: (property index, label, help)
POINT_STATS = (
    (34, 'Attribute points', 'Points for Strength, Dexterity, Willpower, Magic, Cunning, Constitution'),
    (35, 'Skill points', 'Points for skills such as Herbalism, Stealing, Combat Training'),
    (36, 'Talent / spell points', 'Points for new talents (warrior, rogue) or spells (mage)'),
    (38, 'Specialization points', 'Points to unlock a specialization such as Blood Mage'),
)

Entry = namedtuple('Entry', 'kind group id name')

def _skill(group, base, name):
    ranks = ('', 'Improved ', 'Expert ', 'Master ')
    return [('skill', group, base + i, ranks[i] + name) for i in range(4)]

def _talents(group, items):
    return [('talent', group, i, n) for i, n in items]

def _spells(group, items):
    return [('spell', group, i, n) for i, n in items]

_RAW = []

# ------------------------------------------------------------------ skills (ranks 1-4)
_RAW += _skill('Skills', 100011, 'Coercion')
_RAW += _skill('Skills', 100110, 'Combat Tactics')
_RAW += _skill('Skills', 100100, 'Combat Training')
_RAW += _skill('Skills', 100061, 'Herbalism')
_RAW += _skill('Skills', 100001, 'Lockpicking')
_RAW += _skill('Skills', 100071, 'Poison-Making')
_RAW += _skill('Skills', 100021, 'Stealing')
_RAW += _skill('Skills', 100075, 'Stealth')
_RAW += _skill('Skills', 100051, 'Survival')
_RAW += _skill('Skills', 100041, 'Trap-Making')

# ------------------------------------------------------------------ mage spells
_RAW += _spells('Mage - Arcane', [(4023, 'Mage (base class marker)'), (200254, 'Arcane Bolt'),
                                  (200255, 'Arcane Shield'), (200256, 'Staff Focus'), (200257, 'Arcane Mastery')])
_RAW += _spells('Primal - Fire', [(10001, 'Flame Blast'), (10204, 'Flaming Weapons'), (10003, 'Fireball'), (10002, 'Inferno')])
_RAW += _spells('Primal - Earth', [(11002, 'Rock Armor'), (12004, 'Stonefist'), (11116, 'Earthquake'), (11124, 'Petrify')])
_RAW += _spells('Primal - Cold', [(13001, "Winter's Grasp"), (11007, 'Frost Weapons'), (13002, 'Cone of Cold'), (13000, 'Blizzard')])
_RAW += _spells('Primal - Lightning', [(14001, 'Lightning'), (14000, 'Shock'), (14002, 'Tempest'), (10211, 'Chain Lightning')])
_RAW += _spells('Creation - Heal line', [(10104, 'Heal'), (10200, 'Rejuvenate'), (10210, 'Regeneration'), (10207, 'Mass Rejuvenation')])
_RAW += _spells('Creation - Heroic line', [(10206, 'Heroic Offense'), (10202, 'Heroic Aura'), (10203, 'Heroic Defense'), (10208, 'Haste')])
_RAW += _spells('Creation - Glyph line', [(11001, 'Glyph of Paralysis'), (10601, 'Glyph of Warding'),
                                          (17000, 'Glyph of Repulsion'), (17028, 'Glyph of Neutralization')])
_RAW += _spells('Creation - Spell Wisp line', [(11006, 'Spell Wisp'), (11113, 'Grease'), (11005, 'Spellbloom'), (12008, 'Stinging Swarm')])
_RAW += _spells('Spirit - Spell Shield line', [(10400, 'Spell Shield'), (10401, 'Dispel Magic'),
                                               (10900, 'Anti-Magic Ward'), (11003, 'Anti-Magic Burst')])
_RAW += _spells('Spirit - Mana line', [(10704, 'Mana Drain'), (11004, 'Mana Cleanse'), (17001, 'Spell Might'), (11000, 'Mana Clash')])
_RAW += _spells('Spirit - Walking Bomb line', [(12005, 'Walking Bomb'), (10500, 'Death Syphon'),
                                               (12011, 'Virulent Walking Bomb'), (10508, 'Animate Dead')])
_RAW += _spells('Spirit - Mind Blast line', [(12006, 'Mind Blast'), (17019, 'Force Field'),
                                             (10209, 'Telekinetic Weapons'), (11123, 'Crushing Prison')])
_RAW += _spells('Entropy - Weakness line', [(11106, 'Weakness'), (11107, 'Paralyze'), (11122, 'Miasma'), (11110, 'Mass Paralysis')])
_RAW += _spells('Entropy - Hex line', [(11112, 'Vulnerability Hex'), (11111, 'Affliction Hex'),
                                       (11114, 'Misdirection Hex'), (11100, 'Death Hex')])
_RAW += _spells('Entropy - Disorient line', [(11115, 'Disorient'), (11108, 'Horror'), (11121, 'Sleep'), (11109, 'Waking Nightmare')])
_RAW += _spells('Entropy - Drain Life line', [(15002, 'Drain Life'), (17002, 'Death Magic'),
                                              (11101, 'Curse of Mortality'), (15003, 'Death Cloud')])
# mage specializations
_RAW += _spells('Specialization - Arcane Warrior', [(4012, 'Arcane Warrior (specialization)'), (17023, 'Combat Magic'),
                                                    (17020, 'Aura of Might'), (17022, 'Shimmering Shield'), (17021, 'Fade Shroud')])
_RAW += _spells('Specialization - Blood Mage', [(4017, 'Blood Mage (specialization)'), (10700, 'Blood Magic'),
                                                (10701, 'Blood Sacrifice'), (10702, 'Blood Wound'), (10703, 'Blood Control')])
_RAW += _spells('Specialization - Shapeshifter', [(4018, 'Shapeshifter (specialization)'), (17008, 'Spider Shape'),
                                                  (17010, 'Bear Shape'), (17007, 'Flying Swarm'), (17009, 'Master Shapeshifter')])
_RAW += _spells('Specialization - Spirit Healer', [(4025, 'Spirit Healer (specialization)'), (10509, 'Group Heal'),
                                                   (10504, 'Revival'), (10506, 'Lifeward'), (10507, 'Cleansing Aura')])

# ------------------------------------------------------------------ warrior / rogue talents
_RAW += _talents('Warrior - base', [(4022, 'Warrior (base class marker)'), (14, 'Powerful'), (808, 'Threaten'), (17, 'Bravery'),
                                    (3021, 'Death Blow'), (19, 'Precise Striking'), (3041, 'Taunt'), (3016, 'Disengage'),
                                    (20, 'Perfect Striking')])
_RAW += _talents('Warrior - Dual Weapon', [(6, 'Dual-Weapon Training'), (8, 'Dual-Weapon Finesse'), (5, 'Dual-Weapon Expert'),
                                           (3036, 'Dual-Weapon Mastery'), (11, 'Dual Striking'), (9, 'Riposte'), (10, 'Cripple'),
                                           (7, 'Punisher'), (3044, 'Dual-Weapon Sweep'), (3035, 'Flurry'), (717, 'Momentum'),
                                           (3043, 'Whirlwind')])
_RAW += _talents('Warrior - Weapon and Shield', [(617, 'Shield Bash'), (1, 'Shield Pummel'), (3073, 'Overpower'), (38, 'Assault'),
                                                 (704, 'Shield Defense'), (37, 'Shield Balance'), (12, 'Shield Wall'),
                                                 (36, 'Shield Expertise'), (3074, 'Shield Block'), (13, 'Shield Cover'),
                                                 (3030, 'Shield Tactics'), (2, 'Shield Mastery')])
_RAW += _talents('Warrior - Two-Handed', [(3024, 'Pommel Strike'), (28, 'Indomitable'), (3000, 'Stunning Blows'), (3, 'Critical Strike'),
                                          (3025, 'Sunder Arms'), (3001, 'Shattering Blows'), (4, 'Sunder Armor'), (3032, 'Destroyer'),
                                          (3028, 'Mighty Blow'), (718, 'Powerful Swings'), (27, 'Two-Handed Strength'),
                                          (3031, 'Two-Handed Sweep')])
_RAW += _talents('Rogue - Archery', [(34, 'Melee Archer'), (500, 'Aim'), (33, 'Defensive Fire'), (35, 'Master Archer'),
                                     (803, 'Pinning Shot'), (805, 'Crippling Shot'), (804, 'Critical Shot'), (802, 'Arrow of Slaying'),
                                     (3071, 'Rapidshot'), (3072, 'Shattering Shot'), (801, 'Suppressing Fire'), (800, 'Scattershot')])
_RAW += _talents('Rogue - base', [(4020, 'Rogue (base class marker)'), (603, 'Dirty Fighting'), (21, 'Combat Movement'),
                                  (3002, 'Coup de Grace'), (3023, 'Feign Death'), (3026, 'Below the Belt'), (708, 'Deadly Strike'),
                                  (777, 'Lethality'), (3069, 'Evasion')])
# warrior / rogue specializations
_RAW += _talents('Specialization - Champion', [(4013, 'Champion (specialization)'), (3037, 'War Cry'), (3038, 'Rally'),
                                               (42, 'Motivate'), (3039, 'Superiority')])
_RAW += _talents('Specialization - Assassin', [(4014, 'Assassin (specialization)'), (3060, 'Mark of Death'),
                                               (56, 'Exploit Weakness'), (3059, 'Lacerate'), (3058, 'Feast of the Fallen')])
_RAW += _talents('Specialization - Bard', [(4015, 'Bard (specialization)'), (3045, 'Song of Valor'), (701, 'Distraction'),
                                           (705, 'Song of Courage'), (1000, 'Captivating Song')])
_RAW += _talents('Specialization - Berserker', [(4016, 'Berserker (specialization)'), (700, 'Berserk'), (48, 'Resilience'),
                                                (3006, 'Constraint'), (3009, 'Final Blow')])
_RAW += _talents('Specialization - Reaver', [(4019, 'Reaver (specialization)'), (3065, 'Devour'),
                                             (3066, 'Frightening Appearance'), (3067, 'Aura of Pain'), (713, 'Blood Frenzy')])
_RAW += _talents('Specialization - Templar', [(4021, 'Templar (specialization)'), (23, 'Righteous Strike'), (3017, 'Cleanse Area'),
                                              (52, 'Mental Fortress'), (25, 'Holy Smite')])
_RAW += _talents('Specialization - Ranger', [(4029, 'Ranger (specialization)'), (1004, 'Summon Wolf'), (91, 'Summon Bear'),
                                             (93, 'Summon Spider'), (92, 'Master Ranger')])
_RAW += _talents('Specialization - Duelist', [(4030, 'Duelist (specialization)'), (709, 'Dueling'), (3050, 'Upset Balance'),
                                              (3049, 'Keen Defense'), (3051, 'Pinpoint Strike')])
_RAW += _talents('Companion - Shale / War Dog', [(4033, 'Shale (specialization)'), (4034, 'War Dog (specialization)'),
                                                 (90017, 'Growl'), (90048, 'Dread Howl'), (90049, 'Combat Training (dog)'),
                                                 (90015, 'Overwhelm'), (90050, 'Fortitude'), (90016, 'Charge'),
                                                 (90047, 'Shred'), (90051, 'Nemesis')])

# ------------------------------------------------------------------ immunities (traits) - experimental
_RAW += [('trait', 'Immunities (experimental)', i, n) for i, n in [
    (150011, 'Cold Immunity'), (150010, 'Fire Immunity'), (150014, 'Nature Immunity'),
    (150015, 'Spirit Immunity'), (150016, 'Lightning Immunity'), (150007, 'Critical Hit Immunity')]]

CATALOG = [Entry(*r) for r in _RAW]

def list_label(kind):
    return KIND_LABEL[kind]

def catalog_by_list():
    """{savegame list label: {ability id: Entry}}"""
    out = {}
    for e in CATALOG:
        out.setdefault(KIND_LABEL[e.kind], {})[e.id] = e
    return out

Row = namedtuple('Row', 'kind id name group learned known')

class AbilityModel(object):
    """Reads and changes the spells/talents/skills of one creature (its CPS1 stats structure)."""
    def __init__(self, stats):
        self.stats = stats

    def _list(self, label):
        try:
            return self.stats[label]
        except KeyError:
            return None

    def ids(self, label):
        lst = self._list(label)
        return [int(x) for x in lst] if lst is not None else []

    def is_learned(self, kind, ability_id):
        return int(ability_id) in self.ids(KIND_LABEL[kind])

    def rows(self):
        """Every catalog ability plus every id found in the savegame that the catalog does not know."""
        by_list = catalog_by_list()
        have = {label: set(self.ids(label)) for label in (LABEL_SPELLLIST, LABEL_TALENTLIST, LABEL_SKILLLIST)}
        rows = [Row(e.kind, e.id, e.name, e.group, e.id in have[KIND_LABEL[e.kind]], True) for e in CATALOG]
        for label, kind in ((LABEL_SPELLLIST, 'spell'), (LABEL_TALENTLIST, 'talent'), (LABEL_SKILLLIST, 'skill')):
            for aid in self.ids(label):
                if aid not in by_list.get(label, {}):
                    rows.append(Row(kind, aid, 'Unknown ability %d' % aid, 'Unknown / internal (in this save)', True, False))
        return rows

    def set_learned(self, kind, ability_id, learned):
        """Adds or removes an ability. Returns True if the savegame changed."""
        ability_id = int(ability_id)
        lst = self._list(KIND_LABEL[kind])
        if lst is None:
            raise KeyError('this character has no %s list' % kind)
        present = [i for i, x in enumerate(lst) if int(x) == ability_id]
        if learned and not present:
            lst.append(lst.elem_type(ability_id))
            return True
        if not learned and present:
            for i in reversed(present):
                del lst[i]
            self._purge_quickslots(ability_id)
            return True
        return False

    def _purge_quickslots(self, ability_id):
        """A removed ability must not stay on the quickbar."""
        for label in QUICKSLOT_LISTS:
            slots = self._list(label)
            if slots is None:
                continue
            for i in range(len(slots) - 1, -1, -1):
                try:
                    if int(slots[i][LABEL_QUICKSLOT_ABILITY]) == ability_id:
                        del slots[i]
                except KeyError:
                    pass

# ------------------------------------------------------------------ stat properties / points
def find_stat(stat_list, index):
    for entry in stat_list:
        if int(entry[LABEL_STAT_INDEX]) == index:
            return entry
    return None

def stat_value(stat_list, index):
    """Base value of a stat property, 0 if the character does not have it."""
    entry = find_stat(stat_list, index)
    return float(entry[LABEL_STAT_BASE]) if entry is not None else 0.0

def add_stat_property(root, stat_list, index, fourcc):
    """Appends a new stat property (all values zero) and returns it."""
    cls = root.header.find(fourcc)
    entry = cls()
    entry[LABEL_STAT_INDEX] = index
    stat_list.append(entry)
    return entry

def set_point_stat(root, stat_list, index, value):
    """Sets the base value of a point stat, creating the property if needed. True if something changed."""
    entry = find_stat(stat_list, index)
    if entry is None:
        if value == 0:
            return False
        entry = add_stat_property(root, stat_list, index, 'SMPL')
    if float(entry[LABEL_STAT_BASE]) == float(value):
        return False
    entry[LABEL_STAT_BASE] = float(value)
    return True
