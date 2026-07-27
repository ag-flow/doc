-- 0048_datasets.sql
-- Datasets tabulaires requêtables (fondation).
--
-- Modèle EAV en miroir de functional_type -> properties_defs -> properties_values :
--   - dataset            : le tableau, porté par un workspace (unité d'isolation).
--   - dataset_column     : la FORME (colonnes typées) — c'est de la donnée, pas du schéma.
--   - dataset_row        : une ligne du tableau.
--   - dataset_cell       : une cellule (row x column) avec OMBRES TYPÉES
--                          (num_value / date_value / bool_value) pour un filtrage indexé.
--   - dataset_reference  : rattachement d'un dataset à un document.
--
-- Additive et idempotente (CREATE TABLE / INDEX IF NOT EXISTS). Cascade sur la
-- suppression du dataset (colonnes, lignes, cellules, références) et du workspace :
-- aucune ligne orpheline.
CREATE TABLE IF NOT EXISTS dataset (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_technical_key uuid NOT NULL
        REFERENCES workspace(workspace_technical_key) ON DELETE CASCADE,
    slug text NOT NULL,
    label text NOT NULL,
    created_by uuid REFERENCES app_user(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_technical_key, slug)
);

CREATE TABLE IF NOT EXISTS dataset_column (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_ref uuid NOT NULL REFERENCES dataset(id) ON DELETE CASCADE,
    slug text NOT NULL,
    label text NOT NULL,
    type text NOT NULL CHECK (type IN ('text', 'int', 'float', 'date', 'bool', 'url')),
    position integer NOT NULL DEFAULT 0,
    required boolean NOT NULL DEFAULT false,
    UNIQUE (dataset_ref, slug)
);

CREATE TABLE IF NOT EXISTS dataset_row (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_ref uuid NOT NULL REFERENCES dataset(id) ON DELETE CASCADE,
    position integer NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS dataset_cell (
    row_ref uuid NOT NULL REFERENCES dataset_row(id) ON DELETE CASCADE,
    column_ref uuid NOT NULL REFERENCES dataset_column(id) ON DELETE CASCADE,
    value text,
    num_value numeric,
    date_value date,
    bool_value boolean,
    PRIMARY KEY (row_ref, column_ref)
);

CREATE TABLE IF NOT EXISTS dataset_reference (
    dataset_ref uuid NOT NULL REFERENCES dataset(id) ON DELETE CASCADE,
    document_ref uuid NOT NULL REFERENCES document(doc_technical_key) ON DELETE CASCADE,
    workspace_technical_key uuid NOT NULL,
    PRIMARY KEY (dataset_ref, document_ref)
);

-- Index de requêtage par cellule (ombres typées) + traversées
CREATE INDEX IF NOT EXISTS dataset_cell_col_num_idx  ON dataset_cell (column_ref, num_value)  WHERE num_value IS NOT NULL;
CREATE INDEX IF NOT EXISTS dataset_cell_col_date_idx ON dataset_cell (column_ref, date_value) WHERE date_value IS NOT NULL;
CREATE INDEX IF NOT EXISTS dataset_cell_col_val_idx  ON dataset_cell (column_ref, value)      WHERE value IS NOT NULL;
CREATE INDEX IF NOT EXISTS dataset_cell_row_idx      ON dataset_cell (row_ref);
CREATE INDEX IF NOT EXISTS dataset_column_ds_pos_idx ON dataset_column (dataset_ref, position);
CREATE INDEX IF NOT EXISTS dataset_row_ds_pos_idx    ON dataset_row (dataset_ref, position);
CREATE INDEX IF NOT EXISTS dataset_reference_doc_idx ON dataset_reference (document_ref);
