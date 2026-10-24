// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Gregory Anderson
//
// A minimal adb client over WebUSB: connect + authenticate, run shell
// commands, push a file with the sync protocol, and install an APK.
// (An off-the-shelf WebUSB adb library hung on the Quest 1 before sending
// its first packet; this speaks the protocol directly.)
// Needs node-forge (window.forge) for the RSA key and signature.

const forge = globalThis.forge;
export const PACKAGE = 'com.valvesoftware.steamlinkvr';
const REMOTE_APK = '/data/local/tmp/quest1-steamlink-patched.apk';
const ADB_KEY_STORAGE = 'quest1-patcher-adb-key';
const ADB_VERSION = 0x01000001;
const MAX_DATA = 256 * 1024;

const cmd = (s) => [...s].reduce((v, ch, i) => v | (ch.charCodeAt(0) << (8 * i)), 0) >>> 0;
const A_CNXN = cmd('CNXN'), A_AUTH = cmd('AUTH'), A_OPEN = cmd('OPEN');
const A_OKAY = cmd('OKAY'), A_CLSE = cmd('CLSE'), A_WRTE = cmd('WRTE');
const AUTH_TOKEN = 1, AUTH_SIGNATURE = 2, AUTH_RSAPUBLICKEY = 3;

const utf8 = new TextEncoder();
const fromUtf8 = new TextDecoder();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

class Disconnected extends Error {}

export function webUsbSupported() {
  return !!navigator.usb;
}

// --- adb key -------------------------------------------------------------------

