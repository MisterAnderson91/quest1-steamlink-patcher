// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Gregory Anderson
//
// APK v1 (JAR) signing in the browser: META-INF/MANIFEST.MF, QUEST1.SF and
// QUEST1.RSA (PKCS #7 detached signature over the .SF, SHA-256 with RSA).
// v1 is enough for the Quest 1 (Android 10). Needs node-forge (window.forge)
// for X.509 and PKCS #7.

import { zipSync } from 'https://cdn.jsdelivr.net/npm/fflate@0.8.3/esm/browser.js';

const forge = globalThis.forge;
const utf8 = new TextEncoder();
const CREATED_BY = '1.0 (quest1-steamlink-patcher)';

async function sha256Base64(bytes) {
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
  let s = '';
  for (const b of digest) s += String.fromCharCode(b);
  return btoa(s);
}

// Manifest lines are at most 72 bytes including CRLF; longer ones continue on
// the next line after a single space.
function manifestLine(text) {
  const bytes = utf8.encode(text);
  const parts = [];
  let i = 0;
  let max = 70;
  while (i < bytes.length) {
    let end = Math.min(i + max, bytes.length);
    while (end < bytes.length && (bytes[end] & 0xc0) === 0x80) end--; // don't split a UTF-8 character
    parts.push((parts.length ? ' ' : '') + new TextDecoder().decode(bytes.subarray(i, end)));
    i = end;
    max = 69;
  }
  return parts.join('\r\n') + '\r\n';
}

// --- Signing key -------------------------------------------------------------
// Every patched APK is signed with the project's public key (signing-key.pem),
// so updates install in place whichever browser or computer made them.

/** Load the project's signing key: { keyPem, certPem }. */
export async function loadProjectKey(url = 'signing-key.pem') {
  return keyFromPem(await (await fetch(url)).text());
}

export function keyFromPem(text) {
  const keyMatch = text.match(/-----BEGIN (RSA )?PRIVATE KEY-----[\s\S]+?-----END (RSA )?PRIVATE KEY-----/);
  const certMatch = text.match(/-----BEGIN CERTIFICATE-----[\s\S]+?-----END CERTIFICATE-----/);
  if (!keyMatch || !certMatch) throw new Error('expected a private key and a certificate in PEM format');
  const key = { keyPem: keyMatch[0] + '\n', certPem: certMatch[0] + '\n' };
  const privateKey = forge.pki.privateKeyFromPem(key.keyPem);
  const cert = forge.pki.certificateFromPem(key.certPem);
  if (privateKey.n.compareTo(cert.publicKey.n) !== 0) throw new Error("the private key doesn't match the certificate");
  return key;
}

// --- Signing -----------------------------------------------------------------

/** Sign entries ({ name, data, store }) and return the APK as a Uint8Array. */
export async function signApk(entries, key) {
  let mf = 'Manifest-Version: 1.0\r\nCreated-By: ' + CREATED_BY + '\r\n\r\n';
  let sfEntries = '';
  for (const e of entries) {
    const section = manifestLine('Name: ' + e.name) + 'SHA-256-Digest: ' + (await sha256Base64(e.data)) + '\r\n\r\n';
    mf += section;
    sfEntries += manifestLine('Name: ' + e.name) + 'SHA-256-Digest: ' + (await sha256Base64(utf8.encode(section))) + '\r\n\r\n';
  }
  const mfBytes = utf8.encode(mf);
  const sf = 'Signature-Version: 1.0\r\nCreated-By: ' + CREATED_BY + '\r\nSHA-256-Digest-Manifest: '
    + (await sha256Base64(mfBytes)) + '\r\n\r\n' + sfEntries;
  const sfBytes = utf8.encode(sf);

  const privateKey = forge.pki.privateKeyFromPem(key.keyPem);
  const cert = forge.pki.certificateFromPem(key.certPem);
  const p7 = forge.pkcs7.createSignedData();
  let sfBinary = '';
  for (const b of sfBytes) sfBinary += String.fromCharCode(b);
  p7.content = forge.util.createBuffer(sfBinary);
  p7.addCertificate(cert);
  p7.addSigner({ key: privateKey, certificate: cert, digestAlgorithm: forge.pki.oids.sha256 });
  p7.sign({ detached: true });
  const rsaDer = forge.asn1.toDer(p7.toAsn1()).getBytes();
  const rsaBytes = Uint8Array.from(rsaDer, (c) => c.charCodeAt(0));

  const zipFiles = {
    'META-INF/MANIFEST.MF': [mfBytes, { level: 6 }],
    'META-INF/QUEST1.SF': [sfBytes, { level: 6 }],
    'META-INF/QUEST1.RSA': [rsaBytes, { level: 6 }],
  };
  for (const e of entries) zipFiles[e.name] = [e.data, { level: e.store ? 0 : 6 }];
  return zipSync(zipFiles, { mtime: new Date('2026-01-01T00:00:00Z') });
}
