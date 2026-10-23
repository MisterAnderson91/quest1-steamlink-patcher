#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Gregory Anderson
"""Patch Valve's Steam Link VR app so it runs on the original Oculus Quest (Quest 1).

Takes the Steam Link APK from your own SteamVR install, patches it, signs it
with the project's public key (so updates install in place), and installs it
on the headset over adb. Valve's own code isn't modified:

  1. supported devices: the Quest 1 runtime aborts on device names it doesn't
     know ("Unknown device to support: quest3"), so the manifest's
     com.oculus.supportedDevices list is cut down to names it knows.
  2. display 0: the Quest 1 leaves the VR activity on the 2D panel's virtual
     display, so it never gets the screen. Our own small class,
     com.valvesoftware.steamlink.SteamLinkQ1 (added as classes2.dex; source in
     payload/), subclasses the 2D activity and launches the VR activity on
     display 0. The manifest's launcher activity is pointed at it.
  3. Quest 1 identity: SteamVR sees the headset as "Oculus Quest" and the
     controllers as Quest 1 Touch models, instead of "unknown" and Quest 2.

Needs only Python 3.8+ (standard library). If adb isn't installed, it downloads
Google's platform-tools into a cache folder, checking the published checksum.

Usage:
    python3 quest1_patcher.py              # find, patch, sign, install
    python3 quest1_patcher.py --no-install # just write the patched APK
    python3 quest1_patcher.py --apk PATH   # use a specific Steam Link APK
"""
import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

PACKAGE = 'com.valvesoftware.steamlinkvr'
APK_NAME = 'android-steamlinkvr-release.apk'
STEAMVR_APK = Path('steamapps', 'common', 'SteamVR', 'drivers', 'vrlink', 'resources', APK_NAME)

PLATFORM_TOOLS = {
    'linux': ('https://dl.google.com/android/repository/platform-tools_r37.0.1-linux.zip',
              '477254aa5f903c15cf51001717bdf347fb6b53e0'),
    'windows': ('https://dl.google.com/android/repository/platform-tools_r37.0.1-win.zip',
                'e03e78b1d80b396f1c3358e31251cb31740e1110'),
    'mac': ('https://dl.google.com/android/repository/platform-tools_r37.0.1-darwin.zip',
            '6ae73f4de6452dc57e62ec02b68eed92a4c21661'),
}


