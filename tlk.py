# -*- coding: utf-8 -*-
"""Dragon Age: Origins talk tables (*.tlk, GFF "TLK" V0.4) - reads texts by their string id (no GUI).

A talk table holds three lists: (string id, bit offset) pairs, a Huffman tree and the Huffman coded text as 32-bit
words. Characters are UTF-16 code units; the bits of each 32-bit word are used starting with the least significant
one. Files named '*_f.tlk' hold the variants for a female player character.
"""
import os
import re
import struct

_LABEL_STRINGS, _LABEL_TREE, _LABEL_BITS = 19006, 19007, 19008      # lists of the root structure HTLK

class _Table(object):
    def __init__(self, path):
        with open(path, 'rb') as f:
            data = f.read()
        if data[:4] != b'GFF ' or data[12:16] != b'TLK ':
            raise ValueError('not a Dragon Age talk table: %s' % os.path.basename(path))
        end = '>' if data[8:12] == b'X360' else '<'
        struct_count, data_offset = struct.unpack_from(end + 'II', data, 20)
        # the structure table follows directly (talk tables use the plain V4.0 layout)
        probe = data[28:32]
        if len(probe) < 4 or not all(0x20 <= b < 0x7F for b in probe):
            raise ValueError('unsupported talk table layout: %s' % os.path.basename(path))
        root_fields = None
        for i in range(struct_count):
            fourcc, field_count, field_offset, size = struct.unpack_from(end + '4sIII', data, 28 + 16 * i)
            if fourcc == b'HTLK':
                root_fields = {}
                for j in range(field_count):
                    label, flags, type_id, offset = struct.unpack_from(end + 'IHHI', data, field_offset + 12 * j)
                    root_fields[label] = offset
        if root_fields is None or not {_LABEL_STRINGS, _LABEL_TREE, _LABEL_BITS} <= set(root_fields):
            raise ValueError('unsupported talk table structure: %s' % os.path.basename(path))

        def list_at(label):
            pointer, = struct.unpack_from(end + 'I', data, data_offset + root_fields[label])
            position = data_offset + pointer
            count, = struct.unpack_from(end + 'I', data, position)
            return position + 4, count
        pos, n = list_at(_LABEL_STRINGS)
        pairs = struct.unpack_from('%s%dI' % (end, 2 * n), data, pos)
        self.offsets = dict(zip(pairs[0::2], pairs[1::2]))
        pos, n = list_at(_LABEL_TREE)
        self.tree = struct.unpack_from('%s%di' % (end, n), data, pos)
        pos, n = list_at(_LABEL_BITS)
        self.words = struct.unpack_from('%s%dI' % (end, n), data, pos)

    def __len__(self):
        return len(self.offsets)

    def get(self, string_id):
        start = self.offsets.get(string_id)
        if start is None:
            return None
        tree, words = self.tree, self.words
        root = len(tree) // 2 - 1
        total = len(words) * 32
        pos, out = start, []
        while pos < total and len(out) < 20000:
            node = root
            while True:
                if pos >= total:
                    return ''.join(out)
                bit = (words[pos >> 5] >> (pos & 31)) & 1
                pos += 1
                value = tree[2 * node + bit]
                if value < 0:
                    symbol = -value - 1
                    break
                node = value
            if symbol == 0:
                break
            out.append(chr(symbol))
        return ''.join(out)

_TAGS = re.compile(r'<[^>]*>')

def plain_text(text):
    """Text without the markup tags the game puts into quest texts (e.g. <emp>...</emp>)."""
    return _TAGS.sub('', text).strip()

class TalkTable(object):
    """One or more talk table files of the same language."""
    def __init__(self):
        self.files = []
        self._normal = []
        self._female = []

    def add_file(self, path):
        """Loads a .tlk file; returns the number of strings in it. Raises ValueError for other files."""
        table = _Table(path)
        female = os.path.basename(path).lower().endswith('_f.tlk')
        (self._female if female else self._normal).append(table)
        if path not in self.files:
            self.files.append(path)
        return len(table)

    def __bool__(self):
        return bool(self._normal or self._female)

    def text(self, string_id, female=False):
        """The text for a string id, or None if no loaded file has it."""
        if string_id is None or string_id <= 0:
            return None
        for table in (self._female + self._normal) if female else self._normal:
            text = table.get(string_id)
            if text is not None:
                return text
        return None
