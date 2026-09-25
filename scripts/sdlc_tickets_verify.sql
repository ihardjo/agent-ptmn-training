-- Verifying queries for the planted findings (F*) and detecting queries for the
-- planted defects (D*) in `workshop_ai_platform.default.sdlc_tickets`.
--
-- These are committed so ground truth can be *refreshed* rather than re-derived
-- by hand: regenerate the table with the same seed, re-run these, update the
-- expected values downstream. Magnitudes are recorded in design Decisions 7
-- and 8 of the `replace-ticket-table-with-sdlc-schema` change.
--
-- Each block is separated by `-- @@` so a runner can split and execute them
-- individually. Note the three carried-over custom fields require backticks;
-- the other twenty-one do not.

-- @@ F1a: waiting dominates working -- median wait, in days (target ~19)
SELECT percentile_cont(0.5) WITHIN GROUP (
         ORDER BY (unix_timestamp(started_at) - unix_timestamp(created_at)) / 86400.0
       ) AS median_wait_days
FROM workshop_ai_platform.default.sdlc_tickets
WHERE started_at IS NOT NULL;

-- @@ F1b: median working time, in days (target ~2)
SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY cycle_time_hours) / 24 AS median_cycle_days
FROM workshop_ai_platform.default.sdlc_tickets
WHERE closed_at IS NOT NULL AND cycle_time_hours IS NOT NULL;

-- @@ F2: unplanned work's share of recorded effort (target ~35%)
SELECT
  SUM(CASE WHEN ticket_type IN ('Incident', 'Service Request', 'Change')
           THEN `Time Spent (hours)` ELSE 0 END) / SUM(`Time Spent (hours)`) AS unplanned_effort_share
FROM workshop_ai_platform.default.sdlc_tickets
WHERE `Time Spent (hours)` IS NOT NULL;

-- @@ F3: P2 bugs exceed a five-day working target (target median ~6.5 d)
-- The target itself is NOT in this table. That is deliberate: adherence is
-- unanswerable until a target is supplied from outside the dataset.
SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY cycle_time_hours) / 24 AS p2_bug_median_cycle_days,
       COUNT(*) AS n
FROM workshop_ai_platform.default.sdlc_tickets
WHERE ticket_type = 'Bug' AND priority = 'P2' AND cycle_time_hours IS NOT NULL;

-- @@ F4: estimation carries no signal -- medians by story point should not trend
SELECT story_points,
       COUNT(*) AS n,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY cycle_time_hours) / 24 AS median_cycle_days
FROM workshop_ai_platform.default.sdlc_tickets
WHERE ticket_type = 'Story' AND story_points IS NOT NULL AND cycle_time_hours IS NOT NULL
GROUP BY story_points
ORDER BY story_points;

-- @@ F5: one component dominates defects (target ~40% of Bugs)
SELECT component,
       COUNT(*) AS bugs,
       COUNT(*) / SUM(COUNT(*)) OVER () AS share
FROM workshop_ai_platform.default.sdlc_tickets
WHERE ticket_type = 'Bug'
GROUP BY component
ORDER BY bugs DESC;

-- @@ F6: throughput dips around Idul Fitri (target ~2x working time)
SELECT
  CASE WHEN (DATE(started_at) BETWEEN DATE'2025-03-24' AND DATE'2025-04-07')
         OR (DATE(started_at) BETWEEN DATE'2026-03-14' AND DATE'2026-03-28')
       THEN 'idul_fitri' ELSE 'other' END AS period,
  COUNT(*) AS n,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY cycle_time_hours) / 24 AS median_cycle_days
FROM workshop_ai_platform.default.sdlc_tickets
WHERE cycle_time_hours IS NOT NULL AND started_at IS NOT NULL
GROUP BY period;

-- @@ F7: closures concentrate on one individual -- TRUE share, normalised
-- (target ~22%). `lower(trim(...))` collapses the D5 spelling variants.
-- `lower`, not `initcap`: identities are email addresses, and an address is
-- canonically lower-case, so `initcap` would report every row as a variant.
SELECT lower(trim(regexp_replace(assigned_to, '\\s+', ' '))) AS person,
       COUNT(*) AS closures,
       COUNT(*) / SUM(COUNT(*)) OVER () AS share
FROM workshop_ai_platform.default.sdlc_tickets
WHERE closed_at IS NOT NULL AND assigned_to IS NOT NULL
GROUP BY person
ORDER BY closures DESC
LIMIT 5;

-- @@ F7-naive: the same question asked carelessly. Returns a materially lower
-- share for the same person, with no error. This is the pair that makes D5
-- worth planting -- compare against F7 above.
SELECT assigned_to,
       COUNT(*) AS closures,
       COUNT(*) / SUM(COUNT(*)) OVER () AS share
FROM workshop_ai_platform.default.sdlc_tickets
WHERE closed_at IS NOT NULL AND assigned_to IS NOT NULL
GROUP BY assigned_to
ORDER BY closures DESC
LIMIT 5;

-- @@ D1: closed before created (target 8 rows)
SELECT COUNT(*) AS d1_closed_before_created
FROM workshop_ai_platform.default.sdlc_tickets
WHERE closed_at IS NOT NULL AND closed_at < created_at;

-- @@ D2: a working duration recorded against work that has not closed (target 12)
SELECT COUNT(*) AS d2_duration_on_unclosed
FROM workshop_ai_platform.default.sdlc_tickets
WHERE cycle_time_hours IS NOT NULL AND status NOT IN ('Done', 'Cancelled');

-- @@ D3: closed with no resolution (target 15)
SELECT COUNT(*) AS d3_done_without_resolution
FROM workshop_ai_platform.default.sdlc_tickets
WHERE status = 'Done' AND resolution IS NULL;

-- @@ D4: status_category disagreeing with status (target 5)
SELECT COUNT(*) AS d4_category_mismatch
FROM workshop_ai_platform.default.sdlc_tickets
WHERE status_category <> CASE
        WHEN status = 'New' THEN 'To Do'
        WHEN status IN ('In Progress', 'Blocked', 'In Review') THEN 'In Progress'
        ELSE 'Done' END;

-- @@ D5: spelling variants of one identity (target ~315, 45% of that person's rows)
SELECT COUNT(*) AS d5_identity_variants
FROM workshop_ai_platform.default.sdlc_tickets
WHERE assigned_to IS NOT NULL
  AND assigned_to <> lower(trim(regexp_replace(assigned_to, '\\s+', ' ')));

-- @@ D6: story points on an Incident, which no team estimates (target 10)
SELECT COUNT(*) AS d6_points_on_incident
FROM workshop_ai_platform.default.sdlc_tickets
WHERE ticket_type = 'Incident' AND story_points IS NOT NULL;

-- @@ Absences: confirm no column exists for a target, squad, release, cost, or
-- narrative description. Expect zero rows.
SELECT column_name
FROM workshop_ai_platform.information_schema.columns
WHERE table_schema = 'example' AND table_name = 'sdlc_tickets'
  AND (lower(column_name) LIKE '%target%' OR lower(column_name) LIKE '%sla%'
       OR lower(column_name) LIKE '%squad%' OR lower(column_name) LIKE '%team%'
       OR lower(column_name) LIKE '%release%' OR lower(column_name) LIKE '%version%'
       OR lower(column_name) LIKE '%cost%' OR lower(column_name) LIKE '%description%'
       OR lower(column_name) LIKE '%satisfaction%');
