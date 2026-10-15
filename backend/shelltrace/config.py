from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))


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
    llm_model: str = os.getenv("LLM_MODEL", "claude-opus-5")
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY") or None
    mcp_url: str = os.getenv("ST_MCP_URL", "http://127.0.0.1:8000/mcp/")
    mcp_api_key: str | None = os.getenv("ST_MCP_API_KEY") or None
    budget_steps: int = 8
    budget_model_calls: int = 10
    budget_wall_s: float = 45.0
    tool_timeout_s: float = 2.0

    @property
    def llm_enabled(self) -> bool:
        return self.llm_provider == "anthropic" and bool(self.anthropic_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
