-- A failed bank cannot file a Call Report for a quarter that ends after its failure date.
select cert, repdte, fail_date
from {{ ref('bank_quarter') }}
where fail_date is not null and repdte > fail_date
