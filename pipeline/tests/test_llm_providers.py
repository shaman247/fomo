"""Tests for llm_providers.py — provider selection for the single-call
extraction path, and the failure translation that keeps a bad provider call
from being stored as a "this page has no events" zero."""

import asyncio
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import llm_providers
from llm_providers import (
    GEMINI,
    OPENAI,
    ProviderCallFailure,
    generate_structured,
    single_call_provider,
)


def run(coro):
    return asyncio.run(coro)


class SelectionTests(unittest.TestCase):
    """EXTRACTION_PROVIDER_SINGLE picks the provider; unset/garbage means Gemini."""

    def _with(self, value):
        # Strip EVERY EXTRACTION_PROVIDER* key, not just the one under test.
        # `.env` is loaded into os.environ, so once production set
        # EXTRACTION_PROVIDER=openai these "unset means Gemini" cases were
        # silently reading the real config and failing — the assertion never
        # exercised the unset path at all.
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("EXTRACTION_PROVIDER")}
        if value is not None:
            env["EXTRACTION_PROVIDER_SINGLE"] = value
        return mock.patch.dict(os.environ, env, clear=True)

    def test_default_is_gemini(self):
        with self._with(None):
            self.assertEqual(single_call_provider(), GEMINI)

    def test_openai_selected(self):
        with self._with("openai"):
            self.assertEqual(single_call_provider(), OPENAI)

    def test_case_and_whitespace_tolerated(self):
        with self._with("  OpenAI \n"):
            self.assertEqual(single_call_provider(), OPENAI)

    def test_unknown_value_falls_back_to_gemini(self):
        # A typo must not silently disable extraction — fall back to the
        # provider the rest of the pipeline already depends on.
        with self._with("gpt5"):
            self.assertEqual(single_call_provider(), GEMINI)

    def test_empty_value_falls_back_to_gemini(self):
        with self._with(""):
            self.assertEqual(single_call_provider(), GEMINI)


class PinningTests(unittest.TestCase):
    """vision regressed in measurement, so the blanket EXTRACTION_PROVIDER
    switch must not reach it — but an explicit per-path override still must.

    chunked is deliberately NOT pinned: its regression was a record-counted
    max_batches budget, fixed at the source in _execute_chunked_sync.
    """

    def _env(self, **kw):
        return mock.patch.dict(os.environ, kw, clear=True)

    def test_global_switch_moves_every_unpinned_path(self):
        with self._env(EXTRACTION_PROVIDER="openai"):
            for path in ('single', 'enrichment', 'detail', 'chunked'):
                self.assertEqual(llm_providers.provider_for(path), OPENAI, path)

    def test_global_switch_does_not_reach_vision(self):
        with self._env(EXTRACTION_PROVIDER="openai"):
            self.assertEqual(llm_providers.provider_for('vision'), GEMINI)

    def test_explicit_override_still_reaches_pinned_paths(self):
        with self._env(EXTRACTION_PROVIDER="gemini",
                       EXTRACTION_PROVIDER_VISION="openai"):
            self.assertEqual(llm_providers.provider_for('vision'), OPENAI)
            self.assertEqual(llm_providers.provider_for('single'), GEMINI)

    def test_every_pinned_path_is_a_real_path(self):
        for path in llm_providers.GEMINI_PINNED:
            self.assertIn(path, llm_providers.PATHS)

    def test_pinned_paths_document_why(self):
        # The pin is a measurement result; an undocumented one would get
        # removed by the next person who reads it as a stale default.
        for path, reason in llm_providers.GEMINI_PINNED.items():
            self.assertGreater(len(reason), 80, path)

    def test_default_is_gemini_everywhere(self):
        with self._env():
            self.assertEqual(llm_providers.providers_in_use(), {GEMINI})


class GeminiPathTests(unittest.TestCase):
    def _client(self, result):
        async def generate_content(**kwargs):
            if isinstance(result, Exception):
                raise result
            return SimpleNamespace(text=result)
        return SimpleNamespace(aio=SimpleNamespace(
            models=SimpleNamespace(generate_content=generate_content)))

    def test_returns_stripped_text(self):
        out = run(generate_structured(
            "p", object, 5, provider=GEMINI,
            gemini_client=self._client('  {"events": []}  '), gemini_model="m"))
        self.assertEqual(out, '{"events": []}')

    def test_api_error_becomes_provider_failure(self):
        # Use a NON-retryable error: 503 is now retried with backoff (see
        # TransientRetryTests), so using it here would test the retry loop and
        # spend ~7s of real sleep rather than testing the error mapping.
        with self.assertRaises(ProviderCallFailure):
            run(generate_structured(
                "p", object, 5, provider=GEMINI,
                gemini_client=self._client(RuntimeError("400 invalid argument")),
                gemini_model="m"))

    def test_empty_body_is_a_failure_not_an_empty_result(self):
        # An empty body must never become `{"events": []}` — that reads
        # downstream as "no events on this page" and feeds archival.
        with self.assertRaises(ProviderCallFailure):
            run(generate_structured(
                "p", object, 5, provider=GEMINI,
                gemini_client=self._client(""), gemini_model="m"))


