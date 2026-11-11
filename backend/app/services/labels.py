"""Spanish labels for enum codes (mirrors the artifact's EST_ACT, TIPOS, EST_COMP ... arrays)."""

ACTIVITY_STATUS = {"pendiente": "Pendiente", "proceso": "En proceso", "completada": "Completada", "bloqueada": "Bloqueada"}
CONFIDENCE = {"pendiente": "Pendiente de confirmar", "estimada": "Estimada", "confirmada": "Confirmada"}
ACTIVITY_TYPE = {
    "gestion": "Gestión / coordinación", "documento": "Documento / ingeniería", "compra": "Compra / pago",
    "suministro": "Fabricación / entrega de proveedor", "ejecucion": "Ejecución en campo", "hito": "Hito",
}
PURCHASE_STATUS = {
    "cotizacion": "Pendiente de cotización", "aprobada": "Compra aprobada", "anticipo": "Anticipo pendiente",
    "realizada": "Compra realizada", "recibida": "Material recibido",
}
INVOICE = {"con": "Con factura", "sin": "Sin factura"}
EXTERNAL_STATUS = {"por_solicitar": "Por solicitar", "esperando": "Esperando respuesta", "resuelto": "Resuelto"}
BILLING_STATUS = {"por_facturar": "Por facturar / solicitar", "facturado": "Facturado", "cobrado": "Cobrado"}
FRONT = {"civil": "Obra civil", "electrica": "Obra eléctrica", "admin": "Procesos administrativos"}
WORKER_ROLE = {"tecnico": "Técnico", "ayudante": "Ayudante", "supervisor": "Supervisor", "otro": "Otro"}
PER_DIEM_CATEGORY = {
    "alimentacion": "Alimentación", "hospedaje": "Hospedaje", "combustible": "Combustible",
    "peaje": "Peajes y parqueos", "transporte": "Transporte / bus / taxi", "otros": "Otros",
}
RECEIPT = {"factura": "Factura", "recibo": "Recibo", "ninguno": "Sin comprobante"}
PER_DIEM_STATUS = {"pendiente": "Pendiente de liquidar", "liquidado": "Liquidado", "reembolsado": "Reembolsado"}

ALL = {
    **ACTIVITY_STATUS, **CONFIDENCE, **ACTIVITY_TYPE, **PURCHASE_STATUS, **INVOICE, **EXTERNAL_STATUS,
    **BILLING_STATUS, **FRONT, **WORKER_ROLE, **PER_DIEM_CATEGORY, **RECEIPT, **PER_DIEM_STATUS,
}


def label(value):
    """Human label for audit entries; unknown values are returned as plain text."""
    if value is None:
        return None
    return ALL.get(str(value), str(value))


MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
MONTHS_LONG = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def fd(d):
    """'5 nov' style date used in reports."""
    return "" if d is None else f"{d.day} {MONTHS[d.month - 1]}"


def fdy(d):
    return "" if d is None else f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def money(v, currency="GTQ"):
    if v is None:
        return None
    return ("US$ " if currency == "USD" else "Q ") + f"{float(v):,.2f}"
