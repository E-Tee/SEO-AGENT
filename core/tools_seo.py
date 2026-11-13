"""РўСѓР»Р·С‹ SEO-Р°РіРµРЅС‚Р°. Whitelist, РЅРёС‡РµРіРѕ СЃРІРµСЂС…."""
import json
from pathlib import Path
import serp

SCHEMAS = [
    {"name": "serp_search",
     "description": "РўРѕРї-10 РІС‹РґР°С‡Рё С‡РµСЂРµР· OpenSERP. Р”РІРёР¶РєРё: google | yandex.",
     "parameters": {"type": "object",
                    "properties": {"engine": {"type": "string", "enum": ["google", "yandex"]},
                                   "query": {"type": "string"},
                                   "limit": {"type": "integer"}},
                    "required": ["engine", "query"]}},
    {"name": "read_file", "description": "РџСЂРѕС‡РёС‚Р°С‚СЊ С‚РµРєСЃС‚РѕРІС‹Р№ С„Р°Р№Р» РїСЂРѕРµРєС‚Р°.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Р—Р°РїРёСЃР°С‚СЊ Р°СЂС‚РµС„Р°РєС‚ РІ С„Р°Р№Р» РїСЂРѕРµРєС‚Р°.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                    "required": ["path", "content"]}},
    {"name": "list_dir", "description": "РџРѕРєР°Р·Р°С‚СЊ СЃРѕРґРµСЂР¶РёРјРѕРµ РїР°РїРєРё (СЂРµРєСѓСЂСЃРёРІРЅРѕ).",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
]

def run(name, args):
    try:
        if name == "serp_search":
            return json.dumps(serp.fetch(args["engine"], args["query"], args.get("limit", 10)), ensure_ascii=False)
        if name == "read_file":
            p = Path(args["path"])
            return p.read_text(encoding="utf-8")[:20000] if p.exists() else f"ERROR: РЅРµС‚ С„Р°Р№Р»Р° {p}"
        if name == "write_file":
            p = Path(args["path"]); p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args["content"], encoding="utf-8"); return f"ok: {p}"
        if name == "list_dir":
            p = Path(args["path"])
            return "\n".join(sorted(str(x) for x in p.rglob("*")))[:6000] if p.exists() else f"ERROR: РЅРµС‚ РїР°РїРєРё {p}"
        return f"ERROR: РЅРµРёР·РІРµСЃС‚РЅР°СЏ С‚СѓР»Р·Р° {name}"
    except Exception as ex:
        return f"ERROR: {name}: {ex}"