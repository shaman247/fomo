"""Refresh ordinary matched-event metadata only with attributable source evidence."""
import json
import re
from datetime import date, datetime
from math import ceil

from occurrence_times import standardize_time
from delivery import virtual_tags_for_location


def _label(value):
    return ' '.join((value or '').split()).casefold()


def _empty_room(value, location_name=None):
    label = _label(value)
    return (label in {'', 'not specified', 'unknown', 'tba', 'tbd', 'n/a', 'none'}
            or bool(label and label == _label(location_name)))


def _description(value):
    label = _label(value)
    return bool(label and label != 'no description available.')


def _substantive_description(value):
    """A price-only extraction cannot replace an existing program description.

    Match complete metadata statements, not length: a short corrected summary
    can be useful, and a real description may legitimately contain a price.
    """
    label = _label(value)
    price = r'(?:free(?: admission)?|\$\s*\d+(?:\.\d{1,2})?(?:\s*[-–/]\s*\$?\s*\d+(?:\.\d{1,2})?)?)'
    metadata = rf'(?:(?:price|cost|admission|tickets?)\s*:\s*)?{price}[.!]?'
    return _description(value) and re.fullmatch(metadata, label) is None


def _abridges(old, new):
    """A shorter same-source refresh must not discard substantive program text.

    Listing re-crawls often carry a one-line stub ("Brooklyn Brainery class",
    "Workshop at ... Price: $45.00") for an event whose detail page supplied the
    stored description. Measured 2026-10-07 over 1,576 such merge refreshes: a
    30-row sample had 20 clear losses, 10 neutral condensations and no
    corrections. Rendered session lists are not program text and stay
    replaceable; short descriptions keep the existing refresh policy.
    """
    before, after = _label(old), _label(new)
    return (len(before) >= 200 and 2 * len(after) <= len(before)
            and re.match(r'20\d\d-\d\d-\d\d\b', before) is None)


# Same-page paraphrase (BL21). Every same-source re-crawl re-extracts the
# page, and the model rewords it each time: 43,102 logged description
# refreshes in the 30 days to 2026-10-23, 89% from the very URL that supplied
# the stored text. Each rewrite churned icon-review context, similarity and
# embeddings without saying anything new. A rewrite of the same page keeps
# the stored text when its content words overlap at least this much (light
# stemming, rendered session lines dropped) and it neither adds a number nor a
# logistics word, nor drops a status marker such as "sold out".
_PARAPHRASE_OVERLAP = 0.5
_SCHEDULE_LINE = re.compile(r'^\s*20\d\d-\d\d-\d\d\b.*$', re.M)
_STOP_WORDS = frozenset(
    'the and for with from are this that its your you our will join all more who their they '
    'them his her was were has have can into about also any each than then there these those '
    'what when where which while how out not but get one'.split())
_LOGISTICS = ('sold', 'cancel', 'postpon', 'reschedul', 'waitlist', 'regist', 'rsvp', 'ticket',
              'donat', 'livestream', 'zoom', 'virtual', 'online', 'hybrid', 'relocat', 'capacity')
_LOGISTICS_WORDS = frozenset({'free', 'full', 'limited', 'closed', 'moved'})
_STATUS = ('sold', 'cancel', 'postpon', 'reschedul', 'waitlist')


def _tokens(text):
    text = _SCHEDULE_LINE.sub('', text or '').casefold().replace('’', "'")
    return re.findall(r"[a-z0-9$][a-z0-9'$:+.-]*[a-z0-9+]|[a-z0-9]", text)


def _stem(word):
    for suffix in ('ing', 'ed', 'es', 's', 'ly'):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[:-len(suffix)]
    return word


def _facts(tokens):
    """Numbers (dates, times, prices, ages) and logistics/status words."""
    numbers = {n for t in tokens for n in re.findall(r'\d+', t)}
    words = {w for w in tokens if w in _LOGISTICS_WORDS}
    words |= {p for p in _LOGISTICS for t in tokens if t.startswith(p)}
    return numbers | words


