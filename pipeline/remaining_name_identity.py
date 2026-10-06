"""Explicit identity markers that generic title containment must not erase.

These predicates only veto matches. Ordinary missing labels, abbreviations,
presenter credits and changing concert lineups do not establish a conflict.
Explicit booking-section IDs additionally distinguish a registered section
from its unlabelled curriculum umbrella.
"""
import re
import unicodedata


def _norm(value):
    value = unicodedata.normalize('NFKD', value.casefold())
    return ' '.join(re.findall(r'\w+', ''.join(
        c for c in value if not unicodedata.combining(c))))


def registration_section_mismatch(left, right):
    """A labelled booking section cannot be absorbed by a course umbrella.

    These long, explicit registration identifiers are producer-preserved
    identity, unlike course levels, dates or ordinary title numbers. A bare
    curriculum name does not identify one of its separately bookable sections.
    """
    def section(value):
        match = re.search(
            r'\b(?:sawyer section|registration section(?: id)?)\s+(\d{5,})$',
            _norm(value))
        return match[1] if match else None
    a, b = section(left), section(right)
    return bool((a or b) and a != b)


def explicit_program_role_mismatch(left, right):
    """Keep a named production's explicit participation/delivery parts separate.

    Both titles must name the same parent and end with concrete role labels.
    An unlabelled parent or a workshop about performance supplies no conflict.
    """
    def role(value):
        match = re.fullmatch(
            r'(.+?) (enrollment and rehearsal course|tech and dress rehearsals|'
            r'performances?|exhibitions?|live concerts?|online dance films?)', _norm(value))
        if not match:
            return None
        label = match[2]
        kind = ('rehearsal' if label in ('enrollment and rehearsal course', 'tech and dress rehearsals')
                else 'online_film' if label.startswith('online ')
                else 'live_concert' if label.startswith('live ')
                else 'exhibition' if label.startswith('exhibition')
                else 'performance')
        return match[1], kind
    a, b = role(left), role(right)
    return bool(a and b and a[0] == b[0] and frozenset((a[1], b[1])) in (
        frozenset(('rehearsal', 'performance')),
        frozenset(('live_concert', 'online_film')),
        frozenset(('performance', 'exhibition'))))


def numbered_course_mismatch(left, right):
    """Explicit course numbers under the same named curriculum are identity."""
    def parts(value):
        return re.fullmatch(r'(.+?)\s+course\s+(\d+)\s+(.+)', _norm(value))
    a, b = parts(left), parts(right)
    if not a or not b or a[1] != b[1]:
        return False
    if a[2] != b[2]:
        return True
    # A named course may have separately registered physical and remote
    # sessions. Both modes must be explicit; a neutral course title is unknown.
    return any('virtual session' in remote and 'in person' in physical
               for remote, physical in ((a[3], b[3]), (b[3], a[3])))


def parent_afterparty_mismatch(left, right):
    """A concert/benefit and its explicitly billed afterparty are distinct.

    Bare party names often abbreviate an afterparty and remain eligible. Both
    sides must retain the concrete concert/benefit label to invoke this rule.
    """
    a, b = _norm(left), _norm(right)
    after = [bool(re.search(r'\bafter\s?party\b', n)) for n in (a, b)]
    if after[0] == after[1]:
        return False
    for label in ('rock show', 'concert', 'benefit'):
        pattern = rf'\b{label}\b'
        if re.search(pattern, a) and re.search(pattern, b):
            return True
    return False


def sports_watch_dance_mismatch(left, right):
    """A named sports matchup watch party is not a venue's dance party."""
    a, b = _norm(left), _norm(right)
    return any(
        re.search(r'\bwatch party\b', watch)
        and re.search(r'\bv(?:s)?\b', watch)
        and (re.search(r'\bdance party\b', dance)
             or ('salsa' in dance.split() and 'party' in dance.split()))
        and not re.search(r'\bwatch party\b', dance)
        for watch, dance in ((a, b), (b, a)))


