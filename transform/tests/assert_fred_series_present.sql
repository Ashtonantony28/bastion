-- Every configured FRED series produced observations (catches a renamed or empty download).
with expected as (
    select unnest(['UNRATE', 'CSUSHPINSA', 'GDPC1', 'DGS10', 'DRSFRMACBS']) as series_id
)
select e.series_id
from expected e
left join (select distinct series_id from {{ ref('stg_fred_observations') }}) s using (series_id)
where s.series_id is null
