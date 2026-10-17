# 03 · WebCQ: Cooperative Multi-Agent Deep RL for Scalable Web GUI Testing (ASE 2026)

> **Fact sheet** (research notes from a full read of the arXiv v1, 2606.22502). Not submission text. **This is the closest G1 competitor.**

| | |
|---|---|
| **IEEE ref** | Y. Fan, S. Wang, Z. Fei, Y. Qin, H. Li, and Y. Liu, "WebCQ: Cooperative multi-agent deep reinforcement learning for scalable web GUI testing," in *Proc. IEEE/ACM Int. Conf. Automated Softw. Eng. (ASE)*, 2026, doi: 10.1145/3832783.3834374. |
| **Venue / rank** | ASE 2026 (CORE A*, verify) |
| **Artifact** | Code and data on Zenodo: 10.5281/zenodo.19222038 (p.2, p.11) |
| **Relevance** | Gap: G1 (primary) |

## Problem
- Multi-agent RL web testers (MARG; Fastbot on Android) use **tabular Q-learning**. Q-tables blow up on large sites, and the coordination/communication overhead grows with the number of agents (p.1–2).
- Actions are identified by locators (XPath), so the *meaning* of an action is lost (p.2).

## Method
- Formulates multi-agent web testing as a **Dec-POMDP**: N agents, each with its own browser, exploring one website (p.3).
- **Centralized training with decentralized execution** (Fig. 2, p.3):
  - Each agent runs a DQN policy.
  - A central learner trains with **QTRAN** (a cooperative multi-agent RL value-factorisation method) on a global replay buffer.
- **State vector:** for each common HTML tag, the average DOM depth. This gives a fixed-length vector that is cheap to compare (Fig. 3, p.4).
- **Action vector** (p.4):
  - GloVe similarity of the button text to "positive" words (submit, next…).
  - How often the action has been executed.
  - A 10-bin "exploration potential" of the child state.
- **Lightweight synchronization:** agents run asynchronously, and central training fires once every agent has at least one new transition (Alg. 1, p.5).
- **Hybrid reward** = (page novelty + execution-frequency bonus) × time compensation (Eq. 6–9).
  - The execution count N(e) is **shared across all agents**, so repeats are penalised globally.

## Data
- **8 live commercial websites:** EatingWell, ESPN, FoxNews, GameRant, GameSpot, Gap, GitHub, Smadex (Table 2, p.7). Mostly taken from MARG's benchmark.
- Sites with small state spaces or non-English content were excluded.
- No source code or ground-truth faults are available, since these are production sites.

## Results
- **Setup** (p.7): 5 agents, 3 h per run, **6 repetitions**. Statistics: Mann-Whitney U plus Vargha-Delaney A12.
- **Metrics:**
  - States, defined as "URL plus element set".
  - Unique actions.
  - **Failures, taken from browser console logs** (JS errors, network failures, rendering warnings), deduplicated.
- **RQ1** (Table 3), average over the 8 sites:

  | Tool | States | Unique actions | Failures |
  |---|---|---|---|
  | WebCQ | 978.8 | 1220.6 | 44.4 |
  | MARG | 734.1 (WebCQ +33.3%) | 858.2 (WebCQ +42.2%) | 42.6 |
  | WebExplor ×5 | 51.2 | n/a | 22.7 |

  - Failures: more than MARG on 6 of 8 sites, but **not statistically significant on most sites** (Table 4).
- **RQ2, ablation:**
  - Full WebCQ vs. *independent agents with no communication*: +27.1% states.
  - Full WebCQ vs. *MARG-style experience sharing*: +21.3% states (p.9).
- **RQ3:** over 20 hours on Gap, MARG's hourly action count collapses as its Q-tables grow, while WebCQ declines more slowly (Fig. 5).
- **RQ4, scaling** with N = 3, 5, 8, 12 on Gap (Fig. 6): WebCQ improves with N, while MARG plateaus or drops at 8–12 agents.

## Limitations

**Stated by the authors (p.10):**
- Only 8 websites.
- Randomness (weights, ε-greedy).
- The method is "less suitable for open-source websites", which have limited functionality.

**Spotted myself:**
- **Dataset**
  - **Live production websites can't be reproduced**: content changes between runs, and nobody else can replicate the results.
  - No code coverage. There are **no seeded or known faults**, so recall can't be measured.
- **Oracle**
  - Failures are **console-log messages only**, an implicit oracle. Many are third-party ad or analytics noise.
  - **No verification that a failure reproduces**, and no check that it is a real application bug.
- **Evaluation**
  - The state metric ("URL plus element set") counts trivially different pages as different states, which inflates the numbers.
  - The comparison holds the *number of agents and wall-clock time* equal, not *total compute*.
  - RQ4 runs on **only one site**.
  - No cost figures (GPU training overhead is excluded).
- **Method:** no semantic understanding of forms. It can't produce meaningful inputs or reason about expected behaviour.
- **Missing baselines:** no LLM-based explorer, and no comparison of N agents against 1 agent with N× the time.

**Future directions:** LLM-based semantic agents; reproducible benchmarks; failure validation; budget-normalized scaling.

## Relevance to our project
- **G1 prior art. Our novelty must be stated against this paper.** It shows that coordinated parallel web testing beats independent agents, but with RL, on live sites, with an unverified console-log oracle.
- **Our differences:**
  1. LLM workers with a semantic shared frontier, instead of learned Q-values.
  2. **Equal total token and browser-minute budgets**, plus a 1-vs-N comparison.
  3. Reproducible local apps with code coverage and seeded faults.
  4. Verified findings (G2).
- **To reuse:**
  - Their "w/o comm." ablation is the same idea as our B2 (independent workers).
  - Their N = 3/5/8/12 design and A12 statistics are precedent for our scaling curve.
- **Possible baseline:** their artifact is on Zenodo. Running WebCQ on our apps would give us a non-LLM coordinated baseline.

## Your summary (150–250 words, your own words)
<!-- Write here -->
