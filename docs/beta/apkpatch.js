// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Gregory Anderson
//
// Patch Steam Link VR for the Quest 1 without touching Valve's code:
//   - manifest: cut com.oculus.supportedDevices down to names the Quest 1
//     runtime knows, and point the launcher activity at our subclass
//     com.valvesoftware.steamlink.SteamLinkQ1 (in classes2.dex), which
//     starts the VR activity on display 0
//   - assets/config: a Quest 1 headset entry and Quest 1 Touch controllers
// Everything else is copied byte-for-byte.

import { unzipSync } from 'https://cdn.jsdelivr.net/npm/fflate@0.8.3/esm/browser.js';

const ACTIVITY = 'com.valvesoftware.steamlink.SteamLink';
const ACTIVITY_Q1 = 'com.valvesoftware.steamlink.SteamLinkQ1';
const QUEST1_KNOWN_DEVICES = ['quest', 'quest2', 'questpro'];
const SIGNATURE_FILE = /^META-INF\/[^/]+\.(SF|RSA|DSA|EC|MF)$/i;

export class PatchError extends Error {}

const utf8 = new TextEncoder();
const fromUtf8 = new TextDecoder();

// --- Binary manifest string pool ---------------------------------------------

const RES_STRING_POOL_TYPE = 0x0001;
const RES_XML_START_ELEMENT_TYPE = 0x0102;
const UTF8_FLAG = 0x100;

function readLen(buf, pos, isUtf8) {
  if (isUtf8) {
    const n = buf[pos];
    return n & 0x80 ? [((n & 0x7f) << 8) | buf[pos + 1], pos + 2] : [n, pos + 1];
  }
  const v = new DataView(buf.buffer, buf.byteOffset);
  const n = v.getUint16(pos, true);
  return n & 0x8000 ? [((n & 0x7fff) << 16) | v.getUint16(pos + 2, true), pos + 4] : [n, pos + 2];
}

function readStringPool(axml) {
  const v = new DataView(axml.buffer, axml.byteOffset, axml.byteLength);
  const pos = v.getUint16(2, true);
  const type = v.getUint16(pos, true);
  const hdr = v.getUint16(pos + 2, true);
  const size = v.getUint32(pos + 4, true);
  if (type !== RES_STRING_POOL_TYPE) throw new PatchError('manifest: first chunk is not a string pool');
  const count = v.getUint32(pos + 8, true);
  const styles = v.getUint32(pos + 12, true);
  const flags = v.getUint32(pos + 16, true);
  const stringsStart = v.getUint32(pos + 20, true);
  if (styles) throw new PatchError('manifest: string pool has styles; not handled');
  const pool = axml.subarray(pos, pos + size);
  const isUtf8 = !!(flags & UTF8_FLAG);
  const strings = [];
  for (let i = 0; i < count; i++) {
    let p = stringsStart + v.getUint32(pos + hdr + 4 * i, true);
    if (isUtf8) {
      [, p] = readLen(pool, p, true);
      let blen;
      [blen, p] = readLen(pool, p, true);
      strings.push(fromUtf8.decode(pool.subarray(p, p + blen)));
    } else {
      let clen;
      [clen, p] = readLen(pool, p, false);
      strings.push(new TextDecoder('utf-16le').decode(pool.subarray(p, p + clen * 2)));
    }
  }
  return { strings, pos, hdr, size, count, flags, isUtf8, pool };
}

function encodeString(s, isUtf8) {
  if (isUtf8) {
    const len8 = (n) => (n < 0x80 ? [n] : [0x80 | (n >> 8), n & 0xff]);
    const b = utf8.encode(s);
    return Uint8Array.from([...len8(s.length), ...len8(b.length), ...b, 0]);
  }
  const out = [];
  const n = s.length;
  if (n < 0x8000) out.push(n & 0xff, n >> 8);
  else out.push((0x8000 | (n >> 16)) & 0xff, (0x8000 | (n >> 16)) >> 8, n & 0xff, (n >> 8) & 0xff);
  for (let i = 0; i < n; i++) out.push(s.charCodeAt(i) & 0xff, s.charCodeAt(i) >> 8);
  out.push(0, 0);
  return Uint8Array.from(out);
}

function concat(parts) {
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let o = 0;
  for (const p of parts) { out.set(p, o); o += p.length; }
  return out;
}

