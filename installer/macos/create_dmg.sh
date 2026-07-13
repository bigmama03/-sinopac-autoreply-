#!/bin/bash
# Create macOS DMG installer for SinoPac AutoReply
# Usage: bash installer/macos/create_dmg.sh [version]

set -eu

# Anchor to repository root (two levels up from this script)
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

APP_NAME="SinoPac AutoReply"
APP_BUNDLE="SinoPacAutoReply.app"
VERSION="${1:-1.0.0}"
DMG_NAME="SinoPacAutoReply-Installer-${VERSION}"
DIST_DIR="${REPO_ROOT}/dist"
STAGING_DIR="${DIST_DIR}/dmg-staging"

# Clean up staging on exit (success or failure)
cleanup() { rm -rf "${STAGING_DIR}"; }
trap cleanup EXIT

echo "=== Building DMG: ${DMG_NAME}.dmg ==="

# Clean up previous staging
rm -rf "${STAGING_DIR}"
mkdir -p "${STAGING_DIR}"

# Verify .app exists
if [ ! -d "${DIST_DIR}/${APP_BUNDLE}" ]; then
    echo "ERROR: ${DIST_DIR}/${APP_BUNDLE} not found."
    echo "Run PyInstaller first: python -m PyInstaller sinopac_autoreply.spec --noconfirm"
    exit 1
fi

# Copy .app to staging
echo "Copying ${APP_BUNDLE}..."
cp -R "${DIST_DIR}/${APP_BUNDLE}" "${STAGING_DIR}/"

# Ad-hoc code sign to avoid "app is damaged" Gatekeeper error.
# Without this, macOS quarantines unsigned apps downloaded from the internet
# and shows a misleading "damaged" dialog with no option to open.
# Ad-hoc signing changes the behavior to "unidentified developer", which
# users can bypass via right-click > Open.
#
# Sign inside-out, excluding Playwright's bundled Chrome (it ships with
# Google's own signature and has an ambiguous bundle format that codesign
# cannot re-sign).
echo "Signing ${APP_BUNDLE} (ad-hoc, inside-out)..."

# 1. Sign our shared libraries (skip ms-playwright — Chrome is pre-signed)
find "${STAGING_DIR}/${APP_BUNDLE}" -depth \
    \( -name "*.dylib" -o -name "*.so" \) \
    ! -path "*/ms-playwright/*" -print0 |
while IFS= read -r -d '' item; do
    codesign --force --sign - "$item"
done

# 2. Sign the main bundle last (without --deep to avoid Chrome re-sign)
codesign --force --sign - "${STAGING_DIR}/${APP_BUNDLE}"

echo "Verifying signature..."
codesign --verify --verbose "${STAGING_DIR}/${APP_BUNDLE}" || echo "WARN: signature verification failed (non-fatal)"

# Remove quarantine attributes from the staged copy
xattr -cr "${STAGING_DIR}/${APP_BUNDLE}"

# Create symlink to Applications folder
ln -s /Applications "${STAGING_DIR}/Applications"

# Create DMG
echo "Creating DMG..."
hdiutil create -volname "${APP_NAME}" \
    -srcfolder "${STAGING_DIR}" \
    -ov -format UDZO \
    -imagekey zlib-level=9 \
    "${DIST_DIR}/${DMG_NAME}.dmg"

echo "=== Done: ${DIST_DIR}/${DMG_NAME}.dmg ==="
ls -lh "${DIST_DIR}/${DMG_NAME}.dmg"