# The project's signing key, deliberately public (same as docs/signing-key.pem):
# every patched APK, from this script or the web page, is signed with it, so
# updates install in place from any computer. --key-pem signs with your own.
SIGNING_KEY_PEM = """\
-----BEGIN PRIVATE KEY-----
MIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQCHzUY7RImQ9iBo
nC5x+BNzgm3KnWaUxBr2sNJvBWEtm7cMZA6guJea/7IKD2YcxFFkhCORslGyLOQr
eD+mq3eJSHVi4NjDAtmzLTwcFGk8JQ0i8TkMI19LGVPtgBsa4rCBQwCKXEyogBCR
mL+lGSNFug+jyYIw4m/R+RJJlUbkzaUgoaQj1It7QXJav2UZp9eOC1YP39LfXFiY
CcUQGUbPHu9oWiWflBYPUcnHs7sbEfGk2t5cCl5Tteg1qSZvFbmVA26uInuxfV9X
rycuxC/Agb0I9a/Hk41ncd4AVqNXtK9W2CTs604ZA5vYVJk6U9tO+l7QtQDSgjHg
TN1g5SHdAgMBAAECggEAU44OjzrNNX7qU9L8lKzhMunmKYsM6a17NZt37k0uDITJ
bHtHsMXCqeB3J89vsXVs6t6Oj/9aWrlaLhDPgPnxE2ucphjX5aykS6UiXdiFIzdc
zMoEop5E7I0J4ZA3nSQrG20hMQA3PlmFWD/Wcnt0A1vGcazzSKaZzGRmRxXsx6uC
ZBGRVLN6n8Le8J7k3DzW0SPiT2sX8fGPUpGhxEerW5q53lTY/YQDZ5d4CAl42O6u
T5tSYpU0SoP5Bgmt8M5BSADdhKINpGwzEWRfdEJ4zBXwGgaLPWB3jukQAagTPQ8O
1RCMf6F4u2FufNvw2/ZHw224HrzaipFozlATiE2yYQKBgQDgqQo2BiUCduPWkw7k
3LeOwMPuICjLUj0sNZmyw/T1TAFiOodsAVC41l5brd6nTciZ2VovMmWZOouy4J3b
pQeMp2aEazR9U/oOts5ssEOlLPfs5znWPYJwh3r5ZaXU6IJFdLf8X+vYaxSiZNty
f0oYXaDK+vy6BNi6aiImdhPuVQKBgQCavvbZXQjY3rIKz1c6c7Em+DeiBN9q90G3
FAF8skisbj8iHrPHgCasuuxIpyIGVWtGf8idjUiEa085cJSYqoa8xrG8UZ+UIp+D
Tn5umO0PUyayBRwOif+2GWKBKnNrz/GC3WMVSz6GlKh8Og8VtDS84a88ynHUSeAR
2hPfbRXdaQKBgDbitV7rc2E9wH3soYfiMGoMyBFGBBFgPxes5Kba3t6Kug/QcsM9
MwZlQNovCSVgiHClvDWpn06nEfgajhZaJBUF1LLnKgSwXnf3y0ica3pQGSXke6nO
jy6EutNxNOlmAGWNlWFv4cOWrYzbDQ3U8TowrZbJaLLdekFYqo0w7b+dAoGACUW+
FuI7QHt/oaQw7uC10cb31m6CUK+GMYkyWZ15O1PT1qCOVzr3lkwREn1pTYXayrun
csFfggfIFIIJdWhqcG9bgRRHAqJceoq+irQBKHTsEai6uKhOOUQmIeVAS0qHhzbq
1ADRO1E3E1KLStqkeljvni3nSjgvBALURAQOVlkCgYAS2PgdthOxlTFWbXRUwerv
SkgN1Hi4n9rrBl3KzheSypJahXQhboFZqeXo9o/PwBpuRxM0YdAFDVbEyOqgYWBH
TpJL7ElprZp4CvKpgPmYEWQidcw8UWseiwIY/90UBUi3x0CjGeTvbis5mvJadZtI
CYuG4qv1jmGP/kcEn+soug==
-----END PRIVATE KEY-----
"""
SIGNING_CERT_PEM = """\
-----BEGIN CERTIFICATE-----
MIIC1TCCAb2gAwIBAgIEIs+I1DANBgkqhkiG9w0BAQsFADAaMRgwFgYDVQQDEw9R
dWVzdDEgU2lkZWxvYWQwIBcNMjYxMDIxMDk0MTU5WhgPMjA1NDAzMDgwOTQxNTla
MBoxGDAWBgNVBAMTD1F1ZXN0MSBTaWRlbG9hZDCCASIwDQYJKoZIhvcNAQEBBQAD
ggEPADCCAQoCggEBAIfNRjtEiZD2IGicLnH4E3OCbcqdZpTEGvaw0m8FYS2btwxk
DqC4l5r/sgoPZhzEUWSEI5GyUbIs5Ct4P6ard4lIdWLg2MMC2bMtPBwUaTwlDSLx
OQwjX0sZU+2AGxrisIFDAIpcTKiAEJGYv6UZI0W6D6PJgjDib9H5EkmVRuTNpSCh
pCPUi3tBclq/ZRmn144LVg/f0t9cWJgJxRAZRs8e72haJZ+UFg9RycezuxsR8aTa
3lwKXlO16DWpJm8VuZUDbq4ie7F9X1evJy7EL8CBvQj1r8eTjWdx3gBWo1e0r1bY
JOzrThkDm9hUmTpT2076XtC1ANKCMeBM3WDlId0CAwEAAaMhMB8wHQYDVR0OBBYE
FAg/LHBLAsn3WiUjOe8vHBp4JNZ7MA0GCSqGSIb3DQEBCwUAA4IBAQBGHjq0e/Kk
P8BYCPrKO0yMn/CTI0GaFgbQEb6zrIp3W5yQR0xV7NmCdg6iYzu+CenCKvibv1pe
ljJcAhMb9ZF4HqXITAGq0zMQfEnTMIjmzS/cJWI7D6wrQ/v3jeyxoc/+sPcZbC4Y
tiPhufZZYWk5/RvsrtOQBT7eCPjJQm4eO2AMokq+nITm/V4k4ogDuKdxYsURQA+p
L9madHXx/+OMZWWUsg0uhoFsmr4XB0+/dCrsbf7LCg1nvcz65qOJ5Cf78YVTn9U0
A0Q6zIYwGRh6Hv1ynfTJ3CTd1IZztwUEToiqXWQPa1ybYMQ9SFcskDjFvHUZzfAN
mzszx/aJ1D91
-----END CERTIFICATE-----
"""

