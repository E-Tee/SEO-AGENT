# setup.ps1 — стенд отдельного SEO-агента
param([switch]$VendorOnly)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Write-File {
    param([string]$Path, [string]$Content)
    $dir = Split-Path $Path -Parent
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    [System.IO.File]::WriteAllText((Join-Path $PSScriptRoot $Path), $Content, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "  + $Path"
}

# ---------- папки ----------
foreach ($d in @("config","agents\seo","core","seo","data\raw","data\serp\google","data\serp\yandex","data\processed","runs","vendor")) {
    New-Item -ItemType Directory -Force -Path $d | Out-Null
}

# ---------- vendor: ВСЕ скиллы notfair-plugin ----------
if (-not (Test-Path "vendor\notfair-plugin\AGENTS.md")) {
    Write-Host "Качаю notfair-plugin (все скиллы)..."
    $zip = "$env:TEMP\notfair.zip"
    curl.exe -sL -o $zip https://github.com/nowork-studio/notfair-plugin/archive/refs/heads/main.zip
    Expand-Archive -Path $zip -DestinationPath "$env:TEMP\notfair" -Force
    if (Test-Path "vendor\notfair-plugin") { Remove-Item -Recurse -Force "vendor\notfair-plugin" }
    Move-Item "$env:TEMP\notfair\notfair-plugin-main" "vendor\notfair-plugin"
}
if ($VendorOnly) { Write-Host "vendor обновлён"; exit }

# ========== ФАЙЛ: .env.example ==========
Write-File ".env.example" @'
# === KIE: модели ===
KIE_API_KEY=
# === OpenSERP: выдача ===
OPENSERP_BASE_URL=http://127.0.0.1:7000
OPENSERP_TOKEN=
# === поисковики: только эти два ===
SERP_ENGINES=google,yandex
SERP_LANG=RU
YANDEX_LR=2
GOOGLE_REGION=Saint Petersburg
'@
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env"; Write-Host "  + .env (впиши ключи!)" }

# ========== ФАЙЛ: .gitignore ==========
Write-File ".gitignore" @'
.env
__pycache__/
runs/
data/serp/
vendor/
'@

# ========== ФАЙЛ: requirements.txt ==========
Write-File "requirements.txt" @'
requests
pyyaml
python-dotenv
pandas
openpyxl
'@

# ========== ФАЙЛ: config/models.yaml ==========
Write-File "config\models.yaml" @'
# KIE, протокол Responses. Слаги сверь: GET https://api.kie.ai/openai/v1/models
roles:
  seo:        {proto: codex,       model: gpt-6-1-terra,    effort: high,   max_tokens: 16000}
  seo_bulk:   {proto: openai-resp, model: deepseek-v4-1-flash, thinking: off, max_tokens: 8000}
  seo_critic: {proto: grok,        model: grok-4-5,         effort: medium, max_tokens: 8000}
fallback:
  codex:       [gpt-6-1-sol, gpt-5-6-sol]
  openai-resp: [kimi-k3-1-pro]
  grok:        [grok-4-6]
'@

# ========== ФАЙЛ: config/seo.yaml ==========
Write-File "config\seo.yaml" @'
domain_punycode: xn--e1aapkhdgegceho3a2m.xn--p1ai
region: SPb
engines: [google, yandex]
serp_cache_days: 7
serp_delay_sec: 1.5
vendor: vendor/notfair-plugin
artifacts: data/processed
'@

# ========== ФАЙЛ: agents/seo/AGENT.md ==========
Write-File "agents\seo\AGENT.md" @'
# SEO-агент (центрпескоструя.рф, СПб)

Ты — SEO-архитектор. Работаешь по скиллам из vendor/notfair-plugin (каталог SEO/GEO).
Резолвер «интент → скилл»:

| Интент задачи | Скилл |
|---|---|
| ядро, кластеры, интенты | keyword-research |
| разбор страниц конкурентов из топа | competitor-pages |
| аудит всего сайта (нужен crawl-экспорт в data/raw/) | seo-analysis |
| аудит одной страницы | seo-page |
| title/description/OG | meta-tags-optimizer |
| JSON-LD | schema-markup-generator |
| план страниц под шаблон (осторожно, дорвеи!) | programmatic-seo |
| тексты страниц/статей | content-writer |
| редплан (нужен экспорт GSC) | content-planner |
| локальная выдача, карты, NAP | local-seo |
| sitemap / битые ссылки / alt / дрейф / ссылки | sitemap-audit / broken-link-checker / image-seo / seo-drift / backlink-audit |
| GSC/GA4 | search-console / google-analytics — ТОЛЬКО по экспорту из data/raw/, живого OAuth у нас нет |

## Жёсткие правила
1. Выдача — только тулзой serp_search, движки google и yandex. Никаких «по памяти».
2. Частоты не выдумывать: только из data/raw/ или из статистики выдачи.
3. Кластеры — по пересечению топ-10 (3+ общих URL), не по эмбеддингам.
4. Один primary_kw — один URL. Каннибализация = провал гейта.
5. Артефакты пиши в data/processed/<skill>_<дата>/, начинай каждый с саммари на 5 строк.
6. Скиллы paid-ads/meta-ads/wordpress в vendor есть, но вне твоей компетенции: не трогай.
7. Язык артефактов — русский, цифры и приоритеты обязательны, вода запрещена.
'@

# ========== ФАЙЛ: core/llm.py ==========
Write-File "core\llm.py" @'
"""Клиент KIE для SEO-агента: протокол Responses (codex / openai / grok)."""
import os, json, requests, yaml
from dotenv import load_dotenv
load_dotenv()

BASE = "https://api.kie.ai"
ROLES = yaml.safe_load(open("config/models.yaml", encoding="utf-8"))["roles"]

class KieError(Exception):
    def __init__(self, code, msg):
        self.code, self.msg = code, msg
        super().__init__(f"[{code}] {msg}")
class OutOfCredits(KieError): pass
class RateLimited(KieError): pass

def _hdr():
    return {"Authorization": f"Bearer {os.environ['KIE_API_KEY']}", "Content-Type": "application/json"}

def _post(url, payload):
    # у KIE HTTP 200 даже при ошибке: смотрим code в теле
    r = requests.post(url, headers=_hdr(), json=payload, timeout=600).json()
    if isinstance(r, dict) and r.get("code") not in (None, 200):
        raise {402: OutOfCredits, 429: RateLimited}.get(r["code"], KieError)(r["code"], r.get("msg"))
    if isinstance(r, dict) and "error" in r:
        raise KieError(500, r["error"].get("message"))
    return r

def _to_input(messages):
    out = []
    for m in messages:
        if isinstance(m, dict) and m.get("type") in ("function_call", "function_call_output"):
            out.append(m); continue                      # тулз-раундtrip как есть
        role, c = m["role"], m["content"]
        kind = "output_text" if role == "assistant" else "input_text"
        out.append({"role": role, "content": [{"type": kind, "text": c}] if isinstance(c, str) else c})
    return out

def call(role, messages, tools=None, schema=None):
    cfg = ROLES[role]
    p = {"model": cfg["model"], "stream": False, "input": _to_input(messages),
         "reasoning": {"effort": "none" if cfg.get("thinking") == "off" else cfg.get("effort", "medium")}}
    if tools:
        p["tools"] = [{"type": "function", **t} for t in tools]; p["tool_choice"] = "auto"
    if schema:
        p["text"] = {"format": {"type": "json_schema", "name": "out", "strict": True, "schema": schema}}
    base = {"codex": f"{BASE}/codex/v1", "grok": f"{BASE}/xai/v1"}.get(cfg["proto"], f"{BASE}/openai/v1")
    r = _post(f"{base}/responses", p)
    text, calls = "", []
    for it in r.get("output", []):
        if it.get("type") == "message":
            text += "".join(c.get("text", "") for c in it.get("content", []) if c.get("type") == "output_text")
        elif it.get("type") == "function_call":
            calls.append({"id": it["call_id"], "name": it["name"], "arguments": it["arguments"], "raw": it})
    return {"text": text, "calls": calls, "usage": r.get("usage"), "credits": r.get("credits_consumed")}
'@

# ========== ФАЙЛ: core/serp.py ==========
Write-File "core\serp.py" @'
"""Выдача через OpenSERP. Движки: только google и yandex, whitelist жёсткий."""
import os, hashlib, json, time, requests
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

HARD_CAP = {"google", "yandex"}
ALLOWED = HARD_CAP & set(os.getenv("SERP_ENGINES", "google,yandex").split(","))
BASE = os.getenv("OPENSERP_BASE_URL", "http://127.0.0.1:7000").rstrip("/")
TOKEN = os.getenv("OPENSERP_TOKEN", "")
LANG = os.getenv("SERP_LANG", "RU")
YLR = os.getenv("YANDEX_LR", "2")
GREG = os.getenv("GOOGLE_REGION", "Saint Petersburg")
CACHE = Path("data/serp")

class SerpError(Exception): pass

def fetch(engine, query, limit=10, max_age_days=7):
    if engine not in ALLOWED:
        raise SerpError(f"движок {engine} запрещён, можно только {sorted(ALLOWED)}")
    f = CACHE / engine / f"{hashlib.sha1(query.encode()).hexdigest()}.json"
    if f.exists() and (time.time() - f.stat().st_mtime) < max_age_days * 86400:
        return json.loads(f.read_text(encoding="utf-8"))
    params = {"text": query, "limit": limit, "lang": LANG,
              "region": YLR if engine == "yandex" else GREG}
    hdr = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
    r = requests.get(f"{BASE}/{engine}/search", params=params, headers=hdr, timeout=90)
    r.raise_for_status(); doc = r.json()
    failed = doc.get("meta", {}).get("engines_failed") or []
    if failed:
        raise SerpError(f"{engine}: engines_failed={failed} (капча/блок? попробуй прокси или позже)")
    out = {"query": query, "engine": engine, "fetched_at": time.time(),
           "results": [{"rank": x.get("rank"), "title": x.get("title"), "url": x.get("url"),
                        "snippet": x.get("snippet")}
                       for x in doc.get("results", []) if x.get("type") == "organic"][:limit]}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out

def batch(pairs, delay=1.5):
    outs = []
    for e, q in pairs:
        try: outs.append(fetch(e, q))
        except Exception as ex: outs.append({"query": q, "engine": e, "error": str(ex)})
        time.sleep(delay)
    return outs

if __name__ == "__main__":
    import sys
    e = sys.argv[1] if len(sys.argv) > 1 else "yandex"
    q = " ".join(sys.argv[2:]) or "пескоструйная обработка спб"
    print(json.dumps(fetch(e, q), ensure_ascii=False, indent=2)[:1200])
'@

# ========== ФАЙЛ: core/tools_seo.py ==========
Write-File "core\tools_seo.py" @'
"""Тулзы SEO-агента. Whitelist, ничего сверх."""
import json
from pathlib import Path
import serp

SCHEMAS = [
    {"name": "serp_search",
     "description": "Топ-10 выдачи через OpenSERP. Движки: google | yandex.",
     "parameters": {"type": "object",
                    "properties": {"engine": {"type": "string", "enum": ["google", "yandex"]},
                                   "query": {"type": "string"},
                                   "limit": {"type": "integer"}},
                    "required": ["engine", "query"]}},
    {"name": "read_file", "description": "Прочитать текстовый файл проекта.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Записать артефакт в файл проекта.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                    "required": ["path", "content"]}},
    {"name": "list_dir", "description": "Показать содержимое папки (рекурсивно).",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
]

def run(name, args):
    try:
        if name == "serp_search":
            return json.dumps(serp.fetch(args["engine"], args["query"], args.get("limit", 10)), ensure_ascii=False)
        if name == "read_file":
            p = Path(args["path"])
            return p.read_text(encoding="utf-8")[:20000] if p.exists() else f"ERROR: нет файла {p}"
        if name == "write_file":
            p = Path(args["path"]); p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args["content"], encoding="utf-8"); return f"ok: {p}"
        if name == "list_dir":
            p = Path(args["path"])
            return "\n".join(sorted(str(x) for x in p.rglob("*")))[:6000] if p.exists() else f"ERROR: нет папки {p}"
        return f"ERROR: неизвестная тулза {name}"
    except Exception as ex:
        return f"ERROR: {name}: {ex}"
'@

# ========== ФАЙЛ: seo/run.py ==========
Write-File "seo\run.py" @'
"""Отдельный SEO-агент: скилл notfair + тулзы + KIE. Запуск: python seo/run.py [--skill ИМЯ] задача"""
import sys, json, datetime
from pathlib import Path
sys.path.insert(0, "core")
import llm, tools_seo

VENDOR = Path("vendor/notfair-plugin")

def skill_text(name):
    parts = []
    entry = VENDOR / "skills" / name / "SKILL.md"
    if entry.exists(): parts.append(entry.read_text(encoding="utf-8"))
    for w in list(VENDOR.rglob(f"*/{name}/WORKFLOW.md"))[:1]:
        parts.append(w.read_text(encoding="utf-8"))
    if not parts:
        parts = [h.read_text(encoding="utf-8") for h in list(VENDOR.rglob(f"**/{name}/*.md"))[:3]]
    return "\n\n---\n\n".join(parts) or f"(скилл {name} не найден в vendor)"

def main():
    argv = sys.argv[1:]
    skill = None
    if argv[:1] == ["--skill"]:
        skill, argv = argv[1], argv[2:]
    task = " ".join(argv) or "keyword-research по data/raw/keywords.xlsx"
    system = (Path("agents/seo/AGENT.md")).read_text(encoding="utf-8")
    if skill:
        system += f"\n\n# АКТИВНЫЙ СКИЛЛ: {skill}\nВыполняй его workflow пошагово.\n\n" + skill_text(skill)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": task + "\n\nАртефакты: data/processed/. Выдача: только serp_search. Файлы ядра и экспорты: data/raw/."},
    ]
    run = Path("runs") / datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run.mkdir(parents=True, exist_ok=True)
    log = []
    for step in range(12):
        res = llm.call("seo", messages, tools=tools_seo.SCHEMAS)
        log.append({"step": step, "calls": [c["name"] for c in res["calls"]],
                    "credits": res["credits"], "text_head": res["text"][:500]})
        if not res["calls"]:
            break
        messages.append({"role": "assistant", "content": res["text"] or "(вызываю тулзы)"})
        for c in res["calls"]:
            messages.append(c["raw"])
        for c in res["calls"]:
            args = json.loads(c["arguments"]) if isinstance(c["arguments"], str) else c["arguments"]
            messages.append({"type": "function_call_output", "call_id": c["id"],
                             "output": tools_seo.run(c["name"], args)[:12000]})
    (run / "log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    (run / "answer.md").write_text(res["text"], encoding="utf-8")
    print(res["text"][:4000])
    print(f"\n[логи] {run}  [кредиты] {sum(x['credits'] or 0 for x in log):.3f}")

if __name__ == "__main__":
    main()
'@

# ========== ФАЙЛ: run.ps1 ==========
Write-File "run.ps1" @'
param(
  [Parameter(Position=0)][string]$Task = "help",
  [Parameter(ValueFromRemainingArguments=$true)][string[]]$Rest
)
switch ($Task) {
  "seo"    { python seo/run.py @Rest }
  "serp"   { python core/serp.py @Rest }
  "credit" { curl.exe https://api.kie.ai/api/v1/chat/credit -H "Authorization: Bearer $env:KIE_API_KEY" }
  "models" { curl.exe https://api.kie.ai/openai/v1/models  -H "Authorization: Bearer $env:KIE_API_KEY" }
  "vendor" { powershell -NoProfile -File .\setup.ps1 -VendorOnly }
  default  { Write-Host "использование: .\run.ps1 seo|serp|credit|models|vendor [аргументы]" }
}
'@

