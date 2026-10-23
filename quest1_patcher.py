#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Gregory Anderson
"""Patch Valve's Steam Link VR app so it runs on the original Oculus Quest (Quest 1).

Takes the Steam Link APK from your own SteamVR install, applies three patches,
signs it with the project's public key (so updates install in place), and
installs it on the headset over adb:

  1. supported devices: the Quest 1 runtime aborts on device names it doesn't
     know ("Unknown device to support: quest3"), so the manifest's
     com.oculus.supportedDevices list is cut down to names it knows.
  2. display 0: the Quest 1 leaves the VR activity on the 2D panel's virtual
     display, so it never gets the screen. startVRLink() now launches it on
     display 0.
  3. Quest 1 identity: SteamVR sees the headset as "Oculus Quest" and the
     controllers as Quest 1 Touch models, instead of "unknown" and Quest 2.

Needs only Python 3.8+. On first run it downloads a Java runtime, apktool,
apksigner and (if not installed) adb into a cache folder, checking each
download against a published checksum.

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
import platform
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

PACKAGE = 'com.valvesoftware.steamlinkvr'
APK_NAME = 'android-steamlinkvr-release.apk'
STEAMVR_APK = Path('steamapps', 'common', 'SteamVR', 'drivers', 'vrlink', 'resources', APK_NAME)

APKTOOL_URL = 'https://github.com/iBotPeaches/Apktool/releases/download/v3.0.3/apktool_3.0.3.jar'
APKTOOL_SHA256 = 'dbf930b076c6b9be08d57c449cacefc3bdd6b71ebd59b3066fc0e1f5b14f9423'

# apksigner is a Java program, so the Linux build-tools package works everywhere.
BUILD_TOOLS_URL = 'https://dl.google.com/android/repository/build-tools_r36.1_linux.zip'
BUILD_TOOLS_SHA1 = '936a0d6bd5ae3e2118a7567dddbc95ff67ed46e9'

PLATFORM_TOOLS = {
    'linux': ('https://dl.google.com/android/repository/platform-tools_r37.0.1-linux.zip',
              '477254aa5f903c15cf51001717bdf347fb6b53e0'),
    'windows': ('https://dl.google.com/android/repository/platform-tools_r37.0.1-win.zip',
                'e03e78b1d80b396f1c3358e31251cb31740e1110'),
    'mac': ('https://dl.google.com/android/repository/platform-tools_r37.0.1-darwin.zip',
            '6ae73f4de6452dc57e62ec02b68eed92a4c21661'),
}

JRE_API = ('https://api.adoptium.net/v3/assets/latest/17/hotspot'
           '?architecture={arch}&image_type=jre&os={os}&vendor=eclipse')

# The project's signing key, deliberately public (same as docs/signing-key.pem):
# every patched APK, from this script or the web page, is signed with it, so
# updates install in place from any computer. --keystore signs with your own.
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


def host_arch():
    m = platform.machine().lower()
    if m in ('x86_64', 'amd64'):
        return 'x64'
    if m in ('arm64', 'aarch64'):
        return 'aarch64'
    raise PatchError(f'unsupported CPU architecture: {platform.machine()}')


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
    # Some servers (e.g. api.adoptium.net) reject Python's default user agent.
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


def find_java():
    """A Java 17 runtime from Eclipse Temurin, downloaded on first use."""
    os_name, arch = host_os(), host_arch()
    root = cache_dir() / 'jre'
    exe = 'java.exe' if os_name == 'windows' else 'java'
    for java in root.glob(f'*/**/bin/{exe}'):
        return java
    log('Getting a Java runtime (Eclipse Temurin 17)...')
    with urlopen(JRE_API.format(arch=arch, os=os_name)) as resp:
        package = json.load(resp)[0]['binary']['package']
    archive = download(package['link'], cache_dir() / 'downloads' / package['name'],
                       'sha256', package['checksum'])
    root.mkdir(parents=True, exist_ok=True)
    if archive.name.endswith('.zip'):
        with zipfile.ZipFile(archive) as z:
            z.extractall(root)
    else:
        with tarfile.open(archive) as t:
            if hasattr(tarfile, 'data_filter'):
                t.extractall(root, filter='data')
            else:
                t.extractall(root)
    archive.unlink()
    for java in root.glob(f'*/**/bin/{exe}'):
        if os_name != 'windows':
            java.chmod(0o755)
        return java
    raise PatchError('downloaded Java runtime has no java executable')


def find_apktool():
    return download(APKTOOL_URL, cache_dir() / 'apktool_3.0.3.jar', 'sha256', APKTOOL_SHA256)


def find_apksigner():
    jar = cache_dir() / 'apksigner.jar'
    if jar.exists():
        return jar
    log('Getting apksigner (Android build-tools)...')
    archive = download(BUILD_TOOLS_URL, cache_dir() / 'downloads' / 'build-tools.zip',
                       'sha1', BUILD_TOOLS_SHA1)
    with zipfile.ZipFile(archive) as z:
        name = next(n for n in z.namelist() if n.endswith('/lib/apksigner.jar'))
        jar.write_bytes(z.read(name))
    archive.unlink()
    return jar


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
    if Path(cmd[0]).stem == 'java':
        # Don't let the JVM create /tmp/hsperfdata_<user> (it ignores java.io.tmpdir).
        cmd.insert(1, '-XX:-UsePerfData')
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


def patch_supported_devices(axml):
    """Rewrite the com.oculus.supportedDevices list in a binary manifest.

    Works on the manifest's string pool: finds the one '|'-separated list of
    Quest device names and keeps only names the Quest 1 runtime knows."""
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


LAUNCH_OLD = (
    '    invoke-virtual {p0, v0}, Lcom/valvesoftware/steamlink/SteamLink;'
    '->startActivity(Landroid/content/Intent;)V\n'
)

LAUNCH_NEW = """\
    const-string v1, "SteamLinkQ1"

    const-string v2, "startVRLink: launching on display 0"

    invoke-static {v1, v2}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I

    invoke-static {}, Landroid/app/ActivityOptions;->makeBasic()Landroid/app/ActivityOptions;

    move-result-object v1

    const/4 v2, 0x0

    invoke-virtual {v1, v2}, Landroid/app/ActivityOptions;->setLaunchDisplayId(I)Landroid/app/ActivityOptions;

    move-result-object v1

    invoke-virtual {v1}, Landroid/app/ActivityOptions;->toBundle()Landroid/os/Bundle;

    move-result-object v1

    invoke-virtual {p0, v0, v1}, Lcom/valvesoftware/steamlink/SteamLink;->startActivity(Landroid/content/Intent;Landroid/os/Bundle;)V
