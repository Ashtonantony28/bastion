-- Fed supervisory scenario paths in long form, one row per vintage/scenario/quarter/variable.
select vintage_year, scenario, scenario_name, quarter_end, variable, value
from {{ ref('stg_fed_scenarios') }}
