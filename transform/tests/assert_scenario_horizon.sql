-- DFAST projections cover 13 quarters (9-quarter planning horizon plus jump-off quarters).
select vintage_year, scenario, variable, count(*) as n
from {{ ref('scenario_paths') }}
where scenario in ('baseline', 'severely_adverse')
group by all
having count(*) <> 13