class OpenAIPathTests(unittest.TestCase):
    def _patch_client(self, response=None, error=None):
        async def parse(**kwargs):
            if error is not None:
                raise error
            return response
        return mock.patch.object(
            llm_providers, "openai_client",
            SimpleNamespace(responses=SimpleNamespace(parse=parse)))

    @staticmethod
    def _response(status="completed", parsed=None, refusal=None, reason=None):
        content = [SimpleNamespace(refusal=refusal)] if refusal else []
        return SimpleNamespace(
            status=status,
            incomplete_details=SimpleNamespace(reason=reason),
            output=[SimpleNamespace(content=content)],
            output_parsed=parsed,
        )

    def test_returns_serialized_parsed_output(self):
        parsed = SimpleNamespace(model_dump_json=lambda: '{"events": [1]}')
        with mock.patch.object(llm_providers, "OPENAI_MODEL", "gpt-5.6-luna"), \
                self._patch_client(response=self._response(parsed=parsed)):
            out = run(generate_structured("p", object, 5, provider=OPENAI))
        self.assertEqual(out, '{"events": [1]}')

    def test_unconfigured_raises_rather_than_returning_empty(self):
        with mock.patch.object(llm_providers, "openai_client", None):
            with self.assertRaises(ProviderCallFailure):
                run(generate_structured("p", object, 5, provider=OPENAI))

    def test_truncated_response_is_a_failure(self):
        # A truncated response carries the events parsed so far. Accepting it
        # would silently under-extract and could cascade into false archival.
        parsed = SimpleNamespace(model_dump_json=lambda: '{"events": [1]}')
        with mock.patch.object(llm_providers, "OPENAI_MODEL", "m"), \
                self._patch_client(response=self._response(
                    status="incomplete", parsed=parsed, reason="max_output_tokens")):
            with self.assertRaises(ProviderCallFailure) as ctx:
                run(generate_structured("p", object, 5, provider=OPENAI))
        self.assertIn("max_output_tokens", str(ctx.exception))

    def test_refusal_is_a_failure(self):
        with mock.patch.object(llm_providers, "OPENAI_MODEL", "m"), \
                self._patch_client(response=self._response(refusal="no")):
            with self.assertRaises(ProviderCallFailure):
                run(generate_structured("p", object, 5, provider=OPENAI))

    def test_missing_parsed_output_is_a_failure(self):
        with mock.patch.object(llm_providers, "OPENAI_MODEL", "m"), \
                self._patch_client(response=self._response(parsed=None)):
            with self.assertRaises(ProviderCallFailure):
                run(generate_structured("p", object, 5, provider=OPENAI))

    def test_api_error_becomes_provider_failure(self):
        # Use a NON-retryable error: 429 is now retried with backoff (see
        # TransientRetryTests), so using it here would test the retry loop and
        # spend ~7s of real sleep rather than testing the error mapping.
        with mock.patch.object(llm_providers, "OPENAI_MODEL", "m"), \
                self._patch_client(error=RuntimeError("400 invalid schema")):
            with self.assertRaises(ProviderCallFailure) as ctx:
                run(generate_structured("p", object, 5, provider=OPENAI))
        self.assertIn("400", str(ctx.exception))

    def test_timeout_becomes_provider_failure(self):
        async def parse(**kwargs):
            await asyncio.sleep(0.2)
        with mock.patch.object(llm_providers, "OPENAI_MODEL", "m"), \
                mock.patch.object(llm_providers, "openai_client", SimpleNamespace(
                    responses=SimpleNamespace(parse=parse))):
            with self.assertRaises(ProviderCallFailure) as ctx:
                run(generate_structured("p", object, 0.01, provider=OPENAI))
        self.assertIn("timed out", str(ctx.exception))

    def test_reasoning_effort_is_sent(self):
        seen = {}

        async def parse(**kwargs):
            seen.update(kwargs)
            return self._response(
                parsed=SimpleNamespace(model_dump_json=lambda: '{}'))

        with mock.patch.object(llm_providers, "OPENAI_MODEL", "m"), \
                mock.patch.object(llm_providers, "OPENAI_REASONING_EFFORT", "low"), \
                mock.patch.object(llm_providers, "openai_client", SimpleNamespace(
                    responses=SimpleNamespace(parse=parse))):
            run(generate_structured("p", object, 5, provider=OPENAI))
        # 'none' collapsed a dense listing page from 19 events to 2, so the
        # effort we send is load-bearing, not cosmetic.
        self.assertEqual(seen["reasoning"], {"effort": "low"})


