# Individual reflection (one per intern)

Write 1-1.5 pages, first person, specific.  Evidence beats adjectives: link commits / PRs / files.  Save as `docs/reflections/<your-name>.md`.

## 1. What I owned
| Area | What exactly I built or decided | Evidence (commit / file / PR) | Done? |
|---|---|---|---|
| e.g. Identity graph | shared-device guard, evaluation vs naive baseline | `customer360/identity.py`, `tests/test_identity.py` | yes |
| | | | |

*Ownership means you could explain every line and would be paged if it broke.  State clearly what you only reviewed or paired on.*

Suggested split for four interns (adapt to your team):
| Intern | Owns |
|---|---|
| A - Data & sources | GA4 sample access, simulator / BigQuery loader, Segment tracking plan and replay, reconciliation |
| B - Modelling (dbt) | staging, sessions, orders, customer profile, macros for BigQuery vs DuckDB, dbt tests |
| C - Customers & identity | identity graph, RFM, BG/NBD CLV, segments, evaluation vs ground truth |
| D - Attribution, ROI & BI | attribution models, ROI / CPA marts, budget optimiser, Tableau, final story |

## 2. What I learned
* **Technical** (name 3 concrete things, e.g. "why connected components need a guard", "how BG/NBD's drop-out assumption shows up in the likelihood", "adapter.dispatch for multi-warehouse dbt").
* **Analytical** (e.g. "attribution assigns credit, not incrementality", "a metric needs a baseline before it means anything").
* **Working as a team** (code review, tests as a contract, documenting decisions).

## 3. A challenge I faced (STAR)
* **Situation** - what was the problem and why did it matter?
* **Task** - what were you responsible for?
* **Action** - what did you try (including what failed)?
* **Result** - what changed, with a number if possible (e.g. "false merges 53 -> 2", "parameter recovery within 25 %").

## 4. A mistake and what I'd do differently
Be honest and specific (wrong assumption, untested edge case, late integration...).  What process or test would have caught it earlier?

## 5. Quality and impact
* Which tests did I write, and which bug did one of them catch?
* One decision where I chose the simpler / safer option and why.
* Which limitation of my component should the audience know about?

## 6. Next steps for me
* Skills to deepen (e.g. incrementality testing, Bayesian MMM, dbt incremental models, BigQuery cost tuning).
* What I would build next on this project if I had another month.

---
### Self-check before you submit
- [ ] I can explain my component in 2 minutes without notes.
- [ ] My claims link to code, tests or numbers in this repository.
- [ ] I state what I did **not** verify (e.g. BigQuery execution, live Segment, Tableau).
- [ ] I named at least one thing a teammate taught me.
