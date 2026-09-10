# Content similarity and constituent matching

The model represents user profiles, venue programming, and tags as sets of
constituents. Matching uses the closest pair, never an aggregate centroid. The
browser keeps preferences on the device; training reads canonical public event
content without user behavior, API inference calls, or database writes.

## Build and refresh

The production builder uses a local sentence encoder in an isolated environment.
It does not install packages in the shared pipeline venv:

```sh
./venv/bin/python scripts/build_similarity.py --setup
./venv/bin/python scripts/build_similarity.py \
  --cases .claude/notes/similarity-relevance.json \
  --baseline .scratch/similarity-constituents/baseline
./venv/bin/python pipeline/similarity_health.py --report .scratch/similarity/health.json
```

Setup installs `pipeline/requirements-similarity.txt` in `.scratch/similarity-runtime`.
The encoder downloads once into `.scratch/similarity/encoder-cache`. Its weights
are pinned to `sentence-transformers/all-MiniLM-L6-v2` revision
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`; remote model code is disabled. Event text
is encoded locally. Cached weights load without network metadata requests; only
missing weights require a download. NumPy/SciPy-only experiments remain available using
`./venv/bin/python pipeline/similarity.py --encoder lexical`, but that challenger
regressed in the initial evaluation and is not the recommended release model.

The build exports `src/data/similarity/`; the normal frontend build copies it to
`dist/data/similarity/`. Publishing uses the existing full-site upload. Building
does not deploy. A checkout without artifacts still supports exact preferences.
The active deployment comes from `FOMO_CITY` and `pipeline/city_config.py`.

`--snapshot`, `--output`, and `--workspace` support reproducible candidates. Save
the previous manifest, report, vectors and snapshot in a separate workspace before
comparison. `--baseline` must not be the workspace being overwritten. A workspace
file lock prevents simultaneous builds from changing the same private artifacts.
A reused snapshot retains its capture timestamp; a new build timestamp does not
make old data fresh.

## Leaf representations

- Read all canonical events, places, tags, relationships and hierarchy in a
  repeatable-read, read-only transaction. Include historical events and exclude
  suppressed events. Raw crawl rows are not additional training documents.
- Encode each event/place's name, the first 1,600 description characters and
  curated tag names, subject to the encoder's token limit. Coordinates, addresses,
  excluded geographic tags and the Neighborhood hierarchy are not features.
- Encode a tag's own name as its semantic anchor. Unsupported and geographic tags
  stay unavailable. No invented tag definitions are added to the database.
- Fit a shared, uncentered 96-dimensional projection of the encoder's 384-dimensional
  output using the canonical entity corpus. This compresses individual content
  vectors; it does not average distinct interests or programs. Save the projection
  for repeatable inference. Model quality is evaluated after this compression.
- Cache encoder outputs by text plus pinned encoder revision. Subsequent refreshes
  encode only new or changed text, then rebuild the shared projection and aggregates.
  Never mix vectors from independently fitted projections.

The lexical challenger retains weighted TF-IDF and randomized SVD for comparison.
It removes inherited ancestor features, weights curated/text channels 0.8/0.6,
and retains all curated features plus up to 30,000 supported word features.

## Aggregates and scoring

An event has its individual content vector. A place with programming has actual
canonical event examples; a place without programming uses its intrinsic profile.
A tag keeps its own semantic anchor, the anchors of all supported descendant
branches, and examples of its attached events. Ancestor membership is expanded
without double-counting an entity. Venue audience tags never flow into event
features or new-event fallback.

The compact mode retains up to **12 event examples per aggregate**. Repeated
normalized event names at the same location contribute one example, preferring
active and then more recent records. Deterministic farthest-first selection keeps
actual examples of distinct programming, rather than generating averaged cluster
centers. Near-identical examples can stop selection early. All supported descendant
tag anchors remain; normalized public aliases union constituents and sum support.

This is an approximation to matching every historical event: a small set can miss
niche programs. `--max-constituents 0` keeps all distinct series for offline comparison
but substantially increases payloads and work. The user-approved default is compact
matching. The same maximum-pair rule applies on both sides of a comparison, including
candidate places/tags and the diversity penalty for suggested interest chips.

Liked and disliked profiles are separate unions of constituent vectors. For event
or aggregate `x`, compute maximum cosine against each profile, then:

```
positive_strength = max(0, (closest_positive - 0.35) / 0.65)
negative_strength = max(0, (closest_negative - 0.55) / 0.45)
affinity = positive_strength - negative_strength
rank = 100 * exact_preference_sum + 20 * affinity + existing_baseline
```

The higher negative threshold limits penalties from generic thematic overlap.
These are conservative operating defaults, not calibrated probabilities. Thresholds
are stored in the manifest/core and evaluation report. Exact preferences remain
stronger than inferred scores. Date, search, tag and viewport eligibility still
run before ranking. Adding an unrelated preference cannot dilute a previous match.
Broad profiles are scored in small asynchronous slices; exact ranking is available
while scores are prepared. Profile edits discard stale work, and score arrival
invalidates map/list caches.

## New events

The ordinary crawl → extract → merge → export flow makes new events immediately
eligible for display and exact preference matching. Before the next model refresh,
their known tag constituents provide temporary inferred scores, without averaging
multiple tags. Events with no known semantic tags get no inferred boost or penalty.
A new-event like/dislike still remains exact-only until that event has a model vector.
New tags and places likewise need a refresh for full semantic preference propagation.

The encoder cache makes refreshes incremental at the text-encoding stage. **A
per-crawl projection/publication hook is not installed**: the ordinary data uploader
does not publish model shards. Saved projection files enable future incremental
projection in a fixed generation, but such a hook must update aggregate membership
and publishing consistently. Until then, weekly/coverage-triggered model refreshes
and the tag fallback remain the production contract.

## Artifact and loading contract

Schema 2 stores signed int8 unit vectors scaled by 127, packed row-major as base64.
Aggregate blocks have unique string `ids`, `offsets` of length `ids.length + 1`,
packed constituent vectors, and support counts. Empty ranges represent unavailable
vectors. The browser renormalizes decoded vectors and interns identical constituents.
Schema 1 remains readable for rollback; its saved aggregates retain their legacy
single-vector representation.

The core includes topic/branch anchors and place metadata. It loads only when a
semantic preference or interest lookup needs it. Concrete examples load lazily:

- Active events: consecutive chunks of at most 2,048 events, two concurrent requests.
- Historical saved events: `floor(event_id / 2048)` shards as needed.
- Venue examples: batches of 128 place identities, fetched for selected or suggested places.
- Tag examples: batches of 64 tag identities, fetched for selected or suggested tags.

Aggregate downloads use two workers per request group. Missing shards keep exact
ranking available and retry on later edits/lookups. Profile and suggestion scoring
use the same constituent rule. The place key remains normalized name + address;
renamed venues need their saved preference reselected until stable exported place
IDs and preference migration are implemented.

Generations are immutable content-digest directories. Build in a private staging
directory, validate the relevance gate, install complete files, and replace the
manifest last. Repeated builds verify existing bytes instead of rewriting them.
The full-site uploader transfers nested assets before parent manifests and stops
on failure; uploaded files are atomically renamed. Keep workspace and output on
the same filesystem for atomic directory rename. Retain old generations for cached
clients and rollback; never prune them during a refresh.

## Quality evaluation and release procedure

The initial corpus-specific judgments are in `.claude/notes/similarity-relevance.json`:
180 assistant-authored topic judgments across 10 cases, including mixed preferences,
a parent tag and the known Black History Month false matches. They are regression
cases, **not independent human preference data**. They include historical candidates;
frontend date eligibility is tested separately. Some labeled events can also be
training constituents, so these metrics do not establish out-of-sample quality.

```sh
./venv/bin/python pipeline/similarity_eval.py \
  --workspace .scratch/similarity \
  --cases .claude/notes/similarity-relevance.json \
  --baseline .scratch/similarity-constituents/baseline \
  --report .scratch/similarity/evaluation-comparison.json --gate
