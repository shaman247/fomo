"""Which location rows sit INSIDE which: a campus, park or complex and its venues.

The schema has no parent/child relation between locations, and none is needed
for the question the merger asks ("is the event's current venue a part of the
umbrella this source names?"). A child names its container in its own row:

    248  "David Geffen Hall at Lincoln Center"     name
    249  "David H. Koch Theater", "20 Lincoln Center Plaza"   address
    3356 "Alice Tully Hall" / alias "Alice Tully Hall at Lincoln Center"

while the container (493 "Lincoln Center for the Performing Arts", alias
"Lincoln Center") names none of them. That is the same signal
`processor._child_of_parent` uses for "<venue> at <container>" strings, keyed
here on location ids instead of a source string.

`contains(outer, inner)` is True only when ALL hold:

  * one of `outer`'s keys (its name or a GLOBAL alternate name) appears, on word
    boundaries, in `inner`'s name, address or global alternate names;
  * none of `inner`'s keys appears in `outer`'s text — containment is one-way,
    so two rows that mention each other are siblings or duplicates, not a
    parent and child;
  * the two are within MAX_CONTAINMENT_KM — "Jazz at Lincoln Center" names the
    campus but sits on Columbus Circle, and a borough-named umbrella must not
    claim a venue on the far side of it;
  * `inner` is not a generic (neighborhood/area) row unless `outer` is too.

Short names are deliberately NOT keys: 248, 249 and 493 all have the short
name "Lincoln Center", which would make every hall contain every other.
Website-scoped aliases are not keys or text either — they hold only in that
website's context ("The Dance Floor" on w4833).
"""
import re
import unicodedata
from math import cos, radians

# A campus measured from its centroid: Lincoln Center's halls are 70-260 m
# from 493. A sanity gate, not the signal — a venue that names its container
# and sits this close is inside it or right beside it. Jazz at Lincoln Center
# (0.47 km, Columbus Circle) passes, which is harmless: a JALC pin should not
# be pulled back to the campus either.
MAX_CONTAINMENT_KM = 0.6

_CONNECTORS = {'the', 'at', 'of', 'and', 'a', 'an', 'in', 'on', 'for', 's'}
# Words that name a KIND of place; a key made only of these (plus connectors)
# would match every venue of that kind.
_GENERIC_WORDS = {
    'gallery', 'bar', 'lounge', 'studio', 'garden', 'lobby', 'hall', 'room',
    'cafe', 'kitchen', 'market', 'club', 'space', 'theater', 'theatre',
    'museum', 'library', 'park', 'shop', 'store', 'center', 'centre', 'hotel',
    'restaurant', 'rooftop', 'terrace', 'patio', 'courtyard', 'atrium',
    'auditorium', 'chapel', 'pavilion', 'plaza', 'field', 'court', 'pool',
    'deck', 'stage', 'ballroom', 'building', 'campus', 'floor', 'dance',
    'new', 'york', 'nyc', 'ny', 'city', 'street', 'st', 'avenue', 'ave',
    'wide', 'experience', 'full',
}
_STREET_SUFFIXES = {'st', 'street', 'ave', 'avenue', 'blvd', 'boulevard', 'rd', 'road',
                    'pl', 'place', 'pkwy', 'parkway', 'ln', 'lane', 'dr', 'drive'}


def normalize(text):
    """Lowercase, accent-free, punctuation-to-space form for word matching."""
    text = unicodedata.normalize('NFKD', text or '')
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace('’', "'").replace("'", '')
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', text).split())


def _is_key(key):
    """A key distinctive enough to stand for one place.

    A key carrying a ZIP code is an address pasted into an alias ("Brooklyn, NY
    11215" on CHiPS 2840) and would claim every venue in that ZIP; a bare street
    ("Montague St" on Books Are Magic 109) would claim the whole street. A
    numbered street address ("520 8th Ave", "873 Broadway") is one building and
    stays a key.
    """
    tokens = key.split()
    if any(len(t) == 5 and t.isdigit() for t in tokens):
        return False
    if tokens and tokens[-1] in _STREET_SUFFIXES and not tokens[0].isdigit():
        return False
    distinctive = [t for t in tokens if t not in _CONNECTORS and t not in _GENERIC_WORDS
                   and not t.isdigit()]
    if not distinctive:
        return False
    return len(tokens) >= 2 or len(key) >= 6


