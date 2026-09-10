"""Optional local sentence encoder with a pinned model and reusable content cache."""
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile

import numpy as np

MODEL = 'sentence-transformers/all-MiniLM-L6-v2'
REVISION = '1110a243fdf4706b3f48f1d95db1a4f5529b4d41'


def encode(texts, workspace, model_cache):
    from sentence_transformers import SentenceTransformer
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    path = workspace / 'sentence-cache.npz'
    keys = [hashlib.sha256((MODEL + REVISION + text).encode()).hexdigest() for text in texts]
    cached, old_keys = {}, []
    old_vectors = np.empty((0, 384), dtype=np.float32)
    if path.exists():
        with np.load(path, allow_pickle=False) as data:
            old_keys = data['keys'].astype(str).tolist()
            old_vectors = data['vectors']
            if old_vectors.shape != (len(old_keys), 384) or not np.isfinite(old_vectors).all():
                raise ValueError('Invalid sentence cache; remove it to rebuild')
            cached = {key: i for i, key in enumerate(old_keys)}
    missing = {key: text for key, text in zip(keys, texts) if key not in cached}
    print(f'Sentence cache: {len(keys) - sum(key in missing for key in keys):,} hits; '
          f'{len(missing):,} unique new texts', flush=True)
    if missing:
        options = dict(revision=REVISION, cache_folder=str(model_cache), trust_remote_code=False)
        try:
            model = SentenceTransformer(MODEL, local_files_only=True, **options)
        except OSError:
            # Download the pinned weights only on first setup or an incomplete
            # cache. A normal refresh must work without metadata network calls.
            model = SentenceTransformer(MODEL, **options)
        print(f'Encoding locally on {model.device}', flush=True)
        # Small batches bound GPU memory and allow progress between batches.
        added = model.encode(list(missing.values()), batch_size=128, normalize_embeddings=True,
                             show_progress_bar=True, convert_to_numpy=True).astype(np.float32)
        if added.shape != (len(missing), 384) or not np.isfinite(added).all():
            raise ValueError('Encoder returned invalid vectors')
        old_vectors = np.concatenate([old_vectors, added])
        old_keys += list(missing)
        cached = {key: i for i, key in enumerate(old_keys)}
        with tempfile.NamedTemporaryFile(dir=workspace, suffix='.npz', delete=False) as stream:
            temporary = Path(stream.name)
        try:
            np.savez(temporary, keys=np.array(old_keys, dtype='S64'), vectors=old_vectors)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return old_vectors[[cached[key] for key in keys]]


def content_vectors(data, rows, attached, excluded, dimensions, workspace, model_cache):
    from similarity import unit
    tags = {tag['id']: tag for tag in data['tags']}
    texts = []
    for kind, row in rows:
        names = sorted(tags[tid]['name'] for tid in attached[kind][row['id']] - excluded
                       if tid in tags and tags[tid]['type'] == 'tag')
        texts.append(row['name'] + '. ' + (row.get('description') or '')[:1600]
                     + '. Topics: ' + ', '.join(names))
    texts += [tag['name'] for tag in data['tags']]
    encoded = encode(texts, workspace, model_cache)
    # Learn a shared low-dimensional projection from content, never relevance
    # labels. This compresses leaf vectors, not aggregates of distinct interests.
    training = encoded[:len(rows)]
    eigenvalues, basis = np.linalg.eigh(training.T @ training)
    rank = min(dimensions, encoded.shape[1], len(rows))
    basis = basis[:, -rank:][:, ::-1].copy()
    # Fix eigenvector sign ambiguity for reproducible generation bytes.
    for column in range(rank):
        if basis[np.argmax(np.abs(basis[:, column])), column] < 0:
            basis[:, column] *= -1
    projected = unit(encoded @ basis).astype(np.float32)
    energy = float(eigenvalues[-rank:].sum() / eigenvalues.sum())
    return projected[:len(rows)], projected[len(rows):], {'basis': basis,
        'encoder': np.array(MODEL), 'encoder_revision': np.array(REVISION)}, energy
