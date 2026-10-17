# 06 · RippleGUItester: Change-Aware Exploratory Testing (PACMSE 2026)

> **Fact sheet** (research notes from a full read of arXiv 2603.03121v1). Not submission text.

| | |
|---|---|
| **IEEE ref** | Y. Su, M. Pradel, and C. Chen, "RippleGUItester: Change-aware exploratory testing," *Proc. ACM Softw. Eng.*, 2026, doi: 10.1145/3832240. |
| **Venue / rank** | Published in PACMSE 2026. **Check whether this is the FSE 2026 or ISSTA 2026 issue** (open the DOI page). Both are top SE venues; save the proof. |
| **Artifact** | github.com/RippleTester/RippleGUItesting (p.19) |
| **Relevance** | Gap: G2 (primary). Its false-positive analysis is the strongest evidence that our evidence gate is needed. |

## Problem
- Code changes keep introducing user-visible bugs despite tests, CI and code review. In Firefox, **12.2% of 97,347 merged PRs introduced a new bug** (p.3).
- These bugs are hard to catch because they need varied event sequences and test data, they spread across scenarios, and their oracles are hard to predict (p.3–4).

## Method
Three LLM-based components (Fig. 2, p.5):
1. **Generator** (§3.1):
   - Change-impact analysis from the PR's intent and diff, plus "preceding change intents" found through git blame.
   - Event sequences enriched through RAG over a **Scenario Knowledge Base** mined from past bug reports.
   - Concrete test data instantiated.
2. **Executor** (§3.2): the LLM translates steps into UI instructions (11 action types) and runs them with xdotool. **Each scenario runs in a fresh Docker container on both the pre-change and post-change builds**, and the post-change instructions are replayed verbatim on the pre-change build.
3. **Detector** (§3.3): a pixel diff (threshold 30, dilation, bounding boxes), then an LLM judges each difference as *expected* (matches the change intent) or a *bug*. A final LLM filter removes duplicates and timing or non-deterministic artifacts.

Models: GPT-5.2 for the Generator and Detector, Claude Opus 4.5 for the Executor.

## Data
- 4 open-source **desktop** apps: Firefox, Zettlr, JabRef, Godot (p.11–12).
- **111 PRs** in total:
  - Firefox: 30 PRs with known introduced bugs, giving 46 ground-truth bugs.
  - Zettlr: 38 recent PRs. JabRef: 18. Godot: 25.
- To prevent data leakage, the knowledge base only uses issues created before each PR (p.12).

## Results
- **RQ1:** **119 unique bugs** detected. **26 were previously unknown and still present**: 16 fixed, 2 confirmed, 6 under discussion, 2 judged as intended (p.12).
- **RQ2, precision** (Table 1): **0.464 overall** (148 TP, 171 FP). Per app: Firefox 0.559, Zettlr 0.414, JabRef 0.475, Godot 0.417.
- **False-positive taxonomy** (§4.3, the important part for us):

  | Cause | Share of FPs | Breakdown |
  |---|---|---|
  | **GUI rendering and timing instability** | **45.6%** | 39 screenshot-timing, 39 unstable layout |
  | LLM reasoning and hallucination | 27.5% | Misread annotations, assumed actions that never ran, unnecessary "improvements" |
  | **Interaction and replay instability** | **15.2%** | Wrong element located; layout differences break replay |
  | Expected differences flagged as bugs | 9.9% | n/a |

  - The authors' suggested fix (p.14): "**execute the same UI instructions multiple times and check for consistent GUI states**".
- **RQ3, recall** on Firefox: 13/46 ground-truth bugs (about 28%). Misses come from scenario coverage (60.6%) and incomplete execution (39.4%) (§4.4).
- **RQ4, cost:** **$5.99 and 54.8 min per PR**. The Executor accounts for 62% of the cost (Fig. 9).

## Limitations

**Stated by the authors (p.17):**
- High false-positive rate.
- Desktop apps only.
- Expensive frontier LLMs.

**Spotted myself:**
- **Method**
  - Needs a code change (PR) and both builds. It can't test an app as a black box.
  - The oracle is *differential*: it only catches changes in behaviour, not bugs that already exist.
  - Verification is an **LLM filter rather than re-execution**, which is why timing and rendering false positives survive.
- **Evaluation**
  - Recall is measured on only one app (Firefox).
  - Precision is labelled manually by the authors, with no inter-rater agreement reported.
  - No baseline tool is compared; this is a feasibility-style evaluation.
  - Single runs, with no variance reported.
- **Cost:** $6 per PR, using the strongest frontier models. Cheaper models were not tested.

**Future directions:** repeated execution with consistency checks; replay that adapts to layout changes; randomized interactions for better coverage.

## Relevance to our project
- **Key G2 evidence:**
  - Even with GPT-5.2 and Opus 4.5, **more than half of the reported bugs were false** (precision 0.46).
  - **About 61% of the false positives (45.6% + 15.2%) come from non-determinism and replay instability.** Our fresh-session k-fold replay targets exactly these.
  - The authors propose repeated execution as future work, and we implement and measure it.
- **Design to borrow:**
  - A fresh Docker container per execution, for isolation. Same idea as our per-replay app reset.
  - Their FP categories become our **failure-analysis codebook** for rejected and flaky findings.
- **Difference from us:** their oracle is differential (pre vs. post build). Ours is spec-free and inferred from exploration. Both rely on execution evidence.

## Your summary (150–250 words, your own words)
<!-- Write here -->
