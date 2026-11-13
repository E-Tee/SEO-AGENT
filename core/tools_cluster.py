"""Тулзы кластеризации. Механика — Python, семантика — агент."""
import json, re
from pathlib import Path
import pandas as pd

OUT = Path("data/processed"); OUT.mkdir(parents=True, exist_ok=True)
STATE = OUT / "cluster_state.json"

COLS = {
    "kw":   ["ключ", "ключевая фраза", "keyword", "query", "фраза", "запрос"],
    "domain": ["домен", "domain", "сайт"],
    "url":  ["страница", "url", "page", "адрес"],
    "pos":  ["позиция", "position", "pos"],
}

def norm(s):
    s = str(s).lower().replace("ё", "е")
    return re.sub(r"[^a-zа-я0-9 ]+", " ", s).strip()

def _pick(cn, target):
    """Выбор колонки по приоритету правил, а не по порядку слева направо."""
    if target == "freq":
        rules = [
            lambda c: "региональн" in c and "общая" in c,      # региональная общая — то, что надо
            lambda c: "региональн" in c and "точн" not in c,
            lambda c: "региональн" in c,
            lambda c: ("частотн" in c or c in ("freq", "wsr")) and "глобальн" not in c,
            lambda c: "частотн" in c or c in ("freq", "wsr"),
        ]
    else:
        rules = [lambda c, n=n: n in c for n in COLS[target]]
    for r in rules:
        for orig, c in cn:
            if r(c):
                return orig
    return None

def _read_sheet(path, sh):
    raw = pd.read_excel(path, sheet_name=sh, header=None).dropna(how="all")
    if raw.empty:
        return None
    hdr = None
    for i in range(min(15, len(raw))):
        vals = [norm(v) for v in raw.iloc[i].values]
        if any(any(n in v for n in COLS["kw"]) for v in vals):
            hdr = i; break
    if hdr is not None:
        df = pd.read_excel(path, sheet_name=sh, header=hdr)
        cn = [(c, norm(c)) for c in df.columns]
        ren = {}
        for t in ("kw", "freq", "domain", "url", "pos"):
            c = _pick(cn, t)
            if c is not None and c not in ren:
                ren[c] = t
        df = df.rename(columns=ren)
    else:
        # ЗАГОЛОВКА НЕТ: текстовая колонка = kw, числовая = freq
        df = raw.copy()
        text_col = num_col = None
        for c in df.columns:
            s = df[c].dropna()
            if s.empty: continue
            share = pd.to_numeric(s, errors="coerce").notna().mean()
            if share > 0.8 and num_col is None: num_col = c
            elif share < 0.2 and text_col is None: text_col = c
        if text_col is None: return None
        ren = {text_col: "kw"}
        if num_col is not None: ren[num_col] = "freq"
        df = df.rename(columns=ren)
    return df if "kw" in df.columns else None

def _read(path, role=None):
    frames = []
    for sh in pd.ExcelFile(path).sheet_names:
        d = _read_sheet(path, sh)
        if d is not None: frames.append(d)
    if not frames:
        raise ValueError(f"не нашёл колонку с ключами в {path}")
    df = pd.concat(frames, ignore_index=True)
    for c in ("freq", "domain", "url", "pos"):
        if c not in df.columns: df[c] = None
    df = df[["kw", "freq", "domain", "url", "pos"]].copy()
    df["kw"] = df["kw"].astype(str).str.strip()
    df["freq"] = pd.to_numeric(df["freq"], errors="coerce").fillna(0)
    df["kwn"] = df["kw"].map(norm)
    df = df[(df.kwn.str.len() > 1) & (df.freq >= 0)]
    df = df[df.kw.str.lower() != "nan"]
    # role=None → автоопределение по наличию URL
    if role is None:
        role = "comp" if df.url.notna().any() else "core"
    if role == "comp":
        # ключ может ранжироваться на НЕСКОЛЬКИХ URL — это доказательная база, не дубли
        df = df.drop_duplicates(["kwn", "domain", "url"])
    else:
        df = df.sort_values("freq", ascending=False).drop_duplicates("kwn")
    return df

