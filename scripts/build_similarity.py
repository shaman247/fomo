#!/usr/bin/env python3
"""Build the similarity model in its isolated runtime; --setup installs that runtime."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.scratch/similarity-runtime'


def main():
    arguments = sys.argv[1:]
    python = RUNTIME / 'bin/python'
    if '--setup' in arguments:
        arguments.remove('--setup')
        subprocess.run([sys.executable, '-m', 'venv', str(RUNTIME)], check=True)
        subprocess.run([str(python), '-m', 'pip', 'install', '-r',
                        str(ROOT / 'pipeline/requirements-similarity.txt')], check=True)
        if not arguments:
            return 0
    if not python.exists():
        print('Similarity runtime missing. Run ./venv/bin/python scripts/build_similarity.py --setup', file=sys.stderr)
        return 2
    return subprocess.call([str(python), str(ROOT / 'pipeline/similarity.py'), *arguments], cwd=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
