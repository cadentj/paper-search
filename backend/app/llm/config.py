"""TOML-backed model routing for LLM calls."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import tomllib


BACKEND_DIR = Path(__file__).resolve().parents[2]
LLM_CONFIG_PATH = BACKEND_DIR / "llm_config.toml"

FILTER_GENERATION_PROFILE = "filter_generation"
JUDGE_PROFILE = "judge"
IDEA_MAP_PROFILE = "idea_map"
SUMMARY_PROFILE = "summary"
REQUIRED_PROFILES = (
    FILTER_GENERATION_PROFILE,
    JUDGE_PROFILE,
    IDEA_MAP_PROFILE,
    SUMMARY_PROFILE,
)


@dataclass(frozen=True)
class LLMModelConfig:
    model: str
    provider: str


@lru_cache
def load_llm_config(path: Path = LLM_CONFIG_PATH) -> dict[str, LLMModelConfig]:
    try:
        with path.open("rb") as f:
            raw_config = tomllib.load(f)
    except FileNotFoundError as exc:
        raise RuntimeError(f"LLM config file not found: {path}") from exc

    config: dict[str, LLMModelConfig] = {}
    for profile in REQUIRED_PROFILES:
        raw_profile = raw_config.get(profile)
        if not isinstance(raw_profile, dict):
            raise RuntimeError(f"Missing LLM config group [{profile}] in {path}")

        model = raw_profile.get("model")
        provider = raw_profile.get("provider")
        if not isinstance(model, str) or not model.strip():
            raise RuntimeError(f"Missing model for LLM config group [{profile}] in {path}")
        if not isinstance(provider, str) or not provider.strip():
            raise RuntimeError(
                f"Missing provider for LLM config group [{profile}] in {path}"
            )

        config[profile] = LLMModelConfig(model=model, provider=provider)

    return config


def get_llm_config(profile: str) -> LLMModelConfig:
    config = load_llm_config()
    try:
        return config[profile]
    except KeyError as exc:
        raise RuntimeError(f"Unknown LLM config profile: {profile}") from exc
