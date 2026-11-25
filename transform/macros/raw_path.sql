{# Absolute glob under the configured raw root, e.g. raw_path('fred/*.csv'). #}
{% macro raw_path(glob) -%}
'{{ var("raw_root") }}/{{ glob }}'
{%- endmacro %}
