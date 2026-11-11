"""Business rules ported from the artifact (schedule, status, critical path, priorities, risks, staffing).

Everything here is pure: it takes plain dict rows plus a `today` date, so it can be tested without a database.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.services.labels import ACTIVITY_STATUS, fd

DAY = timedelta(days=1)
PRIORITY_POINTS = {"Crítica": 8, "Alta": 5, "Media": 2, "Baja": 0}


def nat_key(s: str):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", str(s))]


@dataclass(frozen=True)
class Sched:
    start: date
    end: date  # end == start - 1 day means zero duration
    kind: str  # 'real' | 'conf' | 'est' | 'esc'

    @property
    def zero(self) -> bool:
        return self.end < self.start

    def as_dict(self) -> dict:
        return {"start": self.start, "end": self.end, "kind": self.kind, "zero": self.zero}


# ---------------------------------------------------------------- schedule
def compute_schedule(acts: dict[str, dict], preds: dict[str, list[str]], scenario: dict[str, date | None], today: date) -> dict[str, Sched | None]:
    """Confirmed/estimated dates win. Undated activities get a forward pass from the project's
    scenario start and their predecessors, never before today."""
    memo: dict[str, Sched | None] = {}
    visiting: set[str] = set()

    def calc(aid: str) -> Sched | None:
        if aid in memo:
            return memo[aid]
        if aid in visiting:  # cycle guard; the API also rejects cycles on write
            return None
        visiting.add(aid)
        a = acts[aid]
        r: Sched | None = None
        dur = a.get("duration_days") or 0
        if a["status"] == "completada" and a.get("actual_date"):
            r = Sched(a.get("start_date") or a["actual_date"], a["actual_date"], "real")
        elif a.get("start_date"):
            s = a["start_date"]
            e = a.get("end_date") or (s + (dur - 1) * DAY if dur > 0 else s)
            r = Sched(s, max(e, s), "conf" if a.get("date_confidence") == "confirmada" else "est")
        else:
            scen = scenario.get(a["project_id"])
            es = max(scen, today) if scen else None
            pl = [p for p in preds.get(aid, []) if p in acts]
            ok = True
            for p in pl:
                pa = acts[p]
                if pa["status"] == "completada" and not pa.get("actual_date"):
                    continue
                pr = calc(p)
                if pr is None:
                    ok = False
                    break
                nxt = pr.end + DAY
                es = nxt if es is None else max(es, nxt)
            if ok and es is not None and (pl or scen):
                if a["status"] != "completada":
                    es = max(es, today)
                r = Sched(es, es + (dur - 1) * DAY if dur > 0 else es - DAY, "esc")
        visiting.discard(aid)
        memo[aid] = r
        return r

    return {aid: calc(aid) for aid in acts}


def critical_path(acts: dict[str, dict], preds: dict[str, list[str]], succ: dict[str, list[str]], sched: dict[str, Sched | None]) -> set[str]:
    """Per project: open, schedulable activities with zero slack against the latest finish."""
    crit: set[str] = set()
    by_proj: dict[str, list[str]] = defaultdict(list)
    for aid, a in acts.items():
        if sched.get(aid) and a["status"] != "completada":
            by_proj[a["project_id"]].append(aid)
    for ids in by_proj.values():
        if len(ids) < 2:
            continue
        idset = set(ids)
        end = max(sched[i].end.toordinal() for i in ids)
        order = sorted(ids, key=lambda i: (-sched[i].start.toordinal(), -sched[i].end.toordinal()))
        lf: dict[str, int] = {}
        for i in order:
            v = end
            for j in succ.get(i, []):
                if j in idset and j in lf:
                    ls = lf[j] - (sched[j].end.toordinal() - sched[j].start.toordinal())
                    v = min(v, ls - 1)
            lf[i] = v
        for i in ids:
            has_net = any(j in idset for j in succ.get(i, [])) or any(j in idset for j in preds.get(i, []))
            if has_net and lf[i] - sched[i].end.toordinal() <= 0:
                crit.add(i)
    return crit


def descendants(succ: dict[str, list[str]], acts: dict[str, dict]) -> dict[str, list[str]]:
    """Transitive successors that are still open."""
    out: dict[str, list[str]] = {}
    for aid in acts:
        seen: set[str] = set()
        stack = list(succ.get(aid, []))
        while stack:
            j = stack.pop()
            if j in seen:
                continue
            seen.add(j)
            stack.extend(succ.get(j, []))
        out[aid] = [j for j in seen if j in acts and acts[j]["status"] != "completada"]
    return out


def would_cycle(act_id: str, new_preds: list[str], succ: dict[str, list[str]]) -> bool:
    """True if making `new_preds` predecessors of `act_id` creates a cycle (a pred is already downstream of it)."""
    seen: set[str] = set()
    stack = list(succ.get(act_id, []))
    targets = set(new_preds)
    while stack:
        j = stack.pop()
        if j in targets:
            return True
        if j in seen:
            continue
        seen.add(j)
        stack.extend(succ.get(j, []))
    return False


# ---------------------------------------------------------------- model
class Model:
    """Everything derived from a snapshot of the database at `today`."""

    def __init__(self, *, projects, activities, dependencies, externals, ext_blocks, purchases, assignments, workers, today: date):
        self.today = today
        self.P = {p["id"]: p for p in projects}
        self.A = {a["id"]: a for a in activities}
        self.preds: dict[str, list[str]] = defaultdict(list)
        self.succ: dict[str, list[str]] = defaultdict(list)
        for d in dependencies:
            self.preds[d["activity_id"]].append(d["depends_on_id"])
            self.succ[d["depends_on_id"]].append(d["activity_id"])
        self.externals = {x["id"]: x for x in externals}
        self.ext_by: dict[str, list[dict]] = defaultdict(list)  # activity -> OPEN externals blocking it
        for b in ext_blocks:
            x = self.externals.get(b["external_id"])
            if x and x["status"] != "resuelto":
                self.ext_by[b["activity_id"]].append(x)
        self.ext_blocks = ext_blocks
        self.purchases = purchases
        self.assignments = assignments
        self.workers = {w["id"]: w for w in workers}
        scenario = {p["id"]: p.get("scenario_start") for p in projects}
        self.sched = compute_schedule(self.A, self.preds, scenario, today)
        self.crit = critical_path(self.A, self.preds, self.succ, self.sched)
        self.desc = descendants(self.succ, self.A)

    # ---- helpers
    def pname(self, pid: str) -> str:
        p = self.P.get(pid) or {}
        return p.get("short_name") or p.get("name") or pid

    def pred_acts(self, a: dict) -> list[dict]:
        return [self.A[p] for p in self.preds.get(a["id"], []) if p in self.A]

    def actionable(self, a: dict) -> bool:
        return all(p["status"] == "completada" for p in self.pred_acts(a))

    def dated(self, aid: str) -> Sched | None:
        s = self.sched.get(aid)
        return s if s and s.kind != "esc" else None

    # ---- derived status
    def status(self, a: dict) -> dict:
        def r(code, tone, label):
            return {"code": code, "tone": tone, "label": label}

        if a["status"] == "completada":
            return r("completada", "ok", "Completada")
        if a["status"] == "bloqueada":
            return r("bloqueada", "bad", "Bloqueada")
        if self.ext_by.get(a["id"]):
            return r("bloqueada_tercero", "bad", "Bloqueada por tercero")
        sc = self.dated(a["id"])
        if sc and sc.end < self.today:
            return r("atrasada", "bad", "Atrasada")
        if sc and a["status"] != "proceso" and sc.start < self.today:
            return r("inicio_atrasado", "bad", "Inicio atrasado")
        if a["status"] == "proceso":
            return r("proceso", "warn", "En proceso")
        if sc and (sc.start - self.today).days <= 3:
            return r("proxima", "warn", "Próxima a vencer")
        return r("pendiente", "idle", "Pendiente")

    def is_late(self, a: dict) -> bool:
        return self.status(a)["code"] in ("atrasada", "inicio_atrasado")

    def violation(self, a: dict) -> str | None:
        sc = self.dated(a["id"])
        if not sc:
            return None
        for p in self.pred_acts(a):
            ps = self.dated(p["id"])
            if not ps or p["type"] == "hito":
                continue
            bad = sc.start < ps.end if a["type"] == "hito" else sc.start <= ps.end
            if bad:
                return p["id"]
        return None

    # ---- priorities
    def score(self, a: dict) -> tuple[int, list[tuple[str, str]]]:
        sc, tags = 0, []
        n = len(self.desc.get(a["id"], []))
        s = self.sched.get(a["id"])
        if self.is_late(a):
            sc += 40
            tags.append(("r", self.status(a)["label"]))
        if n:
            sc += 12 + 3 * n
            tags.append(("a", f"Desbloquea {n}"))
        if s and s.kind == "conf" and (s.start - self.today).days <= 14:
            sc += 25
            tags.append(("a", "Fecha comprometida"))
        group = [a] + [self.A[i] for i in self.succ.get(a["id"], []) if i in self.A]
        long_lead = any(x["type"] == "suministro" and (x.get("duration_days") or 0) >= 30 for x in group)
        if long_lead and a["type"] != "suministro":
            sc += 20
            tags.append(("a", "Entrega larga"))
        if a.get("generates_income"):
            sc += 15
            tags.append(("a", "Permite facturar"))
        if a["type"] == "gestion" or a.get("needs_external"):
            sc += 6
            tags.append(("", "Coordinación externa"))
        if a["id"] in self.crit:
            sc += 10
            tags.append(("r", "Ruta crítica"))
        if s and s.kind != "esc" and 0 <= (s.start - self.today).days <= 7:
            sc += 10
        sc += PRIORITY_POINTS.get((self.P.get(a["project_id"]) or {}).get("priority"), 0)
        return sc, tags

    def priorities(self, limit: int | None = 10, project_id: str | None = None) -> list[dict]:
        rows = []
        for a in self.A.values():
            if a["status"] == "completada" or a["type"] in ("suministro", "hito"):
                continue
            if project_id and a["project_id"] != project_id:
                continue
            if not self.actionable(a) or self.ext_by.get(a["id"]):
                continue
            sc, tags = self.score(a)
            rows.append((sc, a, tags))
        rows.sort(key=lambda x: (-x[0], nat_key(x[1]["id"])))
        if limit:
            rows = rows[:limit]
        return [{"activity_id": a["id"], "score": sc, "tags": [{"tone": t, "text": x} for t, x in tags]} for sc, a, tags in rows]

    # ---- staffing
    def staff_needs(self) -> list[dict]:
        out = []
        for p in sorted(self.P.values(), key=lambda p: (p.get("sort_order") or 0, nat_key(p["id"]))):
            rt, rh = p.get("req_technicians") or 0, p.get("req_helpers") or 0
            if not (rt or rh):
                continue
            act = self.A.get(p.get("staffing_activity_id"))
            sc = self.dated(act["id"]) if act else None
            win = (sc.start, max(sc.end, sc.start)) if sc else None
            asg = []
            for x in self.assignments:
                if x["project_id"] != p["id"]:
                    continue
                end = x.get("end_date") or x["start_date"]
                if win is None or (x["start_date"] <= win[1] and end >= win[0]):
                    asg.append(x)
            ids = {x["worker_id"] for x in asg}
            roles = [(self.workers.get(i) or {}).get("role") for i in ids]
            t = sum(1 for r in roles if r in ("tecnico", "supervisor"))
            h = sum(1 for r in roles if r == "ayudante")
            falta = max(0, rt - t) + max(0, rh - h)
            out.append({
                "project_id": p["id"], "required_technicians": rt, "required_helpers": rh,
                "assigned_technicians": t, "assigned_helpers": h, "missing": falta,
                "window": {"start": win[0], "end": win[1]} if win else None,
                "activity_id": act["id"] if act else None,
            })
        return out

    # ---- risks
    def risks(self, project_id: str | None = None) -> list[dict]:
        out: list[dict] = []
        today = self.today

        def add(sev, title, detail, activity_id=None, area=None, pid=None):
            if project_id and pid and pid != project_id:
                return
            out.append({"severity": sev, "title": title, "detail": detail, "activity_id": activity_id, "area": area, "project_id": pid})

        for a in self.A.values():
            st = self.status(a)
            if st["code"] in ("atrasada", "inicio_atrasado"):
                add("bad", f"{a['id']} · {a['description']}", f"{st['label']}. Reprograma o registra el avance real.", a["id"], "actividades", a["project_id"])
        for c in self.purchases:
            if c["status"] in ("cotizacion", "aprobada", "anticipo") and (c.get("lead_time_days") or 0) >= 60:
                add("warn", f"{c['product']} · {c.get('supplier') or 'proveedor por definir'}",
                    f"{c['lead_time_days']} días de entrega ({c.get('lead_time_source') or 'plazo estimado'}) y aún sin orden colocada. "
                    "Cada semana sin anticipo corre la llegada una semana.", None, "compras", c["project_id"])
            nb = c.get("needed_by")
            if nb and nb < today + 14 * DAY and c["status"] not in ("realizada", "recibida"):
                add("bad" if nb < today else "warn", f"Compra: {c['product']}",
                    f"Se necesita {'desde el' if nb < today else 'el'} {fd(nb)} y está en \"{ {'cotizacion': 'Pendiente de cotización', 'aprobada': 'Compra aprobada', 'anticipo': 'Anticipo pendiente'}.get(c['status'], c['status']) }\".",
                    None, "compras", c["project_id"])
        for x in self.externals.values():
            if x["status"] == "esperando" and x.get("requested_on") and (today - x["requested_on"]).days >= 7:
                add("warn", f"{x['counterparty']}: {x['subject']}", f"{(today - x['requested_on']).days} días sin respuesta. Escala o llama.", None, "externos", x["project_id"])
        for a in self.A.values():
            v = self.violation(a)
            if v:
                add("bad", f"{a['id']} inicia antes de terminar {v}", "La fecha planificada viola la dependencia técnica. Ajusta una de las dos fechas.", a["id"], "actividades", a["project_id"])
        for n in self.staff_needs():
            if n["missing"] > 0:
                req = f"{n['required_technicians']} técnicos" + (f" y {n['required_helpers']} ayudantes" if n["required_helpers"] else "")
                asg = f"{n['assigned_technicians']} técnicos" + (f" y {n['assigned_helpers']} ayudantes" if n["required_helpers"] else "")
                add("warn", f"Personal faltante · {self.pname(n['project_id'])}",
                    f"Requiere {req}; asignados {asg}." + ("" if n["window"] else " Ventana de trabajo sin fecha."), None, "personal", n["project_id"])
        return out

    # ---- API shape
    def describe(self, a: dict) -> dict:
        sc = self.sched.get(a["id"])
        return {
            **a,
            "dependencies": list(self.preds.get(a["id"], [])),
            "successors": list(self.succ.get(a["id"], [])),
            "unlocks": len(self.desc.get(a["id"], [])),
            "status_info": self.status(a),
            "sched": sc.as_dict() if sc else None,
            "critical": a["id"] in self.crit,
            "violation": self.violation(a),
            "actionable": self.actionable(a),
            "blocked_by": [
                {"id": x["id"], "counterparty": x["counterparty"], "subject": x["subject"], "status": x["status"]}
                for x in self.ext_by.get(a["id"], [])
            ],
        }


def status_label(code: str) -> str:
    return ACTIVITY_STATUS.get(code, code)
