# 05 · Breaking Single-Tester Limits: Multi-Agent LLMs for Multi-User Feature Testing (MAdroid, ICSE 2026)

> **Fact sheet** (research notes from a full read of arXiv 2506.17539v3). Not submission text.

| | |
|---|---|
| **IEEE ref** | S. Feng, C. Du, H. Liu, Q. Wang, Z. Lv, M. Wang, and C. Chen, "Breaking single-tester limits: Multi-agent LLMs for multi-user feature testing," in *Proc. IEEE/ACM 48th Int. Conf. Softw. Eng. (ICSE)*, Rio de Janeiro, Brazil, 2026, doi: 10.1145/3744916.3764535. |
| **Venue / rank** | ICSE 2026 (CORE A*, verify) |
| **Artifact** | github.com/sidongfeng/MAdroid (p.2) |
| **Relevance** | Gap: G1 (multi-agent LLM coordination across several devices) |

## Problem
- **Multi-user interactive features** (calls, live streams, invitations, join-by-code) need **several users on separate devices**, acting in a strict order under time pressure (p.1–2).
- Single-device testers and random tools almost never trigger these features.
- Earlier multi-agent testing used hard-coded agents, so it didn't generalize (p.2).

## Method
- **MAdroid**, with three LLM roles, each a separate GPT-4 instance on its own thread (p.3–6):
  - **Coordinator:** works out how many users are needed, splits the task into per-user sub-tasks, and picks who acts first (Fig. 3).
  - **Operator:** one per device, from a Genymotion device farm. Its actions are tap, input, back, **switch_user(message)** and end_task. It sees a simplified XML view hierarchy (Table 1, §3.2).
  - **Observer:** runs every 2 actions and at the end. It reviews the cross-device trace and catches wrong, hallucinated or repeated actions.
- **Error recovery:** interactive actions can't be undone (e.g. a declined invitation), so the system **restarts the task, replays up to the step before the error**, and tells the Operator that action was wrong (§3.3.2).

## Data
- **41 multi-user tasks from 16 popular apps** (TikTok, WeChat, Discord, Teams, Skype…). They were labelled by 4 annotators and checked by 2 industry developers. Each task needs 2–3 users, with about 2.87 actions per user (p.6–7).
- **Regression study:** 37 tasks across 3 versions of 18 F-Droid social apps, giving 111 runs (p.9–10).

## Results
- **RQ1** (Table 2, p.7), over 3 runs:

  | Variant | Success | Action similarity (LCS) |
  |---|---|---|
  | **MAdroid** | **82.9%** | 96.8% |
  | Operator only | 46.3% | 79.1% |
  | + Coordinator | 56.1% | n/a |
  | + Observer | 65.8% | n/a |

- **RQ2** (Table 3): the best LLM baseline, Mobile-agent, reaches 68.3%. Random/model-based tools (Monkey, Sapienz, Stoat, Humanoid) reach 7–12%.
- **RQ3:** 88.3% of regression runs succeed. **11 interactive bugs** found; 7 confirmed or fixed (Table 4).
- Main remaining failures: **timing** (LLM latency longer than a 2-second UI window) and flows that span several apps (p.8).

## Limitations

**Stated by the authors (p.10):**
- Possible LLM data leakage, reduced by labelling fresh tasks.
- Device scalability not tested (at most 3 devices).
- GPT-4 only.

**Spotted myself:**
- **Task setting:** the feature to test is given in natural language. There is no exploration or discovery of features.
- **Coordination:** handled by an LLM Coordinator through **turn-taking** (switch_user), so devices act one after another, not concurrently. Throughput and scaling are not measured.
- **Evaluation**
  - Success and action similarity are measured against a ground-truth trace. There is no fault-detection oracle; bugs were found indirectly, by spotting tasks that broke in later versions.
  - Small dataset (41 tasks), only 3 runs, and no statistical tests.
  - No cost or latency numbers, even though latency is the main failure cause.
- **Verification:** the Observer is an LLM judging LLM actions, with no execution-based check.
- **Generalizability:** Android only, 2–3 users.

**Future directions:** local LLMs to cut latency; cross-app flows; more users.

## Relevance to our project
- **G1 context:** shows that *role-specialized* multi-agent LLMs coordinating over **several separate devices** beat a single agent (46.3% to 82.9%). This supports multi-agent design in GUI testing.
- **Different from us:** MAdroid's agents *cooperate on one task* in turn. Our workers *split up exploration work* concurrently through a shared frontier. These are different coordination problems, so we should cite it as the nearest LLM multi-device precedent.
- **Ideas to borrow:**
  - The Observer is a **verification role**. Our G2 evidence gate is the execution-based version (replay, not an LLM opinion).
  - "Restart and replay to the step before the error" is the same mechanism our fresh-session replay needs.
  - The ablation design (Operator only, +Coordinator, +Observer) is a model for our component-by-component ablations.

## Your summary (150–250 words, your own words)
<!-- Write here -->
