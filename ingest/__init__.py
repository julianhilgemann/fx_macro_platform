"""Ingestion: fetch -> immutable raw JSON -> parse -> DuckDB raw table.

Plain Python. dbt does not fetch; its source is the already-landed raw table.
"""
