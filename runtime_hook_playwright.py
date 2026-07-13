"""PyInstaller runtime hook: set PLAYWRIGHT_BROWSERS_PATH to bundled browsers."""
import os
import sys

if getattr(sys, 'frozen', False):
    base_dir = sys._MEIPASS
    # Check _MEIPASS first (Windows _internal), then macOS Frameworks
    for candidate in [
        os.path.join(base_dir, 'ms-playwright'),
        os.path.join(os.path.dirname(base_dir), 'Frameworks', 'ms-playwright'),
        os.path.join(os.path.dirname(base_dir), 'Resources', 'ms-playwright'),
    ]:
        if os.path.isdir(candidate):
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = candidate
            break
