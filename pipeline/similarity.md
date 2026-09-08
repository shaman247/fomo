# Offline similarity model

`similarity.py` builds a shared 96-dimensional content space for events, places,
and tags from a consistent, read-only MariaDB snapshot. It uses the full canonical
event history, rather than only the currently exported events. No API calls,
user behavior collection, DB writes, or new database tables are required.

```sh
./venv/bin/python pipeline/similarity.py
```

Dependencies: the project venv's NumPy and SciPy. No scikit-learn or model download
is needed. The active city comes from `FOMO_CITY` and `pipeline/city_config.py`.
The build generates `src/data/similarity/`; the normal frontend build copies it to
`dist/data/similarity/`. Publishing uses the existing full-site upload. Training
and building do not deploy anything. A fresh checkout without model artifacts
still supports exact preference ranking and interest search.

For reproducible experiments without another database read:

```sh
./venv/bin/python pipeline/similarity.py \
  --snapshot .scratch/similarity/snapshot.json.gz \
  --output .scratch/similarity/experiment-public \
  --workspace .scratch/similarity/experiment
```

The scratch snapshot is local and gitignored. It includes canonical event/place
descriptions and tag relationships, with no user, credential or feedback tables.
Default diagnostics are in `.scratch/similarity/report.json`; the full vectors
and database entity IDs are in `.scratch/similarity/vectors.npz`.

## Training

- Read **all** canonical events, places, tags/keywords, their relationships, and
  the tag hierarchy in a repeatable-read, read-only transaction. Suppressed events
  are counted in the report but excluded from fitting. Archived events remain.
  Crawl tables are not extra training documents: they duplicate canonical events.
- Represent each event/place using its name, the first 1,600 characters of its
  description, curated tags, and words from its keyword tags. Names receive three
  word counts, description words one, and tag-name words two. Text receives
  sublinear term-frequency and corpus inverse-document-frequency weighting.
- Remove inherited ancestor tags when a more specific tag is attached. Exclude
  configured geographic tags and the Neighborhood hierarchy from semantic
  features and tag vectors. Coordinates and addresses are never features.
  Explicit geographic preferences still work through the exact matcher.
- Normalize curated-tag and text channels separately, with weights 0.8 and 0.6.
  Retain all observed curated features and up to 30,000 text features appearing
  in at least five documents and fewer than 65% of documents.
