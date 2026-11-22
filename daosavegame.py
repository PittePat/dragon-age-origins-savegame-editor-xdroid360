#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dragon Age Origins Savegame Editor for XDroid360.

Python 3 / wxPython 4 port of the savegame editor from pygff 1.0
(original by William Clark, savegame editor by Mephales) for Linux.
"""
import os
import sys
import zlib
import struct
import zipfile
from io import BytesIO
from functools import partial
from traceback import print_exc

import wx
import wx.dataview
import wx.lib.delayedresult as delayedresult
from wx.lib.mixins.listctrl import TextEditMixin, ColumnSorterMixin

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

from gff4 import *
from gff4.lazy import LazyGFF4
from gff4.datoolset_fields import *
from savezip import find_saves, read_member, replace_in_zip, format_seconds
from saveinfo import quest_entries, location_info, player_is_female
from tlk import TalkTable, plain_text
from settings import load_talktable, remember_talk_files
from abilities import (AbilityModel, current_class, class_change_plan, change_class, CLASS_TITLES, POINT_STATS, KIND_TITLE, KIND_LABEL, stat_value, set_point_stat,
                       add_stat_property)

_resdir = os.path.join(_here, 'gff4')

def selectedIndices(lst, i=-1):
    """Indices of the selected rows of a list control."""
    if i < 0:
        i = lst.GetFirstSelected()
    while i >= 0:
        yield i
        i = lst.GetNextSelected(i)

VERSION = "0.5"          # program version (shown in the About dialog)
VERSION_DAO = 1

def _read_lines(name):
    with open(os.path.join(_resdir, name), encoding='utf-8') as f:
        return [line.strip() for line in f]

_attribute_names = [line.split(',') for line in _read_lines('StatPropertyNames.txt')]
_resrefnames = dict(line.split(None, 1) for line in _read_lines('ResRefNames.txt') if line)

def update_checksum_file(path):
    """XDroid360 (Xenia based) stores the CRC32 of every file, big-endian, in '<file>.x'.
    If such a companion file exists it must be refreshed after the file was changed,
    otherwise the game reports the savegame as corrupt. Returns the new CRC or None."""
    xfile = path + '.x'
    if not os.path.exists(xfile):
        return None
    with open(path, 'rb') as f:
        crc = zlib.crc32(f.read()) & 0xFFFFFFFF
    with open(xfile, 'wb') as f:
        f.write(struct.pack('>I', crc))
    return crc

import re as _re

_RESREF_RE = _re.compile(r'^[A-Za-z0-9_]+$')

def format_playtime(root):
    """The play time stored in the savegame (read-only), e.g. '12 h 05 min 31 s  (43531 seconds)'."""
    try:
        seconds = int(float(root[SAVEGAME_PLAYERCHAR][SAVEGAME_PLAYER_TIME_PLAYED]))
    except (KeyError, TypeError, ValueError):
        return "unknown"
    return "%d h %02d min %02d s  (%d seconds)" % (seconds // 3600, (seconds // 60) % 60, seconds % 60, seconds)

def _fit_string(old, new):
    """Strings of V4.0 (PC) files carry a trailing NUL; keep whatever convention the old value used."""
    new = new.strip().strip('\0')
    return new + '\0' if old.endswith('\0') else new

def describe_fields(row):
    """Every field of a structure as (label, name, typename, text, editable)."""
    out = []
    for field in row.fields:
        label = field.label
        try:
            value = row[label]
        except Exception:
            continue
        name = str(get_field_name(label))
        editable = False
        if isinstance(value, bytes):
            text = 'Binary (%d bytes)' % len(value)
        elif isinstance(value, str):
            text, editable = value.strip('\0'), True
        elif isinstance(value, (int, float)):
            text, editable = str(value), True
        elif isinstance(value, tuple):
            text = repr(value)
        elif hasattr(value, 'fields'):
            text = 'Struct %s' % getattr(value, 'fourcc', '?')
        elif hasattr(value, '__len__'):
            text = 'List (%d entries)' % len(value)
        else:
            text = repr(value)
        out.append((label, name, type(value).__name__.replace('Lazy', ''), text, editable))
    return out

def apply_field_texts(row, texts):
    """Writes {label: text} into a structure. Returns (changed_labels, [(label, text, error)])."""
    changed, errors = [], []
    for label, text in texts.items():
        old = row[label]
        try:
            if isinstance(old, str):
                new = type(old)(_fit_string(old, text))
            else:
                new = type(old)(text.strip())
        except (ValueError, TypeError, OverflowError) as ex:
            errors.append((label, text, str(ex)))
            continue
        if new != old:
            row[label] = new
            changed.append(label)
    return changed, errors

def filter_known_items(names, text, limit=400):
    """Entries (resref, name) of a resref->name mapping containing all words of text."""
    words = text.lower().split()
    result = []
    for resref in sorted(names):
        hay = (resref + ' ' + names[resref]).lower()
        if all(w in hay for w in words):
            result.append((resref, names[resref]))
            if len(result) >= limit:
                break
    return result

class _ValueEditList(wx.ListCtrl, TextEditMixin):
    """Plain list whose 'Value' column (3) can be edited in place for the rows marked editable."""
    def __init__(self, parent):
        wx.ListCtrl.__init__(self, parent, style=wx.LC_REPORT | wx.LC_HRULES | wx.LC_VRULES | wx.LC_SINGLE_SEL)
        self.editable = []
        TextEditMixin.__init__(self)
        self.Bind(wx.EVT_LIST_BEGIN_LABEL_EDIT, self.OnBeginEdit)
    
    def OnBeginEdit(self, event):
        row, column = event.GetIndex(), event.GetColumn()
        if column != 3 or not (0 <= row < len(self.editable)) or not self.editable[row]:
            event.Veto()

class ItemFieldsDialog(wx.Dialog):
    """Shows every field of an item; scalar fields (numbers, text) can be edited."""
    def __init__(self, parent, row, title):
        super(ItemFieldsDialog, self).__init__(parent, title=title, size=(760, 560),
                                               style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.result = {}
        self.fields = describe_fields(row)
        
        hint = wx.StaticText(self, label="Click a selected value to edit it. Grey rows are lists/structures "
                                         "and cannot be edited here.")
        self.list = _ValueEditList(self)
        self.list.InsertColumn(0, "Id", wx.LIST_FORMAT_LEFT, 60)
        self.list.InsertColumn(1, "Field", wx.LIST_FORMAT_LEFT, 250)
        self.list.InsertColumn(2, "Type", wx.LIST_FORMAT_LEFT, 90)
        self.list.InsertColumn(3, "Value", wx.LIST_FORMAT_LEFT, 280)
        for i, (label, name, typename, text, editable) in enumerate(self.fields):
            self.list.InsertItem(i, str(label))
            self.list.SetItem(i, 1, name)
            self.list.SetItem(i, 2, typename)
            self.list.SetItem(i, 3, text)
            self.list.editable.append(editable)
            if not editable:
                self.list.SetItemTextColour(i, wx.Colour(130, 130, 130))
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(hint, 0, wx.ALL, 5)
        sizer.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        sizer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(sizer)
    
    def ShowModal(self):
        result = super(ItemFieldsDialog, self).ShowModal()
        if result == wx.ID_OK:
            for i, (label, name, typename, text, editable) in enumerate(self.fields):
                if editable:
                    new = self.list.GetItem(i, 3).GetText()
                    if new != text:
                        self.result[label] = new
        return result

class ItemPickerDialog(wx.Dialog):
    """Searchable list of the item/resource names known to the editor."""
    def __init__(self, parent, names):
        super(ItemPickerDialog, self).__init__(parent, title="Pick an item", size=(640, 520),
                                               style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.names = names
        self.shown = []
        self.selected_resref = None
        
        self.filter = wx.TextCtrl(self)
        self.info = wx.StaticText(self, label="")
        self.list = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.list.InsertColumn(0, "ResRef", wx.LIST_FORMAT_LEFT, 260)
        self.list.InsertColumn(1, "Name", wx.LIST_FORMAT_LEFT, 320)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(self, label="Type part of a name or resref (e.g. 'ring', 'staff', 'cold'):"), 0, wx.ALL, 5)
        sizer.Add(self.filter, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        sizer.Add(self.info, 0, wx.ALL, 5)
        sizer.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        sizer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(sizer)
        
        self.filter.Bind(wx.EVT_TEXT, self.OnFilter)
        self.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnActivate)
        self.Refresh_()
    
    def Refresh_(self):
        self.shown = filter_known_items(self.names, self.filter.GetValue())
        self.list.DeleteAllItems()
        for i, (resref, name) in enumerate(self.shown):
            self.list.InsertItem(i, resref)
            self.list.SetItem(i, 1, name)
        self.info.SetLabel("%d match(es) shown%s" % (len(self.shown), " (limit reached - refine the search)" if len(self.shown) >= 400 else ""))
    
    def OnFilter(self, event):
        self.Refresh_()
    
    def OnActivate(self, event):
        self.selected_resref = self.shown[event.GetIndex()][0]
        self.EndModal(wx.ID_OK)
    
    def ShowModal(self):
        result = super(ItemPickerDialog, self).ShowModal()
        if result == wx.ID_OK and self.selected_resref is None:
            i = self.list.GetFirstSelected()
            self.selected_resref = self.shown[i][0] if 0 <= i < len(self.shown) else None
        return result


class InventoryPanel(wx.Panel):
    def __init__(self, *args, **kwargs):
        super(InventoryPanel, self).__init__(*args, **kwargs)
        self.sizer = wx.FlexGridSizer(3)
        text_flag = wx.TOP|wx.LEFT|wx.RIGHT|wx.ALL|wx.ALIGN_RIGHT|wx.ALIGN_CENTRE_VERTICAL
        item_flag = wx.GROW|wx.ALIGN_CENTER_VERTICAL|wx.LEFT|wx.RIGHT|wx.TOP
        
        self.sizer.Add(wx.StaticText(self, label="Money"), border=5, flag=text_flag)
        
        self.money = wx.SpinCtrl(self, max=999999999)
        self.sizer.Add(self.money, border=5, flag=item_flag)
        
        self.maxmoney = wx.Button(self, label='Max')
        self.sizer.Add(self.maxmoney, border=5, flag=item_flag)
        
        self.sizer.Add(wx.StaticText(self, label="Max Weight"), border=5, flag=text_flag)
        
        self.capacity = wx.SpinCtrl(self, max=999999999)
        self.sizer.Add(self.capacity, border=5, flag=item_flag)
        
        self.maxcapacity = wx.Button(self, label='Max')
        self.sizer.Add(self.maxcapacity, border=5, flag=item_flag)
        
        self.sizer.Add(wx.StaticText(self, label="Play time"), border=5, flag=text_flag)
        
        self.playtime = wx.StaticText(self, label="")
        self.sizer.Add(self.playtime, border=5, flag=item_flag)
        self.sizer.Add((0, 0))
        
        self.SetSizer(self.sizer)
        
        self.Bind(wx.EVT_BUTTON, lambda e: self.money.SetValue(self.money.GetMax()), self.maxmoney)
        self.Bind(wx.EVT_BUTTON, lambda e: self.capacity.SetValue(self.capacity.GetMax()), self.maxcapacity)
    
    def save(self):
        changed = False
        value = INT32(self.money.GetValue())
        if self.data[SAVEGAME_MONEY] != value:
            self.data[SAVEGAME_MONEY] = value
            changed = True
        value = INT32(self.capacity.GetValue())
        if self.data[SAVEGAME_MAX_ITEMS] != value:
            self.data[SAVEGAME_MAX_ITEMS] = value
            changed = True
        return changed
    
    def load(self, data, root, game_version=VERSION_DAO):
        self.data = data
        self.money.SetValue(int(data[SAVEGAME_MONEY]))
        self.capacity.SetValue(int(data[SAVEGAME_MAX_ITEMS]))
        self.playtime.SetLabel(format_playtime(root))

class ItemList(wx.ListCtrl, TextEditMixin, ColumnSorterMixin):
    structural = True           # offer Duplicate / Move Item (not for lists with a fixed number of slots)
    last_column = "16238"
    
    def __init__(self, *args, **kwargs):
        kwargs['style'] = wx.LC_REPORT|wx.LC_VIRTUAL|wx.LC_HRULES|wx.LC_VRULES
        wx.ListCtrl.__init__(self, *args, **kwargs)
        
        self.changed = False
        
        self.InsertColumn(0, "ResRef", wx.LIST_FORMAT_CENTRE, 200)
        self.InsertColumn(1, "Name", wx.LIST_FORMAT_CENTRE, 200)
        self.InsertColumn(2, "Count", wx.LIST_FORMAT_CENTRE, 50)
        self.InsertColumn(3, "Infinite", wx.LIST_FORMAT_CENTRE, 50)
        self.InsertColumn(4, "Plot", wx.LIST_FORMAT_CENTRE, 50)
        self.InsertColumn(5, self.last_column, wx.LIST_FORMAT_CENTRE, 50)
        
        TextEditMixin.__init__(self)
        
        self.itemDataMap = []
        self.itemIndexMap = []
        
        ColumnSorterMixin.__init__(self, 6)
        
        self.context_menu = wx.Menu()
        if self.structural:
            dupeitem = self.context_menu.Append(wx.ID_ANY, 'Duplicate')
            moveitem = self.context_menu.Append(wx.ID_ANY, 'Move Item', 'Move selected items to a different inventory')
            self.context_menu.AppendSeparator()
        fielditem = self.context_menu.Append(wx.ID_ANY, 'Edit All Fields...', 'Edit every number/text field of the selected item')
        pickitem = self.context_menu.Append(wx.ID_ANY, 'Pick Item from List...', 'Change the ResRef of the selected items to a known item')
        
        self.Bind(wx.EVT_LIST_BEGIN_LABEL_EDIT, self.OnBeginEdit)
        self.Bind(wx.EVT_CONTEXT_MENU, lambda event: self.PopupMenu(self.context_menu))
        if self.structural:
            self.Bind(wx.EVT_MENU, self.OnDupeItem, dupeitem)
            self.Bind(wx.EVT_MENU, self.OnMoveItem, moveitem)
        self.Bind(wx.EVT_MENU, self.OnEditFields, fielditem)
        self.Bind(wx.EVT_MENU, self.OnPickItem, pickitem)
    
    def DuplicateRow(self, index):
        """Appends a copy (with a fresh object id) of the item at data index. Returns the new data index."""
        # not a deep clone, but doesn't need to be
        row = self.data[index]
        cop = type(row)(row)
        self.wdbe[SAVEGAME_WORLDDB_LASTID] += 1
        cop[OBJECT_ID] = self.wdbe[SAVEGAME_WORLDDB_LASTID]
        self.AppendItem(cop)
        self.changed = True
        return len(self.data) - 1
    
    def OnDupeItem(self, event):
        for index in list(selectedIndices(self)):
            self.DuplicateRow(self.itemIndexMap[index])
    
    def UpdateRow(self, index):
        """Refreshes the cached sort data and the display of the item at data index."""
        self.itemDataMap[index] = self.GetRowText(self.data[index])
        if index in self.itemIndexMap:
            self.RefreshItem(self.itemIndexMap.index(index))
        self.changed = True
    
    def SetResRef(self, index, text):
        """Changes the template resref of the item at data index. Returns False for an invalid resref."""
        text = text.strip().strip('\0')
        if not _RESREF_RE.match(text):
            return False
        row = self.data[index]
        old = row[TEMPLATERESREF]
        row[TEMPLATERESREF] = type(old)(_fit_string(old, text))
        self.UpdateRow(index)
        return True
    
    def OnEditFields(self, event):
        selected = list(selectedIndices(self))
        if not selected:
            return
        index = self.itemIndexMap[selected[0]]
        row = self.data[index]
        title = "Edit item: %s" % row[TEMPLATERESREF].strip('\0')
        with ItemFieldsDialog(self, row, title) as dlg:
            if dlg.ShowModal() != wx.ID_OK or not dlg.result:
                return
            texts = dlg.result
        changed, errors = apply_field_texts(row, texts)
        self.UpdateRow(index)
        if errors:
            wx.MessageBox("These values were not accepted:\n\n" +
                          "\n".join("%s = %r (%s)" % (get_field_name(l), t, e) for l, t, e in errors),
                          "Edit item", wx.OK | wx.ICON_WARNING, self)
    
    def OnPickItem(self, event):
        selected = list(selectedIndices(self))
        if not selected:
            return
        # known names plus every resref that already exists in this savegame's inventories
        names = dict(self.resrefnames)
        for inv in getattr(self, 'inventories', {}).values():
            for item in (inv.data or ()):
                names.setdefault(item[TEMPLATERESREF].strip('\0'), '(in this save)')
        with ItemPickerDialog(self, names) as dlg:
            if dlg.ShowModal() != wx.ID_OK or not dlg.selected_resref:
                return
            resref = dlg.selected_resref
        for v in selected:
            self.SetResRef(self.itemIndexMap[v], resref)
    
    def AppendItem(self, item):
        if self.data:
            item[POSITION] = item[POSITION]._replace(a=self.data[-1][POSITION].a+1)
        else:
            item[POSITION] = item[POSITION]._replace(a=0.)
        index = len(self.data)
        self.itemIndexMap.append(index)
        self.itemDataMap.append(self.GetRowText(item))
        self.data.append(item)
        self.SetItemCount(len(self.data))
        self.RefreshItem(index)
        self.changed = True
    
    def OnMoveItem(self, event):
        selected = list(selectedIndices(self))
        if not selected:
            return
        names = sorted(k for k, v in self.inventories.items() if v != self and v.data != self.data)
        if not names:
            return
        
        with wx.SingleChoiceDialog(self, "Choose destination inventory", "Choose Inventory", names) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            item_list = self.inventories[names[dlg.GetSelection()]]
        
        removed = sorted(set(self.itemIndexMap[v] for v in selected))
        rows = [self.data[i] for i in removed]
        for v in selected:
            self.Select(v, False)
        for index in reversed(removed):
            del self.data[index]
            del self.itemDataMap[index]
        removed_set = set(removed)
        self.itemIndexMap = [n - sum(1 for r in removed if r < n)
                             for n in self.itemIndexMap if n not in removed_set]
        self.SetItemCount(len(self.data))
        self.Refresh()
        self.changed = True
        for row in rows:
            item_list.AppendItem(row)
    
    def save(self):
        return self.changed
    
    def load(self, data, root, game_version=VERSION_DAO):
        self.DeleteAllItems()
        del self.itemDataMap[:]
        del self.itemIndexMap[:]
        
        self.data = data
        self.root = root
        
        self.resrefnames = _resrefnames
        
        self.wdbe = next(x for x in self.root[SAVEGAME_WORLDDATABASE] if x[SAVEGAME_WORLDDB_IDGROUP] == 0)
        
        self.itemDataMap = [self.GetRowText(row) for row in self.data]
        self.itemIndexMap = list(range(len(self.data)))
        self.SetItemCount(len(data))
        self.changed = False
    
    def reset(self):
        self.DeleteAllItems()
        self.itemDataMap = []
        self.itemIndexMap = []
        self.data = None
        self.root = None
        self.changed = False
    
    def OnGetItemText(self, index, column):
        index = self.itemIndexMap[index]
        row = self.data[index]
        if not column:
            return row[TEMPLATERESREF].strip('\0')
        elif column == 1:
            return self.resrefnames.get(row[TEMPLATERESREF].strip('\0'), '')
        elif column == 2:
            return str(row[ITEM_STACKSIZE])
        elif column == 3:
            return str(row[SAVEGAME_ITEM_INFINITE])
        elif column == 4:
            return str(row[SAVEGAME_OBJECT_PLOT])
        elif column == 5:
            return str(row.get(16238, ''))
        return ''
    
    def GetRowText(self, row):
        resref = row[TEMPLATERESREF].strip('\0')
        return [
            resref,
            self.resrefnames.get(resref, ''),
            row[ITEM_STACKSIZE],
            row[SAVEGAME_ITEM_INFINITE],
            row[SAVEGAME_OBJECT_PLOT],
            row.get(16238, -1),
        ]
    
    def SetVirtualData(self, index, column, s):
        index = self.itemIndexMap[index]
        row = self.data[index]
        
        try:
            if column == 0:
                if not self.SetResRef(index, s):
                    wx.Bell()
                return
            elif column == 2:
                row[ITEM_STACKSIZE] = s
                self.itemDataMap[index][2] = row[ITEM_STACKSIZE]
            elif column == 3:
                row[SAVEGAME_ITEM_INFINITE] = s
                self.itemDataMap[index][3] = row[SAVEGAME_ITEM_INFINITE]
        except (ValueError, TypeError):
            wx.Bell()
            return
        self.changed = True
    
    def OnBeginEdit(self, event):
        index, column = event.GetIndex(), event.GetColumn()
        if column not in (0, 2, 3):
            event.Veto()
    
    def SortItems(self, sorter=None):
        col = getattr(self, '_col', 0)
        ascending = bool(self._colSortFlag[col]) if hasattr(self, '_colSortFlag') else True
        def key(i):
            v = self.itemDataMap[i][col]
            return (1, str(v).lower()) if isinstance(v, str) else (0, v)
        self.itemIndexMap = sorted(range(len(self.data)), key=key, reverse=not ascending)
        self.Refresh()

    def GetListCtrl(self):
        return self

class CreatureStatsList(wx.ListCtrl, TextEditMixin):
    def __init__(self, *args, **kwargs):
        kwargs['style'] = wx.LC_REPORT|wx.LC_VIRTUAL|wx.LC_HRULES|wx.LC_VRULES
        wx.ListCtrl.__init__(self, *args, **kwargs)
        
        self.changed = False
        
        self.InsertColumn(0, "Id", wx.LIST_FORMAT_CENTRE, 25)
        self.InsertColumn(1, "Name", wx.LIST_FORMAT_CENTRE, 180)
        self.InsertColumn(2, "Base", wx.LIST_FORMAT_CENTRE)
        self.InsertColumn(3, "Modifier", wx.LIST_FORMAT_CENTRE)
        self.InsertColumn(4, "Current", wx.LIST_FORMAT_CENTRE)
        self.InsertColumn(5, "Regen", wx.LIST_FORMAT_CENTRE)
        self.InsertColumn(6, "Combat Regen", wx.LIST_FORMAT_CENTRE)
        
        TextEditMixin.__init__(self)
        
        self.context_menu = wx.Menu()
        addpropitem = self.context_menu.Append(wx.ID_ANY, 'Add Known Attribute', 'Add an attribute the editor knows by name (e.g. resistances)')
        addidxitem = self.context_menu.Append(wx.ID_ANY, 'Add Attribute by Index...', 'Add an attribute by its numeric property index')
        self.SetToolTip('Right-click for "Add Known Attribute" (resistances etc.)')
        
        self.Bind(wx.EVT_LIST_BEGIN_LABEL_EDIT, self.OnBeginEdit)
        self.Bind(wx.EVT_CONTEXT_MENU, lambda event: self.PopupMenu(self.context_menu))
        self.Bind(wx.EVT_MENU, self.OnAddProperty, addpropitem)
        self.Bind(wx.EVT_MENU, self.OnAddPropertyByIndex, addidxitem)
    
    def save(self):
        return self.changed
    
    def load(self, data, root, game_version=VERSION_DAO):
        self.data = data
        self.root = root
        self.SetItemCount(len(data))
        self._attribute_names = _attribute_names
        self.changed = False
    
    def OnGetItemText(self, index, column):
        if column != 1:
            data = self.data[index]
            id = self._column2id[column]
            if id in data:
                return str(data[id])
        else:
            data = self.data[index]
            id = data[SAVEGAME_STATPROPERTY_INDEX]
            if 0 < id and id <= len(self._attribute_names):
                name = self._attribute_names[id-1][0]
                if name is not None:
                    return name
            return 'Property %d' % id
        return ''
    
    def SetVirtualData(self, index, column, s):
        data = self.data[index]
        id = self._column2id[column]
        if id in data:
            try:
                data[id] = type(data[id])(s)
            except (ValueError, TypeError):
                wx.Bell()
                return
        self.changed = True
    
    def OnBeginEdit(self, event):
        index, column = event.GetIndex(), event.GetColumn()
        if column <= 1:
            event.Veto()
        else:
            data = self.data[index]
            id = self._column2id[column]
            if id not in data:
                event.Veto()
    
    _column2id = [
        SAVEGAME_STATPROPERTY_INDEX, 
        None, 
        SAVEGAME_STATPROPERTY_BASE, 
        SAVEGAME_STATPROPERTY_MODIFIER, 
        SAVEGAME_STATPROPERTY_CURRENT, 
        SAVEGAME_STATPROPERTY_REGEN, 
        SAVEGAME_STATPROPERTY_COMREGEN]
    
    def OnAddProperty(self, event):
        existing = set(attr[SAVEGAME_STATPROPERTY_INDEX] - 1 for attr in self.data)
        properties = sorted(attr[0] for i, attr in enumerate(self._attribute_names) if i not in existing)
        
        with wx.SingleChoiceDialog(self, "Choose a standard attribute", "Choose Attribute", properties) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            propname = properties[dlg.GetSelection()]
        
        for i, attr in enumerate(self._attribute_names):
            if attr[0] == propname:
                self.AddProperty(i + 1, attr[1])
                break
    
    def AddProperty(self, index, fourcc='ATTR'):
        """Appends a new attribute (property index, 1-based) with all values zero. Returns the new row."""
        item = add_stat_property(self.root, self.data, index, fourcc)
        row = len(self.data) - 1
        self.SetItemCount(len(self.data))
        self.RefreshItem(row)
        self.changed = True
        return item
    
    def OnAddPropertyByIndex(self, event):
        index = wx.GetNumberFromUser("Numeric property index (1-based) to add to this character.\n"
                                     "Indices 1-%d are known to the editor." % len(self._attribute_names),
                                     "Index:", "Add Attribute by Index", 1, 1, 255, self)
        if index < 1:
            return
        if any(attr[SAVEGAME_STATPROPERTY_INDEX] == index for attr in self.data):
            wx.MessageBox("This character already has property %d." % index, "Add Attribute",
                          wx.OK | wx.ICON_INFORMATION, self)
            return
        if index <= len(self._attribute_names):
            fourcc = self._attribute_names[index - 1][1]
        else:
            answer = wx.MessageBox("Property %d is not known to this editor. It will be added as a plain "
                                   "attribute, and the game may ignore it or even reject the savegame.\n\n"
                                   "Add it anyway?" % index, "Unknown property",
                                   wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self)
            if answer != wx.YES:
                return
            fourcc = 'ATTR'
        self.AddProperty(index, fourcc)

class PartyPanel(wx.Panel):
    def __init__(self, *args, **kwargs):
        super(PartyPanel, self).__init__(*args, **kwargs)
        
    def load(self, data, root, game_version=VERSION_DAO):
        self.data = data
        
        resrefnames = _resrefnames
        
        self.ids2name = {}
        for crl1 in (data[SAVEGAME_PARTYPOOLMEMBERS] or ()):
            name = crl1[SAVEGAME_OBJECT_NAME].s
            if not name:
                resref = name = crl1[3].strip('\0')
                name = resrefnames.get(resref, resref)
            else:
                name = name.strip('\0')
            self.ids2name[crl1[OBJECT_ID]] = name
        
        text_flag = wx.TOP|wx.LEFT|wx.RIGHT|wx.ALL|wx.ALIGN_RIGHT|wx.ALIGN_CENTRE_VERTICAL
        item_flag = wx.GROW|wx.ALIGN_CENTER_VERTICAL|wx.LEFT|wx.RIGHT|wx.TOP
        
        self.sizer = wx.FlexGridSizer(4)
        self.approval = {}
        self.buttons = {}
        
        for aprv in (data[SAVEGAME_PARTY_APPROVAL_LIST] or ()):
            id = aprv[SAVEGAME_PARTY_APPROVAL_ID]
            level = aprv[SAVEGAME_PARTY_APPROVAL_LEVEL]
            name = self.ids2name.get(id, 'Unknown%d'%id)
            
            self.sizer.Add(wx.StaticText(self, label="%s's Approval"%name), border=5, flag=text_flag)
            
            self.approval[id] = wx.SpinCtrl(self, max=100, min=-100, initial=int(level))
            self.sizer.Add(self.approval[id], border=5, flag=item_flag)
            
            maxbutton = wx.Button(self, label='Max')
            self.buttons[maxbutton] = self.approval[id]
            self.sizer.Add(maxbutton, border=5, flag=item_flag)
            self.Bind(wx.EVT_BUTTON, self.OnMaxSpin, maxbutton)
            
            minbutton = wx.Button(self, label='Min')
            self.buttons[minbutton] = self.approval[id]
            self.sizer.Add(minbutton, border=5, flag=item_flag)
            self.Bind(wx.EVT_BUTTON, self.OnMinSpin, minbutton)
            
        self.SetSizer(self.sizer)
    
    def OnMaxSpin(self, event):
        spin = self.buttons[event.GetEventObject()]
        spin.SetValue(spin.GetMax())
    
    def OnMinSpin(self, event):
        spin = self.buttons[event.GetEventObject()]
        spin.SetValue(spin.GetMin())
    
    def save(self):
        changed = False
        for aprv in self.data[SAVEGAME_PARTY_APPROVAL_LIST]:
            id = aprv[SAVEGAME_PARTY_APPROVAL_ID]
            spin = self.approval[id]
            value = INT32(spin.GetValue())
            if aprv[SAVEGAME_PARTY_APPROVAL_LEVEL] != value:
                aprv[SAVEGAME_PARTY_APPROVAL_LEVEL] = value
                changed = True
        return changed

class AreaInventoryPanel(wx.Panel):
    _choices = [
        'Placeables',
        'Stores',
        'Creature\'s Equipment',
        'Creature\'s Backpack',
        'Creature\'s Plot Items',
    ]
    
    def __init__(self, *args, **kwargs):
        super(AreaInventoryPanel, self).__init__(*args, **kwargs)
        self.arealist = wx.ListCtrl(self, style=wx.LC_REPORT|wx.LC_SINGLE_SEL)
        self.arealist.InsertColumn(0, "Name", wx.LIST_FORMAT_LEFT, 150)
        self.arealist.InsertColumn(1, "Resref", wx.LIST_FORMAT_LEFT, 150)
        self.types = wx.ComboBox(self, choices=self._choices, style=wx.CB_READONLY)
        self.containers = wx.ListCtrl(self, style=wx.LC_REPORT|wx.LC_SINGLE_SEL)
        self.containers.InsertColumn(0, "#", wx.LIST_FORMAT_RIGHT, 25)
        self.containers.InsertColumn(1, "Name", wx.LIST_FORMAT_LEFT, 150)
        self.containers.InsertColumn(2, "Resref", wx.LIST_FORMAT_LEFT, 150)
        self.show_empty = wx.CheckBox(self, label="Show empty containers")
        self.itemlist = ItemList(self)
        
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.arealist, 1, wx.EXPAND)
        sizer2 = wx.BoxSizer(wx.VERTICAL)
        sizer2.Add(self.types, 0, wx.EXPAND)
        sizer2.Add(self.containers, 1, wx.EXPAND)
        sizer2.Add(self.show_empty, 0, wx.EXPAND)
        sizer.Add(sizer2, 1, wx.EXPAND)
        sizer.Add(self.itemlist, 3, wx.EXPAND)
        self.SetSizer(sizer)
        
        self.arealist.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnAreaSelect)
        self.types.Bind(wx.EVT_COMBOBOX, self.OnTypeSelect)
        self.containers.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnContainerSelect)
        self.show_empty.Bind(wx.EVT_CHECKBOX, self.OnShowEmpty)
        
        self.areacont = None
        self.area = None
        self.container = None
        self.area_changed = False
        self.changed = False
    
    @property
    def inventories(self):
        return self.itemlist.inventories
    
    @inventories.setter
    def inventories(self, value):
        self.itemlist.inventories = value
    
    def save(self):
        if self.itemlist.save():
            self.area_changed = True
        if self.area_changed:
            if self.areacont:
                arec, areg = self.areacont
                temp = BytesIO()
                areg.tofile(temp)
                temp.seek(0)
                data = temp.read()
                arec[16022] = len(data)
                data = Binary(zlib.compress(data))
                arec[16021] = data
            self.changed = True
        return self.changed
    
    def load(self, data, root, game_version=VERSION_DAO):
        self.arealist.DeleteAllItems()
        self.containers.DeleteAllItems()
        self.itemlist.reset()
        self.data = data
        self.root = root
        self.game_version = game_version
        list = self.arealist
        for area in data:
            resref = area[TAG].strip('\0')
            name = _resrefnames.get(resref)
            list.Append([name or '', resref])
        
        self.area = None
        self.areacont = None
        self.container = None
        self.area_changed = False
        self.changed = False
    
    def OnAreaSelect(self, event):
        self.save()
        
        tag = self.arealist.GetItem(event.Index, 1).Text
        area = self.data[event.Index]
        assert area[TAG].strip('\0') == tag
        
        if area.fourcc == 'AREC':
            g = LazyGFF4(BytesIO(zlib.decompress(area[16021])))
            self.areacont = (area, g)
            self.area = g.root[16023]
        else:
            self.area = area
        
        self.area_changed = False
        self.RefreshContainerList()
    
    def OnTypeSelect(self, event):
        self.RefreshContainerList()
    
    def OnShowEmpty(self, event):
        self.RefreshContainerList()
    
    def OnContainerSelect(self, event):
        if self.itemlist.save():
            self.area_changed = True
        
        self.itemlist.load(self.shown_containers[event.Index], self.root, self.game_version)
    
    def RefreshContainerList(self):
        self.containers.DeleteAllItems()
        self.itemlist.reset()
        
        area = self.area
        type = self.types.GetValue()
        if not area or not type:
            return
        
        show_all = self.show_empty.IsChecked()
        list = self.containers
        
        resrefnames = _resrefnames
        shown_containers = []
        
        if type == 'Stores':
            def generator():
                for c in area[SAVEGAME_AREA_STORES]:
                    yield c[TEMPLATERESREF], c[SAVEGAME_STORE_ITEMLIST]
        elif type == 'Placeables':
            def generator():
                for c in area[SAVEGAME_AREA_PLACEABLES]:
                    yield c[TEMPLATERESREF], c[SAVEGAME_ITEMS]
        elif type == 'Creature\'s Equipment':
            def generator():
                for c in area[SAVEGAME_AREA_CREATURES]:
                    yield c[TEMPLATERESREF], c[SAVEGAME_EQUIPMENT_ITEMS]
        elif type == 'Creature\'s Backpack':
            def generator():
                for c in area[SAVEGAME_AREA_CREATURES]:
                    yield c[TEMPLATERESREF], c[SAVEGAME_BACKPACK]
        elif type == 'Creature\'s Plot Items':
            def generator():
                for c in area[SAVEGAME_AREA_CREATURES]:
                    yield c[TEMPLATERESREF], c[SAVEGAME_PLOTITEMS]
        
        # ALSO: player character/party pool member equipment/backpack/plotitems
        
        for resref, items in generator():
            itemcount = len(items)
            if show_all or itemcount:
                resref = resref.strip('\0')
                name = resrefnames.get(resref, resref)
                list.Append([str(itemcount), name or '', resref])
                shown_containers.append(items)
        
        self.shown_containers = shown_containers
    
class PointsPanel(wx.Panel):
    """Unspent attribute / skill / talent / specialization points of one character."""
    def __init__(self, parent):
        super(PointsPanel, self).__init__(parent)
        self.changed = False
        self.character = None
        self.spins = {}
        self._shown = {}
    
    def load(self, character, name):
        """character: the CreatureStatsList of this character (shares its stat list)."""
        self.character = character
        data = character.data
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(self, label="Unspent points of %s" % name), 0, wx.ALL, 10)
        grid = wx.FlexGridSizer(3, 8, 8)
        for index, label, hint in POINT_STATS:
            value = int(stat_value(data, index))
            grid.Add(wx.StaticText(self, label=label), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)
            spin = wx.SpinCtrl(self, min=0, max=max(999, value), initial=value)
            self.spins[index] = spin
            self._shown[index] = value
            grid.Add(spin, 0)
            grid.Add(wx.StaticText(self, label=hint), 0, wx.ALIGN_CENTER_VERTICAL)
            spin.Bind(wx.EVT_SPINCTRL, self.OnChange)
            spin.Bind(wx.EVT_TEXT, self.OnChange)
        sizer.Add(grid, 0, wx.ALL, 5)
        
        info = "Level %d, experience %d" % (stat_value(data, 15), stat_value(data, 19))
        sizer.Add(wx.StaticText(self, label=info), 0, wx.ALL, 10)
        sizer.Add(wx.StaticText(self, label="The points are applied when you save the savegame. "
                                            "Entries that do not exist yet are created automatically."), 0, wx.ALL, 10)
        self.SetSizer(sizer)
    
    def OnChange(self, event):
        self.Apply()
        event.Skip()
    
    def Apply(self):
        for index, spin in self.spins.items():
            value = spin.GetValue()
            if value == self._shown[index]:
                continue
            if set_point_stat(self.character.root, self.character.data, index, value):
                self.character.SetItemCount(len(self.character.data))
                self.character.Refresh()
                self.character.changed = True
            self._shown[index] = value
            self.changed = True
    
    def save(self):
        if self.character is not None:
            self.Apply()
        return self.changed

class AbilitiesPanel(wx.Panel):
    """Spells, talents, skills and specializations of one character: tick = learned."""
    KINDS = [None, 'spell', 'talent', 'skill', 'trait']
    
    def __init__(self, parent):
        super(AbilitiesPanel, self).__init__(parent)
        self.changed = False
        self.model = None
        self.shown = []
        
        self.search = wx.TextCtrl(self)
        self.kind = wx.Choice(self, choices=["All types", "Spells (mage)", "Talents (warrior/rogue)", "Skills",
                                             "Immunities (experimental)"])
        self.kind.SetSelection(0)
        self.only_learned = wx.CheckBox(self, label="Learned only")
        self.add_button = wx.Button(self, label="Add by ID...")
        self.class_button = wx.Button(self, label="Change class (experimental)...")
        
        self.list = wx.dataview.DataViewListCtrl(self, style=wx.dataview.DV_ROW_LINES | wx.dataview.DV_SINGLE)
        self.list.AppendToggleColumn("Learned", mode=wx.dataview.DATAVIEW_CELL_ACTIVATABLE, width=70)
        self.list.AppendTextColumn("Name", width=250)
        self.list.AppendTextColumn("Group", width=250)
        self.list.AppendTextColumn("Type", width=120)
        self.list.AppendTextColumn("ID", width=70)
        
        bar = wx.BoxSizer(wx.HORIZONTAL)
        bar.Add(wx.StaticText(self, label="Search:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        bar.Add(self.search, 1, wx.RIGHT, 10)
        bar.Add(self.kind, 0, wx.RIGHT, 10)
        bar.Add(self.only_learned, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        bar.Add(self.add_button, 0, wx.RIGHT, 10)
        bar.Add(self.class_button, 0)
        
        self.title = wx.StaticText(self, label="")
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.title, 0, wx.ALL, 8)
        sizer.Add(bar, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        sizer.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.SetSizer(sizer)
        
        self.search.Bind(wx.EVT_TEXT, self.OnFilter)
        self.kind.Bind(wx.EVT_CHOICE, self.OnFilter)
        self.only_learned.Bind(wx.EVT_CHECKBOX, self.OnFilter)
        self.add_button.Bind(wx.EVT_BUTTON, self.OnAddById)
        self.class_button.Bind(wx.EVT_BUTTON, self.OnChangeClass)
        self.list.Bind(wx.dataview.EVT_DATAVIEW_ITEM_VALUE_CHANGED, self.OnToggle)
    
    def load(self, stats, name, allow_class_change=False):
        """stats: the creature's CPS1 structure. The class can only be changed for the player character."""
        self.model = AbilityModel(stats)
        self.class_button.Show(allow_class_change)
        self.title.SetLabel("Abilities of %s  -  tick = learned, untick = remove. Applied when you save." % name)
        self.Rebuild()
    
    def Rebuild(self):
        words = self.search.GetValue().lower().split()
        wanted_kind = self.KINDS[max(0, self.kind.GetSelection())]
        learned_only = self.only_learned.GetValue()
        self.list.DeleteAllItems()
        self.shown = []
        for r in self.model.rows():
            if wanted_kind and r.kind != wanted_kind:
                continue
            if learned_only and not r.learned:
                continue
            hay = ("%s %s %d" % (r.name, r.group, r.id)).lower()
            if not all(w in hay for w in words):
                continue
            self.list.AppendItem([r.learned, r.name, r.group, KIND_TITLE[r.kind], str(r.id)])
            self.shown.append(r)
    
    def OnFilter(self, event):
        self.Rebuild()
    
    def OnToggle(self, event):
        row = self.list.ItemToRow(event.GetItem())
        if not (0 <= row < len(self.shown)):
            return
        r = self.shown[row]
        wanted = bool(self.list.GetToggleValue(row, 0))
        if not r.known and not wanted:
            answer = wx.MessageBox("Ability %d is not known to this editor (probably an internal entry).\n"
                                   "Removing it may have unwanted side effects. Remove it anyway?" % r.id,
                                   "Remove unknown ability", wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self)
            if answer != wx.YES:
                self.list.SetToggleValue(not wanted, row, 0)
                return
        try:
            if self.model.set_learned(r.kind, r.id, wanted):
                self.changed = True
        except KeyError as ex:
            wx.MessageBox("Not possible for this character: %s" % ex, "Abilities", wx.OK | wx.ICON_INFORMATION, self)
            self.list.SetToggleValue(not wanted, row, 0)
    
    def OnChangeClass(self, event):
        current = current_class(self.model)
        targets = [c for c in ('warrior', 'mage', 'rogue') if c != current]
        with wx.SingleChoiceDialog(self, "Current class: %s\nChange to:" % CLASS_TITLES.get(current, "unknown"),
                                   "Change class (experimental)", [CLASS_TITLES[c] for c in targets]) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            target = targets[dlg.GetSelection()]
        removed = ", ".join(n for kind, i, n in class_change_plan(self.model, target)) or "nothing"
        answer = wx.MessageBox("EXPERIMENTAL - not verified in the game. Make a backup first.\n\n"
                               "Changing to %s removes the spells/talents of the current class (%s) and sets the "
                               "class marker. Skills, attributes, level and equipment stay as they are, and the "
                               "abilities of the new class have to be added afterwards (Spells & Skills, Points).\n\n"
                               "Continue?" % (CLASS_TITLES[target], removed),
                               "Change class", wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self)
        if answer != wx.YES:
            return
        change_class(self.model, target)
        self.changed = True
        self.Rebuild()
    
    def OnAddById(self, event):
        ability_id = wx.GetNumberFromUser("Ability id to add (as used by the console command 'addtalent').",
                                          "ID:", "Add ability by ID", 1, 0, 999999, self)
        if ability_id < 0:
            return
        kinds = ['spell', 'talent', 'skill']
        with wx.SingleChoiceDialog(self, "Which list should it be added to?", "Ability type",
                                   ["Spell (mage)", "Talent (warrior/rogue)", "Skill"]) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            kind = kinds[dlg.GetSelection()]
        try:
            if self.model.set_learned(kind, ability_id, True):
                self.changed = True
        except KeyError as ex:
            wx.MessageBox("Not possible for this character: %s" % ex, "Abilities", wx.OK | wx.ICON_INFORMATION, self)
        self.Rebuild()
    
    def save(self):
        return self.changed

