"""Explicit festival umbrellas and separately named attendance programs.

These rules use title structure, not schedule size: publishers sometimes give a
single festival night the entire festival envelope. They deliberately decline
unstructured extra words, unnamed abbreviations, and grouped night labels.
"""
import re
import unicodedata

_NUMBER = r'(?:[1-9]\d?|one|two|three|four|five|six|seven|eight|nine|ten)'
_NUMBERED = re.compile(r'^(.*?)\s*(?::|[–—]|\s-\s|\()\s*((?:day|night|program)\s+' + _NUMBER + r')\s*\)?(?:\s*[:–—]\s*.+)?$', re.I)
_NUMBER_TOKEN = re.compile(r'\b(?:days?|nights?|programs?)\s+(?:' + _NUMBER + r'|[ivxlcdm]+)\b', re.I)
_MEMBER = re.compile(r'^(.*?)\s*[:–—]\s*(.+)$')


def _normal(text):
    text = unicodedata.normalize('NFKC', text or '').casefold()
    return ' '.join(re.findall(r"[\w]+", text, re.UNICODE))


def _festival(text):
    words = _normal(text).split()
    return 'festival' in words and len(words) >= 3


def _same_festival(left, right):
    # Edition years and small marketing additions do not make a numbered night
    # the umbrella. Require at least two shared substantive words; generic
    # "Music Festival" and one-word festival brands deliberately decline.
    def words(value):
        return {w for w in _normal(value).split()
                if w not in {'festival', 'the', 'of', 'and', 'a', 'an'}
                and not w.isdigit()}
    a, b = words(left), words(right)
    return len(a & b) >= 2 and (a <= b or b <= a)


def explicit_festival_member_mismatch(left, right):
    """Separate explicit named members from an otherwise identical umbrella.

    Requiring a complete shared festival name avoids a generic afterparty flag.
    A subtitle alone can also be marketing prose, so colon members must carry a
    recognizable attendance-program label. Numbered nights remain distinct even
    if their own bad source schedule repeats the parent span.
    """
    if not left or not right or _normal(left) == _normal(right):
        return False
    for member, umbrella in ((left, right), (right, left)):
        numbered = _NUMBERED.fullmatch(member.strip())
        if (numbered and _festival(numbered[1])
                and len(_NUMBER_TOKEN.findall(member)) == 1
                and not _NUMBER_TOKEN.search(umbrella)
                and _same_festival(numbered[1], umbrella)):
            return True
        # A pass or explicit edition identifies the umbrella even when its
        # members omit the word festival. Bare unyeared aliases (for example
        # Akumandra Festival / Akumandra: Open Air) remain conservative.
        festival_title = re.fullmatch(r'(.+?)\s+(?:20\d{2}\s+)?festival(?: pass)?(?:\s+20\d{2})?', umbrella.strip(), re.I)
        member_title = re.fullmatch(r'(.+?):\s*(.+)', member.strip())
        if (festival_title and member_title
                and re.search(r'\b(?:pass|20\d{2})\b', umbrella, re.I)
                and len(_normal(festival_title[1])) >= 4
                and _normal(festival_title[1]) == _normal(member_title[1])):
            return True
        colon = _MEMBER.fullmatch(member.strip())
        if (colon and _festival(colon[1])
                and _normal(colon[1]) == _normal(umbrella)
                and re.search(r'\b(?:reading|workshop|screening|concert|tour|afterparty|after party|opening reception|closing reception)\b', colon[2], re.I)):
            return True
        # Both roles are explicit; a ride *to* a festival and its volunteers'
        # session have separate attendance locations or duties from the festival.
        satellite = re.fullmatch(r'(.+?\b(?:workshops?|readings?|screenings?|tours?))\s+at\s+(.+)', member.strip(), re.I)
        if (satellite and _festival(satellite[2])
                and _normal(satellite[2]) == _normal(umbrella)):
            return True
        ride = re.fullmatch(r'(?:bike|bicycle) ride to (.+)', member.strip(), re.I)
        if (ride and 'festival' in _normal(ride[1]).split()
                and len(_normal(ride[1]).split()) >= 2
                and _normal(ride[1]) == _normal(umbrella)):
            return True
        volunteer = re.fullmatch(r'(.+?)\s+(?:teen\s+)?volunteers?', member.strip(), re.I)
        if (volunteer and 'festival' in _normal(volunteer[1]).split()
                and (_normal(volunteer[1]) == _normal(umbrella)
                     or (_MEMBER.fullmatch(umbrella.strip())
                         and _normal(volunteer[1]) == _normal(_MEMBER.fullmatch(umbrella.strip())[1])))):
            return True
    return False