# Our SteamLinkQ1 class (payload/SteamLinkQ1.smali, assembled with smali).
CLASSES2_DEX = base64.b64decode('''
ZGV4CjAzOQC22+z0VdzYCdFMVGTDHg2gRJ0lfO4v2ZNkBQAAcAAAAHhWNBIAAAAAAAAAANAEAAAf
AAAAcAAAAAwAAADsAAAACgAAABwBAAAAAAAAAAAAAAwAAACUAQAAAQAAAPQBAABQAwAAFAIAABQC
AAAcAgAAHwIAACQCAAAnAgAAKwIAAEoCAABrAgAAhQIAAJoCAACuAgAA1wIAAAIDAAAWAwAAKgMA
ADcDAABJAwAATAMAAFADAABVAwAAWAMAAFwDAACAAwAAiAMAAJYDAACkAwAApwMAALIDAADGAwAA
1QMAAAMEAAABAAAABQAAAAYAAAAHAAAACAAAAAkAAAAKAAAACwAAAAwAAAANAAAAEAAAABMAAAAC
AAAAAAAAACAEAAADAAAAAQAAAAAAAAAEAAAAAQAAABgEAAADAAAAAgAAAAAAAAADAAAABAAAAAAA
AAADAAAACQAAAAAAAAAQAAAACgAAAAAAAAARAAAACgAAADAEAAASAAAACgAAACgEAAAUAAAACwAA
ABAEAAABAAEAGgAAAAEAAgAbAAAAAQAEAB4AAAACAAUAFwAAAAMAAwAYAAAABQAAABkAAAAGAAYA
AAAAAAYABwAcAAAABwAGAAAAAAAHAAcAHAAAAAcACAAcAAAACQAJABYAAAAHAAAAAQAAAAYAAAAA
AAAADwAAAAAAAADABAAAAAAAAAY8aW5pdD4AAUkAA0lMTAABTAACTEkAHUxhbmRyb2lkL2FwcC9B
Y3Rpdml0eU9wdGlvbnM7AB9MYW5kcm9pZC9jb250ZW50L0NvbXBvbmVudE5hbWU7ABhMYW5kcm9p
ZC9jb250ZW50L0ludGVudDsAE0xhbmRyb2lkL29zL0J1bmRsZTsAEkxhbmRyb2lkL3V0aWwvTG9n
OwAnTGNvbS92YWx2ZXNvZnR3YXJlL3N0ZWFtbGluay9TdGVhbUxpbms7AClMY29tL3ZhbHZlc29m
dHdhcmUvc3RlYW1saW5rL1N0ZWFtTGlua1ExOwASTGphdmEvbGFuZy9PYmplY3Q7ABJMamF2YS9s
YW5nL1N0cmluZzsAC1N0ZWFtTGlua1ExABBTdGVhbUxpbmtRMS5qYXZhAAFWAAJWTAADVkxMAAFa
AAJaTAAiY29tLnZhbHZlc29mdHdhcmUuc3RlYW1saW5rLlZSTGluawAGZXF1YWxzAAxnZXRDbGFz
c05hbWUADGdldENvbXBvbmVudAABaQAJbWFrZUJhc2ljABJzZXRMYXVuY2hEaXNwbGF5SWQADXN0
YXJ0QWN0aXZpdHkALHN0YXJ0QWN0aXZpdHk6IGxhdW5jaGluZyBWUkxpbmsgb24gZGlzcGxheSAw
AAh0b0J1bmRsZQAAAAABAAAACAAAAAEAAAAAAAAAAgAAAAkACQACAAAAAwAEAAEAAAADAAAAAAAA
AAEAAQABAAAAAAAAAAQAAABwEAYAAAAOAAQAAgADAAAAAAAAAC4AAABuEAQAAwAMADgAJgBuEAMA
AAAMABoBFQBuIAsAAQAKADgAGgAaAA4AGgEdAHEgBQAQAHEAAAAAAAwAEgFuIAEAEAAMAG4QAgAA
AAwAbjAKADIADgBvIAcAMgAOAAAAAQEIgYAEvAgJAdQIAAAMAAAAAAAAAAEAAAAAAAAAAQAAAB8A
AABwAAAAAgAAAAwAAADsAAAAAwAAAAoAAAAcAQAABQAAAAwAAACUAQAABgAAAAEAAAD0AQAAAiAA
AB8AAAAUAgAAARAAAAUAAAAQBAAAAxAAAAEAAAA4BAAAASAAAAIAAAA8BAAAACAAAAEAAADABAAA
ABAAAAEAAADQBAAA
''')

ACTIVITY = 'com.valvesoftware.steamlink.SteamLink'
ACTIVITY_Q1 = 'com.valvesoftware.steamlink.SteamLinkQ1'
SIGNATURE_FILE = re.compile(r'^META-INF/[^/]+\.(SF|RSA|DSA|EC|MF)$', re.I)

# Device names the Quest 1 runtime knows (from its libvrapiimpl.so).
QUEST1_KNOWN_DEVICES = ('quest', 'quest2', 'questpro')


class PatchError(Exception):
    pass


def log(msg):
    print(msg, flush=True)


# --- Platform and folders ---------------------------------------------------

def host_os():
    if sys.platform.startswith('win'):
        return 'windows'
    if sys.platform == 'darwin':
        return 'mac'
    return 'linux'


def cache_dir():
    """Downloaded tools; safe to delete."""
    if 'QUEST1_PATCHER_CACHE' in os.environ:
        return Path(os.environ['QUEST1_PATCHER_CACHE'])
    if host_os() == 'windows':
        return Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'quest1-patcher' / 'cache'
    if host_os() == 'mac':
        return Path.home() / 'Library' / 'Caches' / 'quest1-patcher'
    return Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'quest1-patcher'


# --- Downloads ----------------------------------------------------------------

def urlopen(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'quest1-patcher'}))