class LocationContainment:
    """Memoized `contains(outer_id, inner_id)` over an in-memory locations snapshot."""

    def __init__(self, locations, aliases=()):
        """`locations`: iterable of (id, name, address, lat, lng, generic_location).
        `aliases`: iterable of (location_id, alternate_name) — GLOBAL aliases only.
        """
        self._coords = {}
        self._generic = {}
        self._keys = {}
        self._texts = {}
        self._addresses = {}
        for loc_id, name, address, lat, lng, generic in locations:
            self._coords[loc_id] = (lat, lng)
            self._generic[loc_id] = bool(generic)
            norm_name = normalize(name)
            self._keys[loc_id] = {norm_name} if _is_key(norm_name) else set()
            self._texts[loc_id] = [norm_name] if norm_name else []
            self._addresses[loc_id] = normalize(address)
        for loc_id, alias in aliases:
            if loc_id not in self._keys:
                continue
            norm_alias = normalize(alias)
            if not norm_alias:
                continue
            self._texts[loc_id].append(norm_alias)
            if _is_key(norm_alias):
                self._keys[loc_id].add(norm_alias)
        self._memo = {}
        self._related = {}
        # Spatial buckets at least MAX_CONTAINMENT_KM wide (longitude cells are
        # sized for latitudes up to 60 degrees), so `related` only has to test
        # the 3x3 cells around a location instead of the whole table.
        self._grid = {}
        for loc_id in self._keys:
            cell = self._cell(loc_id)
            if cell is not None:
                self._grid.setdefault(cell, []).append(loc_id)

    @classmethod
    def load(cls, cursor):
        cursor.execute("SELECT id, name, address, lat, lng, generic_location FROM locations")
        locations = cursor.fetchall()
        cursor.execute(
            "SELECT location_id, alternate_name FROM location_alternate_names "
            "WHERE website_id IS NULL"
        )
        return cls(locations, cursor.fetchall())

    def _mentions(self, keys_of, text_of):
        texts = [f' {t} ' for t in self._texts.get(text_of, ())]
        address = f' {self._addresses.get(text_of) or ""} '
        for key in self._keys.get(keys_of, ()):
            padded = f' {key} '
            if any(padded in text for text in texts):
                return True
            # A one-word key in an address is usually the street, not the
            # container: "Chambers" (a bar) vs "31 Chambers St".
            if ' ' in key and padded in address:
                return True
        return False

    def _near(self, a, b):
        ca, cb = self._coords.get(a), self._coords.get(b)
        if not ca or not cb or None in ca or None in cb:
            return False
        lat_a, lng_a, lat_b, lng_b = float(ca[0]), float(ca[1]), float(cb[0]), float(cb[1])
        dy = (lat_a - lat_b) * 111.0
        dx = (lng_a - lng_b) * 111.0 * cos(radians((lat_a + lat_b) / 2))
        return (dx * dx + dy * dy) ** 0.5 <= MAX_CONTAINMENT_KM

    def _cell(self, loc_id):
        lat, lng = self._coords.get(loc_id) or (None, None)
        if lat is None or lng is None:
            return None
        return (int(float(lat) * 111.0 // MAX_CONTAINMENT_KM),
                int(float(lng) * 55.5 // MAX_CONTAINMENT_KM))

    def related(self, loc_id):
        """Locations that contain `loc_id` or that it contains (memoized)."""
        if loc_id not in self._related:
            found = set()
            cell = self._cell(loc_id)
            if cell is not None and self._keys.get(loc_id) is not None:
                for d_lat in (-1, 0, 1):
                    for d_lng in (-1, 0, 1):
                        for other in self._grid.get((cell[0] + d_lat, cell[1] + d_lng), ()):
                            if self.contains(loc_id, other) or self.contains(other, loc_id):
                                found.add(other)
            self._related[loc_id] = frozenset(found)
        return self._related[loc_id]

    def contains(self, outer, inner):
        """True when location `inner` is a venue inside location `outer`."""
        if outer is None or inner is None or outer == inner:
            return False
        pair = (outer, inner)
        if pair not in self._memo:
            self._memo[pair] = (
                outer in self._keys and inner in self._keys
                and (self._generic[outer] or not self._generic[inner])
                and self._mentions(outer, inner)
                and not self._mentions(inner, outer)
                and self._near(outer, inner)
            )
        return self._memo[pair]
