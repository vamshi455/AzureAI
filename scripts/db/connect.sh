#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Connect to Azure PostgreSQL Flexible Server via AAD token
# ---------------------------------------------------------------------------
# Usage:
#   source scripts/db/connect.sh          # sets env vars
#   psql                                   # connects to postgres
#   psql -d manufacturing_db               # connects to manufacturing_db
#   psql -d vector_db                      # connects to vector_db
#
# Note: PostgreSQL is VNet-isolated. This only works from within the VNet
#       (e.g., ACI, Container Apps, or Azure Cloud Shell with VNet access).
# ---------------------------------------------------------------------------

export PGHOST=dp-psql-dev.postgres.database.azure.com
export PGUSER=vsingam@mhktechinc.com
export PGPORT=5432
export PGDATABASE=postgres
export PGSSLMODE=require
export PGPASSWORD="$(az account get-access-token --resource https://ossrdbms-aad.database.windows.net --query accessToken --output tsv)"

echo "PostgreSQL env vars set:"
echo "  PGHOST=$PGHOST"
echo "  PGUSER=$PGUSER"
echo "  PGPORT=$PGPORT"
echo "  PGDATABASE=$PGDATABASE"
echo ""
echo "Databases: manufacturing_db, vector_db, sales_db"
echo ""
echo "Quick commands:"
echo "  psql                          # connect to postgres"
echo "  psql -d manufacturing_db      # connect to manufacturing_db"
echo "  psql -d vector_db             # connect to vector_db"
