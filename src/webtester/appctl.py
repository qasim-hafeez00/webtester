"""Control of the app under test: start with a fault set, reset data, health check."""

from __future__ import annotations

import os
import re
import subprocess
import time
import urllib.request

from .config import REPO_ROOT, AppConfig


_MARKER = re.compile(r"\[wt-fault\] (F\d+)")


class AppControlError(RuntimeError):
    pass


class AppControl:
    def __init__(self, app: AppConfig):
        if not app.compose_dir:
            raise AppControlError(f"app {app.name!r} has no compose_dir")
        self.app = app
        self.dir = (REPO_ROOT / app.compose_dir).resolve()

    def _compose(self, *args: str, env: dict | None = None, timeout: int = 600) -> str:
        proc = subprocess.run(
            ["docker", "compose", *args], cwd=self.dir, capture_output=True, text=True,
            env={**os.environ, **(env or {})}, timeout=timeout,
        )
        if proc.returncode != 0:
            raise AppControlError(f"docker compose {' '.join(args)} failed:\n{proc.stderr[-2000:]}")
        return proc.stdout

    @property
    def _client_faults_file(self):
        return self.dir / ".enabled_faults"

    def running_faults(self) -> list[str]:
        """The run's ground truth: faults the backend container was started with, or for apps
        with client-side injected faults, the set chosen at the last `app up --faults`."""
        if self.app.fault_script:
            f = self._client_faults_file
            out = f.read_text(encoding="utf-8") if f.exists() else ""
        else:
            out = self._compose("exec", "-T", "backend", "printenv", "FAULTS", timeout=60) if self._backend_up() else ""
        return sorted(f.strip().upper() for f in out.strip().split(",") if f.strip())

    def fired_faults(self, since: float, until: float) -> list[str]:
        """Server-side exposure markers (`[wt-fault] Fxx`) the backend logged between two unix
        times: which seeded faults actually took effect during exploration (I33, D36)."""
        if self.app.fault_script or not self._backend_up():
            return []
        out = self._compose("logs", "backend", "--no-log-prefix", "--since", str(int(since)),
                            "--until", str(int(until) + 1), timeout=120)
        return sorted(set(_MARKER.findall(out)))

    def _backend_up(self) -> bool:
        out = self._compose("ps", "--status", "running", "--services", timeout=60)
        return "backend" in out.split()

    def up(self, faults: list[str] | None = None, build: bool = False) -> None:
        faults = self._expand(faults or [])
        if self.app.fault_script:
            self._client_faults_file.write_text(",".join(faults), encoding="utf-8")
        env = {"FAULTS": ",".join(faults)}
        # --build alone left the old containers running on 25 Oct (I35): recreate them explicitly.
        args = ["up", "-d"] + (["--build", "--force-recreate"] if build else [])
        self._compose(*args, env=env, timeout=1800)
        self.wait_healthy()
        if self.app.setup_service:
            out = self._compose("wait", self.app.setup_service, timeout=600).strip()
            # prints `container "<id>" exited with status code N` (older versions: just N)
            m = re.search(r"(\d+)\s*$", out)
            if not m or m.group(1) != "0":
                raise AppControlError(f"setup service {self.app.setup_service!r} failed: {out[-300:]}; "
                                      f"see `docker compose logs {self.app.setup_service}`")

    def _expand(self, faults: list[str]) -> list[str]:
        """`ALL` means every fault in the app's catalog."""
        if [f.upper() for f in faults] != ["ALL"]:
            return faults
        import tomllib

        catalog = tomllib.loads((self.dir / "faults" / "faults.toml").read_text(encoding="utf-8"))
        return [f["id"].upper() for f in catalog.get("fault", [])]

    def reset(self) -> float:
        """Restore the seeded snapshot. Returns seconds taken."""
        if not self.app.reset_compose_args:
            raise AppControlError(f"app {self.app.name!r} has no reset_compose_args")
        t0 = time.monotonic()
        # Docker Desktop occasionally stalls one `exec` (26 Oct: a reset hung for 120 s and the next
        # took 0.5 s); the reset is idempotent, so a stalled one is retried.
        for attempt in range(3):
            try:
                self._compose(*self.app.reset_compose_args, timeout=90)
                break
            except subprocess.TimeoutExpired:
                if attempt == 2:
                    raise
        return time.monotonic() - t0

    def wait_healthy(self, timeout_s: float = 180) -> None:
        deadline = time.monotonic() + timeout_s
        url = self.app.base_url.rstrip("/") + self.app.health_path
        last = ""
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=5) as r:
                    if r.status == 200:
                        return
            except Exception as e:  # noqa: BLE001 - any failure means "not up yet"
                last = str(e)
            time.sleep(2)
        raise AppControlError(f"app not healthy at {url} after {timeout_s}s: {last}")

