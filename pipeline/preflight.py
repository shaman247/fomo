"""Read-only disk preflight for pipeline entry points.

Warn below 20 GiB free; stop below 5 GiB before opening the database or writing
crawl/export files. Run `python pipeline/preflight.py --scratch` for the largest
scratch directories. Nothing is deleted automatically.
"""
import argparse
from pathlib import Path
import shutil
import subprocess

REPO_ROOT = Path(__file__).resolve().parents[1]
GIB = 1024 ** 3
MIN_FREE_GIB = 5
WARN_FREE_GIB = 20


def largest_scratch_directories(root, limit=5):
    """Bounded disk usage scan; du does not follow directory symlinks by default."""
    scratch = Path(root) / '.scratch'
    if not scratch.is_dir():
        return [], None
    try:
        result = subprocess.run(['du', '-k', '-d', '1', str(scratch)],
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], f'Scratch size scan unavailable: {exc}'
    rows = []
    for line in result.stdout.splitlines():
        size, sep, name = line.partition('\t')
        if sep and size.isdigit() and Path(name) != scratch:
            rows.append((Path(name), int(size) * 1024))
    warning = 'Scratch sizes are incomplete (some paths could not be read).' if result.returncode else None
    return sorted(rows, key=lambda item: item[1], reverse=True)[:limit], warning


def run_disk_preflight(root=REPO_ROOT, *, min_free_gib=MIN_FREE_GIB,
                       warn_free_gib=WARN_FREE_GIB, report_scratch=False, report=print):
    """Return whether this filesystem has room to start a run; never mutate it."""
    if not 0 < min_free_gib <= warn_free_gib:
        raise ValueError('Disk thresholds must satisfy 0 < minimum <= warning')
    root = Path(root).resolve()
    try:
        usage = shutil.disk_usage(root)
    except OSError as exc:
        report(f'Disk preflight failed for {root}: {exc}')
        return False
    free = usage.free / GIB
    critical = usage.free < min_free_gib * GIB
    low = usage.free < warn_free_gib * GIB
    state = 'STOP' if critical else ('WARNING' if low else 'OK')
    report(f'Disk preflight: {state} — {free:.1f} GiB free on {root} '
           f'(warn below {warn_free_gib:g}; stop below {min_free_gib:g} GiB).')
    if low or report_scratch:
        rows, warning = largest_scratch_directories(root)
        for path, size in rows:
            report(f'  Scratch: {size / GIB:.2f} GiB  {path}')
        if warning:
            report(f'  {warning}')
    if critical:
        report('Pipeline stopped before database work. Free space, then retry; '
               'review scratch directories for work still in use before removing files.')
    return not critical


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scratch', action='store_true', help='Report the five largest scratch directories')
    args = parser.parse_args()
    return 0 if run_disk_preflight(report_scratch=args.scratch) else 1


if __name__ == '__main__':
    raise SystemExit(main())
