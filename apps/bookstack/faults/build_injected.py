"""Build faults/injected.js: all WebTestPilot BookStack bug scripts in one browser init script.

    python apps/bookstack/faults/build_injected.py          # (re)write injected.js
    python apps/bookstack/faults/build_injected.py --check  # exit 1 if injected.js is stale

The merge follows the benchmark's own runtime/init.py `prepare_bug_script` (the bug's
isConditionMet / onConditionMet blocks replace the template's placeholders), applied once
per script with the script's stem as its injector kind, so all scripts coexist. Our
adaptations, each asserted to apply exactly once per script (decision D33):

  A1 No activation flag. The benchmark arms the injector only after its scripted login sets
     sessionStorage '__flash_ui_active__'; exploration has no such moment, so it is armed
     from the first page.
  A2 localStorage instead of sessionStorage for the injector's trigger state, so a fired
     fault persists across the tabs of one worker's context (inferred-oracle reload checks
     open a new tab) and is restored with the session by the evidence gate's replays.
  A3 Exposure marker. The first time a script fires it logs
     "[wt-fault] <fault id> <script> visible|no-change", which the harness records as ground
     truth (never as a finding). "visible" = the page DOM differs after the bug's effect ran;
     "no-change" = the trigger condition held but the effect found nothing to change (e.g. the
     'New Book' fault with no such book, a phantom entry on an empty list). Only "visible"
     counts as exposure (D36, refined 16 Oct after the first crawler run).
  A4 Enable switch. A script runs only if its fault id is in window.__WT_FAULTS__ (set by the
     harness from `app up --faults`), like FAULTS for Conduit.
  A5 Error isolation. Init scripts run in every frame, including about:blank and editor
     iframes, where storage access throws, and a bug body can throw on a page it does not
     expect. The benchmark never watches page errors; our implicit oracles do, so such errors
     would become false findings blamed on the app. The injector therefore arms only on
     http(s) pages, and every call into injected code goes through a guard that catches the
     error and logs "[wt-fault-error] ..." instead (ignored by the oracles, kept in the trace).
The bug bodies themselves are not changed.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "injected.js"

_GUARD = "  if (!sessionStorage.getItem('__flash_ui_active__')) return;\n"
_FIRE = "      conditionMet = true;\n      __wtSafe(onConditionMet);\n"
_CALL = re.compile(r"\b(isConditionMet|onConditionMet)\(\)")
_SAFE = ('  const __wtSafe = (fn) => { try { return fn(); } catch (e) { '
         'console.debug("[wt-fault-error] {{INJECTOR_KIND}} " + e); return false; } };\n')


def guard_template(template: str) -> str:
    """A5: route every call of the two injected functions through __wtSafe. Applied to the
    template before merging, so the bug bodies (which never call these) stay unchanged."""
    n = len(_CALL.findall(template))
    if n < 4:
        raise SystemExit(f"injector template: expected >= 4 calls to guard, found {n}")
    out = _CALL.sub(lambda m: f"__wtSafe({m.group(1)})", template)
    return _once(out, "\n(() => {\n", "\n(() => {\n" + _SAFE, "A5 guard definition")  # the top-level IIFE


def _once(text: str, old: str, new: str, what: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"{what}: expected 1 occurrence, found {n}")
    return text.replace(old, new)


def merge(bug_js: str, template: str, kind: str) -> str:
    """The benchmark's prepare_bug_script (runtime/init.py), unchanged in behaviour."""
    is_cond = re.findall(r"// BEGIN isConditionMet\s*(.*?)\s*// END isConditionMet", bug_js, re.DOTALL)
    on_cond = re.findall(r"// BEGIN onConditionMet\s*(.*?)\s*// END onConditionMet", bug_js, re.DOTALL)
    if not is_cond or not on_cond:
        raise SystemExit(f"{kind}: BEGIN/END markers not found")
    script = _once(template, "const isConditionMet = () => {};", is_cond[-1], f"{kind} isConditionMet")
    script = _once(script, "const onConditionMet = () => {};", on_cond[-1], f"{kind} onConditionMet")
    return script.replace("{{INJECTOR_KIND}}", kind)


def adapt(script: str, fault_id: str, stem: str) -> str:
    """A1-A5 on one merged script (A5's call guard was applied to the template already)."""
    script = _once(script, _GUARD, "", f"{stem} A1 activation flag")  # A1
    if "localStorage" in script:
        raise SystemExit(f"{stem}: already uses localStorage; A2 would be ambiguous")
    script = script.replace("sessionStorage", "localStorage")  # A2
    marker = ("      conditionMet = true;\n"
              "      const __wtBefore = document.documentElement.innerHTML;\n"
              "      __wtSafe(onConditionMet);\n"
              f'      console.debug("[wt-fault] {fault_id} {stem} " + '
              '(document.documentElement.innerHTML !== __wtBefore ? "visible" : "no-change"));\n')
    script = _once(script, _FIRE, marker, f"{stem} A3 marker")  # A3
    return (f'if (location.protocol.startsWith("http") && (window.__WT_FAULTS__ || []).includes("{fault_id}")) {{\n'
            f'try {{\n{script}\n}} catch (e) {{ console.debug("[wt-fault-error] {fault_id} {stem} " + e); }}\n}}\n')  # A4, A5


def build() -> str:
    catalog = tomllib.loads((HERE / "faults.toml").read_text(encoding="utf-8"))
    template = guard_template((HERE / "wtp" / "bug_injector.js").read_text(encoding="utf-8"))
    parts = ["// GENERATED by apps/bookstack/faults/build_injected.py from wtp/ (WebTestPilot benchmark,",
             "// CC BY 4.0, github.com/code-philia/WebTestPilot). Do not edit; edit the builder.", ""]
    used = set()
    for fault in catalog["fault"]:
        for stem in fault["scripts"]:
            bug = (HERE / "wtp" / "bugs" / f"{stem}.js").read_text(encoding="utf-8")
            parts.append(f"// ---- {fault['id']} / {stem} ----")
            parts.append(adapt(merge(bug, template, stem), fault["id"], stem))
            used.add(stem)
    unused = {p.stem for p in (HERE / "wtp" / "bugs").glob("*.js")} - used
    if unused:
        raise SystemExit(f"bug scripts not in faults.toml: {sorted(unused)}")
    return "\n".join(parts)


def main() -> int:
    js = build()
    if "--check" in sys.argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != js:
            print("injected.js is stale: run python apps/bookstack/faults/build_injected.py")
            return 1
        print("injected.js is up to date")
        return 0
    OUT.write_text(js, encoding="utf-8", newline="\n")
    print(f"wrote {OUT} ({len(js)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