async function adbKey() {
  const stored = localStorage.getItem(ADB_KEY_STORAGE);
  if (stored) return forge.pki.privateKeyFromPem(stored);
  const pair = await crypto.subtle.generateKey(
    { name: 'RSASSA-PKCS1-v1_5', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256' },
    true, ['sign', 'verify']);
  const pkcs8 = new Uint8Array(await crypto.subtle.exportKey('pkcs8', pair.privateKey));
  const key = forge.pki.privateKeyFromAsn1(forge.asn1.fromDer(String.fromCharCode(...pkcs8)));
  localStorage.setItem(ADB_KEY_STORAGE, forge.pki.privateKeyToPem(key));
  return key;
}

// adb signs the 20-byte token as if it were a SHA-1 digest (PKCS #1 v1.5).
function signToken(key, token) {
  const md = { algorithm: 'sha1', digest: () => forge.util.createBuffer(String.fromCharCode(...token)) };
  return Uint8Array.from(key.sign(md), (c) => c.charCodeAt(0));
}

// Android's adb public key: base64 of { u32 words, u32 n0inv, u32 n[64],
// u32 rr[64], u32 e } (little-endian), then " user@host".
function publicKeyBytes(key) {
  const { BigInteger } = forge.jsbn;
  const words = 64;
  const b32 = BigInteger.ONE.shiftLeft(32);
  const n = key.n;
  const n0inv = b32.subtract(n.mod(b32).modInverse(b32)).mod(b32);
  const rr = BigInteger.ONE.shiftLeft(32 * words * 2).mod(n);
  const v = new DataView(new ArrayBuffer(4 * (3 + 2 * words)));
  v.setUint32(0, words, true);
  v.setUint32(4, n0inv.intValue() >>> 0, true);
  const mask = BigInteger.ONE.shiftLeft(32).subtract(BigInteger.ONE);
  for (let i = 0; i < words; i++) {
    v.setUint32(8 + 4 * i, n.shiftRight(32 * i).and(mask).intValue() >>> 0, true);
    v.setUint32(8 + 4 * words + 4 * i, rr.shiftRight(32 * i).and(mask).intValue() >>> 0, true);
  }
  v.setUint32(8 + 8 * words, key.e.intValue() >>> 0, true);
  let bin = '';
  for (const b of new Uint8Array(v.buffer)) bin += String.fromCharCode(b);
  return utf8.encode(btoa(bin) + ' quest1-patcher@browser\0');
}

// --- Transport -----------------------------------------------------------------

class AdbUsb {
  constructor(device, iface, inEp, outEp) {
    this.device = device;
    this.iface = iface;
    this.inEp = inEp;
    this.outEp = outEp;
    this.maxData = MAX_DATA;
    this.nextLocalId = 1;
  }

  async send(command, arg0, arg1, data = new Uint8Array()) {
    const h = new DataView(new ArrayBuffer(24));
    const sum = data.reduce((a, b) => a + b, 0) >>> 0;
    [command, arg0 >>> 0, arg1 >>> 0, data.length, sum, (command ^ 0xffffffff) >>> 0]
      .forEach((x, i) => h.setUint32(i * 4, x, true));
    await this.device.transferOut(this.outEp.endpointNumber, h.buffer);
    if (data.length) {
      await this.device.transferOut(this.outEp.endpointNumber, data);
      // A transfer that is an exact multiple of the packet size needs a
      // zero-length packet to end it.
      if (data.length % this.outEp.packetSize === 0) {
        await this.device.transferOut(this.outEp.endpointNumber, new Uint8Array());
      }
    }
  }

  async read() {
    const h = await this.device.transferIn(this.inEp.endpointNumber, 24);
    if (h.status !== 'ok' || h.data.byteLength !== 24) throw new Error(`bad adb header (${h.status}, ${h.data.byteLength} bytes)`);
    const v = h.data;
    const msg = { command: v.getUint32(0, true), arg0: v.getUint32(4, true), arg1: v.getUint32(8, true), data: new Uint8Array() };
    const len = v.getUint32(12, true);
    if (len) {
      const parts = [];
      let got = 0;
      while (got < len) {
        const r = await this.device.transferIn(this.inEp.endpointNumber, len - got);
        const chunk = new Uint8Array(r.data.buffer, r.data.byteOffset, r.data.byteLength);
        parts.push(chunk);
        got += chunk.length;
      }
      msg.data = parts.length === 1 ? parts[0] : Uint8Array.from(parts.flatMap((p) => [...p]));
    }
    return msg;
  }

  /** Read until a message for local stream id `local` arrives. */
  async readFor(local) {
    for (;;) {
      const m = await this.read();
      if (m.arg1 === local && (m.command === A_OKAY || m.command === A_WRTE || m.command === A_CLSE)) return m;
      if (m.command === A_WRTE) await this.send(A_OKAY, m.arg1, m.arg0); // stray stream data
    }
  }

  async connect(log) {
    await this.send(A_CNXN, ADB_VERSION, MAX_DATA, utf8.encode('host::\0'));
    const key = await adbKey();
    let sentSignature = false;
    let sentPublicKey = false;
    for (;;) {
      const m = await this.read();
      if (m.command === A_CNXN) {
        this.maxData = Math.min(MAX_DATA, m.arg1);
        return fromUtf8.decode(m.data);
      }
      if (m.command !== A_AUTH || m.arg0 !== AUTH_TOKEN) continue;
      if (!sentSignature) {
        sentSignature = true;
        await this.send(A_AUTH, AUTH_SIGNATURE, 0, signToken(key, m.data));
      } else if (!sentPublicKey) {
        sentPublicKey = true;
        log('Put the headset on and accept "Allow USB debugging" (tick "Always allow").');
        await this.send(A_AUTH, AUTH_RSAPUBLICKEY, 0, publicKeyBytes(key));
      }
    }
  }

  /** Run a shell command and return its output. */
  async shell(args) {
    const local = this.nextLocalId++;
    const command = args.map((a) => (/^[\w./:=-]+$/.test(a) ? a : `'${a.replace(/'/g, "'\\''")}'`)).join(' ');
    await this.send(A_OPEN, local, 0, utf8.encode(`shell:${command}\0`));
    let output = '';
    for (;;) {
      const m = await this.readFor(local);
      if (m.command === A_WRTE) {
        output += fromUtf8.decode(m.data, { stream: true });
        await this.send(A_OKAY, local, m.arg0);
      } else if (m.command === A_CLSE) {
        await this.send(A_CLSE, local, m.arg0);
        return output.trim();
      }
    }
  }

  /** Push bytes to a file on the device (adb sync SEND). */
  async push(path, bytes, progress) {
    const local = this.nextLocalId++;
    await this.send(A_OPEN, local, 0, utf8.encode('sync:\0'));
    let m = await this.readFor(local);
    if (m.command !== A_OKAY) throw new Error('the headset refused the file transfer');
    const remote = m.arg0;
    let reply = new Uint8Array(); // sync replies from the headset
    const takeReply = async (msg) => {
      reply = Uint8Array.from([...reply, ...msg.data]);
      await this.send(A_OKAY, local, msg.arg0);
    };
    // Send one WRTE and wait for its OKAY (adb flow control). The headset may
    // send its own WRTE (a sync reply) first.
    const write = async (data) => {
      await this.send(A_WRTE, local, remote, data);
      for (;;) {
        const ack = await this.readFor(local);
        if (ack.command === A_OKAY) return;
        if (ack.command === A_WRTE) { await takeReply(ack); continue; }
        throw new Error(`file transfer interrupted: ${fromUtf8.decode(reply.subarray(8))}`);
      }
    };
    const syncHeader = (id, n) => {
      const b = new Uint8Array(8);
      b.set(utf8.encode(id));
      new DataView(b.buffer).setUint32(4, n, true);
      return b;
    };
    const spec = utf8.encode(`${path},${0o100644}`);
    await write(Uint8Array.from([...syncHeader('SEND', spec.length), ...spec]));
    const chunk = Math.min(64 * 1024, this.maxData - 8);
    for (let i = 0; i < bytes.length; i += chunk) {
      const part = bytes.subarray(i, i + chunk);
      const msg = new Uint8Array(8 + part.length);
      msg.set(syncHeader('DATA', part.length));
      msg.set(part, 8);
      await write(msg);
      progress?.(Math.min(i + chunk, bytes.length) / bytes.length);
    }
    await write(syncHeader('DONE', Math.floor(Date.now() / 1000)));
    while (reply.length < 8) {
      m = await this.readFor(local);
      if (m.command === A_WRTE) await takeReply(m);
      else if (m.command === A_CLSE) break;
    }
    const id = fromUtf8.decode(reply.subarray(0, 4));
    if (id !== 'OKAY') throw new Error(`copying failed: ${fromUtf8.decode(reply.subarray(8))}`);
    await write(syncHeader('QUIT', 0)).catch(() => {});
  }

  /**
   * Ask adbd to restart as root ("adb root") and reconnect once it's back.
   * Returns true if adbd is now root; false if this headset doesn't allow it.
   */
  async restartAsRoot(log) {
    const local = this.nextLocalId++;
    const device = this.device;
    const gone = waitForDisconnect(device);
    await this.send(A_OPEN, local, 0, utf8.encode('root:\0'));
    let reply = '';
    try {
      for (;;) {
        const m = await this.readFor(local);
        if (m.command === A_WRTE) {
          reply += fromUtf8.decode(m.data);
          await this.send(A_OKAY, local, m.arg0);
        } else if (m.command === A_CLSE) {
          await this.send(A_CLSE, local, m.arg0);
          break;
        }
      }
    } catch {} // adbd restarting drops the connection mid-reply
    if (/already running as root/i.test(reply)) return true;
    if (!/restarting/i.test(reply)) return false;
    log('Restarting adb on the headset as root...');
    await gone;
    await this.close();
    await sleep(1500);
    const fresh = await handshake(await waitForDevice(device.serialNumber), log);
    Object.assign(this, fresh); // keep using this object, now on the new connection
    return true;
  }

  async close() {
    try { await this.device.releaseInterface(this.iface.interfaceNumber); } catch {}
    try { await this.device.close(); } catch {}
  }
}

// --- Connecting ----------------------------------------------------------------

const ADB_FILTER = { classCode: 0xff, subclassCode: 0x42, protocolCode: 1 };

async function open(device) {
  await device.open();
  if (device.configuration === null) await device.selectConfiguration(1);
  for (const iface of device.configuration.interfaces) {
    for (const alt of iface.alternates) {
      if (alt.interfaceClass === ADB_FILTER.classCode && alt.interfaceSubclass === ADB_FILTER.subclassCode
          && alt.interfaceProtocol === ADB_FILTER.protocolCode) {
        await device.claimInterface(iface.interfaceNumber);
        const inEp = alt.endpoints.find((e) => e.direction === 'in');
        const outEp = alt.endpoints.find((e) => e.direction === 'out');
        return new AdbUsb(device, iface, inEp, outEp);
      }
    }
  }
  throw new Error('the headset has no adb interface; is developer mode on?');
}

async function handshake(device, log) {
  let onDisconnect;
  const disconnected = new Promise((_, reject) => {
    onDisconnect = (e) => { if (e.device === device) reject(new Disconnected('disconnected')); };
    navigator.usb.addEventListener('disconnect', onDisconnect);
  });
  let adb;
  try {
    try {
      adb = await Promise.race([open(device), disconnected]);
    } catch (e) {
      if (e instanceof Disconnected) throw e;
      throw new Error(`couldn't open the headset (${e.message}). If adb or SideQuest is running on this `
        + 'computer, close it (or run "adb kill-server") and try again.');
    }
    log('Connecting to the headset...');
    const banner = await Promise.race([adb.connect(log), disconnected]);
    log(`Connected (${banner.split(';').find((s) => s.startsWith('ro.product.model=')) || 'adb'})`);
    return adb;
  } catch (e) {
    await adb?.close();
    throw e;
  } finally {
    navigator.usb.removeEventListener('disconnect', onDisconnect);
  }
}

/**
 * Ask the user to pick the headset and connect to it.
 *
 * The headset switches USB mode when someone answers its "allow access to
 * files" prompt, which drops it off USB for a moment and breaks a handshake in
 * progress. When that happens, wait for it to come back (same serial number;
 * no new device picker) and try again.
 */
export async function connectHeadset(log) {
  if (!navigator.usb) throw new Error('this browser has no WebUSB; use Chrome, Edge or another Chromium browser');
  let device;
  try {
    device = await navigator.usb.requestDevice({ filters: [ADB_FILTER] });
  } catch {
    throw new Error('no device selected');
  }
  const serial = device.serialNumber;
  for (let attempt = 1; ; attempt++) {
    try {
      return await handshake(device, log);
    } catch (e) {
      if (!(e instanceof Disconnected) || attempt >= 4) throw e;
      log('The headset dropped off USB (it can do this when it switches USB mode). Waiting for it to come back...');
      device = await waitForDevice(serial);
      await sleep(1500);
    }
  }
}

async function waitForDevice(serial, timeoutMs = 30000) {
  for (const end = Date.now() + timeoutMs; Date.now() < end; await sleep(500)) {
    const found = (await navigator.usb.getDevices()).find((d) => d.serialNumber === serial);
    if (found) return found;
  }
  throw new Error("the headset didn't come back on USB. Check the cable, then reload this page and try again.");
}

/** Resolves when `device` drops off USB (or after timeoutMs, as a fallback). */
function waitForDisconnect(device, timeoutMs = 15000) {
  return new Promise((resolve) => {
    const done = () => { navigator.usb.removeEventListener('disconnect', onDisconnect); clearTimeout(timer); resolve(); };
    const onDisconnect = (e) => { if (e.device === device) done(); };
    const timer = setTimeout(done, timeoutMs);
    navigator.usb.addEventListener('disconnect', onDisconnect);
  });
}

// --- Wired-streaming Magisk module ------------------------------------------------

const MODULE_DEST = '/sdcard/Download/q1_steamlink_usb.zip';

const lastLines = (out) => out.split('\n').slice(-2).join(' ').trim() || 'no output';

/**
 * Copy the Magisk module to the headset's Download folder and install it as
 * root: first through "adb root" (headsets set up with
 * androidboot.adb.rootable=1; no prompt), else through Magisk's su (a prompt
 * in the headset). The copy in Download is deleted afterwards. Returns true if
 * installed.
 */
export async function installMagiskModule(adb, zip, log) {
  const device = await adb.shell(['getprop', 'ro.product.device']);
  if (device !== 'monterey') throw new Error(`this device is "${device}"; the module is for the original Quest only`);

  const adbRoot = await adb.restartAsRoot(log);
  log(`Copying the module to the headset (${MODULE_DEST})...`);
  await adb.push(MODULE_DEST, zip);

  let out = '';
  if (adbRoot) {
    log('adb is running as root. Installing with Magisk...');
    out = await adb.shell(['magisk', '--install-module', MODULE_DEST]);
    if (!/- Done/.test(out)) log(`That didn't work: ${lastLines(out)}`);
  } else {
    log("This headset doesn't allow adb root.");
  }
  if (!/- Done/.test(out)) {
    log('Trying Magisk\'s su instead. If the headset asks to allow root for "Shell", allow it.');
    out = await adb.shell(['su', '-c', `magisk --install-module ${MODULE_DEST}`]);
  }
  const installed = /- Done/.test(out);
  if (!installed) {
    log(/not found|inaccessible/i.test(out)
      ? "Magisk's su isn't available on this headset (is Magisk installed?)."
      : `Magisk didn't install it: ${lastLines(out)}`);
  }
  // Magisk keeps its own copy, so the one in Download is no longer needed.
  await adb.shell(['rm', '-f', MODULE_DEST]);
  log('Removed the copy from the headset\'s Download folder.');
  if (installed) log('Installed. Restart the headset to start wired streaming.');
  return installed;
}

// --- Installing ----------------------------------------------------------------

/** Check the device, push the APK and install it. confirm(message) -> bool. */
export async function installApk(adb, apk, log, confirm) {
  const device = await adb.shell(['getprop', 'ro.product.device']);
  if (device !== 'monterey' && !(await confirm(`This device is "${device}", not an original Quest ("monterey"). Install anyway?`))) {
    throw new Error('not installed');
  }

  log('Copying the app to the headset...');
  let shown = 0;
  await adb.push(REMOTE_APK, apk, (f) => {
    if (f * 100 >= shown + 25) { shown = Math.floor(f * 4) * 25; log(`  ${shown}%`); }
  });

  try {
    log('Installing...');
    let out = await adb.shell(['pm', 'install', '-r', REMOTE_APK]);
    if (out.includes('INSTALL_FAILED_UPDATE_INCOMPATIBLE')) {
      const ok = await confirm('The Steam Link already on the headset was signed with a different key, so it has '
        + 'to be uninstalled first. You will need to pair with your PC again. Uninstall it and continue?');
      if (!ok) throw new Error('not installed; you can still download the patched APK');
      log('Uninstalling the old Steam Link...');
      await adb.shell(['pm', 'uninstall', PACKAGE]);
      out = await adb.shell(['pm', 'install', REMOTE_APK]);
    }
    if (!out.includes('Success')) throw new Error(`install failed: ${out}`);
    log('Installed. Open Steam Link from Unknown Sources in your app library.');
  } finally {
    await adb.shell(['rm', '-f', REMOTE_APK]).catch(() => {});
  }
}