def inspect(path):
    df = _read(path)
    return {"file": path, "rows": len(df), "unique_keys": int(df.kwn.nunique()),
            "freq_sum": int(df.drop_duplicates('kwn').freq.sum()),
            "has_competitor_urls": bool(df.url.notna().any()),
            "top30": df.drop_duplicates("kwn").head(30)[["kw", "freq", "domain", "url"]].to_dict("records")}

def load(path, role):
    df = _read(path, role)
    df.to_json(OUT / f"{role}_norm.json", orient="records", force_ascii=False)
    return {"role": role, "rows": len(df), "unique_keys": int(df.kwn.nunique()),
            "freq_sum": int(df.drop_duplicates('kwn').freq.sum()),
            "urls": int(df.url.notna().sum())}

def _evidence(kwn, comp):
    hit = comp[comp.kwn == kwn]
    return [f"{r.domain}{r.url} (поз.{r.pos})" for r in hit.itertuples()][:4]

def apply_policy(policy):
    core = pd.read_json(OUT / "core_norm.json")
    comp = pd.read_json(OUT / "comp_norm.json") if (OUT / "comp_norm.json").exists() else core.iloc[:0]
    stops = [norm(s) for s in policy.get("stop_patterns", [])]
    intents = policy.get("intents", [])
    assign, dropped, conflict, unassigned = {}, [], [], []
    for r in core.itertuples():
        k = r.kwn
        if any(s and s in k for s in stops):
            dropped.append({"kw": r.kw, "reason": "stop"}); continue
        m = [it["id"] for it in intents
             if all(norm(t) in k for t in it.get("markers_all", []))
             and (not it.get("markers_any") or any(norm(t) in k for t in it["markers_any"]))]
        if len(m) == 1: assign[r.kw] = m[0]
        elif len(m) > 1: conflict.append({"kw": r.kw, "freq": r.freq, "intents": m, "evidence": _evidence(k, comp)})
        else: unassigned.append({"kw": r.kw, "freq": r.freq, "evidence": _evidence(k, comp)})
    stats = {}
    for it in intents:
        ks = [k for k, v in assign.items() if v == it["id"]]
        f = int(core[core.kw.isin(ks)].freq.sum())
        stats[it["id"]] = {"keys": len(ks), "freq": f, "url": it.get("url")}
    STATE.write_text(json.dumps({"policy": policy, "assign": assign, "dropped": dropped,
                                 "conflict": conflict, "unassigned": unassigned}, ensure_ascii=False), encoding="utf-8")
    return {"assigned": len(assign), "dropped": len(dropped),
            "conflicts": len(conflict), "unassigned": len(unassigned),
            "by_intent": stats,
            "conflict_sample": sorted(conflict, key=lambda x: -x["freq"])[:25],
            "unassigned_sample": sorted(unassigned, key=lambda x: -x["freq"])[:40]}

