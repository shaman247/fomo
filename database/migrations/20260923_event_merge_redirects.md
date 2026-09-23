# Reviewed duplicate source identities

Apply `20260923_event_merge_redirects.sql` under the shared database write lock before the updated merger or duplicate helper runs. The migration adds one empty table and changes no event data. Its records are deployment data, not city-specific engine constants.

`merge_pair` captures the losing canonical name/primary URL and its source names/URLs at the same known venue, bounded to already reviewed occurrence slots. It records the survivor explicitly and carries older redirects through merge chains. It rejects self/reverse mappings and direct/inherited keep-separate decisions. `load_index` requires hidden reviewed losers, active unchanged survivors, matching venues and current survivor occurrences; missing or ambiguous evidence does not redirect.

The merger tries these identities before ordinary fuzzy matching. New seasons, changed clocks/end dates, new title spellings, different URL query parameters and unknown venues use ordinary matching. This is not a general URL-only merge rule. Dismissals and explicit film-version conflicts also precede automatic exact-name classification; the apply path rereads dismissals under lock.

For previously reviewed source-only repairs, `merge_pair(..., merge_tags=False)` preserves an already curated survivor's tags rather than unioning stale loser classifications. This option requires review; the default still merges tag collections and tag blocks always transfer.

No automatic historical backfill is included. September 23's bounded rollout records 253009 → 243516 and 260848 → 252987, with backups and unchanged canonical fields, schedules, links and tags. See `.claude/notes/backlog-reviewed-identity-20260923.md`. Later calls to the shared merge helper can record additional decisions independently.

For historically repaired pairs, `record_merge(..., reviewed_source_ids=[...])` captures explicitly reviewed source IDs already attached to the survivor, preserving their actual publisher and exact URLs. Invalid/missing ownership fails before writes; the existing venue and reviewed-slot limits still apply. The caller must verify the historical duplicate association. Five calendar decisions were backfilled this way or with ordinary pre-merge capture; see `.claude/notes/backlog-calendar-redirects-20260923.md`.