def _info_panel(parent, text):
    panel = wx.Panel(parent)
    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(wx.StaticText(panel, label=text), 0, wx.ALL, 15)
    panel.SetSizer(sizer)
    return panel

class EquipmentList(ItemList):
    """The equipped items of one character. The number of slots is fixed, so no Duplicate / Move Item here."""
    structural = False
    last_column = "Slot"
    
    def GetRowText(self, row):
        text = ItemList.GetRowText(self, row)
        text[5] = next((i for i, r in enumerate(self.data) if r is row), -1)
        return text
    
    def OnGetItemText(self, index, column):
        if column == 5:
            return str(self.itemIndexMap[index])
        return ItemList.OnGetItemText(self, index, column)

class LocationPanel(wx.Panel):
    """Where the party is: current area, position and the areas stored in the savegame (read-only)."""
    def __init__(self, parent):
        super(LocationPanel, self).__init__(parent)
    
    def load(self, root):
        loc = location_info(root, _resrefnames)
        def vec(v):
            return "x %.2f    y %.2f    z %.2f" % v if v else "unknown"
        area = "%s (%s)" % (loc.area_name, loc.area) if loc.area_name else (loc.area or "unknown")
        visited = "\n".join("%s (%s)" % (name, tag) if name else tag for tag, name in loc.visited) or "none"
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(2, 8, 16)
        for label, value in (("Current area", area), ("Player position", vec(loc.position)),
                             ("Entry position", vec(loc.entry_position)), ("Map zoom", "%.2f" % loc.zoom),
                             ("Areas in this savegame", visited)):
            grid.Add(wx.StaticText(self, label=label), 0, wx.ALIGN_TOP | wx.LEFT, 10)
            grid.Add(wx.StaticText(self, label=value), 0)
        sizer.Add(grid, 0, wx.ALL, 10)
        sizer.Add(wx.StaticText(self, label="Display only. Changing the position is not offered: coordinates are only "
                                            "valid inside their area and a wrong value can leave the character "
                                            "stuck in a wall."), 0, wx.ALL, 15)
        self.SetSizer(sizer)
    
    def save(self):
        return False

