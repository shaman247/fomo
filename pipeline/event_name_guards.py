"""Small name-identity guards shared by source grouping and canonical matching."""
import re
import unicodedata


def conversation_subject_mismatch(left, right):
    """A generic conversation label cannot merge unrelated named speakers.

    Only explicit ``In Conversation: ...`` / ``In Conversation with ...``
    labels qualify. Overlapping names remain compatible: an expanded guest
    list alone does not establish a separate event.
    """
    def subject(name):
        match = re.fullmatch(r'in\s+conversation(?:\s*[:–—]\s*|\s+with\s+)(.+)',
                             name.strip(), re.I)
        if not match:
            return None
        value = unicodedata.normalize('NFKD', match[1].casefold())
        value = ''.join(c for c in value if not unicodedata.combining(c))
        return set(re.findall(r'\w+', value)) - {'and', 'with'}

    a, b = subject(left), subject(right)
    if a and b:
        return len(a) >= 2 and len(b) >= 2 and a.isdisjoint(b)
    return bool((a and right.strip().casefold() == 'in conversation')
                or (b and left.strip().casefold() == 'in conversation'))


def named_sub_event_mismatch(left, right):
    """An explicitly labelled satellite is not its parent event.

    Require a title separator and a specific gathering label. Bare words such
    as opening, preview or tour can describe the parent itself and are not
    sufficient. Two spellings of the same reception/tour remain compatible.
    """
    def normalize(value):
        words = re.findall(r'\w+', value.casefold())
        # Older canonical titles may append the generic format to the title.
        # Keep that spelling from hiding an otherwise explicit satellite.
        if len(words) > 1 and words[-1] in {'exhibition', 'exhibit'}:
            words.pop()
        return ' '.join(words)

    def parts(name):
        split = re.split(r'\s*[:–—]\s*|\s+-\s+', name)
        if len(split) != 2:
            return None
        for base, qualifier in (split, split[::-1]):
            kind = normalize(qualifier)
            if re.fullmatch(r'(?:(?:opening|closing|artist|artists) )?reception', kind):
                return normalize(base), 'reception'
            if re.fullmatch(r'(?:curator|curatorial|artist|artists|gallery) (?:led )?(?:walk through|walkthrough|tour)', kind):
                return normalize(base), 'tour'
            if re.fullmatch(r'(?:curator|curatorial|artist|artists|gallery) talk', kind):
                return normalize(base), 'talk'
            if re.fullmatch(r'\w+(?: \w+)* workshop', kind):
                return normalize(base), kind
        return None

    a, b = parts(left), parts(right)
    if a and b:
        return a[0] == b[0] and a[1] != b[1]
    return bool((a and a[0] == normalize(right))
                or (b and b[0] == normalize(left)))


def library_program_variant_mismatch(left, right):
    """A recurring strand's named book, film or craft identifies its session.

    Compare the raw subject, before stop-word filtering: a film called ``It``
    must not become an empty subject and match every Film Friday screening.
    """
    pattern = r'^(film\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(?:matinee|book\s+club)|great\s+books\s+discussion\s+group|teen\s+night)\s*[:–—-]\s*(.+)$'
    def parts(name):
        match = re.match(pattern, name.strip(), re.I)
        if not match:
            return None
        subject = re.sub(r'\s*\((?:19|20)\d{2}\)\s*$', '', match[2])
        return tuple(' '.join(re.findall(r'\w+', text.casefold())) for text in (match[1], subject))
    a, b = parts(left), parts(right)
    # A legacy weekday book-club umbrella must not become a bridge between
    # separately named monthly books when each incoming row matches it.
    for named, other in ((a, right), (b, left)):
        if (named and named[0].endswith(' book club')
                and named[0] == ' '.join(re.findall(r'\w+', other.casefold()))):
            return True
    return bool(a and b and a[0] == b[0] and a[1] != b[1])


def game_program_variant_mismatch(left, right):
    """A gaming series' pipe-delimited game/set is identity, not decoration.

    E.g. ``RPG Night | Delta Green`` cannot donate its dates to ``RPG Night``
    or ``RPG Night | Brindlewood Bay``. Restrict this to gaming-series heads;
    ordinary fuller book/show titles keep their existing matching behavior.
    """
    def normalize(value):
        value = unicodedata.normalize('NFKD', value.casefold())
        return ' '.join(re.findall(r'\w+', ''.join(c for c in value if not unicodedata.combining(c))))

    head1, separator1, subject1 = left.partition('|')
    head2, separator2, subject2 = right.partition('|')
    if not (separator1 or separator2) or normalize(head1) != normalize(head2):
        return False
    if not re.search(r'\b(?:rpg|role[ -]?playing|mtg|magic the gathering|game night)\b', head1, re.I):
        return False
    return normalize(subject1) != normalize(subject2)


def participatory_program_variant_mismatch(left, right):
    """Keep an explicitly different activity from its similarly named sibling.

    These checks use the activity words before generic title normalization can
    reduce both equipment classes to "BUS / Basic Use and Safety". They do not
    infer a distinction from different dates or missing audience information.
    """
    def normalized(name):
        return ' '.join(re.findall(r'\w+', unicodedata.normalize('NFKC', name).casefold()))

    a, b = normalized(left), normalized(right)
    for jam, parent in ((a, b), (b, a)):
        if len(parent.split()) >= 2 and jam == parent + ' jam':
            return True

    def language(name):
        match = re.fullmatch(
            r'(.+ language) (for families|readiness for pre\s?school)(.*)', name)
        return match.groups() if match else None

    la, lb = language(a), language(b)
    if la and lb and la[0] == lb[0] and la[2] == lb[2] and la[1] != lb[1]:
        return True

    def equipment(name):
        match = re.match(r'^(3d print(?:er|ing)|laser cut(?:ter|ting))\b', name)
        if not match:
            return None
        # Require a class label or a bare equipment activity, not a general
        # lecture mentioning both tools later in its title.
        rest = name[match.end():].strip()
        if rest not in ('', 'bus', 'basic use and safety', 'bus basic use and safety'):
            return None
        return 'printer' if match[1].startswith('3d') else 'laser'

    ea, eb = equipment(a), equipment(b)
    return bool(ea and eb and ea != eb)
