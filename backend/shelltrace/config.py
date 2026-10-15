from __future__ import annotations

import os
import json
from pathlib import Path
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _groq_keys_env():
    try:
        value = json.loads(os.getenv("GROQ_API_KEYS", "[]"))
    except ValueError:
        return ()
    return (
        tuple(k.strip() for k in value if isinstance(k, str) and k.strip())
        if isinstance(value, list)
        else ()
    )


@dataclass(frozen=True)
class Settings:
    falkor_host: str = os.getenv("FALKORDB_HOST", "localhost")
    falkor_port: int = int(os.getenv("FALKORDB_PORT", "6379"))
    falkor_username: str | None = os.getenv("FALKORDB_USERNAME") or None
    falkor_password: str | None = os.getenv("FALKORDB_PASSWORD") or None
    template_graph: str = os.getenv("ST_TEMPLATE", "st_facts_synthetic")
    default_workspace: str = os.getenv("ST_WORKSPACE", "demo")
    snapshot: str = os.getenv("ST_SNAPSHOT", "synthetic-v1")
    query_timeout_ms: int = int(os.getenv("ST_QUERY_TIMEOUT_MS", "2000"))
    scope_cap: int = 500
    llm_provider: str = os.getenv("LLM_PROVIDER", "none").lower()
    llm_model: str = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY") or None
    groq_api_key: str | None = os.getenv("GROQ_API_KEY") or None
    groq_api_keys: tuple[str, ...] = _groq_keys_env()
    llm_timeout_s: float = 8.0
    llm_max_attempts: int = 2
    jev_enabled: bool = os.getenv("JEV_ENABLED", "false").lower() == "true"
    jev_api_key: str | None = (
        os.getenv("TYPESAFE_API_KEY") or os.getenv("JEV_API_KEY") or None
    )
    jev_model: str = os.getenv("JEV_MODEL", "jev-latest")
    jev_timeout_s: float = 5.0

    @property
    def groq_keys(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(k for k in (*self.groq_api_keys, self.groq_api_key) if k)
        )

    mcp_url: str = os.getenv("ST_MCP_URL", "http://127.0.0.1:8000/mcp/")
    mcp_api_key: str | None = os.getenv("ST_MCP_API_KEY") or None
    budget_steps: int = 8
    budget_model_calls: int = 10
    budget_wall_s: float = 45.0
    tool_timeout_s: float = 2.0

    @property
    def llm_enabled(self) -> bool:
        return (self.llm_provider == "groq" and bool(self.groq_keys)) or (
            self.llm_provider == "anthropic" and bool(self.anthropic_api_key)
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