"""


def patch_launch_display(decoded):
    """startVRLink(): start the VR activity on display 0, not the 2D panel's
    virtual display, so the Quest 1 shell hands it the screen."""
    smali = decoded / 'smali' / 'com' / 'valvesoftware' / 'steamlink' / 'SteamLink.smali'
    text = smali.read_text(encoding='utf-8')
    start = text.index('.method public startVRLink(Ljava/lang/String;)V')
    end = text.index('.end method', start)
    method = text[start:end]
    if method.count(LAUNCH_OLD) != 1:
        raise PatchError('startVRLink(): expected exactly one startActivity(Intent)')
    if '.locals 4' not in method:
        raise PatchError('startVRLink(): no longer has .locals 4; registers v1/v2 may not be free')
    smali.write_text(text[:start] + method.replace(LAUNCH_OLD, LAUNCH_NEW) + text[end:],
                     encoding='utf-8')
    log('  startVRLink: launches the VR activity on display 0')


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


def patch_device_config(decoded):
    """Headset and controllers show up in SteamVR as a genuine Oculus Quest.

    hmd_config.json gets a "vr_monterey" (Quest 1) entry with the Quest 2's
    technical values. The oculus/touch_controller profile gets SteamVR's Quest 1
    Touch render models and names; input bindings (oculus_touch,
    touch_profile.json) are unchanged."""
    config = decoded / 'assets' / 'config'
    hmd = config / 'hmd_config.json'
    text = hmd.read_text(encoding='utf-8')
    if '"vr_monterey"' not in text:
        if text.count(HMD_ANCHOR) != 1:
            raise PatchError('hmd_config.json: expected exactly one "unknown" entry')
        text = text.replace(HMD_ANCHOR, HMD_ENTRY + HMD_ANCHOR)
    json.loads(text)
    hmd.write_text(text, encoding='utf-8')

    controllers = config / 'controller_config.json'
    text = controllers.read_text(encoding='utf-8')
    for old, new in CONTROLLER_REPLACEMENTS:
        if text.count(old) != 1:
            raise PatchError(f'controller_config.json: expected one {old}')
        text = text.replace(old, new)
    json.loads(text)
    controllers.write_text(text, encoding='utf-8')
    log('  headset and controllers: identify as Oculus Quest (Quest 1)')


# --- Build, sign, install -------------------------------------------------------

def build_patched_apk(src_apk, out_dir, key, keep_work=False):
    java, apktool, apksigner = find_java(), find_apktool(), find_apksigner()
    work = Path(tempfile.mkdtemp(prefix='quest1-patcher-'))
    try:
        decoded = work / 'decoded'
        framework = cache_dir() / 'apktool-framework'
        log('Decoding the APK...')
        run([java, '-jar', apktool, 'd', '-r', '-f', '-p', framework, '-o', decoded, src_apk])
        manifest = decoded / 'AndroidManifest.xml'
        version = manifest_version(manifest.read_bytes())
        log(f'Steam Link VR {version}. Patching:')
        manifest.write_bytes(patch_supported_devices(manifest.read_bytes()))
        patch_launch_display(decoded)
        patch_device_config(decoded)

        log('Rebuilding...')
        unsigned = work / 'unsigned.apk'
        run([java, '-jar', apktool, 'b', '-p', framework, '-o', unsigned, decoded])

        log('Signing...')
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f'steamlinkvr-{version}-quest1.apk'
        # The web page recognises already-patched APKs by META-INF/QUEST1.SF.
        run([java, '-jar', apksigner, 'sign', *signer_args(key, java, work), '--v1-signer-name', 'QUEST1',
             '--v1-signing-enabled', 'true', '--v2-signing-enabled', 'true',
             '--out', out, unsigned])
        run([java, '-jar', apksigner, 'verify', out])
        log(f'Wrote {out}')
        return out
    finally:
        if keep_work:
            log(f'Work folder kept: {work}')
        else:
            shutil.rmtree(work, ignore_errors=True)


def signer_args(key, java, work):
    """apksigner options for --keystore (key = (path, alias, password)), or
    for the built-in project key."""
    if key:
        keystore, alias, password = key
        return ['--ks', keystore, '--ks-key-alias', alias,
                '--ks-pass', f'pass:{password}', '--key-pass', f'pass:{password}']
    # apksigner wants the key as unencrypted PKCS #8 DER.
    body = ''.join(l for l in SIGNING_KEY_PEM.splitlines() if not l.startswith('-----'))
    key_file, cert_file = work / 'signing-key.pk8', work / 'signing-cert.pem'
    key_file.write_bytes(base64.b64decode(body))
    cert_file.write_text(SIGNING_CERT_PEM)
    return ['--key', key_file, '--cert', cert_file]


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
    p.add_argument('--keep-work', action='store_true', help='keep the temporary work folder')
    p.add_argument('--keystore', type=Path,
                   help="sign with your own keystore instead of the project's public key "
                        '(updates then need the same keystore to install in place)')
    p.add_argument('--key-alias', default='quest1', help='key alias in --keystore')
    p.add_argument('--key-pass', default='', help='password of --keystore and its key')
    args = p.parse_args()
    key = (args.keystore, args.key_alias, args.key_pass) if args.keystore else None

    try:
        apk = args.apk or find_steamvr_apk()
        if not apk:
            raise PatchError("couldn't find SteamVR's Steam Link APK. Install SteamVR, or pass "
                             f'--apk (it is SteamVR/drivers/vrlink/resources/{APK_NAME}).')
        log(f'Using {apk}')
        out = build_patched_apk(Path(apk), args.output_dir, key, args.keep_work)
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
