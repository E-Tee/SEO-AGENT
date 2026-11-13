"""РљР»РёРµРЅС‚ KIE РґР»СЏ SEO-Р°РіРµРЅС‚Р°: РїСЂРѕС‚РѕРєРѕР» Responses (codex / openai / grok)."""
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
    # Сѓ KIE HTTP 200 РґР°Р¶Рµ РїСЂРё РѕС€РёР±РєРµ: СЃРјРѕС‚СЂРёРј code РІ С‚РµР»Рµ
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
            out.append(m); continue                      # С‚СѓР»Р·-СЂР°СѓРЅРґtrip РєР°Рє РµСЃС‚СЊ
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