class QuestsPanel(wx.Panel):
    """Active and completed quests from the journal (read-only). The savegame only holds text ids; readable titles
    and texts come from the game's talk tables (*.tlk), which can be loaded here and are remembered."""
    def __init__(self, parent):
        super(QuestsPanel, self).__init__(parent)
        self.talk = None
        self.quests = []
        self.female = False
        
        self.summary = wx.StaticText(self, label="")
        self.load_button = wx.Button(self, label="Load game text (.tlk)...")
        self.list = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_HRULES | wx.LC_VRULES | wx.LC_SINGLE_SEL)
        for i, (title, width) in enumerate((("Status", 80), ("Quest", 190), ("Group", 140), ("Title", 300),
                                            ("Updated", 70))):
            self.list.InsertColumn(i, title, wx.LIST_FORMAT_LEFT, width)
        self.detail = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 120))
        
        top = wx.BoxSizer(wx.HORIZONTAL)
        top.Add(self.summary, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        top.Add(self.load_button, 0)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(top, 0, wx.EXPAND | wx.ALL, 10)
        sizer.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        sizer.Add(self.detail, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizer(sizer)
        
        self.load_button.Bind(wx.EVT_BUTTON, self.OnLoadText)
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnSelect)
    
    def load(self, root, talk=None):
        self.talk = talk
        self.quests = quest_entries(root)
        self.female = player_is_female(root)
        self.Fill()
    
    def _text(self, string_id):
        text = self.talk.text(string_id, self.female) if self.talk else None
        return plain_text(text) if text else None
    
    def Fill(self):
        self.list.DeleteAllItems()
        for i, q in enumerate(self.quests):
            self.list.InsertItem(i, q.status)
            self.list.SetItem(i, 1, q.resref)
            self.list.SetItem(i, 2, q.group)
            self.list.SetItem(i, 3, self._text(q.title_id) or q.title or "text #%d" % q.title_id)
            self.list.SetItem(i, 4, "yes" if q.updated else "")
        active = sum(1 for q in self.quests if q.status == 'Active')
        hint = ("" if self.talk else " Load the game's .tlk files to see readable titles.")
        self.summary.SetLabel("%d active, %d completed.%s Display only: quest progress also depends on "
                              "game variables, so it is not editable." % (active, len(self.quests) - active, hint))
        self.detail.SetValue("")
    
    def OnSelect(self, event):
        q = self.quests[event.GetIndex()]
        title = self._text(q.title_id) or "text #%d" % q.title_id
        stage = self._text(q.text_id) or ("(text #%d)" % q.text_id)
        self.detail.SetValue("%s\n\n%s" % (title, stage))
    
    def OnLoadText(self, event):
        if self.talk is None:
            self.talk = TalkTable()
        start = os.path.dirname(self.talk.files[-1]) if self.talk.files else ""
        wildcard = "Dragon Age talk tables (*.tlk)|*.tlk;*.TLK|All files|*"
        with wx.FileDialog(self, "Choose the game's text files (e.g. core_de-de.tlk and singleplayer_de-de.tlk)",
                           start, "", wildcard, wx.FD_OPEN | wx.FD_MULTIPLE | wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            paths = dlg.GetPaths()
        loaded, problems = [], []
        for path in paths:
            try:
                self.talk.add_file(path)
                loaded.append(path)
            except (OSError, ValueError) as ex:
                problems.append("%s: %s" % (os.path.basename(path), ex))
        if loaded:
            try:
                remember_talk_files(loaded)
            except OSError as ex:
                problems.append("The settings could not be saved: %s" % ex)
        if problems:
            wx.MessageBox("\n".join(problems), "Game text", wx.OK | wx.ICON_WARNING, self)
        self.Fill()
    
    def save(self):
        return False

class SavegameNotebook(wx.Treebook):
    talk = None        # TalkTable with the game's texts for the quest page; set by the main window
    
    def __init__(self, *args, **kwargs):
        super(SavegameNotebook, self).__init__(*args, **kwargs)
        self.AddPage(wx.Panel(self), "No Data")
        self.savables = []
    
    def save(self):
        changed = False
        for savable in self.savables:
            changed |= savable.save()
        return changed
    
    def load(self, data, root, game_version=VERSION_DAO):
        #print game_version
        self.DeleteAllPages()
        del self.savables[:]
        
        self.data = data
        
        self.inventory = InventoryPanel(self)
        self.inventory.load(data[SAVEGAME_PARTYLIST], root, game_version)
        self.savables.append(self.inventory)
        self.AddPage(self.inventory, "Inventory")
        
        inventories = dict()
        
        self.backpack = ItemList(self)
        self.backpack.load(data[SAVEGAME_PARTYLIST][SAVEGAME_BACKPACK], root, game_version)
        self.savables.append(self.backpack)
        self.AddSubPage(self.backpack, "Backpack")
        inventories["Backpack"] = self.backpack
        self.backpack.inventories = inventories
        
        self.plotitems = ItemList(self)
        self.plotitems.load(data[SAVEGAME_PARTYLIST][SAVEGAME_PLOTITEMS], root, game_version)
        self.savables.append(self.plotitems)
        self.AddSubPage(self.plotitems, "Plot Items")
        inventories["Plot Items"] = self.plotitems
        self.plotitems.inventories = inventories
        
        if 32000 in data[SAVEGAME_PARTYLIST]:
            self.party_store = ItemList(self)
            self.party_store.load(data[SAVEGAME_PARTYLIST][32000][SAVEGAME_STORE_ITEMLIST], root, game_version)
            self.savables.append(self.party_store)
            self.AddSubPage(self.party_store, "Party Storage")
            inventories["Party Storage"] = self.party_store
            self.party_store.inventories = inventories
        
        for area in data[SAVEGAME_AREALIST]:
            if area[TAG] == 'gwb201ar_sp_repaired\0':
                placename = 'gwb201ip_party_chest\0'
                suffix = " (Warden's Keep)"
            elif area[TAG] == 'vgk210ar_throne_room\0':
                placename = 'vgk210ip_party_chest\0'
                suffix = " (Awakening)"
            else:
                continue
            for placeable in area[SAVEGAME_AREA_PLACEABLES]:
                if placeable[TEMPLATERESREF] == placename:
                    party_store = ItemList(self)
                    party_store.load(placeable[SAVEGAME_ITEMS], root, game_version)
                    self.savables.append(party_store)
                    placename = _resrefnames[placename.strip('\0')]+suffix
                    self.AddSubPage(party_store, placename)
                    inventories[placename] = party_store
                    party_store.inventories = inventories
                    break
        
        self.party = PartyPanel(self)
        self.party.load(data[SAVEGAME_PARTYLIST], root, game_version)
        self.savables.append(self.party)
        self.AddPage(self.party, "Party")
        
        crp1 = data[SAVEGAME_PLAYERCHAR][SAVEGAME_PLAYERCHAR_CHAR]
        char_data = crp1[SAVEGAME_CREATURE_STATS][SAVEGAME_STATLIST]
        character = CreatureStatsList(self)
        character.load(char_data, root, game_version)
        self.savables.append(character)
        self.characters = [character]
        names = [crp1[SAVEGAME_OBJECT_NAME].s.strip('\0')]
        creatures = [crp1]
        self.AddSubPage(character, names[0])
        
        for crl1 in (data[SAVEGAME_PARTYLIST][SAVEGAME_PARTYPOOLMEMBERS] or ()):
            char_data = crl1[SAVEGAME_CREATURE_STATS][SAVEGAME_STATLIST]
            character = CreatureStatsList(self)
            character.load(char_data, root, game_version)
            self.savables.append(character)
            self.characters.append(character)
            names.append(self.party.ids2name[crl1[OBJECT_ID]])
            creatures.append(crl1)
            self.AddSubPage(character, names[-1])
        
        self.AddPage(_info_panel(self, "Choose a character on the left to change unspent attribute, skill,\n"
                                       "talent/spell and specialization points."), "Points")
        self.points = []
        for name, character in zip(names, self.characters):
            panel = PointsPanel(self)
            panel.load(character, name)
            self.points.append(panel)
            self.savables.append(panel)
            self.AddSubPage(panel, name)
        
        self.AddPage(_info_panel(self, "Choose a character on the left to see and change learned spells, talents,\n"
                                       "skills and specializations."), "Spells & Skills")
        self.abilities = []
        for number, (name, creature) in enumerate(zip(names, creatures)):
            panel = AbilitiesPanel(self)
            panel.load(creature[SAVEGAME_CREATURE_STATS], name, allow_class_change=(number == 0))
            self.abilities.append(panel)
            self.savables.append(panel)
            self.AddSubPage(panel, name)
        
        self.AddPage(_info_panel(self, "Choose a character on the left to see and change the equipped items."),
                     "Equipment")
        self.equipment = []
        for name, creature in zip(names, creatures):
            try:
                items = creature[SAVEGAME_EQUIPMENT_ITEMS]
            except KeyError:
                continue
            panel = EquipmentList(self)
            panel.load(items, root, game_version)
            self.equipment.append(panel)
            self.savables.append(panel)
            self.AddSubPage(panel, name)
        
        self.quests = QuestsPanel(self)
        self.quests.load(root, self.talk)
        self.AddPage(self.quests, "Quests")
        
        self.location = LocationPanel(self)
        self.location.load(root)
        self.AddPage(self.location, "Location")
        
        self.AddPage(wx.Panel(self), "Areas")
        self.area_items = AreaInventoryPanel(self)
        self.area_items.load(data[SAVEGAME_AREALIST], root, game_version)
        self.area_items.inventories = inventories
        self.savables.append(self.area_items)
        self.AddSubPage(self.area_items, "Items")

class ZipSaveDialog(wx.Dialog):
    """Pick one of several savegames found in an XDroid360 zip export."""
    COLUMNS = (('Save', 250), ('Character', 100), ('Area', 140), ('Play time', 75), ('Level', 45),
               ('Saved', 125), ('Folder', 140))
    
    def __init__(self, parent, saves, title):
        super(ZipSaveDialog, self).__init__(parent, title=title, size=(960, 420),
                                            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.saves = saves
        self.selected = None
        
        hint = wx.StaticText(self, label="This zip contains %d savegames, sorted by play time. "
                                         "The one with the longest play time is the most recent." % len(saves))
        self.list = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        for i, (name, width) in enumerate(self.COLUMNS):
            self.list.InsertColumn(i, name, wx.LIST_FORMAT_LEFT, width)
        for i, save in enumerate(saves):
            level = '' if save.level is None else str(save.level)
            saved = save.saved.strftime('%Y-%m-%d %H:%M') if save.saved else ''
            values = (save.title or save.folder, save.character, save.area, format_seconds(save.played),
                      level, saved, save.folder)
            self.list.InsertItem(i, values[0])
            for col, text in enumerate(values[1:], 1):
                self.list.SetItem(i, col, text)
        if saves:
            self.list.Select(0)
            self.list.Focus(0)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(hint, 0, wx.ALL, 8)
        sizer.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        sizer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizer(sizer)
        self.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnActivate)
    
    def OnActivate(self, event):
        self.selected = self.saves[event.GetIndex()]
        self.EndModal(wx.ID_OK)
    
    def ShowModal(self):
        result = super(ZipSaveDialog, self).ShowModal()
        if result == wx.ID_OK and self.selected is None:
            i = self.list.GetFirstSelected()
            self.selected = self.saves[i] if 0 <= i < len(self.saves) else None
        return result

class MyFrame(wx.Frame):
    def __init__(self, *args, **kwargs):
        super(MyFrame, self).__init__(*args, **kwargs)
        self.control = SavegameNotebook(self, wx.ID_ANY)
        self.control.talk = load_talktable()        # game texts for quest titles (files remembered from earlier runs)
        self.CreateStatusBar()
        
        self.filename = ''
        self.dirname = ''
        self.gff_file = ''
        self.zip_member = None
        self.open_label = ''
        self.header = None
        self.data = None
        self.gff = None
        
        self.filetimer = wx.Timer(self)
        self.fileprogress = None
        self.Bind(wx.EVT_TIMER, self.OnFileOpTimer, self.filetimer)
        
        filemenu = wx.Menu()
        openitem = filemenu.Append(wx.ID_OPEN, "&Open File...\tCTRL+O", "Open a savegame (.das)")
        saveitem = filemenu.Append(wx.ID_SAVE, "&Save\tCTRL+S", "Save the savegame")
        exititem = filemenu.Append(wx.ID_EXIT, "E&xit\tCTRL+Q", "Terminate the program")
        
        helpmenu = wx.Menu()
        aboutitem = helpmenu.Append(wx.ID_ABOUT, "&About", "Information about this program")

        menubar = wx.MenuBar()
        menubar.Append(filemenu, "&File")
        menubar.Append(helpmenu, "&Help")
        self.SetMenuBar(menubar)
        
        self.Bind(wx.EVT_MENU, self.OnOpenFile, openitem)
        self.Bind(wx.EVT_MENU, self.OnSave, saveitem)
        self.Bind(wx.EVT_MENU, self.OnExit, exititem)
        self.Bind(wx.EVT_MENU, self.OnAbout, aboutitem)
        
        self.SetStatusText("Use File > Open File to open a savegame (.das).")
    
    def OpenPath(self, path):
        """Opens a savegame (.das) or an XDroid360 export (.zip)."""
        if path.lower().endswith('.zip'):
            self.OpenZip(path)
        else:
            self._open(path, None, path)
    
    def _open(self, path, member, label):
        self.gff_file = path
        self.zip_member = member
        self.open_label = label
        self.filename = os.path.basename(path)
        self.dirname = os.path.dirname(path)
        self.ShowFileOpDialog("Reading Savegame", "Reading Savegame")
        delayedresult.startWorker(self.OnOpenDone, open_gff, wargs=[path, member])
    
    def OpenZip(self, path):
        """One savegame in the zip: open it. Several: let the user choose (newest = longest play time first)."""
        try:
            saves = find_saves(path)
        except (zipfile.BadZipFile, OSError) as ex:
            wx.MessageBox("This zip file could not be read:\n%s" % ex, "Error", wx.OK | wx.ICON_ERROR, self)
            return
        if not saves:
            wx.MessageBox("No savegame (.das) was found in this zip file.", "Open zip",
                          wx.OK | wx.ICON_INFORMATION, self)
            return
        if len(saves) == 1:
            chosen = saves[0]
        else:
            with ZipSaveDialog(self, saves, "Choose a savegame - %s" % os.path.basename(path)) as dlg:
                if dlg.ShowModal() != wx.ID_OK or dlg.selected is None:
                    return
                chosen = dlg.selected
        self._open(path, chosen.member, "%s (in %s)" % (chosen.title or chosen.folder, os.path.basename(path)))
    
    def OnOpenFile(self, event):
        start = self.dirname
        wildcard = ("Dragon Age Savegames (*.das) or XDroid360 export (*.zip)|*.das;*.DAS;*.zip;*.ZIP|"
                    "All files|*")
        with wx.FileDialog(self, "Choose a file", start, self.filename, wildcard, wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.OpenPath(dlg.GetPath())
    
    def OnSave(self, event):
        if self.data is None or not self.gff_file:
            wx.MessageBox("Open a savegame first.", "Save", wx.OK | wx.ICON_INFORMATION, self)
            return
        try:
            self.control.save()
        except Exception as ex:
            print_exc()
            wx.MessageBox("Could not collect the changes:\n%s" % ex, "Error", wx.OK | wx.ICON_ERROR, self)
            return
        if self.zip_member:
            # the savegame lives inside a zip: rewrite the zip (original is kept as .orig / .bak)
            self.ShowFileOpDialog("Saving Savegame", "Saving Savegame into the zip file")
            delayedresult.startWorker(self.OnZipSaveDone, save_zip,
                                      wargs=[self.gff_file, self.zip_member, self.gff])
            return
        # write to a temporary file first, so a failure can never destroy the original
        tmp_file = self.gff_file + '.tmp'
        self.ShowFileOpDialog("Saving Savegame", "Saving Savegame")
        delayedresult.startWorker(self.OnSaveDone, save_gff, wargs=[tmp_file, self.gff], cargs=(tmp_file,))
    
    def ShowFileOpDialog(self, title, message):
        self.fileprogress = wx.ProgressDialog(title, message, parent=self, style=wx.PD_ELAPSED_TIME)
        self.filetimer.Start(500)
    
    def OnFileOpTimer(self, event):
        if self.fileprogress is not None:
            self.fileprogress.Pulse()

    def CloseFileOpDialog(self):
        self.filetimer.Stop()
        if self.fileprogress is not None:
            self.fileprogress.Destroy()
            self.fileprogress = None
    
    def OnOpenDone(self, result):
        self.CloseFileOpDialog()
        try:
            gff = result.get()
            header, data = gff.header, gff.root
            if header.version != 'V4.0':
                raise ValueError("only Dragon Age: Origins savegames are supported (GFF version %s)" % header.version)
            self.control.load(data, data, VERSION_DAO)
        except Exception as ex:
            print_exc()
            self.header = self.data = self.gff = None
            wx.MessageBox("This file could not be opened as a Dragon Age savegame:\n%s: %s" % (type(ex).__name__, ex),
                          "Error", wx.OK | wx.ICON_ERROR, self)
            return
        self.gff, self.header, self.data = gff, header, data
        self.SetStatusText("Opened %s" % self.open_label)
    
    def OnZipSaveDone(self, result):
        self.CloseFileOpDialog()
        try:
            crc = result.get()
        except Exception as ex:
            print_exc()
            wx.MessageBox("Saving into the zip failed (the zip file was not changed):\n%s: %s" % (type(ex).__name__, ex),
                          "Error", wx.OK | wx.ICON_ERROR, self)
            return
        self.SetStatusText("Saved into %s (backup: .orig / .bak) - updated %s.x (CRC32 %08X)"
                           % (os.path.basename(self.gff_file), os.path.basename(self.zip_member), crc))
    
    def OnSaveDone(self, result, tmp_file):
        self.CloseFileOpDialog()
        try:
            result.get()
            gff_file = self.gff_file
            if not os.path.exists(gff_file + '.orig'):
                os.rename(gff_file, gff_file + '.orig')
            else:
                bak_file = gff_file + '.bak'
                if os.path.exists(bak_file):
                    os.unlink(bak_file)
                os.rename(gff_file, bak_file)
            os.replace(tmp_file, gff_file)
            crc = update_checksum_file(gff_file)
        except Exception as ex:
            print_exc()
            if os.path.exists(tmp_file):
                try:
                    os.unlink(tmp_file)
                except OSError:
                    pass
            wx.MessageBox("Saving failed (the original file was not touched unless noted below):\n%s: %s" % (type(ex).__name__, ex),
                          "Error", wx.OK | wx.ICON_ERROR, self)
            return
        msg = "Saved %s (backup: .orig / .bak)" % self.gff_file
        if crc is not None:
            msg += " - updated %s.x (CRC32 %08X)" % (os.path.basename(self.gff_file), crc)
        self.SetStatusText(msg)

    def OnAbout(self, event):
        with wx.MessageDialog(self, "Dragon Age Origins Savegame Editor for XDroid360\nVersion " + VERSION + "\n\nBased on the savegame editor by Mephales "
                              "(part of pygff by William Clark).\n\nPython 3 / wxPython 4 port for Linux.",
                              "About Dragon Age Origins Savegame Editor for XDroid360", wx.OK) as dlg:
            dlg.ShowModal()
  
    def OnExit(self, event):
        self.Close()

def open_gff(gff_file, member=None):
    """Reads a savegame from a file, or from an entry (member) of a zip file."""
    if member:
        return LazyGFF4(BytesIO(read_member(gff_file, member)))
    with open(gff_file, 'rb') as f:
        gff = LazyGFF4(f)
    return gff

def save_zip(zip_path, member, gff):
    """Writes the savegame back into the zip (and refreshes its '.x' checksum entry). Returns the CRC32."""
    buf = BytesIO()
    gff.tofile(buf)
    return replace_in_zip(zip_path, member, buf.getvalue())

def save_gff(gff_file, gff):
    with open(gff_file, 'wb') as f:
        gff.tofile(f)

def main():
    app = wx.App(False)
    frame = MyFrame(None, title='Dragon Age Origins Savegame Editor for XDroid360', size=(900, 650))
    frame.app = app
    frame.Show(True)
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        frame.OpenPath(os.path.abspath(sys.argv[1]))
    app.MainLoop()

if __name__ == '__main__':
    main()
