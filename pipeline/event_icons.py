"""Conservative, side-effect-free icon proposals. No DB writes or browser inference."""
import hashlib
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / 'config/event-icons/catalog.json').read_text())
ICON_IDS = {entry['id'] for entry in CATALOG['icons']}
RULE_VERSION = 'event-icons-3'
# Strong activity names in titles. Ambiguous title terms can be corroborated by
# the narrow context rules below; description-only mentions remain review-only.
PATTERNS = {
    'game-go': r'\b(?:baduk|weiqi|go (?:club|game|night|board|tournament)|(?:play|playing|learn(?:ing)?(?: to play)?) go)\b',
    'game-dominoes': r'\bdominoes\b|\bdomino (?:game|club|night|tournament)\b',
    'game-scrabble': r'\bscrabble\b',
    'game-mtg': r'\bmagic\s*:?\s*(?:the\s+)?gathering\b|\bmtg\b',
    'tabletop-rpg': r'\bdungeons\s*(?:and|&)\s*(?:dragons|drafts)\b|\bd\s*&\s*d\b|\btabletop (?:rpg|role.?playing)\b',
    'trivia': r'\btrivia\b|\bpub quiz\b',
    'bingo': r'\bbingo\b',
    'music-bingo': r'\b(?:music(?:al)?|mix[ -]?tape|song|sing.?along|rock.?and.?roll) bingo\b|\bbingo\s*[-:]?\s*(?:music|songs)\b',
    'machine-sewing': r'\bsewing machines?\b|\bmachine sewing\b|\b(?:learn|learning) to sew\b',
    '3d-printing': r'\b3[ -]?d print(?:ing|er|ers)?\b',
    'game-backgammon': r'\bbackgammon\b',
    'game-rummikub': r'\brummikub\b',
    'pole-dance': r'\bpole (?:danc\w*|fitness|flow|class(?:es)?)\b',
    'chair-yoga': r'\bchair yoga\b',
    'glassblowing': r'\bglass[ -]?blow(?:ing|er|ers)\b',
}
RULES = {key: re.compile(value, re.I) for key, value in PATTERNS.items()}
# These tags disambiguate a title term; they are not generic tag -> event icon
# inheritance. Broad Games/Board Games tags are deliberately insufficient.
CONTEXT_RULES = {
    'game-go': {
        'title': re.compile(r'\bgo\b', re.I),
        'tags': frozenset({'go', 'baduk', 'weiqi'}),
        'description': re.compile(
            r'\b(?:baduk|weiqi|(?:board game|game of) (?:called )?go|'
            r'go (?:board game|stones|boards?))\b', re.I),
    },
}
# Recognize competing activities even before we have custom artwork for them.
OTHER_GAMES = re.compile(r'\b(?:chess|mah[- ]?jongg?|canasta|bananagrams|rummy|bridge|pok[eé]mon)\b', re.I)
NON_PARTICIPATION = re.compile(r'\b(?:film screening|movie screening|documentary|watch party|exhibition|lecture|history of|discussion about)\b', re.I)


def normalize(value):
    return ' '.join(unicodedata.normalize('NFKC', value or '').split())


def input_hash(event):
    payload = [normalize(event.get('name')), normalize(event.get('description')),
               sorted(str(t) for t in event.get('tags', []))]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()


def propose(event):
    name = normalize(event.get('name'))
    description = normalize(event.get('description'))
    fingerprint = input_hash(event)
    matches = {key: match.group() for key, regex in RULES.items() if (match := regex.search(name))}
    # Music bingo is a refinement, not a conflicting second activity.
    if 'music-bingo' in matches:
        matches.pop('bingo', None)
    evidence = [{'icon_id': key, 'field': 'name', 'text': text} for key, text in matches.items()]
    for key, rule in CONTEXT_RULES.items():
        title_match = rule['title'].search(name)
        if key in matches or not title_match:
            continue
        tags = sorted({str(tag) for tag in event.get('tags', [])
                       if normalize(str(tag)).casefold() in rule['tags']})
        context = rule['description'].search(description)
        if tags or context:
            matches[key] = title_match.group()
            evidence.append({'icon_id': key, 'field': 'name', 'text': title_match.group()})
            evidence.extend({'icon_id': key, 'field': 'tags', 'text': tag} for tag in tags)
            if context:
                evidence.append({'icon_id': key, 'field': 'description', 'text': context.group()})
    decision, icon_id, reason = 'fallback', None, 'No supported primary activity in title.'
    if len(matches) > 1:
        decision, reason = 'review', 'Multiple activity families in title; no primary activity assumed.'
    elif matches:
        candidate = next(iter(matches))
        if NON_PARTICIPATION.search(name):
            decision, reason = 'review', 'Title may describe a topic or spectating rather than participation.'
        elif candidate.startswith('game-') and (OTHER_GAMES.search(name) or re.search(r'\b(?:other|more|various) (?:trading card |board |card )?games\b', name, re.I)):
            decision, reason = 'review', 'Another named game competes with this activity.'
        elif candidate == 'game-mtg' and not re.search(r'magic\s*:?\s*(?:the\s+)?gathering', name, re.I) and not re.search(r'\b(?:commander|draft|cards?|tcg|sealed|modern|standard|magic|gathering)\b', name + ' ' + description, re.I):
            decision, reason = 'review', 'MTG abbreviation needs card-game context.'
        elif candidate == 'machine-sewing' and not re.search(r'\b(?:sewing machine|machine sewing)\b', name + ' ' + description, re.I):
            decision, reason = 'review', 'Sewing does not establish machine use.'
        else:
            reason = ('Title activity corroborated by precise tag or description; pending editorial review.'
                      if any(e['field'] != 'name' for e in evidence)
                      else 'Explicit supported activity in title; pending editorial review.')
            decision, icon_id = 'proposed', candidate
    else:
        evidence = [{'icon_id': key, 'field': 'description', 'text': match.group()}
                    for key, regex in RULES.items() if (match := regex.search(description))]
        if evidence:
            decision, reason = 'review', 'Description-only mention; primary activity needs review.'
    return dict(icon_id=icon_id, decision=decision, reason=reason, evidence=evidence,
                rule_version=RULE_VERSION, input_hash=fingerprint)
