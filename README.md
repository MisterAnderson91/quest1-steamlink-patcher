# Steam Link VR apk for the original Oculus Quest

Valve's Steam Link VR app doesn't run on the original Oculus Quest
(Quest 1). This script takes the copy of the app that comes with **your own
SteamVR install**, patches it to work on the Quest 1, and installs it on your
headset.

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

## What you need
- An original Oculus Quest with **developer mode** on (enable it in the Meta
  Horizon phone app, under the headset's settings).
- A PC with **SteamVR** installed, running Linux/SteamOS or Windows.
- **Python 3.8 or newer.** On Windows, get it from python.org or the
  Microsoft Store.
- A USB cable for the headset.
- About 200 MB of disk space for the tools the script downloads.

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
Link, which needs patching again.

### Options
- `--no-install`: only build the patched APK (saved in the current folder).
- `--apk PATH`: patch a specific APK instead of looking in your SteamVR
  install (useful if Steam is somewhere unusual, or to patch on another
  computer). In SteamVR it's at
  `SteamVR/drivers/vrlink/resources/android-steamlinkvr-release.apk`.
- `--connect HOST:PORT`: install over adb on Wi-Fi instead of USB.
- `--keystore`, `--key-alias`, `--key-pass`: sign with an existing key.
- `--help` lists everything.

## What it does
1. Finds `android-steamlinkvr-release.apk` in your SteamVR install.
2. Downloads its tools into a cache folder, checking each against a
   published checksum: a Java runtime (Eclipse Temurin 17), apktool,
   apksigner (Android build-tools) and, if you don't have it, adb.
3. Applies three patches:
   - **Supported devices:** the Quest 1 crashes on device names it doesn't
     know ("Unknown device to support: quest3"), so the app's device list is
     cut down to names it knows.
   - **Display 0:** the Quest 1 leaves the VR part of the app on the 2D
     window's hidden screen, so the stream never shows. The app now opens it
     on the main display.
   - **Quest 1 identity:** the headset and controllers identify as an Oculus
     Quest, so SteamVR shows the right controller models.
4. Signs the app with a key created on your computer, and installs it with
   adb.

## Your signing key
The first run creates a signing key:
- Linux: `~/.local/share/quest1-patcher/`
- Windows: `%APPDATA%\quest1-patcher\`

**Keep it.** Updates must be signed with the same key to install over the
existing app. With a different key, the old app has to be uninstalled first
(the script asks), and you'll need to pair with your PC again.

## Removing it
- The downloaded tools: delete the cache folder.
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
