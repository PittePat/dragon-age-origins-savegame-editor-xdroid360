# -*- coding: utf-8 -*-
"""Small persistent settings (JSON in the user's config folder), e.g. the talk table files for quest titles."""
import json
import os

def config_path():
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(os.path.expanduser('~'), '.config')
    return os.path.join(base, 'dragonage-savegame-editor', 'settings.json')

def load_settings():
    try:
        with open(config_path(), encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}

def save_settings(data):
    path = config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)

def load_talktable():
    """A TalkTable with the files remembered in the settings; files that vanished or are unusable are skipped."""
    from tlk import TalkTable
    table = TalkTable()
    for path in load_settings().get('tlk_files', []):
        try:
            table.add_file(path)
        except (OSError, ValueError):
            pass
    return table

def remember_talk_files(paths):
    data = load_settings()
    known = list(data.get('tlk_files', []))
    for path in paths:
        if path not in known:
            known.append(path)
    data['tlk_files'] = known
    save_settings(data)
