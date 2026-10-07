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
  --baseline .scratch/similarity-previous \
  --previous-model .scratch/similarity-previous
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

For routine refreshes, `--previous-model` reuses the saved MiniLM projection and
starts aggregate selection from its valid examples. Use a separate saved workspace
containing `report.json`, `vectors.npz`, `projection.npz` and `snapshot.json.gz`.
The command above assumes the accepted previous workspace was saved to
`.scratch/similarity-previous`; never copy a failed candidate as that baseline.
Encoder identity/revision, basis dimensions and orthonormality are checked. New and
edited text is encoded from the current snapshot, and every aggregate is rebuilt
against current membership; deleted/suppressed/detached examples cannot survive
just because they were previously selected. The report records the previous
generation and projection mode. `--baseline` remains an independent evaluation
comparison; it does not silently select the refresh mode.

Omit `--previous-model` for an explicitly evaluated projection refit. A saved
projection can become less representative as the corpus changes: inspect retained
energy and held-out retrieval before deciding to refit. Neither refresh mode
weakens the relevance gate or uses evaluation labels to select examples.

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
  encode only new or changed text, reuse or refit the shared projection, and rebuild aggregates.
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

Each tag constituent is conditioned on that tag before export:
`unit(example + 0.5 * tag_anchor)`. This applies separately to its event examples
and descendant anchors; it does not average different examples or user interests.
A Spanish-language architecture tour can illustrate Architecture without passing
along its entire language similarity unchanged. Event and venue vectors remain
unconditioned. Exact preferences still rank separately, and source memberships and
indices remain available for stable refreshes and overlap diagnostics.

Before anchor conditioning, event examples receive a contextual view for the
selected tag. Co-tags outside its ancestor/descendant hierarchy whose anchor cosine
is below 0.15 identify incidental aspects. Their directions are projected off the
selected anchor, deduplicated with SVD, then removed at half strength. Related
aspects remain. This reduces series/format transfer while preserving genuine
mixed-topic examples. No event IDs or topic names are special-cased. Raw event and
venue vectors, source memberships and refresh indices remain unchanged. Sparse
contextual overrides are stored in the private archive; reports with
`aspectSuppression` require those overrides when loaded.

Conditioning happens before signed-int8 quantization in both the exporter and
evaluator. The public schema stays version 2 because its packed vectors already
contain the transformation; the browser still uses the same closest-pair rule.
Private reports declare `tagAnchorWeight`; old reports without it use zero.
The local explorer applies the same transformation before displaying scores.

Stable refreshes identify an old example by its venue ID and normalized event
name, resolve it to the current preferred record of that series, then fill any
vacant slots with farthest-first selection. A full set swaps an example only if
the worst-covered current program's nearest-example cosine improves by more than
0.02 **and** by more than the largest coverage loss the eviction causes to any
program (usually the evicted series itself). Max-min alone let an outlying
newcomer evict a distinct mode for a marginal floor gain: on the 2026-10-07
snapshot 91% of its 1,444 swaps cost some program more coverage than the floor
gained (median gain 0.049 vs loss 0.417), including Architecture's only
healthcare-design talk. With the bound, 131 swaps remain, all replacing redundant
coverage (median loss 0.075). A summed net-coverage rule was measured and rejected
(it still allowed that eviction because many similar tour programs gained), as was
a description-length floor (swap newcomers were not systematically thinner than
the examples they evicted). This limits churn from recency changes while allowing
new programming to replace redundant coverage. The compact limit remains 12; no benchmark-specific
events receive protection. Topic aliases union constituents; venues retain their
distinct database identities even when their names and addresses coincide.

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

Schema 2 stores signed int8 vectors packed row-major as base64. New reports declare
`quantization: max-abs-int8`: divide each vector by its largest absolute component
before rounding times 127. Decoding renormalizes to unit length, so no per-vector
scale or browser change is needed. Older reports default to `unit-int8` (unit
vectors times 127). Evaluators and the local explorer follow each report's mode.
The byte count stays fixed; using more byte values increases gzip payload size
slightly in exchange for better directional precision.

