# -*- coding: utf-8 -*-
"""Savegames inside XDroid360 export zips (no GUI, so it can be tested on its own).

XDroid360 exports a save like this:

    content/454108C0/00000001/<id>/Saves/savegame.das      the savegame
    content/454108C0/00000001/<id>/Saves/savegame.das.x    its CRC32 (big-endian)
    content/454108C0/00000001/<id>/Saves/savegame.met      metadata (character, area, play time, level)
    content/454108C0/00000001/<id>.name                    display name, UTF-16BE, ends with a timestamp
"""
import io
import os
import re
import shutil
import struct
import zipfile
import zlib
from collections import namedtuple
from datetime import datetime

from gff4.lazy import LazyGFF4
from gff4.datoolset_fields import (
    SAVEGAME_META_AREANAME, SAVEGAME_META_TIMEPLAYED, SAVEGAME_META_LEVEL, SAVEGAME_META_NAME,
    SAVEGAME_PLAYERCHAR, SAVEGAME_PLAYER_TIME_PLAYED,
)

MAX_MEMBER_SIZE = 200 * 1024 * 1024      # refuse absurdly large entries

ZipSave = namedtuple('ZipSave', 'member folder title character area played level saved')

def format_seconds(seconds):
    """'1:02:05' for 3725 seconds, '' if unknown."""
    if seconds is None:
        return ''
    seconds = int(seconds)
    return '%d:%02d:%02d' % (seconds // 3600, (seconds // 60) % 60, seconds % 60)

def _name_text(raw):
    """Display name stored in '<id>.name' (UTF-16BE, NUL terminated, rest of the 256 bytes is garbage)."""
    return raw.decode('utf-16-be', 'ignore').split('\0', 1)[0].strip()

_STAMP = re.compile(r'_(\d{14})$')

def _saved_time(title, info):
    """Time of the save: the timestamp in the display name, otherwise the zip entry date."""
    match = _STAMP.search(title)
    if match:
        try:
            return datetime.strptime(match.group(1), '%Y%m%d%H%M%S')
        except ValueError:
            pass
    try:
        return datetime(*info.date_time)
    except (ValueError, TypeError):
        return None

def _read(zf, info):
    if info.file_size > MAX_MEMBER_SIZE:
        raise ValueError('entry too large: %s' % info.filename)
    return zf.read(info)

def _describe(zf, info, by_lower):
    member = info.filename
    folder = os.path.dirname(member)
    if os.path.basename(folder).lower() == 'saves':
        folder = os.path.dirname(folder)
    title = ''
    name_info = by_lower.get((folder + '.name').lower())
    if name_info is not None:
        try:
            title = _name_text(_read(zf, name_info))
        except Exception:
            title = ''
    character = area = ''
    played = level = None
    met_info = by_lower.get((member[:-4] + '.met').lower())
    if met_info is not None:
        try:
            met = LazyGFF4(io.BytesIO(_read(zf, met_info))).root
            character = str(met[SAVEGAME_META_NAME]).strip('\0')
            area = str(met[SAVEGAME_META_AREANAME]).strip('\0')
            played = int(met[SAVEGAME_META_TIMEPLAYED])
            level = int(met[SAVEGAME_META_LEVEL])
        except Exception:
            pass
    if played is None:
        try:
            root = LazyGFF4(io.BytesIO(_read(zf, info))).root
            played = int(float(root[SAVEGAME_PLAYERCHAR][SAVEGAME_PLAYER_TIME_PLAYED]))
        except Exception:
            played = None
    return ZipSave(member, os.path.basename(folder), title, character, area, played, level,
                   _saved_time(title, info))

def find_saves(zip_path):
    """All savegames (*.das) in the zip, the one with the highest play time (the newest) first."""
    with zipfile.ZipFile(zip_path) as zf:
        infos = zf.infolist()
        by_lower = {i.filename.lower(): i for i in infos}
        saves = [_describe(zf, i, by_lower) for i in infos
                 if not i.is_dir() and i.filename.lower().endswith('.das')]
    saves.sort(key=lambda s: (s.played if s.played is not None else -1,
                              s.saved or datetime.min), reverse=True)
    return saves

def read_member(zip_path, member):
    with zipfile.ZipFile(zip_path) as zf:
        return _read(zf, zf.getinfo(member))

def _clone(info):
    """A fresh ZipInfo with the same name, date, compression and permissions (zipfile mutates what it is given)."""
    new = zipfile.ZipInfo(info.filename, info.date_time)
    new.compress_type = info.compress_type
    new.external_attr = info.external_attr
    new.create_system = info.create_system
    new.comment = info.comment
    return new

def replace_in_zip(zip_path, member, data):
    """Writes `data` as the new content of `member`, refreshes its '<member>.x' CRC32 entry (if present) and
    keeps every other entry untouched. The original zip is saved as '<zip>.orig' (first time) or '<zip>.bak'.
    The zip is only replaced after the new one was written and verified. Returns the new CRC32."""
    crc = zlib.crc32(data) & 0xFFFFFFFF
    tmp = zip_path + '.tmp'
    try:
        with zipfile.ZipFile(zip_path) as zin:
            lower = {i.filename.lower(): i.filename for i in zin.infolist()}
            xname = lower.get((member + '.x').lower())
            if member not in {i.filename for i in zin.infolist()}:
                raise KeyError(member)
            with zipfile.ZipFile(tmp, 'w') as zout:
                for info in zin.infolist():
                    if info.filename == member:
                        zout.writestr(_clone(info), data)
                    elif info.filename == xname:
                        zout.writestr(_clone(info), struct.pack('>I', crc))
                    else:
                        zout.writestr(_clone(info), b'' if info.is_dir() else _read(zin, info))
        with zipfile.ZipFile(tmp) as check:
            bad = check.testzip()
            if bad is not None:
                raise zipfile.BadZipFile('verification failed for %s' % bad)
            if check.read(member) != data:
                raise zipfile.BadZipFile('verification failed for %s' % member)
        backup = zip_path + ('.bak' if os.path.exists(zip_path + '.orig') else '.orig')
        shutil.copy2(zip_path, backup)
        os.replace(tmp, zip_path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
    return crc
