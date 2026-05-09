# Build / package recipes for the discogs_alert macOS menu-bar app.
#
# The Python project itself uses Poetry (see pyproject.toml). This Makefile
# is for the Mac-specific build pipeline that turns the Python package
# into a draggable .dmg.
#
# Quick start:
#     make sparkle  # one-time: download Sparkle.framework
#     make keys     # one-time: generate EdDSA keypair for update signing
#     make app      # build dist/discogs_alert.app
#     make dmg      # build dist/discogs_alert.dmg (the user-facing artifact)
#     make sign     # sign $(DMG) with the private EdDSA key
#     make appcast  # append a release entry to docs/appcast.xml
#     make clean    # nuke build/ and dist/
#
# See docs/release.md for the end-to-end release recipe.

PYTHON ?= python3
# Read the version directly from pyproject.toml so we don't have to import
# the package (which would fail before `pip install -e .`).
VERSION := $(shell grep '^version' pyproject.toml | head -1 | sed -E 's/.*"([^"]+)".*/\1/')
APP := dist/discogs_alert.app
DMG := dist/discogs_alert-$(VERSION).dmg

# Use a clean throwaway venv for the app build so py2app's module-graph
# doesn't pick up unrelated junk from the outer environment (e.g. data-
# science packages with Linux .so files that crash macholib). This venv
# lives in `.build-venv/` and only ever holds the build deps.
BUILD_VENV := .build-venv
BUILD_PY := $(BUILD_VENV)/bin/python

# Sparkle.framework download. Pinned to a release; bump VERSION to
# upgrade.
SPARKLE_VERSION := 2.7.2
SPARKLE_TARBALL_URL := https://github.com/sparkle-project/Sparkle/releases/download/$(SPARKLE_VERSION)/Sparkle-$(SPARKLE_VERSION).tar.xz
VENDOR := vendor
SPARKLE_FRAMEWORK := $(VENDOR)/Sparkle.framework
SPARKLE_BIN := $(VENDOR)/sparkle-bin

# EdDSA keypair for update signing. Lives outside the repo for safety.
RELEASE_DIR := $(HOME)/.discogs_alert_release
PRIV_KEY := $(RELEASE_DIR)/eddsa_priv.key
PUB_KEY := $(RELEASE_DIR)/eddsa_pub.key

.PHONY: all app dmg sparkle keys sign appcast clean clean-build clean-venv clean-vendor

all: dmg

$(BUILD_VENV):
	$(PYTHON) -m venv $(BUILD_VENV)
	$(BUILD_PY) -m pip install --upgrade pip
	$(BUILD_PY) -m pip install -e '.[menubar]'
	$(BUILD_PY) -m pip install py2app

# Build the standalone .app bundle. Full build (not alias) so the
# resulting bundle is portable to any Mac without a Python install.
# Bundles `vendor/Sparkle.framework` if present (auto-update enabled).
app: $(BUILD_VENV) clean-build
	@if [ -f $(PUB_KEY) ]; then \
		export DA_SPARKLE_PUBLIC_KEY="$$(cat $(PUB_KEY))"; \
	fi; \
	$(BUILD_PY) setup_app.py py2app
	@echo
	@echo "✅ Built $(APP)"
	@if [ -d $(SPARKLE_FRAMEWORK) ]; then \
		echo "   Sparkle.framework bundled — auto-update enabled."; \
	else \
		echo "   ⚠️  Sparkle.framework NOT bundled. Run 'make sparkle' if you want auto-update."; \
	fi
	@echo "   Test by opening directly: open $(APP)"

# ---- Sparkle auto-update ---------------------------------------------------
#
# These targets are only needed when building a release. End users never
# run `make sparkle` / `make keys` / `make sign` etc.; that's the maintainer's
# job. See docs/release.md.

# Download Sparkle.framework into vendor/. Run once; the framework is
# gitignored.
sparkle: $(SPARKLE_FRAMEWORK)

$(SPARKLE_FRAMEWORK):
	@mkdir -p $(VENDOR)
	@echo "Downloading Sparkle $(SPARKLE_VERSION)…"
	@curl -fsSL $(SPARKLE_TARBALL_URL) -o $(VENDOR)/sparkle.tar.xz
	@tar -xJf $(VENDOR)/sparkle.tar.xz -C $(VENDOR)
	@rm $(VENDOR)/sparkle.tar.xz
	@# The tarball drops Sparkle.framework + bin/ into vendor/ alongside
	@# whatever was already there.
	@if [ ! -d $(SPARKLE_FRAMEWORK) ]; then \
		echo "❌ Sparkle.framework not where we expected after extract"; \
		exit 1; \
	fi
	@echo "✅ $(SPARKLE_FRAMEWORK) ready"
	@echo "   Sparkle binaries (generate_keys, sign_update) at $(VENDOR)/bin/"

# Generate the EdDSA keypair used to sign updates. The private key NEVER
# enters the repo — it lives at $(PRIV_KEY) (under $HOME). Run once per
# project; treat the private key like any other long-lived signing key.
keys: $(PRIV_KEY)

$(PRIV_KEY): $(SPARKLE_FRAMEWORK)
	@mkdir -p $(RELEASE_DIR)
	@chmod 700 $(RELEASE_DIR)
	@if [ -f $(PRIV_KEY) ]; then \
		echo "❌ $(PRIV_KEY) already exists; refusing to overwrite. Move or rename if you really want a new key."; \
		exit 1; \
	fi
	$(VENDOR)/bin/generate_keys -f $(PRIV_KEY) > $(PUB_KEY)
	@chmod 600 $(PRIV_KEY) $(PUB_KEY)
	@echo
	@echo "✅ Generated EdDSA keypair."
	@echo "   Public key  → $(PUB_KEY)"
	@echo "   Private key → $(PRIV_KEY)  (BACK THIS UP)"
	@echo "   The public key is what we bake into Info.plist; the private key signs DMGs."

# Sign the most recently built DMG with the private key. Prints the
# `sparkle:edSignature` you'll paste into appcast.xml.
sign: $(DMG) $(PRIV_KEY)
	@echo "Signing $(DMG) with $(PRIV_KEY)…"
	@$(VENDOR)/bin/sign_update -f $(PRIV_KEY) $(DMG)

# Wrap the .app in a draggable DMG. Uses macOS-native hdiutil; no
# extra deps. The DMG ends up tagged with the package version so
# you can ship multiple side-by-side during testing.
dmg: app
	@rm -f $(DMG)
	@mkdir -p dist/dmg-staging
	@cp -R $(APP) dist/dmg-staging/
	@ln -sf /Applications dist/dmg-staging/Applications
	hdiutil create -volname "discogs_alert" \
	    -srcfolder dist/dmg-staging \
	    -ov -format UDZO $(DMG)
	@rm -rf dist/dmg-staging
	@echo
	@echo "✅ Built $(DMG)"
	@echo "   Open with: open $(DMG)"
	@echo "   Or attach with: hdiutil attach $(DMG)"

# clean-build wipes only the build artefacts; users probably don't
# want `make clean` to nuke their local virtualenv etc.
clean-build:
	rm -rf build dist/discogs_alert.app dist/dmg-staging

clean: clean-build
	rm -f dist/*.dmg

clean-venv:
	rm -rf $(BUILD_VENV)

clean-vendor:
	rm -rf $(VENDOR)
