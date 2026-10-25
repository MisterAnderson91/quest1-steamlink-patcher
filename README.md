# Steam Link VR apk for the original Oculus Quest

Valve's Steam Link VR app doesn't run on the original Oculus Quest
(Quest 1). This project takes the copy of the app that comes with **your own
SteamVR install**, patches it to work on the Quest 1, and installs it on your
headset, from a web page or a script.

What you get:
- PC VR streaming from SteamVR to a Quest 1 over Wi-Fi with Steam Link.
- Optional wired streaming over USB, for rooted headsets with Magisk (see
  [Wired streaming](#wired-streaming-rooted-headsets-only)).
- SteamVR sees the headset as an "Oculus Quest" and shows genuine Quest 1
  Touch controllers.

Tested with Steam Link VR 2.0.20 and 2.0.24 on a Quest 1 on its final
firmware (V50), streaming from SteamOS. Community members have it working
too, including the script on Windows 11 and with a 90 Hz mod.

Found a problem, or got it working on a setup not mentioned here?
[Open an issue](../../issues) and include the script's output or the web
page's log. For problems on the headset, save its log with the web page's
"Connect and save log" button right after it happens.

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

The page can also install the wired-streaming module, fix a stuck Steam Link
window, and save the headset's log for a bug report.

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
2. Applies these patches. Apart from the in-VR panel fix, Valve's own code
   isn't modified; everything else in the app is copied unchanged:
   - **Supported devices:** the Quest 1 crashes on device names it doesn't
     know ("Unknown device to support: quest3"), so the app's device list is
     cut down to names it knows.
   - **Display 0:** the Quest 1 leaves the VR part of the app on the 2D
     window's hidden screen, so the stream never shows. A small extra class
     added to the app ([payload/SteamLinkQ1.smali](payload/SteamLinkQ1.smali),
     as `classes2.dex`) opens it on the main display instead.
   - **Quest 1 identity:** the headset and controllers identify as an Oculus
     Quest, so SteamVR shows the right controller models.
   - **In-VR panels:** the warnings, loading and error panels inside VR are
     small web pages, and the Quest 1's built-in browser is too old for their
     scripts, so they showed up blank with buttons that didn't work. Their
     scripts are rewritten to work on it, and a 5-byte fix in the app's native
     library stops it crashing when a panel button is used. If a future Steam
     Link changes that library, this fix is skipped and the output says so.
3. Signs the app with the project's public key (see [Signing](#signing)), and
   installs it with adb, downloading adb first if you don't have it.

## Wired streaming (rooted headsets only)
The Quest 1 can't do Steam Link's wired mode by itself: its USB network mode
is locked away. On a headset with an unlocked bootloader, root and
**Magisk**, a small Magisk module from this project
([magisk-module/](magisk-module/)) turns it on. Steam Link then streams over
the cable with Wi-Fi as a backup, or over the cable alone with Wi-Fi off.
Wireless streaming works without any of this.

- Needs: an original Quest on its final firmware, bootloader unlocked (e.g.
  with QuestStack, which **wipes the headset**), Magisk installed, and the
  patched Steam Link.
- Install it from the [web page](https://misteranderson91.github.io/quest1-steamlink-patcher/)
  ("Copy to headset and install"), or download
  [q1_steamlink_usb.zip](docs/q1_steamlink_usb.zip) and install it in the
  Magisk app (Modules → Install from storage), then restart the headset.
- Your PC needs no setup: the headset gives it an address on the cable
  automatically (headset `10.86.13.37`, PC `10.86.13.38`). Tested streaming
  from SteamOS; Windows should work (it has the USB network driver built in)
  but is untested.
- To remove it: Magisk app → Modules → remove, then restart.

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
- **Wired (USB) streaming needs root.** Stock headsets can't present the USB
  network that Steam Link's wired mode needs, so they stream over Wi-Fi only.
  See [Wired streaming](#wired-streaming-rooted-headsets-only).
- **Minimizing the 2D window can leave it stuck or blank.** On the Quest 1, a
  minimized panel sometimes won't come back. This is a bug in the Quest 1
  system software (it also hits Meta's own panels). Restart the headset, use
  "Connect and fix the window" on the web page, or run
  `adb shell am force-stop com.oculus.vrshell`.
- **Stuck on "Connecting", or a black screen with loading dots:** SteamVR on
  the PC may be stuck from an earlier session. Quit SteamVR and connect
  again; if it won't quit, restart the PC (on Linux, `pkill -9 vrserver`
  also works).

## License
MIT, see [LICENSE](LICENSE).

## Legal
Not affiliated with Valve or Meta. Steam Link and SteamVR are Valve's. This
script doesn't include or redistribute Valve's app: it patches the copy from
your own SteamVR install, on your computer, for your own headset.