- Fit randomized truncated SVD (seed 17, 12 oversampling dimensions, two power
  iterations), and unit-normalize the projected vectors. Implementation uses
  [SciPy sparse matrices](https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.csr_matrix.html)
  and [NumPy SVD](https://numpy.org/doc/stable/reference/generated/numpy.linalg.svd.html).
  No dense all-pairs similarity matrix is materialized.
- A place vector combines 25% of its intrinsic profile and 75% of its mean event
  programming. Repeated normalized event names at the same place receive one
  programming vote. Places without event history use their intrinsic profile.
  Place audience tags never flow back into event vectors.
- Tag and keyword vectors are normalized centroids of their attached canonical
  event/place vectors (place contributions weight 0.25). Unsupported and excluded
  tags have zero vectors. All tag/keyword vectors remain in the offline artifact;
  only supported curated tags are exported as suggested interests.

This is unsupervised content similarity, not measured popularity or an engagement
prediction model. Rare tags, broad tags and mixed-program venues can produce
loose matches. The initial diagnostics are retrieval smoke checks, not a held-out
relevance benchmark. Changes to weights should be checked against human relevance
judgments before claiming improvements in recommendation quality.

## Browser behavior

`SimilarityModel` fetches nothing until a user has a non-search preference or opens
the interests editor. The core file supplies place and curated-tag vectors first.
Active-event vectors load in the background in batches of at most 2,048 events,
with two concurrent requests. Historical-event shards load only for saved event
preferences absent from the active set. Preferences remain in local storage.

The existing `placeKey` normalization (name + address) bridges database place IDs
to exports that omit IDs. The offline artifact keeps the DB IDs. A renamed place
currently needs its saved preference reselected; moving to exported stable place
IDs would remove this existing limitation.

The positive and negative profiles are separately normalized sums of known liked
and disliked entity vectors. For a unit event vector `e`, inferred affinity is:

```
max(0, dot(e, liked_profile)) - max(0, dot(e, disliked_profile))
```

Its range is [-1, 1]. Ranking is `100 * exact_preference_sum + 20 * affinity +
existing_baseline`. A one-point exact-preference advantage cannot be reversed
by the inferred term and baseline. Existing date, search, tag and viewport
eligibility rules still run before ranking.

New events absent from the model use an inverse-support-weighted mean of their
own known curated-tag vectors. Search phrases remain exact. A missing model,
unavailable shard, unsupported preference or schema/city mismatch falls back to
the available exact matches. Loading vectors invalidates cached map/list scores.

The empty interest finder suggests eligible loaded places/events or available
curated tags. It omits every already-rated entity, subtracts negative affinity,
and applies a cosine redundancy penalty when choosing up to six chips. Profiles
without usable positive vectors start with coverage-based, diverse suggestions;
coverage is not presented as popularity. Chips are only saved on explicit action.

## Artifact and refresh contract

Vectors are signed int8, scaled by 127, packed row-major as base64 and renormalized
after decoding. Every block contains ordered string `ids` and `vectors` fields.
The core adds corpus support counts for candidate selection. The manifest has a
schema version, domain, dimension count, content generation, timestamp, active
chunk list and historical shard list. History shards use `floor(event_id / 2048)`;
active chunks use consecutive groups, so sparse IDs do not create tiny requests.

Each complete generation lives in an immutable content-digest directory. The
manifest pointer is replaced last; the previous generation remains usable by
cached clients. The digest covers vectors, public metadata, entity IDs and active
IDs. Model artifacts carry no descriptions or private pipeline notes.

Rebuild after substantial database/tag changes and before a frontend release that
should include them. This command is deliberately independent of every crawl:
ordinary pipeline runs keep their current cost, and newer events use the fallback
until the next model build. No recurring automation is installed. Keep old model
generation directories during deployment; prune them only after cached clients
can no longer reference them.

## Verification

### Internal model explorer

```sh
./venv/bin/python pipeline/similarity_viewer.py
```

Open [the local model explorer](http://127.0.0.1:8766/). It reads the saved snapshot,
report and full-precision vectors in `.scratch/similarity`, including historical
events and keyword tags. No database connection or retraining is required.
`--workspace`, `--snapshot` and `--port` support other saved experiments. Restart
the viewer to load a newly trained model; an open viewer retains its loaded model.

Search any entity by name or database ID, then inspect 25–250 nearest neighbors
per type. Results show raw cosine scores, and clicking a neighbor changes the
comparison point. Filters select active/all/outside-active events, curated tags
or keywords, minimum cosine and full versus browser-int8 precision. The URL
preserves the selection and filters and supports back/forward navigation. These
raw neighbors omit the profile weights and suggestion diversity adjustment.

The server binds only to loopback and serves an explicit set of viewer assets and
read-only API routes. It is an internal local tool, not part of the public website
bundle or its upload. Full snapshot files are not served. Tags with no learned
vector remain searchable and show an explanation instead of invented neighbors.

### Tests

```sh
./venv/bin/python -m unittest pipeline/tests/test_similarity.py
./venv/bin/python -m unittest pipeline/tests/test_similarity_viewer.py
node --test src/js/tests/discoveryRanking.test.cjs src/js/tests/similarityModel.test.cjs
npm run build
```

Tests cover historical/suppressed records, geographic exclusion, ancestor
deduplication, cross-entity retrieval, signed quantization, reproducibility,
immutable generations, historical preferences, new-event fallback, exact-match
priority, negative interests, candidate exclusions and failure recovery.