function writeStringPool(axml, sp, strings) {
  const encoded = strings.map((s) => encodeString(s, sp.isUtf8));
  let dataLen = encoded.reduce((n, e) => n + e.length, 0);
  const pad = -dataLen & 3;
  const newStart = sp.hdr + 4 * sp.count;
  const header = new Uint8Array(newStart);
  const hv = new DataView(header.buffer);
  header.set(sp.pool.subarray(0, sp.hdr)); // type/size fields fixed below; keeps any extra header bytes
  hv.setUint16(0, RES_STRING_POOL_TYPE, true);
  hv.setUint16(2, sp.hdr, true);
  hv.setUint32(4, newStart + dataLen + pad, true);
  hv.setUint32(8, sp.count, true);
  hv.setUint32(12, 0, true);
  hv.setUint32(16, sp.flags, true);
  hv.setUint32(20, newStart, true);
  hv.setUint32(24, 0, true);
  let off = 0;
  encoded.forEach((e, i) => { hv.setUint32(sp.hdr + 4 * i, off, true); off += e.length; });
  const pool = concat([header, ...encoded, new Uint8Array(pad)]);
  const rest = axml.subarray(sp.pos + sp.size);
  const out = concat([axml.subarray(0, sp.pos), pool, rest]);
  new DataView(out.buffer).setUint32(4, out.length, true);
  return out;
}

export function manifestVersion(axml) {
  const sp = readStringPool(axml);
  const v = new DataView(axml.buffer, axml.byteOffset, axml.byteLength);
  let pos = sp.pos + sp.size;
  while (pos < axml.length) {
    const type = v.getUint16(pos, true);
    const size = v.getUint32(pos + 4, true);
    if (type === RES_XML_START_ELEMENT_TYPE && sp.strings[v.getUint32(pos + 20, true)] === 'manifest') {
      const attrStart = v.getUint16(pos + 24, true);
      const attrSize = v.getUint16(pos + 26, true);
      const attrCount = v.getUint16(pos + 28, true);
      for (let i = 0; i < attrCount; i++) {
        const a = pos + 16 + attrStart + i * attrSize;
        const raw = v.getUint32(a + 8, true);
        if (sp.strings[v.getUint32(a + 4, true)] === 'versionName' && raw !== 0xffffffff) return sp.strings[raw];
      }
      return 'unknown';
    }
    pos += size;
  }
  return 'unknown';
}

function patchManifest(axml, log) {
  const sp = readStringPool(axml);
  const strings = [...sp.strings];

  const lists = strings.map((s, i) => i).filter((i) => {
    const s = strings[i];
    return s.includes('|') && s.split('|').every((t) => /^quest\w*$/.test(t));
  });
  if (lists.length !== 1) throw new PatchError(`manifest: expected one supportedDevices list, found ${lists.length}`);
  const old = strings[lists[0]];
  const kept = old.split('|').filter((d) => QUEST1_KNOWN_DEVICES.includes(d) && d !== 'quest');
  strings[lists[0]] = ['quest', ...kept].join('|');
  log(`supportedDevices: ${old} -> ${strings[lists[0]]}`);

  const acts = strings.map((s, i) => i).filter((i) => strings[i] === ACTIVITY);
  if (acts.length !== 1) throw new PatchError(`manifest: expected the ${ACTIVITY} activity once, found ${acts.length}`);
  strings[acts[0]] = ACTIVITY_Q1;
  log('launcher activity: SteamLinkQ1 (starts the VR part on display 0)');

  return writeStringPool(axml, sp, strings);
}

// --- Config JSON ---------------------------------------------------------------

const HMD_ANCHOR = '    "unknown": {\n';
const HMD_ENTRY = `    "vr_monterey": {
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
`;

const CONTROLLER_REPLACEMENTS = [
  ['"VRLINKQ2_Controller_Left"', '"VRLINKQ1_Controller_Left"'],
  ['"VRLINKQ2_Controller_Right"', '"VRLINKQ1_Controller_Right"'],
  ['"oculus/VRLINKQ2_Controller_Left"', '"oculus/VRLINKQ1_Controller_Left"'],
  ['"oculus/VRLINKQ2_Controller_Right"', '"oculus/VRLINKQ1_Controller_Right"'],
  ['"Oculus Quest2 (Left Controller)"', '"Oculus Quest (Left Controller)"'],
  ['"Oculus Quest2 (Right Controller)"', '"Oculus Quest (Right Controller)"'],
  ['"oculus_quest2_controller_left"', '"oculus_quest_controller_left"'],
  ['"oculus_quest2_controller_right"', '"oculus_quest_controller_right"'],
];