```

Metrics include NDCG@5, pairwise ordering accuracy, wrong-first-result rate, and
per-query rankings. The comparative gate rejects aggregate ranking regressions
beyond 0.005 or an increased wrong-first-result rate. Without a baseline, it requires
NDCG@5 ≥ 0.9 and no wrong first result. Inspect per-query regressions too: an overall
improvement is not proof that every topic improved. Empty or invalid evaluations fail.
Passing `--cases` to the builder evaluates before replacing the public manifest;
failed candidates remain inspectable in their private workspace.

Unseen authored text probes are committed separately and use the saved projection
without refitting. They test cold-start semantics, not human preference satisfaction:

```sh
.scratch/similarity-runtime/bin/python pipeline/similarity_probes.py \
  --workspace .scratch/similarity --snapshot .scratch/similarity/snapshot.json.gz \
  --model-cache .scratch/similarity/encoder-cache --report .scratch/similarity/probes.json
```

The weekly **Similarity model: freshness, coverage and retrieval review** entry in
`.claude/recurring-checks.md` is read by `scripts/due_tasks.py` in pipeline Step 0.
Refresh at least every **7 days**, sooner below **95% active vector coverage** or
after substantial text/tag changes. Coverage matches IDs and does not detect edited
text for existing IDs; explicit refreshes after large edits address that limitation.

1. Save the previous model and run a candidate build with the relevance gate.
2. Run `similarity_health.py`, the tests below and the new-text probes. Health exit
   codes are 0 healthy, 1 refresh/review, 2 failed audit. Inspect retrieval samples,
   per-query results, zero vectors, payload sizes and browser scoring time.
3. Build and audit `dist/data/similarity`, then publish through the authorized
   full-site release process. Verify the served manifest and referenced shards;
   a local build is not evidence that production refreshed.
4. Save review notes and advance the queue by seven days only after the check is
   complete. Leave failures pending. Roll back by atomically restoring the saved
   prior manifest and republishing it while retaining all referenced generations.

Expand the benchmark with independent user judgments before treating the measured
regression-set gains as general recommendation-quality gains.

## Explorer and tests

```sh
./venv/bin/python pipeline/similarity_viewer.py
./venv/bin/python -m unittest discover -s pipeline/tests -p 'test_similarity*.py'
node --test src/js/tests/discoveryRanking.test.cjs src/js/tests/similarityModel.test.cjs
npm run build
```

The loopback-only explorer at http://127.0.0.1:8766 uses the same closest-constituent
rule, supports full/browser precision, and includes historical events and keywords.
Restart it after a build. It serves only its explicit viewer/API routes, never raw
snapshots. Full-precision vectors, constituent indices, report and projection stay
in `.scratch/similarity`; no descriptions or private notes ship in public artifacts.