Reports since generation `6c74e411bd76358a` declare `quantization: dct-int8`. Every
exported vector (events, venue/tag constituents, anchors) is first multiplied by
the same orthonormal DCT-II matrix (`similarity.dct_rotation`, closed form, nothing
stored), then each vector keeps whichever of 31 byte scales (0.70–1.00 of max-abs)
rounds closest to its direction. The uncentered projection puts the shared mean
direction on axis 0 (median max-abs component 0.47; 0.27 after rotation), so one
per-vector scale wasted precision on the other 95 axes. Cosines are rotation
invariant and the browser compares only exported vectors of one generation, so the
decoder, scorer and byte count are unchanged and old generations still decode.
Measured on the 2026-10-07 snapshot: mean direction error 1−cos 5.7e-5 → 1.9e-5,
pairwise cosine error std 0.0014 → 0.0009; gzip +1.6–2.4% per payload class (core
1.166 → 1.185 MB, places 4.32 → 4.41 MB, tag examples 2.91 → 2.97 MB, active 3.19 →
3.27 MB); real-module parity over 219 scores max error 1.9e-7 with unchanged CPU
time. It cleared an int8-only near-tie flip (ISLAA 238672 vs SNFL tour 249775) that
failed the browser source and hard-negative gates. Private vectors stay unrotated;
`browser_vectors(..., 'dct-int8')` returns rotated vectors, so only compare them with
other browser vectors of the same mode.
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
use the same constituent rule. Place keys are `id:<location_id>`, using the IDs
already exported with locations. After loading the complete location dataset,
the browser migrates unambiguous legacy name/address preferences and preserves
any explicit ID-based stance on a collision. Ambiguous or unavailable legacy
venues remain unresolved. Renames and address changes after migration preserve
the preference. The core carries unambiguous legacy aliases, and the browser also
resolves stable preferences against older models while they remain deployed.
A rename predating migration cannot be inferred from current metadata alone.

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

The builder gates both full precision and the int8 browser representation.
Evaluation reports list candidate/profile constituent overlap so perfect
self-matches remain visible as training overlap. Non-finite scores or metrics
fail closed. The expanded authored probe set has 21 unseen descriptions and 163
judgments across seven topics and three mixed-profile cases, including architecture
distractors and a mixed like/dislike profile. It remains assistant-authored evidence,
not independent user validation.

Unseen authored text probes are committed separately and use the saved projection
without refitting. They test cold-start semantics, not human preference satisfaction:

```sh
.scratch/similarity-runtime/bin/python pipeline/similarity_probes.py \
  --workspace .scratch/similarity --snapshot .scratch/similarity/snapshot.json.gz \
  --model-cache .scratch/similarity/encoder-cache --report .scratch/similarity/probes.json \
  --baseline .scratch/similarity-previous --gate
```

Repeat with `--browser` to check int8 precision. Use each workspace's own saved
projection; the probe runner never refits it. Without a baseline, `--gate` applies
the absolute quality threshold.

Also gate the independently reported hard-negative regression set at both
precisions, rather than pooling its metrics with the older cases:

```sh
./venv/bin/python pipeline/similarity_eval.py \
  --workspace .scratch/similarity \
  --cases pipeline/tests/fixtures/similarity_hard_negatives.json \
  --baseline .scratch/similarity-previous \
  --report .scratch/similarity/hard-negatives.json --gate
```

Repeat with `--browser` and a separate report path. Its 39 judgments cover
incidental language, background music, repeated series names, genuine mixed-topic
programs, and positive/negative preference controls. These cases and the authored
text probes were used during model development, so neither is an independent
held-out evaluation of the final scoring choice. Retain independent user review
as a separate release-quality requirement.

Also run `similarity_probes.py --cases
pipeline/tests/fixtures/similarity_aspect_probes.json` with the same workspace,
snapshot, baseline and gate, at both precisions. Its 16 additional texts and 35
judgments cover language versus subject, repeated series names, background music,
legitimate mixed topics and negative preferences. These authored cases were used
for development; they do not replace independent user judgments.

The weekly **Similarity model: freshness, coverage and retrieval review** entry in
`.claude/recurring-checks.md` is read by `scripts/due_tasks.py` in pipeline Step 0.
Refresh at least every **7 days**, sooner below **95% active vector coverage** or
after substantial text/tag changes. Coverage matches IDs and does not detect edited
text for existing IDs; explicit refreshes after large edits address that limitation.

1. Save the previous model and run a candidate build with the relevance gate.
2. Run `similarity_health.py`, the tests below, new-text probes and hard-negative gates. Health exit
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
