# Attribution

The files in this directory (`bug_injector.js` and `bugs/*.js`) are copied unchanged from the WebTestPilot benchmark:

- Repository: https://github.com/code-philia/WebTestPilot-benchmark, commit `b3055bf7b119dae648f7cddc96973e0a4ee8bb97` (2026-10-01), paths `runtime/bug_injector.js` and `bookstack/bugs/`.
- It is a submodule of https://github.com/code-philia/WebTestPilot (commit `26ed5ad8f4f4325bfb47c44e2c796ad2dd6cc559`), which is licensed **CC BY 4.0**.
- Paper: X. Teoh, Y. Lin, D.-M. Nguyen, R. Ren, W. Zhang, J. S. Dong, "WebTestPilot: Agentic End-to-End Web Testing against Natural Language Specification by Inferring Oracles with Symbolized GUI Elements", Proc. ACM Softw. Eng. 3 (FSE), 2026, doi 10.1145/3797115.

Checksums: [../../VENDORED.sha256](../../VENDORED.sha256). Our changes are applied only at build time by `../build_injected.py` (adaptations A1–A5, documented there and in `../../README.md`).
