// Spanish labels for every enum the API uses. Components never hard-code these.
export type Opt = [string, string]

export const EST_ACT: Opt[] = [['pendiente', 'Pendiente'], ['proceso', 'En proceso'], ['completada', 'Completada'], ['bloqueada', 'Bloqueada']]
export const CONF: Opt[] = [['pendiente', 'Pendiente de confirmar'], ['estimada', 'Estimada'], ['confirmada', 'Confirmada']]
export const TIPOS: Opt[] = [
  ['gestion', 'Gestión / coordinación'], ['documento', 'Documento / ingeniería'], ['compra', 'Compra / pago'],
  ['suministro', 'Fabricación / entrega de proveedor'], ['ejecucion', 'Ejecución en campo'], ['hito', 'Hito'],
]
export const FRENTES: Opt[] = [['civil', 'Obra civil'], ['electrica', 'Obra eléctrica'], ['admin', 'Procesos administrativos']]
export const EST_COMP: Opt[] = [
  ['cotizacion', 'Pendiente de cotización'], ['aprobada', 'Compra aprobada'], ['anticipo', 'Anticipo pendiente'],
  ['realizada', 'Compra realizada'], ['recibida', 'Material recibido'],
]
export const FACT: Opt[] = [['con', 'Con factura'], ['sin', 'Sin factura']]
export const EST_EXT: Opt[] = [['por_solicitar', 'Por solicitar'], ['esperando', 'Esperando respuesta'], ['resuelto', 'Resuelto']]
export const EST_COB: Opt[] = [['por_facturar', 'Por facturar / solicitar'], ['facturado', 'Facturado'], ['cobrado', 'Cobrado']]
export const CANALES: Opt[] = [['correo', 'Correo'], ['llamada', 'Llamada'], ['whatsapp', 'WhatsApp'], ['reunion', 'Reunión'], ['tramite', 'Trámite']]
export const PRIOS = ['Crítica', 'Alta', 'Media', 'Baja']
export const EST_PROY = ['Planificación', 'En ejecución', 'En espera', 'Detenido', 'Cerrado']
export const ROLES: Opt[] = [['tecnico', 'Técnico'], ['ayudante', 'Ayudante'], ['supervisor', 'Supervisor'], ['otro', 'Otro']]
export const MONEDAS: Opt[] = [['GTQ', 'Quetzales (Q)'], ['USD', 'Dólares (US$)']]
export const CAT_V: Opt[] = [
  ['alimentacion', 'Alimentación'], ['hospedaje', 'Hospedaje'], ['combustible', 'Combustible'],
  ['peaje', 'Peajes y parqueos'], ['transporte', 'Transporte / bus / taxi'], ['otros', 'Otros'],
]
export const COMP_V: Opt[] = [['factura', 'Factura'], ['recibo', 'Recibo'], ['ninguno', 'Sin comprobante']]
export const EST_V: Opt[] = [['pendiente', 'Pendiente de liquidar'], ['liquidado', 'Liquidado'], ['reembolsado', 'Reembolsado']]

export const lab = (arr: Opt[], v?: string | null) => (arr.find((x) => x[0] === v) || [, v || '—'])[1] as string
