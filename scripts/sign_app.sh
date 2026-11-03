#!/usr/bin/env bash
# Sign the macOS app bundle with a Developer ID (or any codesigning identity).
#
# Usage: scripts/sign_app.sh "<identity>" dist/discogs_alert.app
#
# Signs from the inside out, as Apple and Sparkle require, and never uses
# --deep: every dylib and extension module, the bundled Python, Sparkle's XPC
# services and helpers, Sparkle.framework, and finally the app itself with
# the hardened runtime and the entitlements the bundled Python needs.
set -euo pipefail

identity="$1"
app="$2"
entitlements="$(cd "$(dirname "$0")" && pwd)/entitlements.plist"
contents="$app/Contents"

sign() { codesign --force --timestamp --options runtime --sign "$identity" "$@"; }

# 1. Every Mach-O file that is not part of Sparkle: extension modules, dylibs, helper binaries.
find "$contents" \( -name '*.so' -o -name '*.dylib' \) -type f -not -path '*/Sparkle.framework/*' -print0 \
    | xargs -0 -n 25 codesign --force --timestamp --options runtime --sign "$identity"
find "$contents/Frameworks/Python.framework" -type f -perm -u+x -not -name '*.so' -not -name '*.dylib' -print0 \
    | xargs -0 -n 25 codesign --force --timestamp --options runtime --sign "$identity"
sign "$contents/Frameworks/Python.framework/Versions/Current"
sign --entitlements "$entitlements" "$contents/MacOS/python"

# 2. Sparkle, in the order its documentation gives.
sparkle="$contents/Frameworks/Sparkle.framework/Versions/B"
sign "$sparkle/XPCServices/Installer.xpc"
sign --preserve-metadata=entitlements "$sparkle/XPCServices/Downloader.xpc"
sign "$sparkle/Autoupdate"
sign "$sparkle/Updater.app"
sign "$contents/Frameworks/Sparkle.framework"

# 3. The app: this signs Contents/MacOS/discogs_alert and seals the bundle.
sign --entitlements "$entitlements" "$app"

codesign --verify --deep --strict --verbose=2 "$app"