def _paraphrase(old, new):
    """A reworded extraction of the same text: nothing to refresh.

    Conservative by construction: a rewrite that adds a number or a logistics
    word ("Registration required", "Free with RSVP", "*SOLD OUT*") is a real
    change, as is one that drops a status marker (an event may be on sale
    again), or one replacing truncated text.
    """
    if re.search(r'(\.\.\.|…)\s*$', (old or '').strip()):
        return False
    before, after = _tokens(old), _tokens(new)
    old_facts, new_facts = _facts(before), _facts(after)
    if new_facts - old_facts or {p for p in _STATUS if p in old_facts} - new_facts:
        return False
    words = [{_stem(w) for w in toks if len(w) > 2 and w not in _STOP_WORDS
              and not any(c.isdigit() for c in w)} for toks in (before, after)]
    if words[0] == words[1]:
        return True
    union = words[0] | words[1]
    return bool(words[0] and words[1]) and len(words[0] & words[1]) / len(union) >= _PARAPHRASE_OVERLAP


def _same_page(a, b):
    return (a or '').strip().rstrip('/') == (b or '').strip().rstrip('/')


# Tag-vote hysteresis (BL21). merger.compute_voted_tags keeps a tag when the
# current crawl supplies it as curated or when at least 30% of crawls carry
# it. A tag near that line flaps on alternate merges (Live Music -425/+289,
# DJ -123/+126, Virtual -111/+111 across events, 2026-10-13), re-queueing
# icon reviews and refreshing similarity each time. A tag the event already
# holds therefore stays while a lower share of crawls still carries it; a
# tag the event lacks must still clear the full threshold to be added.
TAG_KEEP_SHARE = 0.15


def tag_keep_threshold(total_crawls):
    """Crawl votes a held tag needs to stay (the add threshold is 30%, min 2)."""
    return max(1, ceil(total_crawls * TAG_KEEP_SHARE))


def tag_vote_survives(tag, count, threshold, total_crawls, current_curated, held_tags):
    """The compute_voted_tags survival test with hysteresis for held tags.

    `held_tags` is the event's current tag set (names). Without it the test
    is exactly the add rule, so callers that pass nothing keep the old vote.
    """
    if tag in current_curated or count >= threshold:
        return True
    return tag in (held_tags or ()) and count >= tag_keep_threshold(total_crawls)


def _grouped(raw):
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return True  # Unknown provenance must not permit replacing grouped text.
    if data is not None and not isinstance(data, dict):
        return True
    return bool(isinstance(data, dict) and data.get('session_details'))


def _timestamp(value):
    try:
        return datetime.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _delivery_candidate(event, incoming):
    # Positive source evidence can restore a lost label. An omitted Virtual
    # marker cannot establish an in-person transition, and an existing online
    # or hybrid label may carry attendance details that must not be discarded.
    return (not event.get('reviewed')
            and not virtual_tags_for_location(event.get('location_name'))
            and bool(virtual_tags_for_location(incoming.get('location_name'))))


def _slots(occurrences, today):
    slots = set()
    for row in occurrences:
        start = str(row['start_date'] or '')
        end = str(row.get('end_date') or start)
        if max(start, end) < str(today):
            continue
        slots.add((start, standardize_time(row.get('start_time')), end))
    return slots


def plan_source_metadata_refresh(event, incoming, sources, occurrences,
                                 incoming_occurrences, today=None):
    """Return independent field changes; never replace a specific room.

    A canonical description may refresh only if unreviewed and still an exact
    copy of this publisher's older source. A lost online/hybrid location label
    may refresh under the same constraints; absence is not in-person evidence.
    Require one publisher, the same
    known venue, a strictly newer crawl, and evidence covering every remaining
    session. A rolling subset must not describe the whole canonical series.
    Grouped date-specific descriptions retain their separate refresh policy.
    A substantially shorter text never replaces substantive program prose,
    and a reworded re-extraction of the same page never replaces anything.
    """
    today = today or date.today()
    if (event.get('suppressed') or not incoming.get('website_id')
            or event.get('website_id') != incoming['website_id']
            or not event.get('location_id')
            or event['location_id'] != incoming.get('location_id')
            or _grouped(incoming.get('raw_data'))):
        return {}
    prior = [s for s in sources if s['id'] != incoming['id']]
    if not prior or any(s.get('website_id') != incoming['website_id'] for s in prior):
        return {}
    fresh = _timestamp(incoming.get('crawled_at'))
    times = [_timestamp(s.get('crawled_at')) for s in prior]
    if not fresh or any(t is None for t in times) or fresh <= max(times):
        return {}
    current_slots = _slots(occurrences, today)
    if not current_slots or not current_slots <= _slots(incoming_occurrences, today):
        return {}

    fields = {}
    if (_delivery_candidate(event, incoming)
            and any(_label(s.get('location_name')) == _label(event.get('location_name'))
                    for s in prior)
            and not any(_grouped(s.get('raw_data')) for s in prior)):
        fields['location_name'] = incoming['location_name'].strip()[:255]
    room = (incoming.get('sublocation') or '').strip()
    if (_empty_room(event.get('sublocation'), event.get('location_name'))
            and not _empty_room(room, incoming.get('location_name'))
            and _label(room) != 'varies by session; see description'
            # A known historical room at this venue is contrary evidence.
            and all(_empty_room(s.get('sublocation'), s.get('location_name'))
                    or _label(s.get('sublocation')) == _label(room)
                    for s in prior if s.get('location_id') == event['location_id'])):
        fields['sublocation'] = room[:255]

    old, new = event.get('description'), incoming.get('description')
    owners = [s for s in prior if s.get('description') == old]
    if (not event.get('reviewed') and _description(old) and _substantive_description(new)
            and old != new and owners and not _abridges(old, new)
            and not any(_grouped(s.get('raw_data')) for s in prior)
            # A re-extraction of the page that supplied the stored text,
            # reworded, says nothing new (BL21).
            and not (any(_same_page(s.get('url'), incoming.get('url')) for s in owners)
                     and _paraphrase(old, new))):
        fields['description'] = new
    return fields


