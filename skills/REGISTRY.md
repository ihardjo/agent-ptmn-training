# Skill registry

Every skill in this tier has a row here, and every row has a skill. `uv run
check-skills` enforces the correspondence in both directions.

`Dependencies` lists what a skill's correctness rests on outside its own body.
A change to a listed dependency makes the skills naming it suspect — that is
what the column is for.

## Core

| Skill | Purpose | Owner | Version | Dependencies | Evaluation status |
|---|---|---|---|---|---|
| `computing-target-adherence` | Adherence and breach counts, joining the table to wiki-held targets | ihardjo | 1 | `/wiki/raw/policies/resolution-targets.md`, `/wiki/raw/policies/breach-counting.md`, `/wiki/raw/definitions/duration-basis.md`; columns `cycle_time_hours`, `ticket_type`, `priority`, `closed_at`, `started_at` | not yet evaluated — task 5.4 |
| `auditing-data-quality` | The five planted defect classes and their detecting queries | ihardjo | 1 | columns `created_at`, `closed_at`, `status`, `status_category`, `resolution`, `cycle_time_hours`, `assigned_to` | not yet evaluated — task 5.4 |
| `splitting-planned-unplanned-work` | Planned versus unplanned effort split | ihardjo | 1 | columns `ticket_type`, `sprint`, `Time Spent (hours)`, `cycle_time_hours` | not yet evaluated — task 5.4 |
| `measuring-sprint-velocity` | Story points per sprint, and the null-coverage problem | ihardjo | 1 | columns `story_points`, `sprint`, `status_category` | not yet evaluated — task 5.4 |
| `summarising-root-causes` | Root-cause distribution: the population the field applies to, and whether any cause beats an even split | ihardjo | 1 | column `Custom Field (Root Cause)`, `ticket_type` | not yet evaluated — task 5.4 |
| `escalating-breaches` | Escalation routing for breached tickets, with its trust state | ihardjo | 1 | `/wiki/raw/policies/escalation-matrix.md` (expired); `computing-target-adherence` | not yet evaluated — task 5.4 |

## Distractors

Deliberately over-broad descriptions over honest bodies. Each competes for
selection with a skill that fits better, or promises a capability the data does
not have. Reading one costs a turn; none can produce a wrong answer, because
every body either redirects or declines. Bodies that would contradict the
system prompt's safety rules are prohibited — see `SECURITY-REVIEW.md`.

| Skill | Purpose | Owner | Version | Dependencies | Evaluation status |
|---|---|---|---|---|---|
| `checking-due-dates` | Competes with `computing-target-adherence` on SLA and overdue wording; redirects there | ihardjo | 1 | column `due_date`; `computing-target-adherence` | not yet evaluated — task 5.5 |
| `explaining-ticket-history` | Promises a per-ticket narrative the table has no field for; declines | ihardjo | 1 | column `Custom Field (Root Cause)` | not yet evaluated — task 5.4 |
| `ranking-squad-performance` | Promises a team ranking with no team field; declines and forbids proxies | ihardjo | 1 | columns `component`, `project` | not yet evaluated — task 5.4 |
| `formatting-service-review` | Restates nothing; exists to show what a prompt-duplicating skill costs | ihardjo | 1 | the standing instructions | not yet evaluated — task 5.4 |
