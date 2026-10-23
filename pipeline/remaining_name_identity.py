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


_BAND_UNIT = r'(?:\s*(months?|mos?|years?|yrs?)(?:\s*old)?)?'
_AGE_BAND_RE = re.compile(
    r'\b(ages?|grades?)\s*:?\s*'
    r'(\d{1,2}|birth|newborns?|pre-?k|k)' + _BAND_UNIT +
    r'\s*(?:(?:[-–—]|\bto\b|\bthrough\b|\bthru\b)\s*(\d{1,2})' + _BAND_UNIT +
    r'(?!\s*[/:.]\d)|(\+|\s*(?:&|and)\s*(?:up|older|over)\b|\s*or\s*older\b))',
    re.I)


def _band_bound(token, unit):
    token = token.lower().replace('-', '')
    value = {'birth': 0, 'newborn': 0, 'newborns': 0, 'k': 0, 'prek': -1}.get(token)
    value = int(token) if value is None else value
    return value / 12 if unit and unit.lower().startswith('mo') else value


def _age_band(value):
    """(kind, low, high, parent) for ONE explicit age/grade band, else None.

    "(Ages 4-6)", "for ages 9-13", "• Ages 4-8 •", "(Ages Birth-1 year)",
    "Grades K-2", "Ages 6-18 months", "(Ages 7+)" / "ages 5 and up". A title
    naming two bands, or a band followed by another number ("Ages 4-8 & 9-13"),
    is ambiguous and returns None.
    """
    matches = list(_AGE_BAND_RE.finditer(value or ''))
    if len(matches) != 1:
        return None
    match = matches[0]
    if re.match(r'\s*(?:[&,/]|\band\b|\bor\b)\s*\d', value[match.end():], re.I):
        return None
    kind = 'grade' if match[1].lower().startswith('grade') else 'age'
    hi_unit = match[5]
    lo_unit = match[3] or (hi_unit if hi_unit and hi_unit.lower().startswith('mo') else None)
    low = _band_bound(match[2], lo_unit)
    high = _band_bound(match[4], hi_unit) if match[4] else float('inf')
    if high < low:
        return None
    # Bilingual titles may repeat the same age qualifier in their other
    # language. Remove only an exactly agreeing Chinese age parenthesis;
    # a contradictory translation remains part of the parent and cannot
    # manufacture a same-program witness.
    def repeated_age(other):
        lo = int(other[1])
        hi = int(other[2]) if other[2] else float('inf')
        return '' if (lo, hi) == (low, high) else other[0]
    parent_text = re.sub(
        r'\(\s*(\d{1,2})(?:\s*[-–—]\s*(\d{1,2})|(\+))\s*[岁歲]\s*\)',
        repeated_age, value[:match.start()] + ' ' + value[match.end():])
    return kind, low, high, ' '.join(w for w in _norm(parent_text).split() if w != 'for')


def explicit_disjoint_age_band_mismatch(left, right):
    """The same program offered to explicitly different age/grade cohorts.

    Both titles name one band of the same kind, the rest of the titles agree
    exactly (at least two words, "for" ignored), and
    the bands are disjoint or only touch at an endpoint: libraries number
    consecutive cohorts "Ages 1-2" / "Ages 2-4" and "9-13" / "13-17" (BL62).
    An unlabelled program or genuinely overlapping audiences ("Ages 7+" vs
    "Ages 9-12") remain eligible; this is not a general numeric-title or
    minimum-age heuristic.
    """
    a, b = _age_band(left), _age_band(right)
    if not (a and b) or a[0] != b[0] or a[1:3] == b[1:3]:
        return False
    if a[3] != b[3] or len(a[3].split()) < 2:
        return False
    return a[2] <= b[1] or b[2] <= a[1]


_ROMAN_TAIL_RE = re.compile(
    r"(?<![\w'’.&/-])([IVX]{1,5})(?=\s*[.!]?\s*$|\s*[:(\[|]|\s+[-–—]\s)")


def _roman_tail(value):
    """(head words, value) for an uppercase Roman numeral I-XX ending a title.

    "Beethoven Piano Sonatas II", "Act III: …". Sequels, cycles and course
    levels publish one listing per numeral; the head words alone are shared.
    """
    match = _ROMAN_TAIL_RE.search(value or '')
    if not match or not re.fullmatch(r'X{0,2}(?:IX|IV|V?I{0,3})', match[1]):
        return None
    head = _norm(value[:match.start()])
    if not head:
        return None
    digits = {'I': 1, 'V': 5, 'X': 10}
    token, total = match[1], 0
    for i, ch in enumerate(token):
        val = digits[ch]
        total += -val if i + 1 < len(token) and val < digits[token[i + 1]] else val
    return head, total


def trailing_roman_ordinal_mismatch(left, right):
    """Same title head, different bare trailing Roman numeral (BL62).

    "Beethoven Piano Sonatas II" is a raw substring of "… III", which is how
    the processor's containment grouping and the merger's ratio tiers fused
    CMS's two cycle concerts. Requires a numeral on BOTH sides and one head
    ending the other ("CMS: Beethoven Piano Sonatas III" still compares).
    """
    a, b = _roman_tail(left), _roman_tail(right)
    if not (a and b) or a[1] == b[1]:
        return False
    return a[0] == b[0] or a[0].endswith(' ' + b[0]) or b[0].endswith(' ' + a[0])


GUARDS = (registration_section_mismatch, explicit_program_role_mismatch,
          named_tree_lighting_display_mismatch, explicit_disjoint_age_band_mismatch,
          trailing_roman_ordinal_mismatch,
          numbered_course_mismatch, parent_afterparty_mismatch,
          sports_watch_dance_mismatch, branded_boat_mismatch,
          duration_class_subject_mismatch, college_audience_mismatch,
          holiday_weekday_mismatch, named_class_variant_mismatch,
          seasonal_mixology_mismatch, named_tour_subject_mismatch)


def remaining_name_identity_mismatch(left, right):
    return any(guard(left, right) for guard in GUARDS)