function count(text, s) {
  return text.split(s).length - 1;
}

function patchHmdConfig(bytes) {
  let text = fromUtf8.decode(bytes);
  if (!text.includes('"vr_monterey"')) {
    if (count(text, HMD_ANCHOR) !== 1) throw new PatchError('hmd_config.json: expected exactly one "unknown" entry');
    text = text.replace(HMD_ANCHOR, HMD_ENTRY + HMD_ANCHOR);
  }
  JSON.parse(text);
  return utf8.encode(text);
}

function patchControllerConfig(bytes) {
  let text = fromUtf8.decode(bytes);
  for (const [old, now] of CONTROLLER_REPLACEMENTS) {
    if (count(text, old) !== 1) throw new PatchError(`controller_config.json: expected one ${old}`);
    text = text.replace(old, now);
  }
  JSON.parse(text);
  return utf8.encode(text);
}

// The in-VR panels (preflight warnings, loading, dashboard) are web pages shown
// in the system WebView. The Quest 1's is Chrome 74, which can't parse optional
// chaining (Chrome 80+), so every script, including the shared ipc.js that
// fills in the text and handles laser clicks, fails to load: blank panels with
// dead buttons. Rewrite each `x?.y` as `(x == null ? {} : x).y`.
const WEBUI_JS = /^assets\/webui\/.+\.js$/;
const OPTIONAL_CHAIN = /(?<=[\w$)\]])\?\.(?!\d)/;

function receiverStart(text, end) {
  let i = end;
  while (i > 0) {
    const c = text[i - 1];
    if (c === ')' || c === ']') {
      let depth = 0;
      while (i > 0) {
        i--;
        if (text[i] === ')' || text[i] === ']') depth++;
        else if (text[i] === '(' || text[i] === '[') {
          depth--;
          if (depth === 0) break;
        }
      }
      if (depth) throw new PatchError('webui: unbalanced brackets before ?.');
    } else if (/[\w$.]/.test(c)) {
      i--;
    } else {
      break;
    }
  }
  return i;
}

// The scripts send messages back to libvrlink_scene.so, whose WebView thread
// reads them off its Looper queue by poking at the WebView's own classes:
// newer WebViews (obfuscated z5/U4/Z5) have the encoded message in a byte[]
// field "a"; otherwise it expects msg.obj to be a Pair whose first has a String
// field "b". On Chrome 74, Pair.first is the encoded byte[] itself, so that
// lookup aborts the app (JNI "fid == null") as soon as the page sends anything,
// e.g. a haptic when the laser touches a button. Patch the Pair branch to hand
// Pair.first straight to the byte[] decoder.
const WEBVIEW_LIB = 'lib/arm64-v8a/libvrlink_scene.so';
const WEBVIEW_PAIR_BRANCH = hex(
  '605e40f9' +   // ldr x0, [x19, #0xb8]     env
  'e10319aa' +   // mov x1, x25              msg.obj (the Pair)
  '620a40f9' +   // ldr x2, [x19, #0x10]     Pair.first field id
  '080040f9087d41f900013fd6' +  // env->GetObjectField
  'f90300aa' +   // mov x25, x0              -> mov x26, x0
  '605e40f9');   // ldr x0, [x19, #0xb8]     -> b <byte[] decoder>
const WEBVIEW_BYTES_DECODER = hex(
  '605e40f9' +   // ldr x0, [x19, #0xb8]
  'e1031aaa' +   // mov x1, x26              the byte[]
  '080040f908ad42f900013fd6');  // env->GetArrayLength

function hex(s) {
  return Uint8Array.from(s.match(/../g), (b) => parseInt(b, 16));
}

function findAll(data, pattern) {
  const found = [];
  for (let i = data.indexOf(pattern[0]); i >= 0 && i <= data.length - pattern.length; i = data.indexOf(pattern[0], i + 1)) {
    let j = 1;
    while (j < pattern.length && data[i + j] === pattern[j]) j++;
    if (j === pattern.length) found.push(i);
  }
  return found;
}

