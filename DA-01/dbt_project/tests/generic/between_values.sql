{% test between_values(model, column_name, min_value, max_value) %}
{#- Fails for every row outside [min_value, max_value]. NULLs are ignored (add not_null if they matter). -#}
select * from {{ model }}
where {{ column_name }} is not null
  and ({{ column_name }} < {{ min_value }} or {{ column_name }} > {{ max_value }})
{% endtest %}