def branded_boat_mismatch(left, right):
    """A shared presenter cannot outweigh disjoint named boat programs."""
    def brand(value):
        value = _norm(value)
        if not re.search(r'\bpresents\b|\bpowered by\b', value):
            return set()
        value = re.sub(r'^.*?\bpresents\s+', '', value)
        match = re.match(r'(.+?)\s+boat\b', value)
        if not match:
            return set()
        # Require a named brand, not a generic genre/venue description.
        return set(match[1].split()) - {
            'the', 'a', 'an', 'nyc', 'new', 'york', 'party', 'cruise',
            'sunset', 'latin', 'reggaeton', 'hip', 'hop', 'house', 'music',
            'r', 'b', 'yacht', 'on', 'river', 'hudson', '1',
        }
    a, b = brand(left), brand(right)
    return bool(a and b and a.isdisjoint(b))


def duration_class_subject_mismatch(left, right):
    """Quoted or unquoted art subjects outrank identical duration/room suffixes."""
    def parts(value):
        # A duration AND a colon-delimited branch label distinguishes this from
        # ordinary artist credits, age ranges and parenthetical show metadata.
        return re.fullmatch(
            r'\s*(.+?)\s*\((\d+(?:\.\d+)?\s*hr\s*:[^()]+)\)'
            r'(?:\s*\$\d+(?:\.\d+)?)?\s*', value, re.I)
    a, b = parts(left), parts(right)
    if not a or not b or _norm(a[2]) != _norm(b[2]):
        return False
    ignored = {'a', 'an', 'the', 'of', 'in', 'on', 'at', 'with', 'and'}
    wa, wb = set(_norm(a[1]).split()) - ignored, set(_norm(b[1]).split()) - ignored
    # Preserve simple plural variants in either direction without stripping a
    # suffix from every proper name (e.g. "Paris").
    def difference(one, other):
        return {w for w in one if w not in other and w + 's' not in other
                and not (w.endswith('s') and w[:-1] in other)}
    return bool(wa and wb and difference(wa, wb) and difference(wb, wa))


def college_audience_mismatch(left, right):
    """Explicit pre-college and college/adult webinar audiences are separate."""
    a, b = _norm(left), _norm(right)
    return any('pre college' in pre and 'college adult' in adult
               and 'webinar' in pre and 'webinar' in adult
               for pre, adult in ((a, b), (b, a)))


def holiday_weekday_mismatch(left, right):
    """Separately billed weekday editions of a holiday party are distinct."""
    a, b = _norm(left), _norm(right)
    holidays = {'halloween', 'christmas', 'thanksgiving'}
    weekdays = {'monday', 'tuesday', 'wednesday', 'thursday', 'friday',
                'saturday', 'sunday'}
    wa, wb = set(a.split()), set(b.split())
    da, db = wa & weekdays, wb & weekdays
    return bool('party' in wa and 'party' in wb and wa & wb & holidays
                and len(da) == len(db) == 1 and da != db)


def named_class_variant_mismatch(left, right):
    """Explicit meditation session labels and kit subjects outrank metadata."""
    a, b = _norm(left), _norm(right)
    def meditation(value):
        return re.fullmatch(r'30 minute (lunchtime|after work) meditation (.+)', value)
    ma, mb = meditation(a), meditation(b)
    if ma and mb and ma[2] == mb[2] and ma[1] != mb[1]:
        return True
    # A general program is a separately named class, not the umbrella label
    # for every child class held at the same center and time.
    def class_kind(value):
        value = re.sub(r'\s+note special time\b', '', value)
        child = re.fullmatch(r'tweens (?:meditation )?class (.+)', value)
        general = re.fullmatch(r'(?:sunday )?general program(?: class)? (.+)', value)
        return ('child', child[1]) if child else ('general', general[1]) if general else None
    ka, kb = class_kind(a), class_kind(b)
    if ka and kb and ka[1] == kb[1] and ka[0] != kb[0]:
        return True
    ca = re.fullmatch(r'(cat|dog) toy take (?:and )?make (.+)', a)
    cb = re.fullmatch(r'(cat|dog) toy take (?:and )?make (.+)', b)
    return bool(ca and cb and ca[2] == cb[2] and ca[1] != cb[1])


def seasonal_mixology_mismatch(left, right):
    """An explicitly named Halloween cocktail class is its own recipe session.

    Scope this to the reviewed ice-cream cocktail curriculum. A vague holiday
    adjective on unrelated programs or two spellings of the themed class does
    not establish different identity.
    """
    a, b = _norm(left), _norm(right)
    family = {'ice', 'cream', 'cocktail', 'mixology'}
    if not all(family <= set(value.split()) for value in (a, b)):
        return False
    return any('halloween cocktails' in themed and 'halloween' not in regular
               and 'mixology class' in regular
               for themed, regular in ((a,b),(b,a)))