def download(url, dest, algo, digest):
    """Download url to dest, checking its hash. Skips if dest already matches."""
    if dest.exists() and file_hash(dest, algo) == digest:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + '.part')
    log(f'  downloading {url}')
    with urlopen(url) as resp, open(tmp, 'wb') as out:
        total = int(resp.headers.get('Content-Length') or 0)
        done = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if total and sys.stdout.isatty():
                print(f'\r  {done * 100 // total:3d}% of {total >> 20} MB', end='', flush=True)
    if total and sys.stdout.isatty():
        print()
    got = file_hash(tmp, algo)
    if got != digest:
        tmp.unlink()
        raise PatchError(f'checksum mismatch for {url}\n  expected {digest}\n  got      {got}')
    tmp.replace(dest)
    return dest


def file_hash(path, algo):
    h = hashlib.new(algo)
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def find_adb():
    """adb from PATH if installed, else Google's platform-tools."""
    found = shutil.which('adb')
    if found:
        return Path(found)
    exe = 'adb.exe' if host_os() == 'windows' else 'adb'
    adb = cache_dir() / 'platform-tools' / exe
    if adb.exists():
        return adb
    log('Getting adb (Android platform-tools)...')
    url, sha1 = PLATFORM_TOOLS[host_os()]
    archive = download(url, cache_dir() / 'downloads' / url.rsplit('/', 1)[1], 'sha1', sha1)
    with zipfile.ZipFile(archive) as z:
        z.extractall(cache_dir())
    archive.unlink()
    if host_os() != 'windows':
        for f in adb.parent.iterdir():
            f.chmod(0o755)
    return adb


def run(cmd, **kw):
    cmd = [str(c) for c in cmd]
    result = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if result.returncode != 0:
        raise PatchError(f'command failed: {" ".join(cmd)}\n{result.stdout}{result.stderr}')
    return result.stdout



# --- Finding the APK ----------------------------------------------------------

def steam_roots():
    roots = []
    if host_os() == 'windows':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as k:
                roots.append(Path(winreg.QueryValueEx(k, 'SteamPath')[0]))
        except OSError:
            pass
        for env in ('ProgramFiles(x86)', 'ProgramFiles'):
            if env in os.environ:
                roots.append(Path(os.environ[env]) / 'Steam')
    else:
        home = Path.home()
        roots += [home / '.local/share/Steam', home / '.steam/steam',
                  home / '.var/app/com.valvesoftware.Steam/.local/share/Steam',
                  home / 'Library/Application Support/Steam']
    return [r for r in roots if r.is_dir()]


def steam_libraries(root):
    """The Steam root plus any extra library folders it lists."""
    libs = [root]
    vdf = root / 'steamapps' / 'libraryfolders.vdf'
    if vdf.exists():
        for m in re.finditer(r'"path"\s+"([^"]+)"', vdf.read_text(errors='replace')):
            libs.append(Path(m.group(1).replace('\\\\', '\\')))
    return libs


def find_steamvr_apk():
    for root in steam_roots():
        for lib in steam_libraries(root):
            apk = lib / STEAMVR_APK
            if apk.exists():
                return apk
    return None


# --- Patches -------------------------------------------------------------------

RES_STRING_POOL_TYPE = 0x0001
RES_XML_START_ELEMENT_TYPE = 0x0102
UTF8_FLAG = 0x100


def _read_len(buf, pos, utf8):
    if utf8:
        n = buf[pos]
        if n & 0x80:
            return ((n & 0x7F) << 8) | buf[pos + 1], pos + 2
        return n, pos + 1
    n = struct.unpack_from('<H', buf, pos)[0]
    if n & 0x8000:
        return ((n & 0x7FFF) << 16) | struct.unpack_from('<H', buf, pos + 2)[0], pos + 4
    return n, pos + 2


def _encode_string(s, utf8):
    def len8(n):
        return bytes([n]) if n < 0x80 else bytes([0x80 | (n >> 8), n & 0xFF])
    if utf8:
        b = s.encode('utf-8')
        return len8(len(s)) + len8(len(b)) + b + b'\x00'
    b = s.encode('utf-16-le')
    n = len(b) // 2
    head = struct.pack('<H', n) if n < 0x8000 else struct.pack('<HH', 0x8000 | (n >> 16), n & 0xFFFF)
    return head + b + b'\x00\x00'


def read_string_pool(axml):
    """Parse a binary manifest's string pool: (strings, pool info)."""
    _, file_hdr, _ = struct.unpack_from('<HHI', axml, 0)
    pos = file_hdr
    ctype, chdr, csize = struct.unpack_from('<HHI', axml, pos)
    if ctype != RES_STRING_POOL_TYPE:
        raise PatchError('manifest: first chunk is not a string pool')
    count, style_count, flags, strings_start, _ = struct.unpack_from('<IIIII', axml, pos + 8)
    if style_count:
        raise PatchError('manifest: string pool has styles; not handled')
    pool = axml[pos:pos + csize]
    utf8 = bool(flags & UTF8_FLAG)
    strings = []
    for off in struct.unpack_from(f'<{count}I', pool, chdr):
        p = strings_start + off
        if utf8:
            _, p = _read_len(pool, p, True)
            blen, p = _read_len(pool, p, True)
            strings.append(pool[p:p + blen].decode('utf-8'))
        else:
            clen, p = _read_len(pool, p, False)
            strings.append(pool[p:p + clen * 2].decode('utf-16-le'))
    return strings, (pos, ctype, chdr, csize, count, flags, utf8, pool)


