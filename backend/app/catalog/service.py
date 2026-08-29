"""
Catalog service — reads/writes catalog_tables and catalog_columns.

L2.2 implementation (write path).
L3.1 will add read endpoints.
"""
from __future__ import annotations

import json

from app.core.logging import get_logger
from app.core.supabase_client import service_client

logger = get_logger(__name__)


def create_catalog_entry(
    workspace_id: str,
    file_id: str,
    table_name: str,
    row_count: int,
    columns: list[dict],
) -> dict:
    """
    Insert a catalog_tables row + batch of catalog_columns rows.

    Parameters:
      workspace_id : workspace UUID string
      file_id      : files.id UUID string
      table_name   : logical table name (derived from filename, without .csv)
      row_count    : number of data rows
      columns      : list of dicts from schema_inference.infer_schema()

    Returns the inserted catalog_tables row (with id).
    """
    client = service_client()

    # 1. Insert catalog_tables row
    table_result = (
        client
        .table("catalog_tables")
        .insert({
            "workspace_id": workspace_id,
            "file_id": file_id,
            "name": table_name,
            "row_count": row_count,
        })
        .execute()
    )

    if not table_result.data:
        raise RuntimeError("catalog_tables insert returned no data")

    table_row = table_result.data[0]
    table_id = table_row["id"]
    logger.info("catalog_tables created id=%s name=%s", table_id, table_name)

    # 2. Batch-insert catalog_columns
    col_rows = [
        {
            "workspace_id": workspace_id,
            "table_id": table_id,
            "name": col["name"],
            "data_type": col["data_type"],
            "nullable": col["nullable"],
            "sample_values": json.dumps(col["sample_values"]),
        }
        for col in columns
    ]

    if col_rows:
        client.table("catalog_columns").insert(col_rows).execute()
        logger.info("catalog_columns inserted %d columns for table %s", len(col_rows), table_id)

    return table_row


def get_tables(workspace_id: str, jwt: str) -> list[dict]:
    """Return all catalog_tables for a workspace (RLS-enforced)."""
    from app.core.supabase_client import rls_client
    result = (
        rls_client(jwt)
        .table("catalog_tables")
        .select("*")
        .eq("workspace_id", workspace_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


def get_table_with_columns(workspace_id: str, table_id: str, jwt: str) -> dict | None:
    """
    Return a single catalog_table + its columns (RLS-enforced).

    Returns None if the table doesn't exist or isn't visible to the caller.
    """
    from app.core.supabase_client import rls_client
    client = rls_client(jwt)

    table_result = (
        client
        .table("catalog_tables")
        .select("*")
        .eq("id", table_id)
        .eq("workspace_id", workspace_id)
        .execute()
    )
    if not table_result.data:
        return None

    table_row = table_result.data[0]

    cols_result = (
        client
        .table("catalog_columns")
        .select("*")
        .eq("table_id", table_id)
        .order("name")
        .execute()
    )
    table_row["columns"] = cols_result.data
    return table_row
