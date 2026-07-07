"""Post-build script: copy Playwright browsers into the packaged app."""
import os
import platform
import shutil
import subprocess
import sys


def get_browser_dirs():
    """Get the Playwright browser directories that should be bundled."""
    # Ask Playwright which browsers it needs
    result = subprocess.run(
        [sys.executable, '-m', 'playwright', 'install', '--dry-run', 'chromium'],
        capture_output=True, text=True,
    )
    needed = result.stdout

    # Find browser cache path
    system = platform.system()
    if system == 'Darwin':
        cache = os.path.join(os.path.expanduser('~'), 'Library', 'Caches', 'ms-playwright')
    elif system == 'Windows':
        cache = os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'ms-playwright')
    else:
        cache = os.path.join(os.path.expanduser('~'), '.cache', 'ms-playwright')

    if not os.path.isdir(cache):
        print(f'ERROR: Playwright cache not found at {cache}')
        print('Run: playwright install chromium')
        sys.exit(1)

    # Only bundle the main chromium browser (not headless shell or ffmpeg)
    dirs = []
    for entry in os.listdir(cache):
        full = os.path.join(cache, entry)
        if not os.path.isdir(full):
            continue
        # Only include chromium-XXXX (not chromium_headless_shell)
        if entry.startswith('chromium-') and entry in needed:
            dirs.append((full, entry))
            print(f'  Found: {entry}')

    if not dirs:
        for entry in os.listdir(cache):
            full = os.path.join(cache, entry)
            if os.path.isdir(full) and entry.startswith('chromium-'):
                dirs.append((full, entry))
                print(f'  Fallback: {entry}')

    return dirs


def main():
    system = platform.system()

    # Determine destination
    if system == 'Darwin':
        dest_base = os.path.join('dist', 'SinoPacAutoReply.app', 'Contents', 'Frameworks', 'ms-playwright')
    else:
        dest_base = os.path.join('dist', 'SinoPacAutoReply', '_internal', 'ms-playwright')

    print(f'Bundling Playwright browsers to: {dest_base}')

    dirs = get_browser_dirs()
    if not dirs:
        print('ERROR: No browser directories found')
        sys.exit(1)

    os.makedirs(dest_base, exist_ok=True)

    for src_path, name in dirs:
        dest = os.path.join(dest_base, name)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        print(f'  Copying {name}...')
        shutil.copytree(src_path, dest)

    total_size = sum(
        os.path.getsize(os.path.join(dp, f))
        for d in dirs
        for dp, _, fns in os.walk(os.path.join(dest_base, d[1]))
        for f in fns
    )
    print(f'Done! Bundled {len(dirs)} browser components ({total_size / 1024 / 1024:.0f} MB)')


if __name__ == '__main__':
    main()
