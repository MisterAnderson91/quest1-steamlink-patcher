#!/usr/bin/env python3
"""Stamp the web pages' links to their scripts and data with a content hash.

GitHub Pages lets browsers cache every file for 10 minutes (and Chrome can
keep an ES module longer), so after an update a page could run an old
apkpatch.js or classes2.dex. Each reference in docs/index.html gets "?v=<first 10 hex digits of the file's sha256>",
so a changed file has a new URL. Run before committing changes under docs/.
"""
import hashlib
import re
from pathlib import Path

DOCS = Path(__file__).resolve().parent / 'docs'
ASSETS = ('apkpatch.js', 'apksign.js', 'adb.js', 'classes2.dex', 'q1_steamlink_usb.zip')
REF = re.compile(r"""(['"])((?:\./)?(%s))(?:\?v=[0-9a-f]*)?\1""" % '|'.join(map(re.escape, ASSETS)))

for page in (DOCS / 'index.html',):
    text = page.read_text()

    def stamp(m):
        file = page.parent / m.group(3)
        if not file.exists():
            raise SystemExit(f'{page.relative_to(DOCS)}: {m.group(3)} is referenced but missing')
        digest = hashlib.sha256(file.read_bytes()).hexdigest()[:10]
        return f'{m.group(1)}{m.group(2)}?v={digest}{m.group(1)}'

    new, count = REF.subn(stamp, text)
    if new != text:
        page.write_text(new)
    print(f'{page.relative_to(DOCS)}: {count} references{" (updated)" if new != text else ""}')