def manifest_version(axml):
    """versionName from the <manifest> element of a binary manifest."""
    strings, (pos, _, _, csize, _, _, _, _) = read_string_pool(axml)
    pos += csize
    while pos < len(axml):
        ctype, chdr, csize = struct.unpack_from('<HHI', axml, pos)
        if ctype == RES_XML_START_ELEMENT_TYPE:
            name = struct.unpack_from('<I', axml, pos + 20)[0]
            attr_start, attr_size, attr_count = struct.unpack_from('<HHH', axml, pos + 24)
            if strings[name] == 'manifest':
                for i in range(attr_count):
                    a = pos + 16 + attr_start + i * attr_size
                    aname, raw = struct.unpack_from('<II', axml, a + 4)
                    if strings[aname] == 'versionName' and raw != 0xFFFFFFFF:
                        return strings[raw]
                return 'unknown'
        pos += csize
    return 'unknown'


def patch_manifest(axml):
    """Edit a binary manifest's string pool: cut the com.oculus.supportedDevices
    list down to names the Quest 1 runtime knows, and point the launcher
    activity at our SteamLinkQ1 subclass."""
    file_type, file_hdr, _ = struct.unpack_from('<HHI', axml, 0)
    strings, (pos, ctype, chdr, csize, count, flags, utf8, pool) = read_string_pool(axml)

    lists = [i for i, s in enumerate(strings)
             if '|' in s and all(re.fullmatch(r'quest\w*', t) for t in s.split('|'))]
    if len(lists) != 1:
        raise PatchError(f'manifest: expected one supportedDevices list, found {len(lists)}')
    old = strings[lists[0]]
    kept = [d for d in old.split('|') if d in QUEST1_KNOWN_DEVICES]
    new = '|'.join(['quest'] + [d for d in kept if d != 'quest'])
    strings[lists[0]] = new
    log(f'  supportedDevices: {old} -> {new}')

    acts = [i for i, s in enumerate(strings) if s == ACTIVITY]
    if len(acts) != 1:
        raise PatchError(f'manifest: expected the {ACTIVITY} activity once, found {len(acts)}')
    strings[acts[0]] = ACTIVITY_Q1
    log('  launcher activity: SteamLinkQ1 (starts the VR part on display 0)')

    data = b''
    offsets = []
    for s in strings:
        offsets.append(len(data))
        data += _encode_string(s, utf8)
    data += b'\x00' * (-len(data) % 4)
    new_start = chdr + 4 * count
    new_pool = struct.pack('<HHIIIIII', ctype, chdr, new_start + len(data),
                           count, 0, flags, new_start, 0)
    new_pool += pool[struct.calcsize('<HHIIIIII'):chdr]
    new_pool += struct.pack(f'<{count}I', *offsets) + data
    body = axml[8:pos] + new_pool + axml[pos + csize:]
    return struct.pack('<HHI', file_type, file_hdr, 8 + len(body)) + body


HMD_ANCHOR = '    "unknown": {\n'

HMD_ENTRY = """\
    "vr_monterey": {
      "sTrackingSystem": "oculus",
      "sSerialNumber": "VRLINKHMDQUEST1",
      "sManufacturerName": "Oculus",
      "sModelNumber": "Oculus Quest",
      "sRenderModelName": "generic_hmd",
      "sResourceRoot": "vrlink",
      "sInputProfilePath": "{oculus}/input/rift_profile.json",
      "flLaserMouseHmdAngleDegrees": 0,
      "sControllerType": "rift",
      "sDeviceType": "oculus/VRLINKHMDQUEST1"
    },
"""

CONTROLLER_REPLACEMENTS = [
    ('"VRLINKQ2_Controller_Left"', '"VRLINKQ1_Controller_Left"'),
    ('"VRLINKQ2_Controller_Right"', '"VRLINKQ1_Controller_Right"'),
    ('"oculus/VRLINKQ2_Controller_Left"', '"oculus/VRLINKQ1_Controller_Left"'),
    ('"oculus/VRLINKQ2_Controller_Right"', '"oculus/VRLINKQ1_Controller_Right"'),
    ('"Oculus Quest2 (Left Controller)"', '"Oculus Quest (Left Controller)"'),
    ('"Oculus Quest2 (Right Controller)"', '"Oculus Quest (Right Controller)"'),
    ('"oculus_quest2_controller_left"', '"oculus_quest_controller_left"'),
    ('"oculus_quest2_controller_right"', '"oculus_quest_controller_right"'),
]



