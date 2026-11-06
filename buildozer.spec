[app]

title = ChessMatch
package.name = chessmatch
package.domain = org.chessmatch

source.dir = .

# ship the chess-glyph font plus the legacy asset fallback (targetSdk <= 28);
# the primary Android engine path is the native library below
source.include_exts = py,ttf
source.include_patterns = assets/*

requirements = python3,kivy,chess

version = 0.1

orientation = all

#
# Android specific
#

# arm64 only: opening models run on-device and Stockfish is the arm64 build.
# Add armeabi-v7a once you also bundle that build.
android.archs = arm64-v8a

# Copies the Stockfish engine binary into the APK's native lib directory.
# Binaries in the native lib dir are executable on all Android versions;
# binaries copied to app data are blocked from exec on Android 10+ (targetSdk 29+).
# After `buildozer android debug`, the engine is run from <nativeLibraryDir>/libstockfish.so
android.add_libs_arm64_v8a = libs/android-v8/*.so

android.minapi = 24

# don't stall on the interactive SDK license prompt during the first build
android.accept_sdk_license = True

# no special permissions needed: the engine runs inside the app sandbox

#
# python-for-android
#
#p4a.branch = master

[buildozer]
log_level = 2
warn_on_root = 1
