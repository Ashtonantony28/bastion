select curve_date, tenor, tenor_months, par_yield_pct
from {{ ref('stg_treasury_par_curve') }}
