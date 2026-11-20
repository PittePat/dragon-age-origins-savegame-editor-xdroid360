import sys, io
import os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gff4; gff4._DEBUG_COMPARISONS = True
from gff4 import *
from gff4 import _structtype, _listtype
from gff4.lazy import LazyGFF4

Item = _structtype('ITEM', (Field(1, INT32, False, 0), Field(2, ECString, False, 4)), 8)
ItemList_ = _listtype(Item)
BinList = _listtype(UINT8)
Root = _structtype('ROOT', (
    Field(1, INT32, False, 0),
    Field(2, ECString, False, 4),
    Field(3, ItemList_, False, 8),
    Field(4, TlkString, False, 12),
    Field(5, BinList, False, 20),
    Field(6, FLOAT32, False, 24),
    Field(7, Item, True, 28),       # reference to struct
    Field(8, Vector3f, False, 32),
), 44)

def make():
    r = Root()
    r[1] = 123456
    r[2] = 'Hällo Wörld'
    items = ItemList_()
    for i in range(3):
        it = Item(); it[1] = i*10; it[2] = 'item%d'%i
        items.append(it)
    r[3] = items
    r[4] = TlkString(77, 'tlk text')
    r[5] = b'\x01\x02\x03\xff'
    r[6] = 1.5
    ref = Item(); ref[1] = 99; ref[2] = 'ref'
    r[7] = ref
    r[8] = Vector3f(1.0, 2.0, 3.0)
    return r

for ver in ('V4.0', 'V4.1'):
    r = make()
    header = build_header(r, gff_version=ver, file_type='TEST', file_version='V1.0')
    buf = io.BytesIO()
    write_gff4(buf, r, header)
    raw = buf.getvalue()
    print(ver, 'written', len(raw), 'bytes', raw[:12])

    # eager read
    buf.seek(0)
    r2, h2 = read_gff4(buf)
    assert h2.file_type == 'TEST' and h2.version == ver, h2[:4]
    assert r2[1] == 123456 and r2[2] == 'Hällo Wörld', (r2[1], r2[2])
    assert [ (i[1], i[2]) for i in r2[3]] == [(0,'item0'),(10,'item1'),(20,'item2')]
    assert r2[4] == TlkString(77, 'tlk text'), r2[4]
    assert r2[5] == b'\x01\x02\x03\xff', r2[5]
    assert type(r2[5]) is Binary
    assert r2[6] == 1.5 and r2[7][1] == 99 and r2[7][2] == 'ref'
    assert r2[8] == Vector3f(1.0, 2.0, 3.0)
    print('  eager read OK')

    # lazy read, no changes -> rewrite must be re-readable and equal
    buf.seek(0)
    g = LazyGFF4(buf)
    root = g.root
    assert root[1] == 123456 and root[2] == 'Hällo Wörld'
    out = io.BytesIO(); g.tofile(out)
    out.seek(0)
    r3, h3 = read_gff4(out)
    assert r3 == r2, 'unchanged lazy roundtrip differs'
    print('  lazy unchanged roundtrip OK')

    # lazy read with modifications
    buf.seek(0)
    g = LazyGFF4(buf)
    root = g.root
    root[1] = 999
    root[2] = 'geändert'
    lst = root[3]
    lst[1][1] = 4242
    newit = type(lst[0])(); newit[1] = 7; newit[2] = 'neu'
    lst.append(newit)
    root[5] = b'zlib-ish\x00\x01'
    out = io.BytesIO(); g.tofile(out)
    out.seek(0)
    r4, h4 = read_gff4(out)
    assert r4[1] == 999 and r4[2] == 'geändert', (r4[1], r4[2])
    assert [(i[1], i[2]) for i in r4[3]] == [(0,'item0'),(4242,'item1'),(20,'item2'),(7,'neu')], [(i[1], i[2]) for i in r4[3]]
    assert r4[5] == b'zlib-ish\x00\x01', r4[5]
    assert r4[4] == TlkString(77, 'tlk text') and r4[7][2] == 'ref' and r4[8] == Vector3f(1.0,2.0,3.0)
    print('  lazy modified roundtrip OK')
print('ALL CORE TESTS PASSED')
