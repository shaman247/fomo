import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from festival_member_identity import explicit_festival_member_mismatch as differs
from festival_member_identity import festival_sibling_program_mismatch as siblings


class FestivalMemberIdentityTests(unittest.TestCase):
    def pair(self, left, right, expected):
        self.assertEqual(differs(left, right), expected)
        self.assertEqual(differs(right, left), expected)

    def test_numbered_night_ignores_contaminated_schedule(self):
        self.pair('City of Gods Festival', 'City of Gods Festival: Night 1', True)
        self.pair('City of Gods Festival', 'City of Gods Festival - Night 2', True)

    def test_numbered_edition_alias(self):
        self.pair('City Of Gods Halloween Festival 2026', 'City of Gods Festival: Night 1', True)
        self.pair('Other Gods Halloween Festival', 'City of Gods Festival: Night 1', False)

    def test_explicit_festival_pass(self):
        self.pair('Durations 2026 Festival Pass', 'DURATIONS: William Basinski, muein', True)
        self.pair('Durations Festival 2026', 'DURATIONS: William Basinski, muein', True)
        self.pair('Durations 2026 Festival Pass', 'DURATIONS', False)
        self.pair('Durations 2026 Festival Pass', 'OTHER: William Basinski, muein', False)

    def test_volunteer_and_named_satellite(self):
        self.pair('Fall Festival Teen Volunteers', 'Fall Festival: Scarecrow Decor Workshop for Adults', True)
        self.pair('Fall Festival Volunteers', 'Fall Festival: Meet the Medium', True)

    def test_numbered_program_subtitle_and_explicit_workshop(self):
        self.pair('Bicycle Film Festival 26th Anniversary', 'Bicycle Film Festival: Program 3 – Looking Forward', True)
        self.pair('Chinatown Mid Autumn Festival', 'Lantern-Making Workshops at Chinatown Mid Autumn Festival', True)
        self.pair('Chinatown Mid Autumn Festival', 'Music at Chinatown Mid Autumn Festival', False)
        self.pair('Chinatown Mid Autumn Festival', 'Lantern-Making Workshops at Other Festival', False)

    def test_named_reading(self):
        self.pair('Dodge Poetry Festival', 'Dodge Poetry Festival: 30 Years of Cave Canem Anniversary Reading', True)

    def test_explicit_volunteering(self):
        self.pair('Fall Festival', 'Fall Festival Volunteers', True)
        self.pair('Fall Festival', 'Fall Festival Teen Volunteers', True)

    def test_ride_requires_named_festival(self):
        self.pair('Randalls Island Harvest Festival', 'Bike Ride to Randalls Island Harvest Festival', True)
        self.pair('Harvest Festival', 'Bike Ride to Harvest Festival', True)

    def test_conservative_negatives(self):
        for left, right in [
            ('City of Gods Festival', 'City of Gods Festival: Nights 1 and 2'),
            ('City of Gods Festival', 'City of Gods Festival: Night I'),
            ('City of Gods Festival', 'City of Gods Festival Night 1 Night 2'),
            ('City of Gods Festival', 'City of Gods Festival: Dance All Night'),
            ('Dodge Poetry Festival', 'Dodge Poetry Festival: Voices of Tomorrow'),
            ('Festival', 'Festival: An Author Reading'),
            ('Akumandra Festival', 'Akumandra: Open Air'),
            ('Mannes Sounds Piano Cantabile Festival', 'Mannes Sounds Piano Cantabile: The Piano in Transition'),
            ('Dodge Poetry Festival', 'Other Poetry Festival: Author Reading'),
            ('Harvest Festival at the Farm', 'Harvest Festival'),
            ('A Festival Reading', 'A Festival Reading'),
            ('', 'City of Gods Festival: Night 1'),
        ]:
            self.pair(left, right, False)


class FestivalSiblingIdentityTests(unittest.TestCase):
    def test_reviewed_program_pairs(self):
        for a, b in [
            ('New York Comedy Festival Presents: DRIP', 'New York Comedy Festival Presents: Johana Coca & Friends'),
            ('El Showcito de Titi presented by New York Comedy Festival', 'Success Jr. presented by New York Comedy Festival'),
            ('Noel B at the New York Comedy Festival', 'Bonkque Show at the New York Comedy Festival'),
            ('TRIO IMAGINATION - Orchard Street Jazz Festival - WKCR 85th', 'MY Trio Album Release - Orchard Street Jazz Festival - Wkcr 85th'),
            ('The Downtown Festival: Beyond the Threshold - Selection of Short Films', 'The Downtown Fest: The Mayflower + Q&A'),
            ('The Downtown Festival: Karishika', 'The Downtown Festival Amos Poe: Unmade'),
            ('Monteleone: The Art of the Guitar Festival - At The Bench: Workshop with John Monteleone', 'Monteleone: The Art of the Guitar Festival - The Tonebars'),
            ('Monteleone: The Art of the Guitar Festival - Jocelyn Gould Trio: Jocelyn Gould, guitar, Pat Bianci, organ', 'Monteleone: The Art of the Guitar Festival - Ted Ludwig Trio: Ted Ludwig, guitar, Pat Bianci, organ'),
            ('NYC South Asian Comedy Festival – Brown Unhinged. Uncensored South Asian Stand-Up Comedy Show', 'NYC South Asian Comedy Festival: The Roast Battle'),
            ('Olga [screening: Havel 90 Festival]', 'Havel [screening: Havel 90 Festival]'),
            ('NYC South Asian Comedy Festival: The Unhinged Show', 'NYC South Asian Comedy Festival Roast Battle – India Vs Pakistan Vs Bangladesh Vs Sri Lanka.'),
            ('Havel [screening: Havel 90 Festival]', 'Havel’s Audience with History [screening + Q&A: Havel 90 Festival]'),
        ]:
            self.assertTrue(siblings(a, b), (a, b))
            self.assertTrue(siblings(b, a), (b, a))

    def test_aliases_and_incomplete_credits(self):
        for a, b in [
            ('NYC South Asian Comedy Festival – Brown Unhinged. Uncensored South Asian Stand-Up Comedy Show', 'NYC South Asian Comedy Festival: The Unhinged Show'),
            ('Noel B at the New York Comedy Festival', 'NOEL B ASKIN LIVE! at the New York Comedy Festival'),
            ('Olga [screening: Havel 90 Festival]', 'Olga (2014) [screening + Q&A: Havel 90 Festival]'),
            ('Mina Trio - East Jazz Festival', 'Mina Trio and Guests - East Jazz Festival'),
            ('A Show - Other Festival', 'Different - East Festival'),
            ('Mina Trio', 'Mina Quartet'),
            ('Winter Festival: Violin Celebration: The Age of Romance', 'Winter Festival: The Age of Romance'),
            ('Shakespeare Festival: The Merry Wives of Windsor', 'Shakespeare Festival — TBD'),
            ('Dear Summer Festival NYC', 'Dear Summer Festival NEW YORK CITY'),
            ('Queer Butoh Festival at the Brick Theater', 'Queer Butoh Festival 2026'),
            ('New York Kurdish Film Festival — 10th Edition', 'New York Kurdish Film Festival (NYKFF10)'),
        ]:
            self.assertFalse(siblings(a, b), (a, b))
            self.assertFalse(siblings(b, a), (b, a))


if __name__ == '__main__':
    unittest.main()
