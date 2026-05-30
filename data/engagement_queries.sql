-- Aggregate-only engagement queries for the MLCompete paper.
-- Produces NO personal data: only counts, distributions, and ratios.
-- Run: psql "host=<db-host> dbname=<db>" -f engagement_queries.sql
\pset footer off
\echo === platform_totals ===
select 'users_registered'        as metric, count(*)::text as value from user_profiles
union all select 'users_on_global_leaderboard', count(*)::text from overall_leaderboard
union all select 'users_with_submissions',      count(distinct user_id)::text from submissions
union all select 'submissions_total',           count(*)::text from submissions
union all select 'submissions_evaluated',        count(*)::text from submissions where status='EVALUATED'
union all select 'problems_total',               count(*)::text from problems
union all select 'problems_published',           count(*)::text from problems where is_draft=false
union all select 'problems_translated_en',       count(*)::text from problems where title_en is not null and title_en<>''
union all select 'competitions_total',           count(*)::text from competitions
union all select 'institutions',                 count(*)::text from institutions
union all select 'distinct_countries',           count(distinct country_code)::text from user_profiles where country_code is not null
union all select 'submission_selection_acks',    count(*)::text from acknowledge_submission_selection_logs;

\echo === submissions_per_user_distribution ===
with s as (select user_id, count(*) c from submissions group by user_id)
select 'n_users' as stat, count(*)::text as value from s
union all select 'mean',   round(avg(c),1)::text from s
union all select 'median', percentile_cont(0.5) within group (order by c)::text from s
union all select 'p90',    percentile_cont(0.9) within group (order by c)::text from s
union all select 'max',    max(c)::text from s;

\echo === onia_stage_participation (distinct platform users per stage) ===
select case when competition_id in (11,12) then 'local'
            when competition_id in (14,15) then 'county'
            when competition_id in (17,18) then 'national' end as stage,
       count(distinct user_id)::text as users
from participants
where competition_id in (11,12,14,15,17,18) and user_id is not null
group by 1 order by 1;

\echo === difficulty_mix_published ===
select coalesce(difficulty,'(unset)') as difficulty, count(*)::text as n
from problems where is_draft=false group by 1 order by 2 desc;

\echo === public_private_leaderboard_populated ===
select 'problem_partial_leaderboard_rows' as metric, count(*)::text as value from problem_partial_leaderboard
union all select 'problem_final_leaderboard_rows', count(*)::text from problem_final_leaderboard
union all select 'competition_final_leaderboard_rows', count(*)::text from competition_final_leaderboard;
