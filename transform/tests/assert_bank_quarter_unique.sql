select cert, repdte, count(*) as n
from {{ ref('bank_quarter') }}
group by all
having count(*) > 1
