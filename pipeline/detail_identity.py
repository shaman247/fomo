"""Bound detail enrichment to explicit session evidence; never rewrite source URLs.

Unknown evidence remains unknown. This guard rejects contradictions, not ordinary
canonical redirects or pages that simply omit structured dates.
"""
import json
import re
from datetime import date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlsplit

_DATE = re.compile(
    r'(?<![A-Za-z0-9])(?P<year>\d{4})[-/](?P<month>\d{1,2}|'
    r'Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
    r'Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
    r'[-/](?P<day>\d{1,2})(?![A-Za-z0-9])', re.I)
_MONTHS = {m: i for i, m in enumerate(
    ('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'), 1)}
_DATE_KEYS = {'date', 'startdate', 'start_date', 'eventdate', 'event_date', 'sessiondate', 'session_date'}


_EXPLICIT_OFFSET = re.compile(r'(?:Z|[+-]\d{2}:?\d{2})$')


@lru_cache(maxsize=1)
def _city_zone():
    """The deployment's timezone (config/<city>.yaml frontend.timezone)."""
    try:
        import city_config
        name = (city_config.get_config().get('frontend') or {}).get('timezone')
    except Exception:
        name = None
    return ZoneInfo(name or 'America/New_York')


def _day(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        # A naive ISO datetime's leading date is the publisher's calendar date.
        # An explicit instant ('2026-10-10T03:00:00.000Z' / '+00:00') is not: its
        # leading date is the UTC date, so every session at/after 8 PM ET read as
        # tomorrow (Partiful JSON-LD, 2026-10-04: 8 'schedule is disjoint'
        # rejections). Convert explicit offsets to the city's zone first; a local
        # offset ('-04:00') maps to the same calendar date it already shows.
        if len(value) > 10 and _EXPLICIT_OFFSET.search(value):
            instant = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return instant.astimezone(_city_zone()).date()
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _url(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            return None
        return parsed
    except ValueError:
        return None


def url_session_dates(url):
    """Explicit valid path dates and named date query values only.

    An opaque ID, tracking parameter, or ambiguous month/day/year is not a date.
    """
    parsed = _url(url)
    if parsed is None:
        return set()
    dates = set()
    for match in _DATE.finditer(unquote(parsed.path)):
        try:
            month = match['month']
            dates.add(date(int(match['year']), int(month) if month.isdigit()
                           else _MONTHS[month[:3].lower()], int(match['day'])))
        except (KeyError, ValueError):
            pass
    for key, values in parse_qs(parsed.query).items():
        if key.casefold() in _DATE_KEYS:
            dates.update(d for value in values if (d := _day(value)) is not None)
    return dates


def _url_key(url):
    parsed = _url(url)
    return ((parsed.hostname.lower().removeprefix('www.'),
             unquote(parsed.path).rstrip('/'), parsed.query) if parsed else None)


class _JSONLD(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.parts = []
        self.documents = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'script':
            self.active = dict(attrs).get('type', '').lower() == 'application/ld+json'
            self.parts = []

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == 'script' and self.active:
            try:
                self.documents.append(json.loads(''.join(self.parts)))
            except (ValueError, TypeError):
                pass
            self.active = False


def _events(value):
    if isinstance(value, list):
        for item in value:
            yield from _events(item)
    elif isinstance(value, dict):
        kinds = value.get('@type', [])
        if isinstance(kinds, str):
            kinds = [kinds]
        if any(isinstance(kind, str) and kind.rsplit('/', 1)[-1].endswith('Event') for kind in kinds):
            yield value
        # Do not interpret nested offers/recommendations as the page's event.
        yield from _events(value.get('@graph', []))
        main = value.get('mainEntity')
        if isinstance(main, (list, dict)):
            yield from _events(main)


def _site_names(value):
    if isinstance(value, list):
        for item in value:
            yield from _site_names(item)
    elif isinstance(value, dict):
        if value.get('@type') == 'WebSite' and isinstance(value.get('name'), str):
            yield value['name']
        yield from _site_names(value.get('@graph', []))


def _name(value):
    return ' '.join(value.casefold().split()) if isinstance(value, str) else ''


def _page_intervals(result, requested_url, final_url, expected):
    html = getattr(result, 'html', None)
    if not isinstance(html, str):
        return []
    parser = _JSONLD()
    parser.feed(html)
    target_keys = {key for url in (requested_url, final_url) if (key := _url_key(url))}
    intervals = []
    site_names = [_name(name) for name in _site_names(parser.documents)]
    for event in _events(parser.documents):
        event_url = event.get('url')
        if isinstance(event_url, dict):
            event_url = event_url.get('@id')
        event_names = {_name(event.get('name'))}
        # Some publishers add their own WebSite name to the Event's title.
        # Strip only that explicitly declared suffix, never arbitrary subtitles.
        for owner in site_names:
            for separator in (' — ', ' – ', ' | ', ' - '):
                suffix = separator + owner
                if _name(event.get('name')).endswith(suffix):
                    event_names.add(_name(event.get('name'))[:-len(suffix)])
        identified = (_url_key(event_url) in target_keys or
                      bool(_name(expected.get('name'))) and
                      _name(expected.get('name')) in event_names)
        if not identified:
            continue
        start = _day(event.get('startDate'))
        end = _day(event.get('endDate')) or start
        if start and end >= start:
            intervals.append((start, end))
    return intervals


def detail_rejection_reason(requested_url, result, expected_session=None):
    """Return an explicit contradiction, or None when identity is not disproved.

    expected_session may contain name and occurrences (or start_date/end_date).
    A missing redirected_url uses result.url when supplied. If both are absent,
    attributed Event JSON-LD still checks a reused URL against the saved session.
    Missing metadata alone never establishes a different event.
    """
    expected = expected_session or {}
    final_url = next((value for value in (getattr(result, 'redirected_url', None),
                                         getattr(result, 'url', None)) if _url(value)), None)
    requested_dates = url_session_dates(requested_url)
    final_dates = url_session_dates(final_url)
    if len(requested_dates) == len(final_dates) == 1 and requested_dates != final_dates:
        return 'detail destination has a different explicit session date'
    intervals = []
    for item in expected.get('occurrences', []) or [expected]:
        start = _day(item.get('start_date'))
        end = _day(item.get('end_date')) or start
        if start and end >= start:
            intervals.append((start, end))
    if not intervals and len(requested_dates) == 1:
        day = next(iter(requested_dates))
        intervals = [(day, day)]
    offered = _page_intervals(result, requested_url, final_url, expected)
    # A stable date in a URL may be the first day of a recurring exhibition.
    # Rolling listings legitimately retain that URL for later sessions. Only
    # a newly dated destination supplies additional URL evidence, and an
    # attributable Event interval is stronger than its slug's first date.
    if (intervals and not requested_dates and len(final_dates) == 1
            and not offered and not any(
                start <= next(iter(final_dates)) <= end for start, end in intervals)):
        return 'detail destination date is outside the source sessions'
    if intervals and offered and not any(
            a <= d and c <= b for a, b in intervals for c, d in offered):
        return 'detail Event schedule is disjoint from the source sessions'
    return None
