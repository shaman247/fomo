"""
City/region configuration loader.

Engine code is city-agnostic; all city-specific strings live in one committed
YAML file under config/. This repo ships config/nyc.yaml (the complete fomo.nyc
config) as the worked example. To run a different city, either edit that file in
place or add config/<city>.yaml and set FOMO_CITY=<city>.

The active file is config/<FOMO_CITY>.yaml, defaulting to config/nyc.yaml.

Bare-importable (`import city_config`) per the sys.path-not-package convention
used across pipeline/ (see CLAUDE.md).
"""
import functools
import os

import yaml

_DIR = os.path.dirname(__file__)


def _config_path() -> str:
    city = os.environ.get("FOMO_CITY", "nyc")
    return os.path.join(_DIR, "..", "config", f"{city}.yaml")


@functools.lru_cache(maxsize=1)
def get_config() -> dict:
    """Load and cache the active city config (config/<FOMO_CITY>.yaml)."""
    path = _config_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except FileNotFoundError:
        raise FileNotFoundError(
            f"City config not found: {os.path.abspath(path)}. "
            f"Create it (copy config/nyc.yaml) or set FOMO_CITY to an existing config."
        )
    cfg["_source_path"] = path
    return cfg


def reset_cache():
    """Clear the cached config (test/verification hook, or after changing FOMO_CITY)."""
    get_config.cache_clear()


# --- Convenience accessors. Each has a safe default so a partial config
# --- (missing optional fields) never throws. ---

def city_name() -> str:
    return get_config().get("city_name", "the city")


def city_short() -> str:
    return get_config().get("city_short", city_name())


def metro_name() -> str:
    return get_config().get("metro_name", city_name())


def _extraction() -> dict:
    return get_config().get("extraction") or {}


def extraction_intro() -> str:
    # The full opening line of get_prompt. Template with {date}, {name}, {url}.
    return _extraction().get(
        "intro",
        "Today's date is {date}. We are assembling a database of upcoming events in "
        f"{metro_name()}. Currently, we are inspecting {{name}} ({{url}}).")


def extraction_chunk_intro() -> str:
    # The full opening line of get_chunk_prompt. Template with {date}.
    return _extraction().get(
        "chunk_intro", "Today's date is {date}. Extract ALL events from this page content.")


def extraction_tag_avoidance() -> str:
    # "Avoid location-specific or <city>-redundant tags."
    return _extraction().get("tag_avoidance", "Avoid location-specific or redundant tags.")


def extraction_region_rule() -> str:
    # The metro-geography rule bullet. Empty => no geographic restriction stated.
    return _extraction().get("region_rule", "")


def _lower_list(items) -> list:
    return [s.lower() for s in (items or [])]


def generic_location_names() -> list:
    return _lower_list(get_config().get("generic_location_names"))


def geotags() -> list:
    """Geographic geotag names (neighborhoods/boroughs/towns), original case.

    Source of truth for the metro region's place names. Consumed by db.py (as
    generic location names) and by build.js (written into the frontend's
    generated src/data/tags.json). Callers lowercase as needed.
    """
    return list(get_config().get("geotags") or [])


def _processor() -> dict:
    return get_config().get("processor") or {}


def state_suffixes() -> list:
    return _lower_list(_processor().get("state_suffixes"))


def city_area_tokens() -> list:
    return _lower_list(_processor().get("city_area_tokens"))


def borough_tokens() -> list:
    return _lower_list(_processor().get("borough_tokens"))


def region_tag_token() -> str:
    return _processor().get("region_tag_token", "")


def non_region_place_patterns() -> list:
    return list((get_config().get("review") or {}).get("non_region_places") or [])
