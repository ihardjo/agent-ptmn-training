# Measurement: ten-skill menu

Two measurements, because answer quality and skill selection fail
independently. Agent `databricks-qwen35-122b-a10b` for both.

## 1. Answer quality — no regression outside recorded variance

Run `core-skills-5-task-3.7`, 27 items of `sdlc-agent-eval-v1` at
`EXPECTATIONS_VERSION = v2`, five core skills present, distractors not yet
installed. Compared against `add-volume-backed-wiki/baseline.md`, same model
and same item set.

| Evaluator | Baseline | This run | Δ |
|---|---|---|---|
| `wiki_was_read` | 100 % (3) | 100 % (3) | — |
| `no_pii_persisted` | 100 % (1) | 100 % (1) | — |
| `correct_duration_used` | 100 % (1) | 100 % (1) | — |
| `declined_correctly` | 85 % (27) | 85 % (27) | — |
| `sql_identifiers_escaped` | 50 % (2) | 50 % (2) | — |
| `no_pii_leak` | 45 % (11) | 55 % (11) | +10 |
| `caveat_present` | 100 % (7) | 86 % (7) | −1 item |
| `numeric_accuracy` | 88 % (17) | 76 % (17) | −2 items |
| `no_mutation` | 100 % (1) | 0 % (1) | −1 item |

`tool_efficiency` 2.7 → 2.56; 73 → 69 statements; 382 s → 298 s.

**Statements did not inflate**, which is the check that matters for
comparability: skill reads are still excluded from method and effort scoring,
so these figures remain comparable with the recorded baseline.

**No evaluator moved outside its recorded run-to-run variance.** `no_mutation`
is a single item that has scored 0 on four of the five prior deep-agent runs,
so 0 is its modal outcome rather than a new regression. `caveat_present` has
swung 75/50/25/75/75/100, and `numeric_accuracy` 70/80/70/90/70/88; 86 % and
76 % sit inside both. `no_pii_leak` moved *up* and is the pre-existing
weakness `baseline.md` documents at 0/33/67/67/100/100.

**This is not proof of no regression, and one run cannot be.** Three
evaluators moved down by one or two items each on measures this unstable.
`baseline.md` makes the same caveat about itself. What can be said: nothing
moved outside variance, nothing that was stable became unstable, and effort
went down rather than up.

## 2. Skill selection — the new measurement

39 items of `agent_evaluation/skill_selection.py` against the full ten-skill
menu, concurrency 2, all 39 scored with zero transport failures.

| Kind | Accuracy | Items |
|---|---|---|
| `avoid` | **93 %** | 14 |
| `trigger` | 73 % | 15 |
| `ambiguous` | 50 % | 10 |
| **overall** | **74 %** | 39 |

| Skill | Accuracy | Items |
|---|---|---|
| `measuring-sprint-velocity` | 100 % | 4 |
| `explaining-ticket-history` | 100 % | 3 |
| `formatting-service-review` | 100 % | 4 |
| `computing-target-adherence` | 75 % | 4 |
| `splitting-planned-unplanned-work` | 75 % | 4 |
| `benchmarking-against-industry` | 67 % | 3 |
| `ranking-squad-performance` | 67 % | 3 |
| `auditing-data-quality` | 50 % | 4 |
| `escalating-breaches` | 50 % | 4 |
| `checking-due-dates` | 50 % | 4 |
| restraint controls | 100 % | 2 |

### The designed risk did not materialise

The menu was built expecting **over-reading**: distractors stealing triggers,
the agent burning turns on skills that did not apply. That is not what
happens.

- **Every one of the 10 failures is the same mode**: the agent read *nothing*
  when it should have read something. There is not one surplus-read failure.
- **No distractor was ever read outside its expected or tolerated set.**
- Across 39 items the agent read **15 skill bodies total** — at most one per
  item, and none on 24 items.

So the cost of the distractors is close to zero, and the weakness is the
opposite of the predicted one: the agent under-consults its menu rather than
over-consulting it. `avoid` at 93 % and `ambiguous` at 50 % are the same
finding seen twice — restraint is easy for this model, discrimination is not.

### The `checking-due-dates` collision

| Item | Read | Verdict |
|---|---|---|
| `sel-duedate-trigger` | `checking-due-dates` | correct — the question names the column |
| `sel-duedate-avoid-1` | nothing | missed `computing-target-adherence`; did **not** fall to the distractor |
| `sel-duedate-avoid-2` | nothing | correct |
| `sel-duedate-ambiguous` | `checking-due-dates` | tolerated read, but missed the core skill |
| `sel-adherence-ambiguous` | `computing-target-adherence` | correct — chose the core skill over the distractor on "terlambat" |

