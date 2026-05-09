# Build / package recipes for the discogs_alert macOS menu-bar app.
#
# The Python project itself uses Poetry (see pyproject.toml). This Makefile
# is for the Mac-specific build pipeline that turns the Python package
# into a draggable .dmg.
#
# Quick start:
#     make app    # build dist/discogs_alert.app
#     make dmg    # build dist/discogs_alert.dmg (the user-facing artifact)
#     make clean  # nuke build/ and dist/

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

.PHONY: all app dmg clean clean-build clean-venv

all: dmg

$(BUILD_VENV):
	$(PYTHON) -m venv $(BUILD_VENV)
	$(BUILD_PY) -m pip install --upgrade pip
	$(BUILD_PY) -m pip install -e '.[menubar]'
	$(BUILD_PY) -m pip install py2app

# Build the standalone .app bundle. Full build (not alias) so the
# resulting bundle is portable to any Mac without a Python install.
app: $(BUILD_VENV) clean-build
	$(BUILD_PY) setup_app.py py2app
	@echo
	@echo "✅ Built $(APP)"
	@echo "   Test by opening directly: open $(APP)"

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
