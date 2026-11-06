# ChessMatch

Compares chess openings against each other. A custom heuristic plays each
opening's model of target squares (in priority order, adapting when the
opponent deviates) for the first 8 half-moves, then hands the game to Stockfish.

## Desktop

```bash
python3 -m venv venv
pip install -r requirements.txt
python main.py
```

The app finds Stockfish anywhere on your `PATH` (via `shutil.which`). If it is
not installed, install it first, e.g. `apt install stockfish` or grab a binary
from https://stockfishchess.org/download/ and put it on your PATH.

Tests (no GUI needed):

```bash
python -m unittest test_openings
```

## Android (buildozer)

### NixOS-specific setup (this machine)

The Android SDK's binaries (aapt2/zipalign etc.) need a normal Linux system
layout, so run buildozer inside `steam-run`; give it the missing build tools
from nix-shell:

```bash
venv/bin/pip install buildozer cython

nix-shell -p git unzip zip patchelf pkg-config cmake autoconf automake libtool \
  gcc ccache zlib libffi openssl ncurses \
  --run 'steam-run venv/bin/buildozer -v android debug'
```

First build downloads ~1.5-2 GB (SDK+NDK) and takes a long time; repeat builds
are much faster. The APK lands in `bin/`.

### Build steps (any distro)

1. Install buildozer (https://github.com/kivy/buildozer) and its dependencies.
2. Put the Stockfish **arm64** Android binary in the APK's native lib dir:

   ```bash
   # download from https://stockfishchess.org/download/ (stockfish-android-armv8*)
   mv stockfish-android-armv8 libs/android-v8/libstockfish.so
   ```

   It must be named `libstockfish.so` — Android only allows executing binaries
   from the app's native library directory. Binaries copied out of an APK's
   assets into app data are **blocked** on Android 10+ when targetSdk >= 29
   (exec/W^X restriction), which is why the native-lib route is the default.
3. Build and run:

   ```bash
   buildozer -v android debug deploy run
   ```

   The app detects the engine automatically through
   `ApplicationInfo.nativeLibraryDir` (via pyjnius).

### old-device fallback

`assets/stockfish_arm64` (copy-to-user-data) is kept for devices running
Android 9 or older builds with `android.api <= 28`. It will fail with
"Permission denied" on Android 10+.

### license note

Stockfish is GPL v3. Distributing it inside your APK means the app must
be released under GPL-compatible terms.