def patch_hmd_config(data):
    """hmd_config.json: add a "vr_monterey" (Quest 1) entry with the Quest 2's
    technical values."""
    text = data.decode('utf-8')
    if '"vr_monterey"' not in text:
        if text.count(HMD_ANCHOR) != 1:
            raise PatchError('hmd_config.json: expected exactly one "unknown" entry')
        text = text.replace(HMD_ANCHOR, HMD_ENTRY + HMD_ANCHOR)
    json.loads(text)
    return text.encode('utf-8')


def patch_controller_config(data):
    """controller_config.json: the oculus/touch_controller profile gets SteamVR's
    Quest 1 Touch render models and names; input bindings (oculus_touch,
    touch_profile.json) are unchanged."""
    text = data.decode('utf-8')
    for old, new in CONTROLLER_REPLACEMENTS:
        if text.count(old) != 1:
            raise PatchError(f'controller_config.json: expected one {old}')
        text = text.replace(old, new)
    json.loads(text)
    return text.encode('utf-8')


# --- Signing (APK v1 / JAR signature, pure Python) ---------------------------------
# META-INF/MANIFEST.MF, QUEST1.SF and QUEST1.RSA (PKCS #7 detached signature
# over the .SF, SHA-256 with RSA). v1 is enough for the Quest 1 (Android 10).

def _der_read(buf, pos):
    """Read one DER TLV at pos: (tag, content_start, end)."""
    tag = buf[pos]
    n = buf[pos + 1]
    pos += 2
    if n & 0x80:
        size = n & 0x7F
        n = int.from_bytes(buf[pos:pos + size], 'big')
        pos += size
    return tag, pos, pos + n


def _der_children(buf, start, end):
    out = []
    while start < end:
        tag, cstart, cend = _der_read(buf, start)
        out.append((tag, start, cstart, cend))
        start = cend
    return out