def refresh_source_metadata(cursor, event_id, crawl_event_id, today=None,
                            edit_logger=None):
    """Plan and apply a refresh inside the merger's existing transaction/lock."""
    event_keys = ('id', 'website_id', 'reviewed', 'suppressed', 'location_id',
                  'location_name', 'sublocation', 'description')
    source_keys = ('id', 'website_id', 'crawled_at', 'location_id', 'location_name',
                   'sublocation', 'description', 'raw_data', 'url')
    cursor.execute('''SELECT e.id,e.website_id,e.reviewed,e.suppressed,e.location_id,
        e.location_name,e.sublocation,e.description,
        ce.id,cr.website_id,cr.crawled_at,ce.location_id,ce.location_name,
        ce.sublocation,ce.description,ce.raw_data,ce.url
        FROM events e JOIN crawl_events ce ON ce.id=%s
        JOIN crawl_results cr ON cr.id=ce.crawl_result_id WHERE e.id=%s''',
                   (crawl_event_id, event_id))
    row = cursor.fetchone()
    if not row:
        return {}
    event = dict(zip(event_keys, row[:len(event_keys)]))
    incoming = dict(zip(source_keys, row[len(event_keys):]))
    # Most matches bring no usable change; avoid history/occurrence queries.
    room_candidate = (_empty_room(event['sublocation'], event['location_name'])
                      and not _empty_room(incoming['sublocation'], incoming['location_name']))
    description_candidate = (not event['reviewed'] and _substantive_description(incoming['description'])
                             and _description(event['description'])
                             and incoming['description'] != event['description'])
    delivery_candidate = _delivery_candidate(event, incoming)
    if (not (room_candidate or description_candidate or delivery_candidate) or event['suppressed']
            or event['website_id'] != incoming['website_id']
            or not event['location_id'] or event['location_id'] != incoming['location_id']
            or _grouped(incoming['raw_data'])):
        return {}
    cursor.execute('''SELECT ce.id,cr.website_id,cr.crawled_at,ce.location_id,
        ce.location_name,ce.sublocation,ce.description,ce.raw_data,ce.url
        FROM event_sources es JOIN crawl_events ce ON ce.id=es.crawl_event_id
        JOIN crawl_results cr ON cr.id=ce.crawl_result_id WHERE es.event_id=%s''', (event_id,))
    sources = [dict(zip(source_keys, r)) for r in cursor.fetchall()]
    cursor.execute('''SELECT 0,start_date,start_time,end_date FROM event_occurrences WHERE event_id=%s
        UNION ALL SELECT 1,start_date,start_time,end_date FROM crawl_event_occurrences
        WHERE crawl_event_id=%s''', (event_id, crawl_event_id))
    schedules = ([], [])
    for kind, start, time, end in cursor.fetchall():
        schedules[kind].append(dict(start_date=start, start_time=time, end_date=end))
    fields = plan_source_metadata_refresh(event, incoming, sources, *schedules, today=today)
    if fields:
        cursor.execute('UPDATE events SET ' + ','.join(k + '=%s' for k in fields)
                       + ' WHERE id=%s', (*fields.values(), event_id))
        if edit_logger:
            for field, value in fields.items():
                edit_logger.log_update('events', event_id, field, event[field], value)
    return fields