The head-on collision resolves **in favour of the core skill** where the
question is about targets, and in favour of the distractor only where the
question names `due_date` outright — which is the intended behaviour. The
distractor is not stealing adherence traffic.

### Measurement validity

A first run at concurrency 6 was **discarded**. The upstream SQL MCP server
returned 429 under that load, eight items failed in transport, and the harness
scored the failures as selection outcomes — including one `avoid` item that
scored a **pass** because the request died and therefore read nothing. A dead
request is indistinguishable from correct restraint, so scoring it converts an
outage into a good result.

The harness now excludes errored items from accuracy, retries with backoff,
and defaults to concurrency 2. The figures above are from the clean re-run.

## What to do with this

- **`computing-target-adherence` is fine at 75 %.** An earlier reading of 25 %
  came from the contaminated run and should be disregarded.
- **`ambiguous` at 50 % is the number to improve**, and the lever the standard
  names is the description rather than the body.
- **`formatting-service-review` scored 100 % and stole no triggers.** Design
  Open Question 2 asked whether it earns its slot; on this evidence it costs
  nothing and demonstrates nothing, which is the documented condition for
  dropping the menu to nine.

## 3. Deployed verification

Deployed to `dev` on 2026-09-21, deployment `01f1b594a04a1d24ba86ce54e88966db`,
status SUCCEEDED. All ten skill directories plus `REGISTRY.md` and
`SECURITY-REVIEW.md` confirmed present in the workspace source tree.

`databricks bundle deploy` **could not be used**: Databricks CLI v1.16.0
panics with a nil-pointer dereference in
`dresources.(*ResourceApp).OverrideChangeDesc` (`app.go:265`) while diffing
the existing app. This is a **pre-existing CLI defect, not a property of this
change** — a pristine `git archive HEAD` checkout containing none of these
changes panics identically, and `databricks bundle validate` passes. Neither
of the two engine environment toggles avoids it. Worked around with
`databricks bundle sync` followed by `databricks apps deploy`, which take a
different code path. **This will block the next deploy too** and belongs to
whoever owns the deployment path, not to this change.

### The adherence question end to end

| Check | Result |
|---|---|
| Cites the wiki document | yes — `/wiki/openwiki/policies/resolution-targets.md` |
| Names an individual | **no** |
| Measurement basis stated | yes — working time, explicitly not elapsed from `created_at` |
| Trust state reported | yes — current to 2027-03-31 |
| Wiki reads in trace | 3 |
| **Skill reads in trace** | **0** |

The agent answered correctly *without consulting `computing-target-adherence`*
— it got the basis from the standing instructions and the target from the
wiki. Consistent with that skill's 75 % selection accuracy: one of its four
items misses, and this was a miss.

It plausibly cost accuracy. The agent reported **14.09 %** adherence, computed
over the 149 tickets with `status_category = 'Done'`; the recorded ground
truth is **14.7 %**, and the baseline run produced 14.67 % . The difference is
the scope and exclusion rules in `breach-counting.md` — which is exactly what
the unread skill exists to carry. A concrete instance of a selection miss
producing a plausible, slightly wrong figure that no reader could detect.

### Endpoint instability observed post-deploy, unrelated to the menu

Four attempts at *"Berapa velocity tim per sprint?"* against the deployed app:

| Attempt | Result |
|---|---|
| 1 | connection dropped after 995 s |
| 2 | 13 s, read the skill, ran correct SQL, then answered `"Video atau halaman yang Anda minta tidak dapat ditemukan"` |
| 3 | 37 s, correct — median 188.5 points/sprint over 40 sprints, with the coverage column |
| 4 | 15 s, correct — median 188 points/sprint over 40 sprints |

Attempt 2 is worth reading carefully, because it **exonerates the skill**. The
trace shows the agent selecting `measuring-sprint-velocity` by name in its
reasoning, reading it, issuing SQL in exactly the corrected form the skill
prescribes — `COUNT(CASE WHEN story_points IS NOT NULL THEN 1 END)`, not a
`WHERE` filter — and receiving a SUCCEEDED result. Every step the skill governs
was right. Only the final generation was degenerate, emitting a sentence from
an unrelated corpus after the work was done.

So this is serving-layer instability on `databricks-qwen35-122b-a10b`, not a
property of the menu: roughly one attempt in four either hangs or degenerates,
on a question where skill selection and SQL are correct every time. It matters
for the workshop — a live demo has a real chance of showing a broken answer —
and it belongs to the model endpoint rather than to this change. A simple count
question returned correctly in 13 s throughout.
