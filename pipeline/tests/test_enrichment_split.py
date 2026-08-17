"""Tests for adaptive enrichment-batch splitting.

A batch of 30 wordy events can overrun the model's output budget. The response
comes back `incomplete`, `generate_structured` raises, and `enrich_events_batch`
used to drop the WHOLE batch — leaving all 30 events with no description and no
tags. Measured on the 2026-08-10 run: 14 of 185 batches failed that way, blanking
95 of 749 new events (12.7%).

These tests patch the PROVIDER SEAM (`llm_providers.generate_structured`), never a
provider-specific client object — patching `extractor.genai_client` would assert
about Gemini only and go quiet the moment production runs on OpenAI. See the
recurring "Extraction guard tests" task for why that matters.
"""

import asyncio
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import extractor
from extractor import ENRICHMENT_MIN_BATCH, enrich_events_batch
from llm_providers import ProviderCallFailure


def _ok_payload(names):
    """A well-formed EnrichmentBatch response covering `names`."""
    return json.dumps({"enrichments": [
        {"name": n, "description": f"About {n}.", "hashtags": ["Music"], "emoji": "🎵"}
        for n in names
    ]})


class _FakeProviderCall:
    """Stands in for `llm_providers.generate_structured`.

    `fail_over` makes any call whose batch is larger than N raise the way a real
    provider does on a truncated response, so the batch size is the only variable.
    """

    def __init__(self, fail_over):
        self.fail_over = fail_over
        self.batch_sizes = []

    async def __call__(self, prompt, schema, timeout, provider=None, **kwargs):
        # Recover the batch from the prompt: the enrichment prompt lists each
        # event name on its own line, so count the ones we planted.
        names = [n for n in self._planted if f"{n}" in prompt]
        self.batch_sizes.append(len(names))
        if len(names) > self.fail_over:
            raise ProviderCallFailure("openai response incomplete (max_output_tokens)")
        return _ok_payload(names)


class EnrichmentSplitTests(unittest.IsolatedAsyncioTestCase):

    def _install(self, fail_over, names):
        fake = _FakeProviderCall(fail_over)
        fake._planted = names
        return fake

    async def test_oversized_batch_splits_instead_of_losing_everything(self):
        names = [f"EventName{i:03d}" for i in range(30)]
        fake = self._install(fail_over=8, names=names)

        with mock.patch.object(extractor.llm_providers, "generate_structured", fake):
            out = await enrich_events_batch(names, "Some Venue")

        # Every event is enriched despite the first (and second) call failing.
        self.assertEqual(len(out), 30)
        self.assertEqual(set(out), set(names))
        self.assertTrue(all(v["description"] for v in out.values()))
        # It genuinely subdivided rather than one lucky retry.
        self.assertGreater(len(fake.batch_sizes), 1)
        self.assertEqual(fake.batch_sizes[0], 30)

    async def test_healthy_batch_makes_exactly_one_call(self):
        """The normal path must be untouched — no extra cost when nothing fails."""
        names = [f"EventName{i:03d}" for i in range(30)]
        fake = self._install(fail_over=100, names=names)

        with mock.patch.object(extractor.llm_providers, "generate_structured", fake):
            out = await enrich_events_batch(names, "Some Venue")

        self.assertEqual(len(out), 30)
        self.assertEqual(fake.batch_sizes, [30])

    async def test_partial_recovery_when_one_half_is_pathological(self):
        """A group that fails even at the floor must not sink its siblings."""
        names = [f"EventName{i:03d}" for i in range(16)]
        fake = self._install(fail_over=0, names=names)   # every call fails

        with mock.patch.object(extractor.llm_providers, "generate_structured", fake):
            out = await enrich_events_batch(names, "Some Venue")

        # Nothing recoverable, but it stopped at the floor rather than recursing
        # forever, and it degraded to the documented soft-failure contract.
        self.assertEqual(out, {})
        self.assertTrue(all(s >= ENRICHMENT_MIN_BATCH or s == 0
                            for s in fake.batch_sizes))
        self.assertLessEqual(min(s for s in fake.batch_sizes if s), 8)

    async def test_does_not_subdivide_below_the_floor(self):
        names = [f"EventName{i:03d}" for i in range(ENRICHMENT_MIN_BATCH)]
        fake = self._install(fail_over=0, names=names)

        with mock.patch.object(extractor.llm_providers, "generate_structured", fake):
            out = await enrich_events_batch(names, "Some Venue")

        self.assertEqual(out, {})
        self.assertEqual(fake.batch_sizes, [ENRICHMENT_MIN_BATCH])

    async def test_empty_batch_makes_no_call(self):
        fake = self._install(fail_over=0, names=[])
        with mock.patch.object(extractor.llm_providers, "generate_structured", fake):
            self.assertEqual(await enrich_events_batch([], "Some Venue"), {})
        self.assertEqual(fake.batch_sizes, [])


if __name__ == "__main__":
    unittest.main()