def _der(tag, content):
    n = len(content)
    if n < 0x80:
        length = bytes([n])
    else:
        b = n.to_bytes((n.bit_length() + 7) // 8, 'big')
        length = bytes([0x80 | len(b)]) + b
    return bytes([tag]) + length + content


def _der_oid(dotted):
    parts = [int(p) for p in dotted.split('.')]
    out = bytes([40 * parts[0] + parts[1]])
    for p in parts[2:]:
        enc = [p & 0x7F]
        p >>= 7
        while p:
            enc.append(0x80 | (p & 0x7F))
            p >>= 7
        out += bytes(reversed(enc))
    return _der(0x06, out)


def _pem_body(pem, label):
    m = re.search(rf'-----BEGIN {label}-----(.+?)-----END {label}-----', pem, re.S)
    if not m:
        raise PatchError(f'no {label} in the PEM')
    return base64.b64decode(''.join(m.group(1).split()))


class SigningKey:
    """An RSA key (PKCS #8) plus its X.509 certificate, from PEM."""

    def __init__(self, key_pem, cert_pem):
        der = _pem_body(key_pem, 'PRIVATE KEY')
        _, s, e = _der_read(der, 0)                       # PrivateKeyInfo
        octets = _der_children(der, s, e)[2]              # privateKey OCTET STRING
        _, s, e = _der_read(der, octets[2])               # RSAPrivateKey
        ints = [int.from_bytes(der[cs:ce], 'big') for _, _, cs, ce in _der_children(der, s, e)]
        _, self.n, self.e, self.d, self.p, self.q, self.dp, self.dq, self.qinv = ints[:9]
        self.cert = _pem_body(cert_pem, 'CERTIFICATE')
        _, s, e = _der_read(self.cert, 0)                 # Certificate
        _, tbs_start, ts, te = _der_children(self.cert, s, e)[0]
        fields = _der_children(self.cert, ts, te)         # TBSCertificate
        if fields[0][0] == 0xA0:                          # [0] version
            fields = fields[1:]
        serial, issuer, spki = fields[0], fields[2], fields[5]
        self.serial_der = self.cert[serial[1]:serial[3]]
        self.issuer_der = self.cert[issuer[1]:issuer[3]]
        # SubjectPublicKeyInfo: AlgorithmIdentifier, BIT STRING { RSAPublicKey { n, e } }
        bits = _der_children(self.cert, spki[2], spki[3])[1]
        _, s, e = _der_read(self.cert, bits[2] + 1)       # skip the unused-bits byte
        cert_n = _der_children(self.cert, s, e)[0]
        if int.from_bytes(self.cert[cert_n[2]:cert_n[3]], 'big') != self.n:
            raise PatchError("the private key doesn't match the certificate")

    @classmethod
    def from_pem_text(cls, text):
        key = re.search(r'-----BEGIN PRIVATE KEY-----.+?-----END PRIVATE KEY-----', text, re.S)
        cert = re.search(r'-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----', text, re.S)
        if not key or not cert:
            raise PatchError('expected a PKCS #8 private key and a certificate in PEM format')
        return cls(key.group(0), cert.group(0))

    def sign_sha256(self, data):
        """RSASSA-PKCS1-v1_5 with SHA-256."""
        k = (self.n.bit_length() + 7) // 8
        digest_info = bytes.fromhex('3031300d060960864801650304020105000420') + hashlib.sha256(data).digest()
        em = b'\x00\x01' + b'\xff' * (k - 3 - len(digest_info)) + b'\x00' + digest_info
        m = int.from_bytes(em, 'big')
        # CRT: s = m^d mod n
        s1, s2 = pow(m, self.dp, self.p), pow(m, self.dq, self.q)
        s = s2 + self.q * ((self.qinv * (s1 - s2)) % self.p)
        return s.to_bytes(k, 'big')

    def pkcs7_detached(self, content):
        """PKCS #7 SignedData over content (detached), no signed attributes,
        as jarsigner writes it."""
        sha256 = _der(0x30, _der_oid('2.16.840.1.101.3.4.2.1') + b'\x05\x00')
        rsa = _der(0x30, _der_oid('1.2.840.113549.1.1.1') + b'\x05\x00')
        signer_info = _der(0x30, _der(0x02, b'\x01')
                           + _der(0x30, self.issuer_der + self.serial_der)
                           + sha256 + rsa + _der(0x04, self.sign_sha256(content)))
        signed_data = _der(0x30, _der(0x02, b'\x01')
                           + _der(0x31, sha256)
                           + _der(0x30, _der_oid('1.2.840.113549.1.7.1'))
                           + _der(0xA0, self.cert)
                           + _der(0x31, signer_info))
        return _der(0x30, _der_oid('1.2.840.113549.1.7.2') + _der(0xA0, signed_data))


def _manifest_line(text):
    """Manifest lines are at most 72 bytes including CRLF; longer ones continue
    on the next line after a single space."""
    data = text.encode('utf-8')
    parts, i, width = [], 0, 70
    while i < len(data):
        end = min(i + width, len(data))
        while end < len(data) and (data[end] & 0xC0) == 0x80:   # don't split a UTF-8 character
            end -= 1
        parts.append((b' ' if parts else b'') + data[i:end])
        i, width = end, 69
    return b'\r\n'.join(parts) + b'\r\n'


def sign_and_write(entries, key, out):
    """Write entries [(name, data, stored)] to out as a v1-signed APK."""
    created = b'Created-By: 1.0 (quest1-steamlink-patcher)\r\n'
    b64 = lambda d: base64.b64encode(hashlib.sha256(d).digest())
    mf = b'Manifest-Version: 1.0\r\n' + created + b'\r\n'
    sf_entries = b''
    for name, data, _ in entries:
        section = _manifest_line('Name: ' + name) + b'SHA-256-Digest: ' + b64(data) + b'\r\n\r\n'
        mf += section
        sf_entries += _manifest_line('Name: ' + name) + b'SHA-256-Digest: ' + b64(section) + b'\r\n\r\n'
    sf = (b'Signature-Version: 1.0\r\n' + created + b'SHA-256-Digest-Manifest: ' + b64(mf)
          + b'\r\n\r\n' + sf_entries)
    rsa = key.pkcs7_detached(sf)

    date = (2026, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(out, 'w') as z:
        for name, data, stored in [('META-INF/MANIFEST.MF', mf, False), ('META-INF/QUEST1.SF', sf, False),
                                   ('META-INF/QUEST1.RSA', rsa, False)] + list(entries):
            info = zipfile.ZipInfo(name, date_time=date)
            info.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)


# --- Build, sign, install -------------------------------------------------------

def inspect_apk(apk):
    """(version, already_patched). An APK already patched and signed by this
    script or the web page has META-INF/QUEST1.SF and can be installed as is."""
    try:
        with zipfile.ZipFile(apk) as z:
            names = z.namelist()
            if 'AndroidManifest.xml' not in names:
                raise PatchError('not an APK: no AndroidManifest.xml')
            return manifest_version(z.read('AndroidManifest.xml')), 'META-INF/QUEST1.SF' in names
    except zipfile.BadZipFile as e:
        raise PatchError(f'not a valid APK (zip): {e}')


def build_patched_apk(src_apk, out_dir, key):
    version, _ = inspect_apk(src_apk)
    log(f'Steam Link VR {version}. Patching:')
    entries = []
    with zipfile.ZipFile(src_apk) as z:
        names = z.namelist()
        if 'classes.dex' not in names:
            raise PatchError('not an APK: no classes.dex')
        if 'classes2.dex' in names:
            raise PatchError('this APK already has classes2.dex; is it already patched?')
        patches = {
            'AndroidManifest.xml': patch_manifest,
            'assets/config/hmd_config.json': patch_hmd_config,
            'assets/config/controller_config.json': patch_controller_config,
        }
        for missing in set(patches) - set(names):
            raise PatchError(f'{missing} not found in the APK')
        for info in z.infolist():
            name = info.filename
            if SIGNATURE_FILE.match(name) or name.endswith('/'):
                continue
            data = z.read(name)
            if name in patches:
                data = patches[name](data)
            entries.append((name, data, info.compress_type == zipfile.ZIP_STORED))
    entries.append(('classes2.dex', CLASSES2_DEX, False))
    log('  headset and controllers: identify as Oculus Quest (Quest 1)')

    log('Signing...')
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f'steamlinkvr-{version}-quest1.apk'
    sign_and_write(entries, key, out)
    log(f'Wrote {out}')
    return out


def adb_devices(adb):
    out = run([adb, 'devices'])
    devices = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            devices.append((parts[0], parts[1]))
    return devices


def pick_device(adb, serial):
    devices = adb_devices(adb)
    if serial:
        devices = [d for d in devices if d[0] == serial]
    if not devices:
        raise PatchError('no headset found over adb. Plug the Quest in by USB, make sure '
                         'developer mode is on, put the headset on and allow USB debugging.')
    unauthorized = [s for s, state in devices if state == 'unauthorized']
    ready = [s for s, state in devices if state == 'device']
    if not ready and unauthorized:
        raise PatchError('the headset hasn\'t allowed this computer yet. Put it on and accept '
                         'the "Allow USB debugging" prompt (tick "Always allow").')
    if len(ready) > 1:
        raise PatchError(f'several devices connected ({", ".join(ready)}); pick one with --serial')
    if not ready:
        raise PatchError(f'device not ready: {devices}')
    return ready[0]


def install(adb, serial, apk, assume_yes, force_device):
    a = [adb, '-s', serial]
    device = run(a + ['shell', 'getprop', 'ro.product.device']).strip()
    if device != 'monterey' and not force_device:
        raise PatchError(f'the connected device is "{device}", not a Quest 1 ("monterey"). '
                         'Use --force-device to install anyway.')
    log(f'Installing on {serial} ({device})...')
    result = subprocess.run([str(x) for x in a + ['install', '-r', apk]],
                            capture_output=True, text=True)
    output = result.stdout + result.stderr
    if result.returncode == 0 and 'Success' in output:
        log('Installed. Open Steam Link from Unknown Sources in your app library.')
        return
    if 'INSTALL_FAILED_UPDATE_INCOMPATIBLE' in output:
        log('The Steam Link already on the headset was signed with a different key, so it\n'
            'has to be uninstalled first. You will need to pair with your PC again.')
        if not assume_yes and input('Uninstall it and continue? [y/N] ').strip().lower() != 'y':
            raise PatchError('not installed; the patched APK is still saved above')
        run(a + ['uninstall', PACKAGE])
        run(a + ['install', apk])
        log('Installed. Open Steam Link from Unknown Sources and pair with your PC.')
        return
    raise PatchError(f'install failed:\n{output}')


def main():
    p = argparse.ArgumentParser(description='Patch Steam Link VR for the original Oculus Quest.')
    p.add_argument('--apk', type=Path, help='Steam Link APK to patch (default: from your SteamVR install)')
    p.add_argument('--output-dir', type=Path, default=Path.cwd(), help='where to save the patched APK')
    p.add_argument('--no-install', action='store_true', help="only build the APK, don't install it")
    p.add_argument('--serial', help='adb serial of the headset, if several devices are connected')
    p.add_argument('--connect', metavar='HOST:PORT',
                   help='headset on adb over Wi-Fi (after `adb tcpip 5555`); implies --serial')
    p.add_argument('--yes', action='store_true', help="don't ask before uninstalling an old build")
    p.add_argument('--force-device', action='store_true', help='install even if the device is not a Quest 1')
    p.add_argument('--key-pem', type=Path,
                   help="sign with your own key (a PEM file with a PKCS #8 private key and its "
                        "certificate) instead of the project's public key")
    args = p.parse_args()

    try:
        key = (SigningKey.from_pem_text(args.key_pem.read_text()) if args.key_pem
               else SigningKey(SIGNING_KEY_PEM, SIGNING_CERT_PEM))
        apk = args.apk or find_steamvr_apk()
        if not apk:
            raise PatchError("couldn't find SteamVR's Steam Link APK. Install SteamVR, or pass "
                             f'--apk (it is SteamVR/drivers/vrlink/resources/{APK_NAME}).')
        apk = Path(apk)
        log(f'Using {apk}')
        version, already = inspect_apk(apk)
        if already:
            log(f'Steam Link VR {version} is already patched and signed; installing it as it is.')
            out = apk
        else:
            out = build_patched_apk(apk, args.output_dir, key)
        if args.no_install:
            return 0
        adb = find_adb()
        if args.connect:
            log(run([adb, 'connect', args.connect]).strip())
        install(adb, pick_device(adb, args.connect or args.serial), out, args.yes, args.force_device)
        return 0
    except PatchError as e:
        print(f'Error: {e}', file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f'Error: download failed: {e}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    sys.exit(main())