class TransientRetryTests(unittest.TestCase):
    """A rate limit is not a permanent failure.

    The 2026-08-04 run took **372 HTTP 429s** against a 200,000 tokens-per-minute
    org cap and discarded the work every time, because the provider call mapped
    every exception straight to ProviderCallFailure. The API even states how long
    to wait. A lost extraction is stored as a FAILED crawl, so each one costs the
    site a full crawl cycle of freshness.
    """

    def setUp(self):
        self.slept = []

        async def _fake_sleep(secs):
            self.slept.append(secs)

        self._patches = [
            mock.patch.object(llm_providers, "_sleep", _fake_sleep),
            mock.patch.object(llm_providers, "OPENAI_MODEL", "m"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def _client(self, outcomes):
        calls = {"n": 0}

        async def parse(**kwargs):
            i = min(calls["n"], len(outcomes) - 1)
            calls["n"] += 1
            out = outcomes[i]
            if isinstance(out, Exception):
                raise out
            return out
        return calls, mock.patch.object(
            llm_providers, "openai_client",
            SimpleNamespace(responses=SimpleNamespace(parse=parse)))

    @staticmethod
    def _ok():
        parsed = SimpleNamespace(model_dump_json=lambda: '{"events": []}')
        return SimpleNamespace(status="completed", incomplete_details=None,
                               output=[], output_parsed=parsed)

    def test_rate_limit_is_retried_and_succeeds(self):
        err = RuntimeError("Error code: 429 - rate_limit_exceeded. "
                           "Please try again in 1.854s.")
        calls, patch = self._client([err, self._ok()])
        with patch:
            out = run(generate_structured("p", object, 5, provider=OPENAI))
        self.assertEqual(out, '{"events": []}')
        self.assertEqual(calls["n"], 2, "should have retried exactly once")

    def test_server_hint_drives_the_delay(self):
        err = RuntimeError("Error code: 429 - Please try again in 1.854s.")
        calls, patch = self._client([err, self._ok()])
        with patch:
            run(generate_structured("p", object, 5, provider=OPENAI))
        self.assertEqual(len(self.slept), 1)
        self.assertAlmostEqual(self.slept[0], 2.104, places=2)

    def test_millisecond_hint_is_parsed_as_ms(self):
        self.assertLess(llm_providers._retry_delay(
            RuntimeError("429 try again in 500ms"), 0), 1.0)

    def test_gives_up_after_max_attempts(self):
        err = RuntimeError("Error code: 429 - rate_limit_exceeded")
        calls, patch = self._client([err])
        with patch, mock.patch.object(llm_providers, "PROVIDER_MAX_ATTEMPTS", 3):
            with self.assertRaises(ProviderCallFailure):
                run(generate_structured("p", object, 5, provider=OPENAI))
        self.assertEqual(calls["n"], 3)

    def test_non_transient_error_is_not_retried(self):
        calls, patch = self._client([RuntimeError("400 invalid schema")])
        with patch:
            with self.assertRaises(ProviderCallFailure):
                run(generate_structured("p", object, 5, provider=OPENAI))
        self.assertEqual(calls["n"], 1)
        self.assertEqual(self.slept, [])

    def test_timeout_is_not_retried(self):
        async def parse(**kwargs):
            await asyncio.sleep(0.2)
        with mock.patch.object(llm_providers, "openai_client", SimpleNamespace(
                responses=SimpleNamespace(parse=parse))):
            with self.assertRaises(ProviderCallFailure) as ctx:
                run(generate_structured("p", object, 0.01, provider=OPENAI))
        self.assertIn("timed out", str(ctx.exception))
        self.assertEqual(self.slept, [])

    def test_status_code_attribute_is_honoured(self):
        err = RuntimeError("something opaque")
        err.status_code = 503
        self.assertTrue(llm_providers._is_retryable(err))

    def test_retry_after_header_wins_over_message(self):
        err = RuntimeError("429 try again in 30s")
        err.response = SimpleNamespace(headers={"retry-after": "2"})
        self.assertAlmostEqual(llm_providers._retry_delay(err, 0), 2.0)

    def test_backoff_is_capped(self):
        with mock.patch.object(llm_providers, "PROVIDER_BACKOFF_CAP_S", 5):
            self.assertLessEqual(
                llm_providers._retry_delay(RuntimeError("429 try again in 900s"), 0), 5)

    def test_gemini_path_retries_too(self):
        calls = {"n": 0}

        async def generate_content(**kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("503 Service Unavailable")
            return SimpleNamespace(text='{"events": []}')
        client = SimpleNamespace(aio=SimpleNamespace(
            models=SimpleNamespace(generate_content=generate_content)))
        out = run(generate_structured("p", object, 5, provider=GEMINI,
                                      gemini_client=client, gemini_model="m"))
        self.assertEqual(out, '{"events": []}')
        self.assertEqual(calls["n"], 2)


if __name__ == '__main__':
    unittest.main()
