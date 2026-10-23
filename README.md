# Steam Link VR apk for the original Oculus Quest

Valve's Steam Link VR app doesn't run on the original Oculus Quest
(Quest 1). This project takes the copy of the app that comes with **your own
SteamVR install**, patches it to work on the Quest 1, and installs it on your
headset, from a web page or a script.

What you get:
- PC VR streaming from SteamVR to a Quest 1 over Wi-Fi with Steam Link.
- SteamVR sees the headset as an "Oculus Quest" and shows genuine Quest 1
  Touch controllers.

Tested with Steam Link VR 2.0.20 and 2.0.24, streaming from SteamOS
(Steam Machine) to a Quest 1 on its final firmware.

> **Windows testers wanted.** The script is written to support Windows, but
> nobody has tried it there yet. If you have a Quest 1 and a Windows PC with
> SteamVR, please give it a go and
> [open an issue](../../issues) with how it went, whether it worked or not,
> and include the script's output.

## Before you start (web page or script)
1. **Turn on developer mode** for the headset. You need a Meta developer
   account that belongs to a verified developer organization; then, in the
   Meta Horizon phone app, signed in with that account: headset icon → your
   headset → **Headset Settings** → **Developer Mode** → on. Full steps:
   [Meta's guide](https://developers.meta.com/horizon/documentation/android-apps/enable-developer-mode/).
2. Use a **data** USB-C cable. Charge-only cables don't work.
3. **Windows only:** install Meta's
   [Oculus ADB Drivers](https://developers.meta.com/horizon/downloads/package/oculus-adb-drivers/):
   unzip, then right-click `android_winusb.inf` → Install.
4. The first time a computer (or browser) connects, the headset asks to
   **allow USB debugging**. Put it on, tick "Always allow from this
   computer" and accept.

Meta no longer supports the Quest 1. If the Developer Mode switch doesn't
appear for yours in today's Horizon app, please
[open an issue](../../issues) so we can document it.

## Easiest: the web page
**https://misteranderson91.github.io/quest1-steamlink-patcher/**

Patches and installs from Chrome, Edge or another Chromium browser, with
nothing to install: choose the APK from your SteamVR folder, patch, plug the
headset in and install. Everything happens in your browser.

The rest of this README covers the command-line script, which does the same
on Linux/SteamOS and Windows.

## What you need
- An original Oculus Quest with **developer mode** on (see
  [Before you start](#before-you-start-web-page-or-script)).
- A PC with **SteamVR** installed, running Linux/SteamOS or Windows.
- **Python 3.8 or newer.** On Windows, get it from python.org or the
  Microsoft Store. Nothing else: no Java, no Android SDK.
- A USB-C data cable for the headset.
- adb, if you have it. If not, the script downloads Google's platform-tools
  (about 10 MB) the first time it installs.

## Use
1. Plug the headset into your PC and put it on. If it asks to **allow USB
   debugging**, tick "Always allow" and accept.
2. Download `quest1_patcher.py` and run it:
   ```
   python3 quest1_patcher.py
   ```
   On Windows use `python quest1_patcher.py` (or `py quest1_patcher.py`).
3. On the headset, open **Steam Link** from **Unknown Sources** in your app
   library, pick your PC and pair.
4. Start SteamVR on your PC, then connect from the headset.

After a SteamVR update, run the script again. SteamVR can ship a newer Steam
Link, which needs patching again. Give it an APK that's already patched (by the
script or the web page) and it just installs it.

### Options
- `--no-install`: only build the patched APK (saved in the current folder).
- `--apk PATH`: patch a specific APK instead of looking in your SteamVR
  install (useful if Steam is somewhere unusual, or to patch on another
  computer). In SteamVR it's at
  `SteamVR/drivers/vrlink/resources/android-steamlinkvr-release.apk`.
- `--connect HOST:PORT`: install over adb on Wi-Fi instead of USB.
- `--key-pem FILE`: sign with your own key instead of the project's (a PEM
  file holding a PKCS #8 private key and its certificate).
- `--help` lists everything.

## What it does
1. Finds `android-steamlinkvr-release.apk` in your SteamVR install.
2. Applies three patches. Valve's own code isn't modified; everything else
   in the app is copied unchanged:
   - **Supported devices:** the Quest 1 crashes on device names it doesn't
     know ("Unknown device to support: quest3"), so the app's device list is
     cut down to names it knows.
   - **Display 0:** the Quest 1 leaves the VR part of the app on the 2D
     window's hidden screen, so the stream never shows. A small extra class of
     ours ([payload/SteamLinkQ1.smali](payload/SteamLinkQ1.smali), added as
     `classes2.dex`) opens it on the main display instead.
   - **Quest 1 identity:** the headset and controllers identify as an Oculus
     Quest, so SteamVR shows the right controller models.
3. Signs the app with the project's public key (see [Signing](#signing)), and
   installs it with adb, downloading adb first if you don't have it.

## Signing
Every patched APK, from the script or the web page, is signed with the same
key, which is deliberately public ([docs/signing-key.pem](docs/signing-key.pem)).
That way an update always installs over the existing app and keeps your
pairing, whichever computer or browser made it.

The trade-off: anyone can sign an app with this key, and Android would accept
it as an update to Steam Link. Only install Steam Link builds you patched
yourself. If you'd rather use your own key, pass `--key-pem` to the script.

Switching from a build signed with a different key needs one uninstall (the
script and page offer it), and then pairing with your PC again.

## Removing it
- adb, if the script downloaded it: delete the cache folder.
  - Linux: `~/.cache/quest1-patcher/`
  - Windows: `%LOCALAPPDATA%\quest1-patcher\`
- The app on the headset: `adb uninstall com.valvesoftware.steamlinkvr`, or
  uninstall it from the headset's app library.

## Known issues
- **Wired (USB) streaming doesn't work.** The Quest 1 can't present the USB
  network that Steam Link's wired mode needs. Use Wi-Fi.
- **Minimizing the 2D window can leave it stuck.** On the Quest 1, a
  minimized panel sometimes won't come back. This is a bug in the Quest 1
  system software (it also hits Meta's own panels). Reboot the headset, or
  restart its shell with `adb shell am force-stop com.oculus.vrshell`.

## License
MIT, see [LICENSE](LICENSE).

## Legal
Not affiliated with Valve or Meta. Steam Link and SteamVR are Valve's. This
script doesn't include or redistribute Valve's app: it patches the copy from
your own SteamVR install, on your computer, for your own headset.
