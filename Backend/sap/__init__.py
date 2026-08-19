"""SAP data access layer for CIRA.

Modules
-------
types_       : shared dataclasses (TableInfo, ColumnInfo, QueryResult, ...)
serialize    : HANA/py -> JSON safe value coercion
sql_guard    : read-only SQL validation + row-limit enforcement + translation
query_spec   : structured, injection-safe SELECT builder (filters/aggregates)
entities     : SAP Business One friendly-name -> table map and value decoding
hana_backend : hdbcli connection pool + full catalog introspection
sim_backend  : offline SQLite sandbox shaped like a real SAP B1 company DB
service_layer: SAP B1 Service Layer (OData v4) client
router       : picks a backend (auto/hana/service/simulator) and exposes the
               single API the agent talks to
"""

from .router import (  # noqa: F401
    describe_table,
    get_active_backend,
    health,
    list_tables,
    run_query,
    run_sql,
    search_schema,
)
