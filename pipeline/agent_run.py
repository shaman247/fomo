"""Durable scope and local singleton for agent-operated pipeline runs."""

from contextlib import contextmanager
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]


def new_work_dir():
    return ROOT / '.scratch' / 'pipeline-agent' / (datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8])


def save(work_dir, state):
    path = Path(work_dir)
    path.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.run-', dir=path)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(state, stream, indent=2)
            stream.write('\n')
        os.replace(temporary, path / 'run.json')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load(work_dir):
    state = json.loads((Path(work_dir) / 'run.json').read_text())
    if state.get('version') != 1:
        raise ValueError('Unsupported agent run manifest')
    if state.get('city') != os.environ.get('FOMO_CITY', 'nyc'):
        raise ValueError('Resume must use the same FOMO_CITY as the original run')
    if state.get('phase') == 'crawling':
        raise ValueError('Crawl was interrupted before its snapshot was saved. Start a new run to recover stored incomplete results.')
    if state.get('phase') == 'crawl_failed':
        raise ValueError('No listing crawls succeeded. Fix the crawl failures and start a new run.')
    return state


def read_results(cursor, ids):
    """Read exact saved crawl IDs, including processed rows, without retry-age gates."""
    from db import FAILED_CRAWL_SUPERSEDED_SQL, failed_crawl_retry_reason
    if not ids:
        return []
    placeholders = ','.join(['%s'] * len(ids))
    cursor.execute(f"""
        SELECT cr.id, cr.status, cr.website_id, cr.crawl_run_id,
               w.name, w.notes, r.run_date, cr.crawled_content,
               w.process_images, cr.extracted_content,
               w.force_chunked, w.max_records_per_chunk,
               CHAR_LENGTH(COALESCE(cr.crawled_content, '')),
               {FAILED_CRAWL_SUPERSEDED_SQL}
        FROM crawl_results cr
        JOIN websites w ON w.id = cr.website_id
        JOIN crawl_runs r ON r.id = cr.crawl_run_id
        WHERE cr.id IN ({placeholders})
        ORDER BY cr.id
    """, list(ids))
    rows = []
    for row in cursor.fetchall():
        status = row[1]
        if status == 'failed' and row[7]:
            status = 'extracted' if row[9] else 'crawled'
        # Bind extraction to source identity and interpretation settings as well
        # as content. A notes/venue/settings edit during review requires refresh.
        identity = [row[2], row[3], row[4], row[5], str(row[6]), row[7], row[8], row[10], row[11]]
        rows.append(dict(crawl_result_id=row[0], status=status, website_id=row[2],
                         crawl_run_id=row[3], name=row[4], notes=row[5] or '',
                         run_date=row[6], use_vision=bool(row[8]),
                         original_status=row[1], content_chars=row[12],
                         superseded_by_success=bool(row[13]),
                         retry_exclusion_reason=failed_crawl_retry_reason(row[1], row[12], bool(row[13])),
                         source_hash=hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()))
    if {r['crawl_result_id'] for r in rows} != set(ids):
        raise ValueError('A saved crawl result or its website was removed; refresh the run instead of applying stale work')
    return rows


def verify_sources(state, results):
    actual = {str(row['crawl_result_id']): row['source_hash'] for row in results}
    if actual != state['source_hashes']:
        raise ValueError('Saved crawl content changed during agent extraction; start a fresh run instead of applying stale work')


@contextmanager
def singleton():
    """Only one local crawl/resume/publish process may run at once; agents review freely."""
    path = ROOT / '.scratch' / 'pipeline-agent.lock'
    path.parent.mkdir(exist_ok=True)
    with path.open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Another pipeline/resume/upload process is running; retry after it finishes') from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)
