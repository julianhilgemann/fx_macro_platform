{% macro generate_schema_name(custom_schema_name, node) -%}
    {# Use the per-folder +schema verbatim (staging/intermediate/marts/meta),
       not target.schema + '_' + custom. Spec §4 fixes the warehouse schemas. #}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
