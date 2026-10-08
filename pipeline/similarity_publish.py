"""Gated publication of immutable similarity model generations.

The ordinary full-site upload never publishes `data/similarity/`; this is the only
path that changes the served model. A publish:

1. requires the recorded release gates for this exact generation (health of src
   and dist, relevance/probe/hard-negative gates at both precisions against the
   currently served baseline, recorded test runs);
2. validates every local file the manifest references;
3. uploads the generation's files (core.json last), then re-downloads every one and
   compares SHA-256 with the local copy;
4. uploads `manifest.json` only after that, verifies the served pointer, and checks
   that the previous generation is still served for cached clients and rollback;
5. records the previous manifest so `rollback` can restore it.

Generations are never deleted. Rollback re-verifies (and if needed re-uploads)
the target generation's files before restoring its manifest.

    ./venv/bin/python pipeline/similarity_publish.py status
    ./venv/bin/python pipeline/similarity_publish.py publish --evidence DIR --dry-run
    ./venv/bin/python pipeline/similarity_publish.py publish --evidence DIR
    ./venv/bin/python pipeline/similarity_publish.py rollback [--manifest FILE] [--dry-run]
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = ROOT / 'dist/data/similarity'
SOURCE_MODEL = ROOT / 'src/data/similarity'
DEFAULT_STATE = ROOT / 'scripts/similarity_publications.json'
REMOTE_PREFIX = 'data/similarity'

# Recorded gate files, as written by the weekly refresh (pipeline/similarity.md).
HEALTH_GATES = ['health-src.json', 'health-dist.json']
COMPARISON_GATES = {  # file -> (candidate key, baseline key, precision)
    'builder-evaluation.json': [('candidate', 'baseline', 'full'),
                                ('browserCandidate', 'browserBaseline', 'browser')],
    'source.json': [('candidate', 'baseline', 'full')],
    'source-browser.json': [('candidate', 'baseline', 'browser')],
    'hard-negatives.json': [('candidate', 'baseline', 'full')],
    'hard-negatives-browser.json': [('candidate', 'baseline', 'browser')],
    'probes.json': [(None, 'baseline', 'full')],
    'probes-browser.json': [(None, 'baseline', 'browser')],
    'aspect-probes.json': [(None, 'baseline', 'full')],
    'aspect-probes-browser.json': [(None, 'baseline', 'browser')],
}
TEST_GATES = {'python-tests.log': re.compile(r'^OK\b', re.M),
              'js-tests.log': re.compile(r'\bfail 0\b')}


class PublicationError(Exception):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def parse_manifest(raw):
    manifest = json.loads(raw)
    if not re.fullmatch(r'[a-f0-9]{16}', str(manifest.get('generation', ''))):
        raise PublicationError('Manifest has no valid generation')
    return manifest


def generation_files(manifest):
    """Every file the manifest makes reachable, with core.json last."""
    names = [f'places-{i}.json' for i in manifest.get('placeShards', [])]
    names += [f'tags-{i}.json' for i in manifest.get('tagShards', [])]
    names += [f'active-{i}.json' for i in manifest.get('activeShards', [])]
    names += [f'events-{i}.json' for i in manifest.get('historyShards', [])]
    return names + ['core.json']


def verify_local(model_dir, raw_manifest, domain):
    """Validate the generation exactly as the health audit does, for any manifest."""
    from similarity_health import inspect_artifacts
    manifest = parse_manifest(raw_manifest)
    directory = Path(model_dir) / manifest['generation']
    if not directory.is_dir():
        raise PublicationError(f'Generation {manifest["generation"]} is not in {model_dir}')
    with tempfile.TemporaryDirectory(prefix='similarity-publish-') as view:
        (Path(view) / 'manifest.json').write_bytes(raw_manifest)
        os.symlink(directory.resolve(), Path(view) / manifest['generation'])
        try:
            inspect_artifacts(view, domain)
        except (ValueError, KeyError, OSError) as error:
            raise PublicationError(f'Local generation {manifest["generation"]} is invalid: {error}') from error
    names = generation_files(manifest)
    extra = sorted({p.name for p in directory.iterdir()} - set(names))
    return [(name, (directory / name).read_bytes()) for name in names], extra


def check_gates(evidence, generation, live_generation):
    """Raise unless every recorded gate passed for this generation; return a summary."""
    from similarity_eval import check_gate
    evidence = Path(evidence)
    lines, failures = [], []

    def read(name):
        path = evidence / name
        if not path.is_file():
            failures.append(f'{name}: missing')
            return None
        return path.read_text()

    for name in HEALTH_GATES:
        text = read(name)
        if text is None:
            continue
        health = json.loads(text)
        if health.get('generation') != generation:
            failures.append(f'{name}: audited generation {health.get("generation")}, not {generation}')
        elif health.get('status') != 'healthy':
            failures.append(f'{name}: status {health.get("status")} {health.get("reasons")}')
        else:
            lines.append(f'{name}: healthy, coverage {health.get("activeVectorCoverage")}, '
                         f'{health.get("tagFallbackEvents")} tag-fallback, {health.get("exactOnlyEvents")} exact-only')
    for name, checks in COMPARISON_GATES.items():
        text = read(name)
        if text is None:
            continue
        result = json.loads(text)
        for candidate_key, baseline_key, precision in checks:
            candidate = result[candidate_key] if candidate_key else result
            baseline = result.get(baseline_key)
            label = f'{name}:{candidate_key or "result"}'
            if candidate.get('generation') != generation:
                failures.append(f'{label}: measured generation {candidate.get("generation")}, not {generation}')
                continue
            if candidate.get('precision') != precision:
                failures.append(f'{label}: precision {candidate.get("precision")}, expected {precision}')
                continue
            if not baseline:
                failures.append(f'{label}: no baseline comparison recorded')
                continue
            # A gate passed against an older generation does not cover a newer live model.
            if live_generation not in (None, generation) and baseline.get('generation') != live_generation:
                failures.append(f'{label}: baseline {baseline.get("generation")} is not the served '
                                f'generation {live_generation}; re-run the gate')
                continue
            try:
                check_gate(candidate, baseline)
            except (ValueError, KeyError, TypeError) as error:
                failures.append(f'{label}: {error}')
                continue
            s, b = candidate['summary'], baseline['summary']
            lines.append(f'{label}: ndcg@5 {s["ndcgAt5"]:.5f} (baseline {b["ndcgAt5"]:.5f}), '
                         f'pairwise {s["pairwiseAccuracy"]:.5f} ({b["pairwiseAccuracy"]:.5f}), '
                         f'wrong-first {s["wrongTop1"]} ({b["wrongTop1"]}) vs {baseline.get("generation")}')
    for name, passed in TEST_GATES.items():
        text = read(name)
        if text is None:
            continue
        if not passed.search(text):
            failures.append(f'{name}: no passing test summary')
        else:
            lines.append(f'{name}: passed')
    if failures:
        raise PublicationError('Release gates failed; nothing was uploaded:\n  ' + '\n  '.join(failures))
    return lines


class HttpSite:
    """Read-only view of the served model. Cache-busted so a CDN copy cannot pass verification."""

    def __init__(self, base_url):
        self.base_url = base_url.rstrip('/') + '/'

    def get(self, relative):
        url = f'{self.base_url}{relative}?verify={uuid.uuid4().hex}'
        request = urllib.request.Request(url, headers={'Cache-Control': 'no-cache',
                                                       'User-Agent': 'fomo-similarity-publish'})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise


class FtpTarget:
    """Atomic same-directory temp upload + rename, like scripts/upload_public_html.py."""

    def __init__(self, ftp, remote_root):
        self.ftp = ftp
        self.root = '/'.join(p for p in [remote_root.strip('/'), REMOTE_PREFIX] if p)

    @classmethod
    def connect(cls, use_tls=False):
        from dotenv import load_dotenv
        from ftplib import FTP, FTP_TLS
        load_dotenv(ROOT / '.env')
        host, user, password = (os.getenv(k) for k in ('FTP_HOST', 'PUBLIC_HTML_FTP_USER', 'FTP_PASSWORD'))
        if not all([host, user, password]):
            raise PublicationError('FTP_HOST, PUBLIC_HTML_FTP_USER and FTP_PASSWORD must be set in .env')
        ftp = (FTP_TLS if use_tls else FTP)(host, timeout=120)
        ftp.login(user, password)
        if use_tls:
            ftp.prot_p()
        return cls(ftp, os.getenv('FTP_REMOTE_DIR', ''))

    def put(self, relative, data):
        directory, _, name = f'{self.root}/{relative}'.rpartition('/')
        current = ''
        for part in directory.split('/'):
            current = f'{current}/{part}'
            try:
                self.ftp.cwd(current)
            except Exception:
                self.ftp.mkd(current)
                self.ftp.cwd(current)
        temporary = f'.{name}.{uuid.uuid4().hex}.upload'
        try:
            self.ftp.storbinary(f'STOR {temporary}', io.BytesIO(data))
            self.ftp.rename(temporary, name)
        except Exception:
            try:
                self.ftp.delete(temporary)
            except Exception:
                pass
            raise

    def close(self):
        try:
            self.ftp.quit()
        except Exception:
            pass


def served_mismatches(site, generation, files, workers=8):
    """Names whose served bytes differ from (or are missing versus) the local copy."""
    def differs(item):
        name, data = item
        served = site.get(f'{generation}/{name}')
        return name if served is None or sha256(served) != sha256(data) else None
    with ThreadPoolExecutor(workers) as pool:
        return [name for name in pool.map(differs, files) if name]


def live_manifest(site):
    raw = site.get('manifest.json')
    return (raw, parse_manifest(raw)) if raw is not None else (None, None)


def read_state(path):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else {'publications': []}


def write_state(path, state):
    path = Path(path)
    temporary = path.with_name(f'.{path.name}.{uuid.uuid4().hex}')
    temporary.write_text(json.dumps(state, indent=2) + '\n')
    temporary.replace(path)


def release(site, target, model_dir, raw_manifest, domain, *, dry_run, log, kind, previous_raw):
    """Shared shard→verify→manifest→verify sequence for publish and rollback."""
    manifest = parse_manifest(raw_manifest)
    generation = manifest['generation']
    files, extra = verify_local(model_dir, raw_manifest, domain)
    total = sum(len(data) for _, data in files)
    log(f'Local generation {generation}: {len(files)} referenced files, {total:,} bytes, validated')
    if extra:
        log(f'  not referenced by the manifest (left unpublished): {", ".join(extra)}')
    pending = served_mismatches(site, generation, files)
    log(f'Served copy: {len(files) - len(pending)} of {len(files)} files already identical; {len(pending)} to upload')
    previous = parse_manifest(previous_raw)['generation'] if previous_raw else None
    steps = [f'upload {REMOTE_PREFIX}/{generation}/{name}' for name in pending]
    steps.append(f'verify SHA-256 of all {len(files)} served {REMOTE_PREFIX}/{generation}/ files against local')
    steps.append(f'upload {REMOTE_PREFIX}/manifest.json  (generation {generation}, sha256 {sha256(raw_manifest)[:12]})')
    steps.append(f'verify served {REMOTE_PREFIX}/manifest.json is byte-identical')
    if previous and previous != generation:
        steps.append(f'verify previous generation {previous} still served (core.json) for rollback')
    log(f'\n{"Would run" if dry_run else "Running"} {kind} in this order:')
    for index, step in enumerate(steps, 1):
        log(f'  {index:3d}. {step}')
    if dry_run:
        return False
    by_name = dict(files)
    for name in pending:
        target.put(f'{generation}/{name}', by_name[name])
    still = served_mismatches(site, generation, files)
    if still:
        raise PublicationError(f'Served generation {generation} does not match after upload ({", ".join(still[:5])}); '
                               'manifest NOT changed')
    target.put('manifest.json', raw_manifest)
    served = site.get('manifest.json')
    if served != raw_manifest:
        raise PublicationError('Served manifest differs from the uploaded one; inspect before retrying')
    if previous and previous != generation and site.get(f'{previous}/core.json') is None:
        raise PublicationError(f'Previous generation {previous} is no longer served; rollback needs it re-uploaded')
    log(f'\n{kind.capitalize()} complete: {generation} is served and verified')
    return True


def publish(site, target, model_dir, evidence, domain, state_path, *, dry_run=False, log=print, source_dir=None):
    raw = (Path(model_dir) / 'manifest.json').read_bytes()
    manifest = parse_manifest(raw)
    generation = manifest['generation']
    if source_dir and (Path(source_dir) / 'manifest.json').exists() \
            and (Path(source_dir) / 'manifest.json').read_bytes() != raw:
        raise PublicationError(f'{source_dir}/manifest.json differs from {model_dir}/manifest.json; rebuild dist first')
    live_raw, live = live_manifest(site)
    live_generation = live and live['generation']
    log(f'Candidate generation: {generation} ({manifest.get("quantization")}, generated {manifest.get("generatedAt")})')
    log(f'Served generation:    {live_generation or "none"}')
    log('\nRecorded gates (' + str(evidence) + '):')
    for line in check_gates(evidence, generation, live_generation):
        log(f'  PASS {line}')
    if live_raw == raw:
        log(f'\n{generation} is already the served manifest; verifying its files only.')
        files, _ = verify_local(model_dir, raw, domain)
        missing = served_mismatches(site, generation, files)
        if missing:
            raise PublicationError(f'Served {generation} is incomplete: {", ".join(missing[:5])}')
        log(f'All {len(files)} served files match. Nothing to upload.')
        return False
    done = release(site, target, model_dir, raw, domain, dry_run=dry_run, log=log,
                   kind='publication', previous_raw=live_raw)
    if done:
        state = read_state(state_path)
        state['publications'].append({'kind': 'publish', 'generation': generation, 'previous': live_generation,
                                      'publishedAt': datetime.now(timezone.utc).isoformat(),
                                      'manifest': raw.decode(), 'previousManifest': live_raw and live_raw.decode(),
                                      'evidence': str(evidence)})
        write_state(state_path, state)
        log(f'Recorded in {state_path}; roll back with: ./venv/bin/python pipeline/similarity_publish.py rollback')
    return done


def rollback(site, target, model_dir, domain, state_path, *, manifest_file=None, dry_run=False, log=print):
    live_raw, live = live_manifest(site)
    if manifest_file:
        raw = Path(manifest_file).read_bytes()
    else:
        history = [p for p in read_state(state_path)['publications'] if p.get('previousManifest')]
        if not history or not live or history[-1]['generation'] != live['generation']:
            raise PublicationError('No recorded publication matches the served manifest; pass --manifest FILE')
        raw = history[-1]['previousManifest'].encode()
    target_generation = parse_manifest(raw)['generation']
    log(f'Served generation:   {live and live["generation"]}')
    log(f'Rollback generation: {target_generation}')
    if live_raw == raw:
        log('That manifest is already served. Nothing to do.')
        return False
    done = release(site, target, model_dir, raw, domain, dry_run=dry_run, log=log,
                   kind='rollback', previous_raw=live_raw)
    if done:
        state = read_state(state_path)
        state['publications'].append({'kind': 'rollback', 'generation': target_generation,
                                      'previous': live and live['generation'],
                                      'publishedAt': datetime.now(timezone.utc).isoformat(),
                                      'manifest': raw.decode(), 'previousManifest': live_raw and live_raw.decode()})
        write_state(state_path, state)
        log(f'Local {model_dir}/manifest.json is unchanged; do not re-publish it without new gates.')
    return done


def main(argv=None):
    sys.path.insert(0, str(ROOT / 'pipeline'))
    from city_config import get_config
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=['status', 'publish', 'rollback'])
    parser.add_argument('--evidence', type=Path, help='Directory with the recorded gate files (publish)')
    parser.add_argument('--manifest', type=Path, help='Saved manifest to restore (rollback)')
    parser.add_argument('--model-dir', type=Path, default=DEFAULT_MODEL)
    parser.add_argument('--state', type=Path, default=DEFAULT_STATE)
    parser.add_argument('--base-url', help='Served model URL (default https://<frontend.domain>/data/similarity/)')
    parser.add_argument('--dry-run', action='store_true', help='Check gates and print the exact upload order only')
    parser.add_argument('--tls', action='store_true')
    args = parser.parse_args(argv)
    domain = get_config().get('frontend', {}).get('domain')
    site = HttpSite(args.base_url or f'https://{domain}/{REMOTE_PREFIX}/')
    try:
        if args.command == 'status':
            raw, live = live_manifest(site)
            print(f'Served: {live and live["generation"]} ({site.base_url}manifest.json)')
            local = parse_manifest((args.model_dir / 'manifest.json').read_bytes())
            print(f'Local:  {local["generation"]} ({args.model_dir}/manifest.json)')
            for entry in read_state(args.state)['publications'][-5:]:
                print(f'  {entry["publishedAt"]} {entry["kind"]} {entry["previous"]} -> {entry["generation"]}')
            return 0
        if args.command == 'publish' and not args.evidence:
            parser.error('publish requires --evidence')
        with open(args.state.with_name(args.state.name + '.lock'), 'a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise PublicationError('Another similarity publication is running')
            target = None if args.dry_run else FtpTarget.connect(args.tls)
            try:
                if args.command == 'publish':
                    publish(site, target, args.model_dir, args.evidence, domain, args.state, dry_run=args.dry_run,
                            source_dir=SOURCE_MODEL if args.model_dir == DEFAULT_MODEL else None)
                else:
                    rollback(site, target, args.model_dir, domain, args.state,
                             manifest_file=args.manifest, dry_run=args.dry_run)
            finally:
                if target:
                    target.close()
        return 0
    except PublicationError as error:
        print(f'\n✗ {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
