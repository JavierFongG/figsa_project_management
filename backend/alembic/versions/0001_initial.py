"""Initial schema

Revision ID: 0001
Revises:
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TABLE app_user (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text UNIQUE NOT NULL,
  name text NOT NULL,
  password_hash text NOT NULL,
  role text NOT NULL DEFAULT 'viewer' CHECK (role IN ('viewer','editor')),
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE project (
  id text PRIMARY KEY CHECK (id ~ '^[A-Z0-9][A-Z0-9-]*$'),
  name text NOT NULL,
  short_name text,
  client text,
  location text,
  scope text,
  status text NOT NULL DEFAULT 'Planificación'
    CHECK (status IN ('Planificación','En ejecución','En espera','Detenido','Cerrado')),
  priority text NOT NULL DEFAULT 'Media' CHECK (priority IN ('Crítica','Alta','Media','Baja')),
  progress_pct numeric(5,2) CHECK (progress_pct BETWEEN 0 AND 100),
  scenario_start date,
  req_technicians int CHECK (req_technicians >= 0),
  req_helpers int CHECK (req_helpers >= 0),
  staffing_activity_id text,
  drive_invoices_folder text,
  drive_receipts_folder text,
  exchange_rate numeric(10,4) CHECK (exchange_rate > 0),
  notes text,
  sort_order int NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE activity (
  id text PRIMARY KEY CHECK (id ~ '^[A-Z0-9][A-Z0-9-]*$'),
  project_id text NOT NULL REFERENCES project(id),
  wbs text,
  description text NOT NULL,
  type text NOT NULL DEFAULT 'ejecucion'
    CHECK (type IN ('gestion','documento','compra','suministro','ejecucion','hito')),
  front text CHECK (front IN ('civil','electrica','admin')),
  owner text,
  status text NOT NULL DEFAULT 'pendiente'
    CHECK (status IN ('pendiente','proceso','completada','bloqueada')),
  start_date date,
  end_date date,
  duration_days int CHECK (duration_days >= 0),
  date_confidence text NOT NULL DEFAULT 'pendiente'
    CHECK (date_confidence IN ('pendiente','estimada','confirmada')),
  actual_date date,
  baseline_start date,
  baseline_end date,
  next_action text,
  remarks text,
  generates_income boolean NOT NULL DEFAULT false,
  needs_external boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date)
);
ALTER TABLE project ADD FOREIGN KEY (staffing_activity_id) REFERENCES activity(id) ON DELETE SET NULL;
CREATE INDEX activity_project_status_idx ON activity (project_id, status);
CREATE INDEX activity_dates_idx ON activity (start_date, end_date);

CREATE TABLE activity_dependency (
  activity_id text NOT NULL REFERENCES activity(id) ON DELETE CASCADE,
  depends_on_id text NOT NULL REFERENCES activity(id) ON DELETE CASCADE,
  PRIMARY KEY (activity_id, depends_on_id),
  CHECK (activity_id <> depends_on_id)
);
CREATE INDEX activity_dependency_rev_idx ON activity_dependency (depends_on_id);

CREATE TABLE activity_note (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  activity_id text NOT NULL REFERENCES activity(id) ON DELETE CASCADE,
  body text NOT NULL,
  author_id uuid REFERENCES app_user(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX activity_note_idx ON activity_note (activity_id, created_at DESC);

CREATE TABLE budget_line (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id text NOT NULL REFERENCES project(id),
  code text NOT NULL,
  phase text NOT NULL DEFAULT 'Otros',
  activity text NOT NULL,
  material text,
  specification text,
  quantity numeric(14,3),
  unit text,
  unit_price numeric(14,2),
  total numeric(14,2),
  review_note text,
  remarks text,
  planned_start date,
  planned_end date,
  completed boolean NOT NULL DEFAULT false,
  completed_on date,
  sort_order double precision NOT NULL DEFAULT 0,
  source text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (project_id, id)
);
CREATE INDEX budget_line_project_idx ON budget_line (project_id, sort_order);

CREATE TABLE purchase (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  legacy_id text UNIQUE,
  project_id text NOT NULL REFERENCES project(id),
  status text NOT NULL DEFAULT 'cotizacion'
    CHECK (status IN ('cotizacion','aprobada','anticipo','realizada','recibida')),
  product text NOT NULL,
  supplier text,
  invoice_mode text CHECK (invoice_mode IN ('con','sin')),
  invoice_no text,
  currency text NOT NULL DEFAULT 'GTQ' CHECK (currency IN ('GTQ','USD')),
  total_amount numeric(14,2),
  advance_required numeric(14,2),
  advance_paid numeric(14,2),
  needed_by date,
  ordered_on date,
  lead_time_days int CHECK (lead_time_days >= 0),
  lead_time_source text,
  received_on date,
  completed_on date,
  budget_line_id uuid,
  activity_id text REFERENCES activity(id) ON DELETE SET NULL,
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (project_id, budget_line_id) REFERENCES budget_line (project_id, id)
    ON DELETE SET NULL (budget_line_id)
);
CREATE INDEX purchase_project_status_idx ON purchase (project_id, status);
CREATE INDEX purchase_budget_line_idx ON purchase (budget_line_id);

CREATE TABLE purchase_file (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  purchase_id uuid NOT NULL REFERENCES purchase(id) ON DELETE CASCADE,
  kind text NOT NULL CHECK (kind IN ('factura','comprobante')),
  filename text NOT NULL,
  size_bytes bigint,
  mime_type text,
  drive_id text,
  url text,
  uploaded_by uuid REFERENCES app_user(id) ON DELETE SET NULL,
  uploaded_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (purchase_id, kind)
);

-- The single per-diem ledger. Expenses count against the budget line they are tagged with.
CREATE TABLE per_diem (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  legacy_id text UNIQUE,
  project_id text NOT NULL REFERENCES project(id),
  entry_date date NOT NULL,
  kind text NOT NULL DEFAULT 'gasto' CHECK (kind IN ('anticipo','gasto')),
  person text NOT NULL,
  amount numeric(14,2) NOT NULL CHECK (amount > 0),
  category text CHECK (category IN ('alimentacion','hospedaje','combustible','peaje','transporte','otros')),
  receipt_type text CHECK (receipt_type IN ('factura','recibo','ninguno')),
  document_no text,
  status text NOT NULL DEFAULT 'pendiente' CHECK (status IN ('pendiente','liquidado','reembolsado')),
  detail text,
  budget_line_id uuid,
  activity_id text REFERENCES activity(id) ON DELETE SET NULL,
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (project_id, budget_line_id) REFERENCES budget_line (project_id, id)
    ON DELETE SET NULL (budget_line_id)
);
CREATE INDEX per_diem_project_idx ON per_diem (project_id, entry_date);

CREATE TABLE billing (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id text NOT NULL REFERENCES project(id),
  status text NOT NULL DEFAULT 'por_facturar' CHECK (status IN ('por_facturar','facturado','cobrado')),
  concept text NOT NULL,
  scope text,
  amount numeric(14,2),
  currency text NOT NULL DEFAULT 'GTQ' CHECK (currency IN ('GTQ','USD')),
  billing_date date,
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE external_item (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id text NOT NULL REFERENCES project(id),
  status text NOT NULL DEFAULT 'por_solicitar' CHECK (status IN ('por_solicitar','esperando','resuelto')),
  counterparty text NOT NULL,
  channel text CHECK (channel IN ('correo','llamada','whatsapp','reunion','tramite')),
  subject text NOT NULL,
  requested_on date,
  follow_up_on date,
  contact text,
  response text,
  resolved_on date,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE external_item_blocks (
  external_id uuid NOT NULL REFERENCES external_item(id) ON DELETE CASCADE,
  activity_id text NOT NULL REFERENCES activity(id) ON DELETE CASCADE,
  PRIMARY KEY (external_id, activity_id)
);

CREATE TABLE worker (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  role text NOT NULL DEFAULT 'tecnico' CHECK (role IN ('tecnico','ayudante','supervisor','otro')),
  phone text,
  specialty text,
  active boolean NOT NULL DEFAULT true,
  notes text
);
CREATE TABLE assignment (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  worker_id uuid NOT NULL REFERENCES worker(id),
  project_id text NOT NULL REFERENCES project(id),
  activity_id text REFERENCES activity(id) ON DELETE SET NULL,
  start_date date NOT NULL,
  end_date date,
  notes text,
  CHECK (end_date IS NULL OR end_date >= start_date),
  CONSTRAINT assignment_no_overlap EXCLUDE USING gist (
    worker_id WITH =,
    daterange(start_date, COALESCE(end_date, start_date), '[]') WITH &&)
);

CREATE TABLE audit_log (
  id bigserial PRIMARY KEY,
  ts timestamptz NOT NULL DEFAULT now(),
  user_id uuid REFERENCES app_user(id) ON DELETE SET NULL,
  entity text NOT NULL,
  entity_id text NOT NULL,
  project_id text,
  field text NOT NULL,
  before_value text,
  after_value text
);
CREATE INDEX audit_entity_idx ON audit_log (entity, entity_id, ts DESC);
CREATE INDEX audit_project_idx ON audit_log (project_id, ts DESC);

CREATE TRIGGER project_touch BEFORE UPDATE ON project FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER activity_touch BEFORE UPDATE ON activity FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER budget_line_touch BEFORE UPDATE ON budget_line FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER purchase_touch BEFORE UPDATE ON purchase FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER per_diem_touch BEFORE UPDATE ON per_diem FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER billing_touch BEFORE UPDATE ON billing FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER external_item_touch BEFORE UPDATE ON external_item FOR EACH ROW EXECUTE FUNCTION set_updated_at();
"""

DROP = """
DROP TABLE IF EXISTS audit_log, assignment, worker, external_item_blocks, external_item, billing,
  per_diem, purchase_file, purchase, budget_line, activity_note, activity_dependency, activity, project, app_user CASCADE;
DROP FUNCTION IF EXISTS set_updated_at();
"""


def upgrade() -> None:
    op.execute(SCHEMA)


def downgrade() -> None:
    op.execute(DROP)
