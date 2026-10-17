# 11 · Judge: Effective State Abstraction for Guiding Automated Web GUI Testing (TOSEM 2026)

> ⚠ **ABSTRACT-LEVEL fact sheet.** The PDF is paywalled (ACM) and not yet in `pdfs/`. Download it through the university library, then fill in the `[TODO-full-read]` items. **Don't write the course summary until you've read the full paper**: the rubric requires critical analysis, and limitations can't come from an abstract.

| | |
|---|---|
| **IEEE ref** | C. Liu, J. Wang, W. Yang, Y. Zhang, and T. Xie, "Judge: Effective state abstraction for guiding automated web GUI testing," *ACM Trans. Softw. Eng. Methodol.*, vol. 35, no. 3, pp. 1–40, 2026, doi: 10.1145/3736162. |
| **Venue / rank** | ACM TOSEM (Q1, verify). Online first 2025; vol. 35(3), 2026. |
| **Artifact** | "Code and data are publicly accessible" (abstract). [TODO-full-read: link] |
| **Relevance** | Gap: G1 (state identity for deduplication). Backup base paper. |

## Problem (from the abstract)
- Automated web GUI testers aim to maximize code coverage within a time budget, but on dynamic web apps they **get stuck in loops or keep exploring the same areas**.
- **State abstraction** groups similar pages into the same state. The ideal state contains exactly the pages that behave the same from a testing point of view.
- Existing DOM- or visual-similarity approaches need thresholds or classifiers, and break on **dynamically loaded data, dynamically expanded UI elements**, and the variety of page complexity and design styles across apps.

## Method (from the abstract)
- **"Merge-and-classify":**
  - **Merge:** walk the DOM and collapse sibling elements with the same subtree structure into one, **dropping text content and HTML attributes**. This neutralizes repeated list items and dynamic data.
  - **Classify:** a **contrastive-learning model** embeds the simplified DOMs, then an **SVM** decides whether two pages are the same state.
- (A third-party review page mentions BERT/Longformer encoders. Confirm in the full text.)

## Data (from the abstract)
- **3 manually labelled page-pair datasets** for classification.
- **6 widely studied web apps** for the guided-exploration experiment. [TODO-full-read: names. Probably the same lineage as Temac/WebRLED.]
- **13 baseline** state-abstraction methods. [TODO-full-read: which ones; likely WebEmbed, FragGen, NDStudy-style thresholds, visual similarity.]

## Results (from the abstract)
- Page-pair classification: **F1 margin of +8.95% to +28.90%** over the baselines, averaged across the 3 datasets.
- Guiding exploration (against the 5 strongest baselines): **code coverage +2.62% to +14.12%** on average across the 6 apps.
- [TODO-full-read: which exploration tool hosts the abstraction; time budget; number of repetitions; statistical tests; cost of the classifier.]

## Limitations
- **Stated by the authors:** [TODO-full-read]
- **Candidates to verify yourself:**
  - The classifier is trained on labelled page pairs. Does it generalize to new apps without retraining?
  - The coverage gains (2.6–14%) are modest. Are they significant across runs?
  - Evaluated only with RL/model-based explorers, not LLM agents.
  - Inference cost per page compared with a cheap structural hash.
  - Dropping all text may merge states that really differ (e.g. an "empty cart" vs. a "full cart" message).

## Relevance to our project
- **G1 core component:** our shared frontier needs a **canonical state ID** that is cheap and holds up against dynamic content. Judge's *merge* step (collapse repeated siblings, strip text and attributes) is a near-direct recipe for our structural hash. The *classify* step is an optional upgrade.
- **Why it matters for parallelism:** with N workers, a weak state abstraction inflates "unique states" and hides duplicated work, so our G1 metric depends on it.
- **Backup base paper (Q1):** its 6-app coverage benchmark and baselines are a ready-made comparison if WebTestPilot's artifact fails.
- **Evaluation precedent:** follow its practice of computing states with *one fixed abstraction for every condition* when comparing tools.

## Your summary (150–250 words, your own words)
<!-- Write only after reading the full PDF -->
