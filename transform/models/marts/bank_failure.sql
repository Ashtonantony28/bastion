-- Failures with a usable CERT; the label source for the early-warning model (M7).
-- Open-bank assistance transactions (resolution_type = 'ASSISTANCE') are excluded: the bank
-- kept operating and filing, so it is not a failure for labelling purposes.
select *
from {{ ref('stg_fdic_failures') }}
where cert is not null and resolution_type = 'FAILURE'
qualify row_number() over (partition by cert order by fail_date desc) = 1
