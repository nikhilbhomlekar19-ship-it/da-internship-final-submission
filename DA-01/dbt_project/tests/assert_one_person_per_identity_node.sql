-- An identifier can belong to only one person.
select node_key, count(*) as n
from {{ source('ml', 'identity_nodes') }}
group by node_key
having count(*) > 1
