"""Computed screens: portfolio cards, "Mis tareas" groups, text reports and the WhatsApp template."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.services import finance
from app.services.labels import EXTERNAL_STATUS, FRONT, MONTHS_LONG, fd, fdy, money
from app.services.rules import DAY, Model, nat_key

FAR = 10**9


# ------------------------------------------------------------------ portfolio
def portfolio(m: Model) -> dict:
    A = list(m.A.values())
    open_ = [a for a in A if a["status"] != "completada"]
    late = [a for a in open_ if m.is_late(a)]
    blocked = [a for a in open_ if m.status(a)["code"] in ("bloqueada", "bloqueada_tercero")]
    open_ext = [x for x in m.externals.values() if x["status"] != "resuelto"]
    blocking_ext = [x for x in open_ext if any(b["external_id"] == x["id"] for b in m.ext_blocks)]
    undated = [a for a in open_ if m.dated(a["id"]) is None]
    top = {}
    for pr in m.priorities(limit=None):
        top.setdefault(m.A[pr["activity_id"]]["project_id"], pr["activity_id"])

    cards = []
    for p in sorted(m.P.values(), key=lambda p: (p.get("sort_order") or 0, nat_key(p["id"]))):
        acts = [a for a in A if a["project_id"] == p["id"]]
        op = [a for a in acts if a["status"] != "completada"]
        crit = [a for a in op if a["id"] in m.crit or len(m.desc.get(a["id"], [])) >= 3]
        comp = [c for c in m.purchases if c["project_id"] == p["id"] and c["status"] not in ("realizada", "recibida")]
        ext = [x for x in blocking_ext if x["project_id"] == p["id"]]
        hitos = sorted(
            (a for a in op if a["type"] == "hito"),
            key=lambda a: (m.dated(a["id"]).start.toordinal() if m.dated(a["id"]) else FAR, nat_key(a["id"])),
        )
        nxt = sorted(
            ((a, m.dated(a["id"])) for a in op if m.dated(a["id"]) and m.dated(a["id"]).end >= m.today),
            key=lambda x: x[1].start,
        )
        tones = [m.status(a)["tone"] for a in op]
        worst = "bad" if "bad" in tones else "warn" if "warn" in tones else "idle" if op else "ok"
        h = hitos[0] if hitos else None
        hs = m.dated(h["id"]) if h else None
        cards.append({
            **p,
            "total_activities": len(acts), "done_activities": len(acts) - len(op), "open_activities": len(op),
            "critical_count": len(crit), "pending_purchases": len(comp), "blocking_externals": len(ext),
            "blocked_by": sorted({x["counterparty"] for x in ext}),
            "next_milestone": {"id": h["id"], "description": h["description"], "date": hs.start if hs else None} if h else None,
            "next_activity": {"id": nxt[0][0]["id"], "start": nxt[0][1].start} if nxt else None,
            "health": worst,
            "next_step": {"id": top[p["id"]], "description": m.A[top[p["id"]]]["description"]} if p["id"] in top else None,
        })
    return {
        "today": m.today,
        "kpis": {
            "projects": len(m.P), "open_activities": len(open_), "late": len(late), "blocked": len(blocked),
            "purchases_unreceived": sum(1 for c in m.purchases if c["status"] != "recibida"),
            "externals_open": len(open_ext), "undated": len(undated),
        },
        "counters": {"tasks_late": len(late), "externals_blocking": len(blocking_ext)},
        "projects": cards,
    }


# ------------------------------------------------------------------ my tasks
def _item(m: Model, a: dict, notes: dict) -> dict:
    d = m.describe(a)
    st = notes.get(a["id"]) or {"count": 0, "last": None}
    d["last_note"], d["note_count"] = st["last"], st["count"]
    d["score"], tags = m.score(a)
    d["tags"] = [{"tone": t, "text": x} for t, x in tags]
    return d


def _front_ok(a: dict, front: str | None) -> bool:
    if not front or front == "ALL":
        return True
    return a.get("front") in ("civil", "electrica") if front == "obra" else a.get("front") == "admin"


def task_groups(m: Model, notes: dict, days: int = 7, project_id: str | None = None, front: str | None = None) -> dict:
    today = m.today
    use_front = bool(project_id and any(a.get("front") for a in m.A.values() if a["project_id"] == project_id))

    def pf(a):
        return (not project_id or a["project_id"] == project_id) and (not use_front or _front_ok(a, front))

    def start_key(a):
        s = m.dated(a["id"])
        return s.start.toordinal() if s else FAR

    open_ = [a for a in m.A.values() if a["status"] != "completada" and a["type"] != "hito" and pf(a)]
    open_.sort(key=lambda a: (start_key(a), -m.score(a)[0], nat_key(a["id"])))
    used: set[str] = set()

    def take(f):
        r = [a for a in open_ if a["id"] not in used and f(a)]
        used.update(a["id"] for a in r)
        return r

    def in_today(a):
        s = m.dated(a["id"])
        return bool(s and s.start <= today <= max(s.end, s.start))

    def upcoming(a):
        s = m.dated(a["id"])
        return bool(s and today < s.start <= today + days * DAY)

    overdue = take(m.is_late)
    now = take(in_today)
    nxt = take(upcoming)
    prog = take(lambda a: a["status"] == "proceso")
    ready = take(lambda a: not m.dated(a["id"]) and a["type"] != "suministro" and m.actionable(a) and not m.ext_by.get(a["id"]))
    ready.sort(key=lambda a: (-m.score(a)[0], nat_key(a["id"])))

    blocks_of: dict[str, list[str]] = {}
    for b in m.ext_blocks:
        blocks_of.setdefault(b["external_id"], []).append(b["activity_id"])
    exts = []
    for x in m.externals.values():
        if x["status"] == "resuelto" or (project_id and x["project_id"] != project_id):
            continue
        waiting = (today - x["requested_on"]).days if x["status"] == "esperando" and x.get("requested_on") else None
        exts.append({**x, "blocks": blocks_of.get(x["id"], []), "waiting_days": waiting})
    exts.sort(key=lambda x: (0 if x["blocks"] else 1, x["counterparty"]))

    done = [a for a in m.A.values() if a["status"] == "completada" and pf(a) and a.get("actual_date") and a["actual_date"] >= today - days * DAY]
    done.sort(key=lambda a: a["actual_date"], reverse=True)

    f = lambda lst: [_item(m, a, notes) for a in lst]  # noqa: E731
    return {
        "days": days, "today": today, "front_filter_active": use_front,
        "overdue": f(overdue), "today_items": f(now), "upcoming": f(nxt), "in_progress": f(prog),
        "ready": f(ready), "externals": exts, "done": f(done),
    }


# ------------------------------------------------------------------ text reports
def build_daily_report(m: Model, notes: dict, recent_notes: list[dict], days: int, project_id: str | None, front: str | None) -> str:
    g = task_groups(m, notes, days, project_id, front)
    today = m.today
    label_front = ""
    if project_id and front and front != "ALL" and g["front_filter_active"]:
        label_front = " · " + ("Obra (civil y eléctrica)" if front == "obra" else "Corporativas / administrativas")

    def L(a):
        s = a["sched"]
        dt = f" ({fd(s['start'])})" if s and s["kind"] != "esc" else ""
        ln = f" — {a['last_note']['body']}" if a.get("last_note") else ""
        return f"- {a['id']} {a['description']}{dt}{ln}"

    def by_project(items, fn):
        out = []
        for p in sorted(m.P.values(), key=lambda p: (p.get("sort_order") or 0, nat_key(p["id"]))):
            sub = [a for a in items if a["project_id"] == p["id"]]
            if sub:
                out.append(f"{m.pname(p['id'])}\n" + "\n".join(fn(a) for a in sub))
        return "\n\n".join(out)

    head = f"ACTUALIZACIÓN DE PROYECTOS FIGSA{' · ' + m.pname(project_id) if project_id else ''}{label_front} — {today.day} {MONTHS_LONG[today.month - 1]} {today.year}"
    parts = [head]
    done = g["done"]
    parts.append(f"\nCOMPLETADO (últimos {days} días)\n" + (by_project(done, lambda a: f"- {a['id']} {a['description']} ({fd(a['actual_date'])})") if done else "- Sin actividades cerradas en el período."))
    prog = g["in_progress"]
    if prog:
        parts.append("\nEN PROCESO\n" + by_project(prog, L))
    if recent_notes:
        parts.append("\nAVANCES REGISTRADOS\n" + "\n".join(f"- {n['created_at'].date().isoformat()} · {n['activity_id']}: {n['body']}" for n in recent_notes))
    if g["overdue"]:
        parts.append("\nATRASADO\n" + by_project(g["overdue"], L))
    nx = g["today_items"] + g["upcoming"]
    parts.append(f"\nPRÓXIMOS {days} DÍAS\n" + (by_project(nx, L) if nx else "- Sin actividades con fecha confirmada."))
    if g["externals"]:
        lines = []
        for x in g["externals"]:
            since = f", desde {fd(x['requested_on'])}" if x["status"] == "esperando" and x.get("requested_on") else ""
            blk = f" — bloquea {', '.join(x['blocks'])}" if x["blocks"] else ""
            lines.append(f"- {x['counterparty']}: {x['subject']} ({EXTERNAL_STATUS[x['status']].lower()}{since}){blk}")
        parts.append("\nPENDIENTE DE TERCEROS\n" + "\n".join(lines))
    return "\n".join(parts)


def range_for(today: date, period: str) -> tuple[date, date, str]:
    if period == "hoy":
        return today, today, "hoy"
    if period == "mes":
        return today.replace(day=1), today, "este mes"
    return today - timedelta(days=today.weekday()), today, "esta semana"


def payments_in_range(m: Model, per_diems: list[dict], a: date, b: date) -> list[dict]:
    out = []
    for c in m.purchases:
        p = m.P.get(c["project_id"]) or {}
        rate = finance.rate_of(p)
        done = c["status"] in ("realizada", "recibida")
        if done:
            day = c.get("received_on") or c.get("completed_on") or c.get("ordered_on")
            v = finance.to_q(finance.executed_native(c), c["currency"], rate)
            kind = "Pago total"
        elif (finance._n(c.get("advance_paid")) or 0) > 0:
            day = c.get("ordered_on") or (c["created_at"].date() if c.get("created_at") else None)
            v = finance.to_q(finance._n(c["advance_paid"]), c["currency"], rate)
            kind = "Anticipo"
        else:
            continue
        if day and a <= day <= b and v:
            out.append({"id": str(c["id"]), "project_id": c["project_id"], "date": day, "amount": v, "concept": c["product"], "kind": kind, "party": c.get("supplier")})
    for d in per_diems:
        if d["kind"] == "gasto" and a <= d["entry_date"] <= b:
            out.append({"id": str(d["id"]), "project_id": d["project_id"], "date": d["entry_date"], "amount": float(d["amount"]), "concept": d.get("detail") or "Viático", "kind": "Viático", "party": d["person"]})
    out.sort(key=lambda x: (x["date"], x["amount"]), reverse=True)
    return out


def summary_text(period_label: str, a: date, b: date, data: dict, m: Model) -> str:
    gq = sum(g["amount"] for g in data["payments"])
    rng = fdy(a) if a == b else f"{fd(a)} – {fdy(b)}"
    L = [
        f"RESUMEN FIGSA — {period_label.upper()} ({rng})", "",
        f"Actividades completadas: {len(data['activities'])}",
        f"Avances registrados: {len(data['notes'])}",
        f"Ejecutado: {money(gq)} en {len(data['payments'])} pagos y anticipos",
        f"Facturas y comprobantes subidos: {len(data['files'])}",
        f"Pendientes externos resueltos: {len(data['externals'])}",
        f"Líneas de presupuesto completadas: {len(data['lines'])}",
    ]
    for pid, r in data["per_project"].items():
        L += ["", m.pname(pid).upper(), f"  {r['activities']} completadas · {r['notes']} avances · {r['payments']} gastos" + (f" ({money(r['amount'])})" if r["amount"] else "") + f" · {r['files']} archivos"]
        L += [f"  ✓ {x['id']} {x['description']}" for x in data["activities"] if x["project_id"] == pid]
        L += [f"  - {n['activity_id']}: {n['body']}" for n in data["notes"] if n["project_id"] == pid]
    return "\n".join(L)


# ------------------------------------------------------------------ WhatsApp (template only)
def whatsapp_data(m: Model, data: dict, a: date, b: date, project_id: str | None, audience: str) -> dict:
    out = []
    for p in sorted(m.P.values(), key=lambda p: (p.get("sort_order") or 0, nat_key(p["id"]))):
        if project_id and p["id"] != project_id:
            continue
        pid = p["id"]
        done = [x["description"] for x in data["activities"] if x["project_id"] == pid]
        av = [f"{m.A[n['activity_id']]['description']}: {n['body']}" for n in data["notes"] if n["project_id"] == pid]
        lin = [x.get("material") or x["activity"] for x in data["lines"] if x["project_id"] == pid]
        ext = [x["subject"] for x in data["externals"] if x["project_id"] == pid]
        gastos = [g for g in data["payments"] if g["project_id"] == pid] if audience == "jefe" else []
        prox = sorted(
            ((x, m.dated(x["id"])) for x in m.A.values() if x["project_id"] == pid and x["status"] != "completada" and x["type"] != "hito"
             and m.dated(x["id"]) and b < m.dated(x["id"]).start <= b + 5 * DAY),
            key=lambda t: t[1].start,
        )[:4]
        prog = [x["description"] for x in m.A.values() if x["project_id"] == pid and x["status"] == "proceso"][:4]
        if done or av or lin or ext or gastos or (project_id and (prox or prog)):
            out.append({
                "project": p["name"], "done": done, "notes": av, "budget_lines_done": lin, "confirmations": ext,
                "in_progress": prog, "payments": gastos, "next": [f"{x['description']} ({fd(s.start)})" for x, s in prox],
            })
    return {"projects": out}


def whatsapp_template(d: dict, period_label: str, rng: str, audience: str) -> str:
    L = [f"Buen día. Le comparto el avance de {'hoy' if period_label == 'hoy' else period_label} ({rng}):"]
    if not d["projects"]:
        L += ["", "Sin avances registrados en el periodo."]
    for p in d["projects"]:
        L += ["", f"*{p['project']}*"]
        L += [f"✅ {t}" for t in p["done"]] + [f"✅ {t}" for t in p["budget_lines_done"]]
        L += [f"🔧 {t}" for t in p["notes"]] + [f"⏳ En proceso: {t}" for t in p["in_progress"]]
        L += [f"📩 Confirmado: {t}" for t in p["confirmations"]]
        if audience == "jefe" and p["payments"]:
            tot = sum(g["amount"] for g in p["payments"])
            L.append(f"💰 Gastos registrados: {len(p['payments'])}" + (f" por {money(tot)}" if tot else ""))
        if p["next"]:
            L.append("📌 Próximos pasos: " + "; ".join(p["next"]))
    L += ["", "Quedo atento a cualquier comentario. Saludos."]
    return "\n".join(L)
