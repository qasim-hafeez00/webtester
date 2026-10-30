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
    role: str = ""  # v5 R3: the account's role name from `[[app.accounts]]` (empty: the template's one role)


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
    # v5 R3 (D60): accounts per role, `[[app.accounts]]` tables with role, username, email, password
    # (each may use {i}). Workers are spread over them in order; empty = one role from the template.
    accounts: tuple = ()
    # v5 R3/M7: the role whose account a probe uses as 'another user' (R46, R67); default: the next role
    second_role: str = ""
    # E6 (D60): extra browser init scripts, always added after the fault script (e.g. the rebranded BookStack)
    init_scripts: tuple = ()
    # X5 / evaluation: the app type of fault_families.md section 4, when known (per-app-type numbers)
    app_type: str = ""
    # D61, evaluation truth for the app-profile step (X5 profile accuracy): the primitives a person sees in the app
    primitives: tuple = ()
    # D61 (WF3, O9): a Mailpit-style HTTP API of the deployment's mail catcher, e.g. "http://localhost:8025"
    mail_api: str = ""
    # D61, evaluation axes: the front-end framework (group 8) and whether the app is held out (group 9)
    framework: str = ""
    heldout: bool = False
    # D61 (R2): the page size of the app's lists when no page shows it (0 = read it from a per-page control)
    page_size: int = 0

    def account(self, worker: int) -> Account:
        """Credentials for worker number `worker` (1-based): the accounts per role in turn, else the template."""
        if self.accounts:
            a = self.accounts[(worker - 1) % len(self.accounts)]
            fmt = {"i": worker}
            return Account(username=a["username"].format(**fmt), email=a["email"].format(**fmt),
                           password=a["password"].format(**fmt), role=a.get("role", ""))
        t = self.account_template
        fmt = {"i": worker}
        return Account(
            username=t["username"].format(**fmt),
            email=t["email"].format(**fmt),
            password=t["password"].format(**fmt),
        )

    def other_account(self, worker: int) -> Account | None:
        """A second account for M7 probes (R46, R67): another role's account, else the next worker's."""
        if self.accounts and len(self.accounts) > 1:
            mine = self.account(worker).role
            for k in range(1, len(self.accounts) + 1):
                cand = self.account(worker + k)
                if cand.role != mine and (not self.second_role or cand.role == self.second_role):
                    return cand
        if self.account_template:
            # Both apps seed worker01..worker16; runs use at most 8 workers, so 17 - worker is never in use
            return self.account(17 - worker if worker <= 8 else max(1, worker - 8))
        return None

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
    # v5 evidence layer (D58, evidence.py): response bodies, network timeline, transient messages.
    # Off by default so runs and resweeps made before D58 replay unchanged.
    capture_evidence: bool = False
    # ---- v5 phases 1-4 (D60). Defaults keep runs made before D60 replayable unchanged, except where noted.
    mode: str = "controlled"  # S1: read-only | reversible | controlled (our own deployments: M11, M13 probes allowed)
    stop_file: str = "STOP"  # S2: a file of this name in the run folder or the repo root ends the run cleanly
    observe_pool: int = 3  # X1: elements read before ranking = max_elements x pool (1 = v4 behaviour, DOM order)
    scroll_once: bool = True  # X1/R6: scroll each new URL to the end once before observing
    pierce: bool = True  # X1/R6: open shadow roots and same-origin iframes
    accept_dialogs: bool = True  # R6: alert/confirm/prompt accepted and logged (Playwright dismisses them otherwise)
    dismiss_popups: bool = True  # R9: cookie walls and newsletter pop-ups closed by known button texts
    dev_noise: bool = True  # O4: console lines from dev servers (HMR, devtools hints) are not signals
    defer_destructive: float = 0.6  # R8: delete/close-account only on own items before this budget share; logout after 0.9
    discover: bool = True  # R7: frontier seeded from sitemap.xml, robots.txt, feeds and network GETs
    seed_copies: int = 2  # R2: extra copies made of the first accepted create of each form (0 = off)
    input_profiles: bool = True  # R1: one retry of a rejected form with values derived from the field and its message
    poll_deadline_s: float = 8.0  # O3: intent-effect checks re-read a fresh view until the effect shows or this passes
    notes_max: int = 6  # E2: tester-note lines in the prompt
    profile_step: bool = True  # X5: the LLM names the app type and primitives after `profile_after` routes
    profile_after: int = 10
    roles: tuple = ()  # X4 (B5): worker roles in turn, e.g. ("explorer", "prober", "switcher", "explorer")
    gate_engines: tuple = ()  # X9: extra engines for confirmed findings, e.g. ("firefox", "webkit")
    gate_ddmin: bool = True  # C5: shrink a confirmed finding's step window (delta debugging, capped)
    env_axes: tuple = ()  # M10/R71: e.g. ("tz-west", "tz-east", "locale", "phone", "firefox", "webkit") after exploration
    coverage_metrics: bool = False  # R12, JS coverage (Chromium CDP), measured only
    # ---- D61
    hover_rows: bool = True  # R6: hover the first rows of a new state's main list once, so hover-only controls are seen
    profile_gating: bool = False  # X5 ablation only: rules outside the app profile's packs are logged unarmed:profile
    # D62: rules a locked version leaves out of its report. They still run (exploration and probe slots stay the same as
    # measured); their findings go to findings_withheld.json, not findings.json, and skip the gate.
    exclude_rules: tuple = ()
    network_routes: bool = True  # R7: same-origin HTML GETs seen in the network timeline join the frontier
    sequences: bool = True  # R11: two- and three-step metamorphic sequences from the state graph as goal flows

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
    for key in ("allowed_origins", "blocked_text", "crawler_avoid_text", "reset_compose_args", "init_scripts", "primitives"):
        if key in app_raw:
            app_raw[key] = tuple(app_raw[key])
    if "accounts" in app_raw:
        app_raw["accounts"] = tuple(dict(a) for a in app_raw["accounts"])
    app = AppConfig(**app_raw, login=LoginRecipe(**login_raw) if login_raw else None)
    llm = LLMConfig(**raw.get("llm", {}))
    budget = BudgetConfig(**raw.get("budget", {}))
    run = dict(raw.get("run", {}))
    for key in ("roles", "gate_engines", "env_axes", "exclude_rules"):
        if key in run:
            run[key] = tuple(run[key])
    return RunConfig(app=app, llm=llm, budget=budget, **run)
