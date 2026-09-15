"""Tests for `processor.normalize_extracted_emoji`.

The 2026-09-15 icon-artwork review had to dismiss 30 values from
`icon_review_queue` by hand, in two recurring classes:

(a) SKIN-TONE VARIANTS the model invents at random. `config/event-icons/
    noto.json` carries 1,712 aliases of which only 178 are toned, so an
    arbitrary tone misses the catalog and the frontend renders the fallback
    calendar icon — while the neutral base resolves for all of them (verified:
    `🚶🏿`, `🧑🏽‍🎨`, `🧘🏻‍♀️` are all unknown; `🚶`, `🧑‍🎨`, `🧘‍♀️` are all known).

    The neutral base is also the form the house palette wants:
    `scripts/standardize_emoji.propose()` replaces ONLY the neutral-yellow
    default with the house tone and deliberately leaves an already-toned value
    alone without `--retone`, so an extraction tone is a permanent fixed point
    the house tone can never reach.

(b) THE 5-HEX-DIGIT ARTIFACT — a codepoint above U+FFFF whose 5-digit hex was
    decoded as 4 digits, leaving the 5th as a literal character. Every case
    below is a real queue row.

Read-only impact scan at the time of the change: 137 of 1,536 distinct
`events.emoji` values and 160 of 1,771 distinct `crawl_events.emoji` values
would normalize differently (existing rows were NOT rewritten — the same day's
review had already corrected them).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processor import normalize_extracted_emoji


class TestSkinToneStripping(unittest.TestCase):
    def test_simple_toned_figures(self):
        # All real queue rows from the 2026-09-15 review.
        cases = {
            '\U0001F6B6\U0001F3FF': '\U0001F6B6',            # 🚶🏿 -> 🚶
            '\U0001F575\U0001F3FD': '\U0001F575',            # 🕵🏽 -> 🕵
            '\U0001F64C\U0001F3FD': '\U0001F64C',            # 🙌🏽 -> 🙌
            '\U0001F64F\U0001F3FF': '\U0001F64F',            # 🙏🏿 -> 🙏
            '\U0001F9D2\U0001F3FE': '\U0001F9D2',            # 🧒🏾 -> 🧒
            '\U0001F930\U0001F3FE': '\U0001F930',            # 🤰🏾 -> 🤰
            '\U0001F468\U0001F3FF': '\U0001F468',            # 👨🏿 -> 👨
            '\U0001F57A\U0001F3FF': '\U0001F57A',            # 🕺🏿 -> 🕺
            '\U0001F91F\U0001F3FE': '\U0001F91F',            # 🤟🏾 -> 🤟
            '\U0001F590\U0001F3FD': '\U0001F590',            # 🖐🏽 -> 🖐
            '\U0001F932\U0001F3FD': '\U0001F932',            # 🤲🏽 -> 🤲
            '\U0001F9B8\U0001F3FD': '\U0001F9B8',            # 🦸🏽 -> 🦸
        }
        for toned, base in cases.items():
            with self.subTest(toned=toned):
                self.assertEqual(base, normalize_extracted_emoji(toned))

    def test_toned_zwj_sequences_stay_valid_sequences(self):
        cases = {
            # 🧑🏽‍🎨 -> 🧑‍🎨
            '\U0001F9D1\U0001F3FD‍\U0001F3A8':
                '\U0001F9D1‍\U0001F3A8',
            # 🧘🏻‍♀️ -> 🧘‍♀️
            '\U0001F9D8\U0001F3FB‍♀️':
                '\U0001F9D8‍♀️',
            # 👩🏽‍💻 -> 👩‍💻
            '\U0001F469\U0001F3FD‍\U0001F4BB':
                '\U0001F469‍\U0001F4BB',
            # 🧑🏿‍🤝‍🧑🏾 -> 🧑‍🤝‍🧑  (both tones, three-part sequence)
            '\U0001F9D1\U0001F3FF‍\U0001F91D‍\U0001F9D1\U0001F3FE':
                '\U0001F9D1‍\U0001F91D‍\U0001F9D1',
            # 💂🏾‍♂️ -> 💂‍♂️
            '\U0001F482\U0001F3FE‍♂️':
                '\U0001F482‍♂️',
        }
        for toned, base in cases.items():
            with self.subTest(toned=toned):
                self.assertEqual(base, normalize_extracted_emoji(toned))

    def test_toned_handshake_folds_to_the_neutral_handshake(self):
        """`🫱🏾‍🫲🏾` strips to `🫱‍🫲`, which is not an emoji at all.

        It becomes `🤝`, whose house tone (`HOUSE_TONE_OVERRIDES['🤝']`) is the
        site's two-tone handshake `🫱🏾‍🫲🏼` — so the standardize pass can still
        reach it.
        """
        for toned in ('\U0001FAF1\U0001F3FE‍\U0001FAF2\U0001F3FE',
                      '\U0001FAF1\U0001F3FE‍\U0001FAF2\U0001F3FC',
                      '\U0001FAF1\U0001F3FF‍\U0001FAF2\U0001F3FC'):
            with self.subTest(toned=toned):
                self.assertEqual('\U0001F91D',
                                 normalize_extracted_emoji(toned))

    def test_bare_skin_tone_modifier_is_rejected(self):
        """`🏾` alone was the single most common junk value (316 crawl_events)."""
        for tone in ('\U0001F3FB', '\U0001F3FC', '\U0001F3FD',
                     '\U0001F3FE', '\U0001F3FF'):
            with self.subTest(tone=tone):
                self.assertEqual('', normalize_extracted_emoji(tone))

    def test_modifier_base_lost_to_the_strip_is_rejected(self):
        """`🏾‍♀️` — the sequence's base WAS the modifier; nothing says what was
        meant, so a bare `♀️` is not shipped."""
        self.assertEqual(
            '', normalize_extracted_emoji('\U0001F3FE‍♀️'))


class TestFiveHexDigitArtifact(unittest.TestCase):
    def test_queue_rows_repair_to_their_intended_emoji(self):
        cases = {
            'ὁE': '\U0001F41E',   # ὁE -> 🐞 lady beetle
            'Ὅ6': '\U0001F4D6',   # Ὅ6 -> 📖 open book
            'ᾘ0': '\U0001F980',   # ᾘ0 -> 🦀 crab
            'ἸF': '\U0001F38F',   # ἸF -> 🎏 carp streamer
            'ὁD': '\U0001F41D',   # ἰD -> 🐝 honeybee
            'ᾞ0': '\U0001F9E0',   # ᾞ0 -> 🧠 brain
            'Ἳ3': '\U0001F3B3',   # ἳ3 -> 🎳 bowling
            'Ἷ9': '\U0001F3F9',   # ἳ9 -> 🏹 bow and arrow
            'Ἰ8': '\U0001F388',   # Ἲ8 -> 🎈 balloon
        }
        for artifact, expected in cases.items():
            with self.subTest(artifact=artifact):
                self.assertEqual(2, len(artifact))   # it really is 2 chars
                self.assertEqual(expected,
                                 normalize_extracted_emoji(artifact))

    def test_literal_escape_strings(self):
        for literal in (r'὏9', r'\U0001F4F9', r'\u{1F4F9}'):
            with self.subTest(literal=literal):
                self.assertEqual('\U0001F4F9',
                                 normalize_extracted_emoji(literal))

    def test_repair_that_does_not_decode_to_an_emoji_is_left_alone(self):
        """U+1F41 + "Z" is not a hex digit, and U+1E00 + "0" is not an emoji."""
        self.assertEqual('', normalize_extracted_emoji('ὁZ'))
        self.assertEqual('', normalize_extracted_emoji('Ḁ0'))

    def test_orphaned_hex_tails_are_rejected(self):
        """Queue rows where the lead character was lost entirely."""
        for junk in ('fb7', 'ee1', 'bc'):
            with self.subTest(junk=junk):
                self.assertEqual('', normalize_extracted_emoji(junk))


class TestValuesThatMustPassThroughUnCHANGED(unittest.TestCase):
    def test_plain_emoji(self):
        for emoji in ('\U0001F389', '\U0001F3B8', '\U0001F4DA', '\U0001F955',
                      '❤️', '✊', '\U0001F483'):
            with self.subTest(emoji=emoji):
                self.assertEqual(emoji, normalize_extracted_emoji(emoji))

    def test_zwj_sequences(self):
        for emoji in (
            '\U0001F9D1‍\U0001F3A8',                     # 🧑‍🎨
            '\U0001F469‍\U0001F4BB',                     # 👩‍💻
            '\U0001F9D8‍♀️',                   # 🧘‍♀️
            '\U0001F468‍\U0001F469‍\U0001F466',     # 👨‍👩‍👦
            '\U0001F3F3️‍\U0001F308',               # 🏳️‍🌈
            '\U0001F441️‍\U0001F5E8️',         # 👁️‍🗨️
        ):
            with self.subTest(emoji=emoji):
                self.assertEqual(emoji, normalize_extracted_emoji(emoji))

    def test_flags(self):
        for flag in ('\U0001F1FA\U0001F1F8',    # 🇺🇸
                     '\U0001F1F5\U0001F1F7',    # 🇵🇷
                     '\U0001F1EF\U0001F1F5',    # 🇯🇵
                     '\U0001F1EE\U0001F1EA'):   # 🇮🇪
            with self.subTest(flag=flag):
                self.assertEqual(flag, normalize_extracted_emoji(flag))

    def test_keycap_sequence(self):
        self.assertEqual('1️⃣',
                         normalize_extracted_emoji('1️⃣'))

    def test_leading_emoji_is_still_extracted_from_a_longer_string(self):
        self.assertEqual('\U0001F389',
                         normalize_extracted_emoji('\U0001F389 Party time'))


class TestRejectedValues(unittest.TestCase):
    def test_non_emoji_text_is_rejected(self):
        """These all reached the DB because `process_crawl_result` only
        OVERWROTE the field when an emoji was found — a junk value with no venue
        fallback kept the junk."""
        for junk in ('clarinet', 'Rex', 'sketch', 'Violin', 'cassette',
                     ' wigs', ' mentors', 'ሀሐሐ', '税',
                     '入門', 'オヘラ'):
            with self.subTest(junk=junk):
                self.assertEqual('', normalize_extracted_emoji(junk))

    def test_bare_digits_and_blanks(self):
        for junk in ('', None, '   ', '4', '3', '8', '#', '*'):
            with self.subTest(junk=junk):
                self.assertEqual('', normalize_extracted_emoji(junk))

    def test_blocked_emoji_are_rejected(self):
        for blocked in ('⬜', '⬛', '■'):
            with self.subTest(blocked=blocked):
                self.assertEqual('', normalize_extracted_emoji(blocked))


if __name__ == '__main__':
    unittest.main()