def finalize(resolutions=None, overrides=None):
    st = json.loads(STATE.read_text(encoding="utf-8"))
    core = pd.read_json(OUT / "core_norm.json")
    freq = dict(zip(core.kw, core.freq))
    assign = st["assign"]
    for r in (resolutions or []):
        if r.get("drop"): st["dropped"].append({"kw": r["kw"], "reason": r["drop"]})
        elif r.get("intent"): assign[r["kw"]] = r["intent"]
    ov = {o["intent"]: o for o in (overrides or [])}
    groups = {}
    for kw, it in assign.items(): groups.setdefault(it, []).append(kw)
    clusters, errors = [], []
    for it in policy_intents(st):
        ks = sorted(groups.get(it["id"], []), key=lambda k: -freq.get(k, 0))
        if not ks: continue
        o = ov.get(it["id"], {})
        primary = o.get("primary_kw", ks[0])
        clusters.append({"intent": it["id"], "url": o.get("url", it.get("url")),
                         "type": it.get("type", "service"), "primary_kw": primary,
                         "secondary_kws": [k for k in ks if k != primary],
                         "total_keys": len(ks), "total_freq": int(sum(freq.get(k, 0) for k in ks))})
    clusters.sort(key=lambda c: -c["total_freq"])
    urls = [c["url"] for c in clusters]; prim = [c["primary_kw"] for c in clusters]
    if len(set(urls)) != len(urls): errors.append("дубли URL — каннибализация")
    if len(set(prim)) != len(prim): errors.append("дубли primary_kw — каннибализация")
    if not clusters: errors.append("пусто: policy не сматчилась")
    pd.DataFrame(clusters).to_csv(OUT / "url_map.csv", index=False, encoding="utf-8-sig")
    (OUT / "clusters_final.json").write_text(json.dumps(clusters, ensure_ascii=False, indent=2), encoding="utf-8")
    rep = [f"# Отчёт кластеризации", f"Ядро: {len(core)} ключей",
           f"Распределено: {len(assign)} | брошено: {len(st['dropped'])} | конфликтов: {len(st['conflict'])} | без интента: {len(st['unassigned'])}",
           f"Кластеров: {len(clusters)}", "", "| URL | primary | ключей | частота |", "|---|---|---|---|"]
    rep += [f"| {c['url']} | {c['primary_kw']} | {c['total_keys']} | {c['total_freq']} |" for c in clusters]
    rep += ["", f"ОШИБКИ ГЕЙТА: {errors or 'нет'}"]
    (OUT / "cluster_report.md").write_text("\n".join(rep), encoding="utf-8")
    return {"clusters": len(clusters), "gate_errors": errors, "report": "data/processed/cluster_report.md"}

def policy_intents(st): return st["policy"].get("intents", [])

SCHEMAS = [
    {"name": "inspect", "description": "Прочитать xlsx: колонки, число ключей, топ-30. Вызывай для обоих файлов первым делом.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "load", "description": "Нормализовать файл в рабочее состояние. role='core' для своего ядра, role='comp' для ключей конкурентов.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "role": {"type": "string", "enum": ["core", "comp"]}}, "required": ["path", "role"]}},
    {"name": "apply_policy", "description": "Применить policy ко всему ядру. Возвращает статистику, конфликты и нераспознанные ключи с URL конкурентов. Можно вызывать многократно, уточняя policy.",
     "parameters": {"type": "object", "properties": {"policy": {"type": "object", "properties": {
         "stop_patterns": {"type": "array", "items": {"type": "string"}},
         "intents": {"type": "array", "items": {"type": "object", "properties": {
             "id": {"type": "string"}, "url": {"type": "string"}, "type": {"type": "string"},
             "markers_all": {"type": "array", "items": {"type": "string"}},
             "markers_any": {"type": "array", "items": {"type": "string"}}}, "required": ["id", "url"]}}},
         "required": ["intents"]}}, "required": ["policy"]}},
    {"name": "finalize", "description": "Добить остатки и собрать url_map.csv + clusters_final.json + отчёт. resolutions — решения по конфликтным/нераспознанным ключам.",
     "parameters": {"type": "object", "properties": {
         "resolutions": {"type": "array", "items": {"type": "object", "properties": {
             "kw": {"type": "string"}, "intent": {"type": "string"}, "drop": {"type": "string"}}, "required": ["kw"]}},
         "overrides": {"type": "array", "items": {"type": "object", "properties": {
             "intent": {"type": "string"}, "primary_kw": {"type": "string"}, "url": {"type": "string"}}, "required": ["intent"]}}}}},
]

def run(name, args):
    try:
        return json.dumps(globals()[name](**args), ensure_ascii=False)[:14000]
    except Exception as e:
        return f"ERROR {name}: {e}"