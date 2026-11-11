"""Request bodies. Responses are plain dicts (FastAPI serializes dates, UUIDs and Decimals)."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, create_model

CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]*$")


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def partial(model: type[BaseModel], name: str | None = None) -> type[BaseModel]:
    """Same model with every field optional (PATCH bodies)."""
    fields = {n: (Optional[f.annotation], None) for n, f in model.model_fields.items()}
    return create_model(name or model.__name__ + "Patch", __base__=Body, **fields)


# ---- auth
class LoginIn(Body):
    email: str
    password: str


# ---- projects
class ProjectIn(Body):
    id: str
    name: str
    short_name: Optional[str] = None
    client: Optional[str] = None
    location: Optional[str] = None
    scope: Optional[str] = None
    status: Literal["Planificación", "En ejecución", "En espera", "Detenido", "Cerrado"] = "Planificación"
    priority: Literal["Crítica", "Alta", "Media", "Baja"] = "Media"
    progress_pct: Optional[Decimal] = Field(None, ge=0, le=100)
    scenario_start: Optional[date] = None
    req_technicians: Optional[int] = Field(None, ge=0)
    req_helpers: Optional[int] = Field(None, ge=0)
    staffing_activity_id: Optional[str] = None
    drive_invoices_folder: Optional[str] = None
    drive_receipts_folder: Optional[str] = None
    exchange_rate: Optional[Decimal] = Field(None, gt=0)
    notes: Optional[str] = None
    sort_order: int = 0

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        v = v.upper()
        if not CODE_RE.match(v):
            raise ValueError("El código solo admite letras, números y guiones.")
        return v


ProjectPatch = partial(ProjectIn, "ProjectPatch")


# ---- activities
ActivityType = Literal["gestion", "documento", "compra", "suministro", "ejecucion", "hito"]
ActivityStatus = Literal["pendiente", "proceso", "completada", "bloqueada"]
Confidence = Literal["pendiente", "estimada", "confirmada"]
Front = Literal["civil", "electrica", "admin"]


class ActivityIn(Body):
    id: str
    project_id: str
    description: str = Field(min_length=1)
    wbs: Optional[str] = None
    type: ActivityType = "ejecucion"
    front: Optional[Front] = None
    owner: Optional[str] = None
    status: ActivityStatus = "pendiente"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    duration_days: Optional[int] = Field(None, ge=0)
    date_confidence: Confidence = "pendiente"
    actual_date: Optional[date] = None
    next_action: Optional[str] = None
    remarks: Optional[str] = None
    generates_income: bool = False
    needs_external: bool = False
    dependencies: list[str] = []

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        v = v.upper()
        if not CODE_RE.match(v):
            raise ValueError("El código solo admite letras, números y guiones.")
        return v

    @field_validator("dependencies")
    @classmethod
    def _deps(cls, v: list[str]) -> list[str]:
        return sorted({d.strip().upper() for d in v if d.strip()})


ActivityPatch = partial(ActivityIn, "ActivityPatch")


class NoteIn(Body):
    body: str = Field(min_length=1, max_length=2000)


class CompleteIn(Body):
    actual_date: Optional[date] = None


# ---- purchases
PurchaseStatus = Literal["cotizacion", "aprobada", "anticipo", "realizada", "recibida"]
Currency = Literal["GTQ", "USD"]


class PurchaseIn(Body):
    project_id: str
    product: str = Field(min_length=1)
    status: PurchaseStatus = "cotizacion"
    supplier: Optional[str] = None
    invoice_mode: Optional[Literal["con", "sin"]] = None
    invoice_no: Optional[str] = None
    currency: Currency = "GTQ"
    total_amount: Optional[Decimal] = Field(None, ge=0)
    advance_required: Optional[Decimal] = Field(None, ge=0)
    advance_paid: Optional[Decimal] = Field(None, ge=0)
    needed_by: Optional[date] = None
    ordered_on: Optional[date] = None
    lead_time_days: Optional[int] = Field(None, ge=0)
    lead_time_source: Optional[str] = None
    received_on: Optional[date] = None
    budget_line_id: Optional[str] = None
    activity_id: Optional[str] = None
    notes: Optional[str] = None


PurchasePatch = partial(PurchaseIn, "PurchasePatch")


# ---- budget
class BudgetLineIn(Body):
    code: str = Field(min_length=1)
    phase: str = "Otros"
    activity: Optional[str] = None
    material: Optional[str] = None
    specification: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    unit_price: Optional[Decimal] = None
    total: Optional[Decimal] = None
    remarks: Optional[str] = None
    planned_start: Optional[date] = None
    planned_end: Optional[date] = None
    completed: bool = False


BudgetLinePatch = partial(BudgetLineIn, "BudgetLinePatch")


# ---- per diem
class PerDiemIn(Body):
    project_id: str
    entry_date: date
    kind: Literal["anticipo", "gasto"] = "gasto"
    person: str = Field(min_length=1)
    amount: Decimal = Field(gt=0)
    category: Optional[Literal["alimentacion", "hospedaje", "combustible", "peaje", "transporte", "otros"]] = None
    receipt_type: Optional[Literal["factura", "recibo", "ninguno"]] = None
    document_no: Optional[str] = None
    status: Literal["pendiente", "liquidado", "reembolsado"] = "pendiente"
    detail: Optional[str] = None
    budget_line_id: Optional[str] = None
    activity_id: Optional[str] = None
    notes: Optional[str] = None


PerDiemPatch = partial(PerDiemIn, "PerDiemPatch")


# ---- billing
class BillingIn(Body):
    project_id: str
    concept: str = Field(min_length=1)
    status: Literal["por_facturar", "facturado", "cobrado"] = "por_facturar"
    scope: Optional[str] = None
    amount: Optional[Decimal] = Field(None, ge=0)
    currency: Currency = "GTQ"
    billing_date: Optional[date] = None
    notes: Optional[str] = None


BillingPatch = partial(BillingIn, "BillingPatch")


# ---- externals
class ExternalIn(Body):
    project_id: str
    counterparty: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    status: Literal["por_solicitar", "esperando", "resuelto"] = "por_solicitar"
    channel: Optional[Literal["correo", "llamada", "whatsapp", "reunion", "tramite"]] = None
    requested_on: Optional[date] = None
    follow_up_on: Optional[date] = None
    contact: Optional[str] = None
    response: Optional[str] = None
    blocks: list[str] = []

    @field_validator("blocks")
    @classmethod
    def _blocks(cls, v: list[str]) -> list[str]:
        return sorted({d.strip().upper() for d in v if d.strip()})


ExternalPatch = partial(ExternalIn, "ExternalPatch")


class ResolveIn(Body):
    response: Optional[str] = None


# ---- staff
class WorkerIn(Body):
    name: str = Field(min_length=1)
    role: Literal["tecnico", "ayudante", "supervisor", "otro"] = "tecnico"
    phone: Optional[str] = None
    specialty: Optional[str] = None
    active: bool = True
    notes: Optional[str] = None


WorkerPatch = partial(WorkerIn, "WorkerPatch")


class AssignmentIn(Body):
    worker_id: str
    project_id: str
    start_date: date
    end_date: Optional[date] = None
    activity_id: Optional[str] = None
    notes: Optional[str] = None


AssignmentPatch = partial(AssignmentIn, "AssignmentPatch")


# ---- reports
class WhatsAppIn(Body):
    project_id: Optional[str] = None
    audience: Literal["jefe", "cliente"] = "jefe"
    period: Literal["hoy", "semana", "mes"] = "semana"