_PROGRAM_BOILERPLATE = {
    'the', 'a', 'an', 'and', 'with', 'by', 'for', 'of', 'at', 'in',
    'show', 'live', 'concert', 'performance', 'screening', 'qa', 'q', 'trio',
    'quartet', 'quintet', 'sextet', 'album', 'release', 'presents', 'present',
    'presented', 'featuring', 'selection', 'short', 'films', 'film', 'friends',
}


def _festival_program(name):
    """Return an explicit festival credit and the separately billed program."""
    # Bracketed screening metadata is a credit, not the film's identity.
    bracket = re.fullmatch(r'(.+?)\s*\[screening(?:\s*\+\s*q&a)?\s*:\s*([^]]*\bfestival)\s*\]', name.strip(), re.I)
    if bracket:
        return _normal(bracket[2]), bracket[1], 'screening'
    suffix = re.fullmatch(r'(.+?)\s+(?:presented by|at(?: the)?)\s+(.+?\bfestival)', name.strip(), re.I)
    if suffix:
        return _normal(suffix[2]), suffix[1], 'program'
    # Repeated sponsor text after the festival remains part of the credit.
    dash = re.split(r'\s+[–—-]\s+', name, maxsplit=1)
    if len(dash) == 2 and re.search(r'\bfestival\b', dash[1], re.I) and not re.search(r'\bfestival\b', dash[0], re.I):
        return _normal(dash[1]), dash[0], 'program'
    prefix = re.fullmatch(r'(.+?\b(?:festival|fest))(?:(?:\s+presents)\s*:?\s*|\s*[:–—-]\s*)(.+)', name.strip(), re.I)
    if not prefix:
        # A secondary separator can still clearly bill a program after a missing
        # first separator ("Festival Amos Poe: Unmade"). Ordinary edition,
        # city and venue suffixes have no such program separator.
        prefix = re.fullmatch(r'(.+?\b(?:festival|fest))\s+([^:–—]+[:–—].+)', name.strip(), re.I)
    if prefix:
        context = re.sub(r'\bfest\b', 'festival', _normal(prefix[1]))
        return context, prefix[2], 'program'
    return None


def festival_sibling_program_mismatch(left, right):
    """A shared explicit festival credit cannot outweigh distinct program names.

    Shared substantive words retain expanded performer lineups and abbreviated
    titles. Bracketed film titles are stronger evidence: differing titles are
    distinct even when one film's title is a word within another's.
    """
    a, b = _festival_program(left), _festival_program(right)
    if not a or not b or a[0] != b[0]:
        return False
    if a[2] == b[2] == 'screening':
        def film(title):
            title = re.sub(r'\s*\((?:19|20)\d{2}\)\s*$', '', title)
            return _normal(title)
        return film(a[1]) != film(b[1])
    def content(title):
        # A following colon often repeats the complete personnel/instruments;
        # the separately billed trio or workshop before it is the identity.
        lead, separator, rest = title.partition(':')
        if separator and re.search(r'\b(?:trio|quartet|quintet|sextet)\s*$', lead, re.I):
            title = lead
        return set(_normal(title).split()) - _PROGRAM_BOILERPLATE
    x, y = content(a[1]), content(b[1])
    if any(words & {'tbd', 'tba'} for words in (x, y)):
        return False
    return bool(x and y and x.isdisjoint(y))