/** Returns the patched library, or null if Valve's code has changed. */
function patchWebviewLib(data) {
  const pair = findAll(data, WEBVIEW_PAIR_BRANCH);
  const dec = findAll(data, WEBVIEW_BYTES_DECODER);
  if (pair.length !== 1 || dec.length !== 1) return null;
  const distance = dec[0] - (pair[0] + 28);
  if (!(distance > 0 && distance < 1 << 27)) return null;
  const out = data.slice();
  const view = new DataView(out.buffer);
  view.setUint32(pair[0] + 24, 0xaa0003fa, true);                  // mov x26, x0
  view.setUint32(pair[0] + 28, 0x14000000 | (distance / 4), true); // b decoder
  return out;
}

function patchWebuiJs(bytes) {
  let text = fromUtf8.decode(bytes);
  for (let m; (m = OPTIONAL_CHAIN.exec(text));) {
    const after = m.index + 2;
    if (text[after] === '(') throw new PatchError('webui: optional call x?.() is not supported');
    const start = receiverStart(text, m.index);
    const recv = text.slice(start, m.index);
    const dot = text[after] === '[' ? '' : '.';
    text = `${text.slice(0, start)}(${recv} == null ? {} : ${recv})${dot}${text.slice(after)}`;
  }
  return utf8.encode(text);
}

// --- APK ---------------------------------------------------------------------

/**
 * Inspect an APK without patching it: { version, patched }. patched is true
 * for an APK already patched and signed by this page or quest1_patcher.py
 * (both sign as META-INF/QUEST1.SF); it can be installed as it is.
 */
export function inspectApk(apkBytes) {
  const names = [];
  let files;
  try {
    files = unzipSync(apkBytes, { filter: (f) => { names.push(f.name); return f.name === 'AndroidManifest.xml'; } });
  } catch (e) {
    throw new PatchError(`not a valid APK (zip): ${e.message}`);
  }
  if (!files['AndroidManifest.xml']) throw new PatchError('not an APK: no AndroidManifest.xml');
  return {
    version: manifestVersion(files['AndroidManifest.xml']),
    patched: names.includes('META-INF/QUEST1.SF'),
  };
}

/**
 * Patch a Steam Link VR APK. Returns { version, entries }, where entries is an
 * ordered list of { name, data, store } (store: keep uncompressed), without
 * any old signature files. Sign with apksign.js before installing.
 */
export function patchApk(apkBytes, classes2Dex, log = () => {}) {
  const compression = {};
  let files;
  try {
    files = unzipSync(apkBytes, { filter: (f) => { compression[f.name] = f.compression; return true; } });
  } catch (e) {
    throw new PatchError(`not a valid APK (zip): ${e.message}`);
  }
  const manifest = files['AndroidManifest.xml'];
  if (!manifest || !files['classes.dex']) throw new PatchError('not an APK: no AndroidManifest.xml or classes.dex');
  if ('classes2.dex' in files) throw new PatchError('this APK already has classes2.dex; is it already patched?');

  const version = manifestVersion(manifest);
  log(`Steam Link VR ${version}`);

  const patched = {
    'AndroidManifest.xml': patchManifest(manifest, log),
    'assets/config/hmd_config.json': patchHmdConfig(files['assets/config/hmd_config.json'] || new Uint8Array()),
    'assets/config/controller_config.json': patchControllerConfig(files['assets/config/controller_config.json'] || new Uint8Array()),
  };
  log('headset and controllers: identify as Oculus Quest (Quest 1)');
  const webviewLib = files[WEBVIEW_LIB] && patchWebviewLib(files[WEBVIEW_LIB]);
  if (webviewLib) {
    patched[WEBVIEW_LIB] = webviewLib;
    for (const name of Object.keys(files)) {
      if (WEBUI_JS.test(name)) patched[name] = patchWebuiJs(files[name]);
    }
    log('in-VR panels: made to work with the Quest 1 WebView');
  } else {
    log('in-VR panels: NOT patched (unknown libvrlink_scene.so); they stay blank');
  }

  const entries = [];
  for (const name of Object.keys(files)) {
    if (SIGNATURE_FILE.test(name) || name.endsWith('/')) continue;
    entries.push({ name, data: patched[name] || files[name], store: compression[name] === 0 });
  }
  entries.push({ name: 'classes2.dex', data: classes2Dex, store: false });
  return { version, entries };
}
