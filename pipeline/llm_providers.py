"""Compatibility interface for API-free extraction by the supervising agent.

Provider environment variables and credentials are deliberately ignored. Every
extraction path exchanges durable local packets through agent_extraction.
"""
import agent_extraction

AGENT = 'agent'
PATHS = ('single', 'chunked', 'vision', 'enrichment', 'detail')


class ProviderCallFailure(RuntimeError):
    """Legacy failure type retained for callers; no remote providers exist."""


def provider_for(path):
    return AGENT


def single_call_provider():
    return AGENT


def provider_summary():
    return [(path, AGENT, 'supervising agent') for path in PATHS]


def providers_in_use():
    return {AGENT}


def unconfigured_paths(gemini_client=None):
    return []


def is_configured(provider, gemini_client=None):
    return provider == AGENT


def model_label(provider):
    return 'supervising agent'


async def generate_structured(prompt, schema, timeout=None, provider=AGENT, images=None,
                              gemini_client=None, gemini_model=None, expected_names=None):
    """Queue local work or return validated agent JSON, never invoke an API.

    Legacy arguments remain accepted so integration callers cannot accidentally
    fall back to a network provider. Pending/invalid responses propagate intact.
    """
    return agent_extraction.request(prompt, schema, images, expected_names=expected_names)