def named_tour_subject_mismatch(left, right):
    """Explicit tour subjects survive a common multiword place/presenter.

    A generic tour title remains unknown. Both titles must carry distinct
    named subjects and share at least two other words; no city-specific venue
    or publisher is embedded in this rule.
    """
    def parts(value):
        words = set(_norm(value).split())
        if not words & {'tour', 'tours'}:
            return None
        kinds = set()
        if words & {'spooky', 'haunted', 'halloween'}:
            kinds.add('haunted')
        if {'art', 'architecture'} <= words:
            kinds.add('architecture')
        if 'historical' in words:
            kinds.add('historical')
        # A separately branded weekend's umbrella tours are not a specific
        # recurring subject tour merely because the same place is named.
        # Keep an explicitly themed weekend eligible for that same theme.
        if not kinds and re.match(r'^.+\bweekend\s*:\s*.+\btours?\b', value, re.I):
            kinds.add('branded_weekend')
        anchors = words - {'tour', 'tours', 'spooky', 'haunted', 'halloween', 'art', 'architecture',
                           'historical', 'the', 'a', 'an', 'of', 'and', 's',
                           'sailor', 'sailors'}
        return kinds, {w for w in anchors if not w.isdigit()}
    a, b = parts(left), parts(right)
    return bool(a and b and len(a[0]) == len(b[0]) == 1
                and a[0] != b[0] and len(a[1] & b[1]) >= 2)


def named_tree_lighting_display_mismatch(left, right):
    """A named tree's lighting occasion differs from its explicit display.

    Both roles and the same multiword place must be present. A generic tree
    label, a light-show title or two lighting aliases remain undecided.
    """
    def role(value):
        match = re.fullmatch(r'(.+?) (?:christmas )?tree (lighting(?: ceremony)?|display)',
                             _norm(value))
        if not match or len(match[1].split()) < 2:
            return None
        return match[1], 'lighting' if match[2].startswith('lighting') else 'display'
    a, b = role(left), role(right)
    return bool(a and b and a[0] == b[0] and a[1] != b[1])


def explicit_disjoint_age_band_mismatch(left, right):
    """Exact same program with explicitly disjoint age suffixes is distinct.

    An unlabelled program or overlapping audiences remain eligible; this is
    not a general numeric-title or minimum-age heuristic.
    """
    def band(value):
        match = re.search(r'\(\s*ages?\s*(\d{1,2})(?:\s*[-–—]\s*(\d{1,2})|(\+))\s*\)\s*$',
                          value or '', re.I)
        if not match:
            return None
        start, end = int(match[1]), int(match[2]) if match[2] else float('inf')
        # Bilingual titles may repeat the same age qualifier in their other
        # language. Remove only an exactly agreeing Chinese age parenthesis;
        # a contradictory translation remains part of the parent and cannot
        # manufacture a same-program witness.
        def repeated_age(other):
            lo = int(other[1])
            hi = int(other[2]) if other[2] else float('inf')
            return '' if (lo, hi) == (start, end) else other[0]
        parent_text = re.sub(
            r'\(\s*(\d{1,2})(?:\s*[-–—]\s*(\d{1,2})|(\+))\s*[岁歲]\s*\)',
            repeated_age, value[:match.start()])
        parent = _norm(parent_text)
        if len(parent.split()) < 2 or end < start:
            return None
        return parent, start, end
    a, b = band(left), band(right)
    return bool(a and b and a[0] == b[0] and (a[2] < b[1] or b[2] < a[1]))


GUARDS = (registration_section_mismatch, explicit_program_role_mismatch,
          named_tree_lighting_display_mismatch, explicit_disjoint_age_band_mismatch,
          numbered_course_mismatch, parent_afterparty_mismatch,
          sports_watch_dance_mismatch, branded_boat_mismatch,
          duration_class_subject_mismatch, college_audience_mismatch,
          holiday_weekday_mismatch, named_class_variant_mismatch,
          seasonal_mixology_mismatch, named_tour_subject_mismatch)


def remaining_name_identity_mismatch(left, right):
    return any(guard(left, right) for guard in GUARDS)
