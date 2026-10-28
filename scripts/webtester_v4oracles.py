"""Run the webtester CLI with the v4 consistency oracles (locked at 29b0940) in place of the current ones.

D55 development baseline: `resweep` replays the same recorded runs with v4 and with v5, so a change
in findings comes from the oracle code alone. Everything else (runner, gate, memory, browser) is the
current code; only consistency.py differs between the two versions.
Usage: python scripts/webtester_v4oracles.py --config CONFIG resweep RUN [--clean]
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import webtester  # noqa: E402,F401  (the package, so the module below can use relative imports)

spec = importlib.util.spec_from_file_location("webtester.consistency",
                                              ROOT / "logs/experiments/v5dev/consistency_v4_29b0940.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["webtester.consistency"] = mod
spec.loader.exec_module(mod)

from webtester.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.argv[0] = "webtester"
    sys.exit(main())
