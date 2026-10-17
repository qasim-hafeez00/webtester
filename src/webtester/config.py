"""Run configuration: one TOML file per app, overridable from the CLI.

Secrets never live in the TOML. API keys come from the environment or from a
gitignored `.env` file at the repository root (KEY=VALUE lines).
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[2]

# OpenAI-compatible endpoints. Switching provider is a config change only.
PROVIDERS: dict[str, dict[str, str | None]] = {
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "key_env": "GEMINI_API_KEY"},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "key_env": "GROQ_API_KEY"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "key_env": "OPENROUTER_API_KEY"},
    "cerebras": {"base_url": "https://api.cerebras.ai/v1", "key_env": "CEREBRAS_API_KEY"},
    "openai": {"base_url": None, "key_env": "OPENAI_API_KEY"},
    "ollama": {"base_url": "http://127.0.0.1:11434/v1", "key_env": None},
}


@dataclass(frozen=True)
class Account:
    username: str
    email: str
    password: str


@dataclass(frozen=True)
class LoginRecipe:
    """How a non-LLM agent logs in: field label -> value template, then a submit button."""

    path: str
    fields: dict[str, str]
    submit: str


@dataclass(frozen=True)
class AppConfig:
    name: str
    base_url: str
    compose_dir: str | None = None
    health_path: str = "/"
    # `docker compose` arguments that restore the seeded data snapshot.
    reset_compose_args: tuple[str, ...] = ()
    allowed_origins: tuple[str, ...] = ()
    # Elements whose visible text contains one of these are never offered to agents.
    blocked_text: tuple[str, ...] = ()
    # Additionally avoided by the crawler, which cannot recover a lost session.
    crawler_avoid_text: tuple[str, ...] = ()
    account_template: dict[str, str] = field(default_factory=dict)
    login: LoginRecipe | None = None
    # Client-side injected faults (WebTestPilot benchmark apps): a JS init script added to every
    # browser context. The faults enabled for a run come from `app up --faults` (AppControl).
    fault_script: str | None = None
    # A one-shot compose service that prepares the data after start (BookStack's seed-loader):
    # `app up` waits for it to exit successfully, so no run starts on half-loaded data.
    setup_service: str | None = None

    def account(self, worker: int) -> Account:
        """Credentials for worker number `worker` (1-based), from the template."""
        t = self.account_template
        fmt = {"i": worker}
        return Account(
            username=t["username"].format(**fmt),
            email=t["email"].format(**fmt),
            password=t["password"].format(**fmt),
        )

    def origins(self) -> tuple[str, ...]:
        if self.allowed_origins:
            return self.allowed_origins
        u = urlsplit(self.base_url)
        return (f"{u.scheme}://{u.netloc}",)


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "gemini"
    model: str = "gemini-2.5-flash"
    base_url: str | None = None  # overrides the provider preset
    api_key_env: str | None = None  # overrides the provider preset
    temperature: float = 0.2
    max_output_tokens: int = 800
    json_mode: bool = True
    # Free tiers are rate limited per minute; spacing calls avoids 429 storms.
    min_interval_s: float = 0.0
    max_retries: int = 6
    # Use numbered fallback keys (GEMINI_API_KEY_1, ...) when the primary hits its
    # quota. Off by default: rotating free keys to get around a provider's usage
    # limits breaks Google's API terms (section 2(d)); see logs/decisions.md D22.
    key_fallback: bool = True
    timeout_s: float = 90.0
    # USD per million tokens, for cost reporting only (0 on free tiers).
    price_in: float = 0.0
    price_out: float = 0.0

    def resolved_base_url(self) -> str | None:
        if self.base_url:
            return self.base_url
        return PROVIDERS.get(self.provider, {}).get("base_url")

    def resolved_key_env(self) -> str | None:
        if self.api_key_env:
            return self.api_key_env
        return PROVIDERS.get(self.provider, {}).get("key_env")


@dataclass(frozen=True)
class BudgetConfig:
    max_steps: int = 300
    max_minutes: float = 15.0
    max_tokens: int = 1_000_000


@dataclass(frozen=True)
class RunConfig:
    app: AppConfig
    llm: LLMConfig = field(default_factory=LLMConfig)
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    seed: int = 1
    headless: bool = True
    out_dir: str = "runs"
    max_elements: int = 80
    action_timeout_ms: int = 4000
    settle_ms: int = 400
    client_faults: tuple[str, ...] = ()  # set by the runner for apps with a fault_script

    def with_overrides(self, **kw) -> "RunConfig":
        app_kw = {k[4:]: v for k, v in kw.items() if k.startswith("app_") and v is not None}
        llm_kw = {k[4:]: v for k, v in kw.items() if k.startswith("llm_") and v is not None}
        bud_kw = {k[7:]: v for k, v in kw.items() if k.startswith("budget_") and v is not None}
        top = {k: v for k, v in kw.items() if not k.startswith(("app_", "llm_", "budget_")) and v is not None}
        return replace(
            self,
            app=replace(self.app, **app_kw),
            llm=replace(self.llm, **llm_kw),
            budget=replace(self.budget, **bud_kw),
            **top,
        )

    def to_dict(self) -> dict:
        return asdict(self)


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader: KEY=VALUE lines, existing environment wins."""
    path = path or REPO_ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_config(path: str | Path) -> RunConfig:
    raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    app_raw = dict(raw["app"])
    login_raw = app_raw.pop("login", None)
    for key in ("allowed_origins", "blocked_text", "crawler_avoid_text", "reset_compose_args"):
        if key in app_raw:
            app_raw[key] = tuple(app_raw[key])
    app = AppConfig(**app_raw, login=LoginRecipe(**login_raw) if login_raw else None)
    llm = LLMConfig(**raw.get("llm", {}))
    budget = BudgetConfig(**raw.get("budget", {}))
    return RunConfig(app=app, llm=llm, budget=budget, **raw.get("run", {}))
