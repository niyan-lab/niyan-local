#!/bin/bash
# Runs once on first Postgres volume init.
# Creates the Niyan control-plane DB plus the vector DB + pgvector.
set -euo pipefail

CONFIG_DB="${POSTGRES_CONFIG_DB:-niyan}"
VECTOR_DB="${POSTGRES_VECTOR_DB:-niyan_vectors}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "postgres" <<-EOSQL
SELECT 'CREATE DATABASE ${CONFIG_DB}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${CONFIG_DB}')\gexec
SELECT 'CREATE DATABASE ${VECTOR_DB}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${VECTOR_DB}')\gexec
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$VECTOR_DB" <<-EOSQL
CREATE EXTENSION IF NOT EXISTS vector;
EOSQL
