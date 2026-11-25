-- The label can only be true for a bank that failed, within a year after the report date.
select cert, repdte, fail_date
from {{ ref('ews_features') }}
where fail_within_4q and (fail_date is null or fail_date <= repdte or fail_date > repdte + interval 1 year)
