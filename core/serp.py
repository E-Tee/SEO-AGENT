"""Р’С‹РґР°С‡Р° С‡РµСЂРµР· OpenSERP. Р”РІРёР¶РєРё: С‚РѕР»СЊРєРѕ google Рё yandex, whitelist Р¶С‘СЃС‚РєРёР№."""
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

def fetch(engine, query, limit=10, max_age_days=7, max_retries=3):
    if engine not in ALLOWED:
        raise SerpError(f"движок {engine} запрещён, можно только {sorted(ALLOWED)}")
    f = CACHE / engine / f"{hashlib.sha1(query.encode()).hexdigest()}.json"
    if f.exists() and (time.time() - f.stat().st_mtime) < max_age_days * 86400:
        return json.loads(f.read_text(encoding="utf-8"))
    
    params = {"text": query, "limit": limit, "lang": LANG,
              "region": YLR if engine == "yandex" else GREG}
    hdr = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
    
    for attempt in range(max_retries):
        try:
            r = requests.get(f"{BASE}/{engine}/search", params=params, headers=hdr, timeout=90)
            if r.status_code == 429:
                wait = (attempt + 1) * 10  # 10, 20, 30 секунд
                print(f"429: жду {wait} сек... (попытка {attempt+1}/{max_retries})")
                time.sleep(wait)
                continue
            r.raise_for_status()
            doc = r.json()
            break
        except requests.exceptions.HTTPError as e:
            if attempt == max_retries - 1:
                raise
            time.sleep((attempt + 1) * 10)
    
    failed = doc.get("meta", {}).get("engines_failed") or []
    if failed:
        raise SerpError(f"{engine}: engines_failed={failed} (капча/блок? попробуй прокси или позже)")
    
    out = {"query": query, "engine": engine, "fetched_at": time.time(),
           "results": [{"rank": x.get("rank"), "title": x.get("title"), "url": x.get("url"),
                        "snippet": x.get("snippet")}
                       for x in doc.get("results", []) if x.get("type") == "organic"][:limit]}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text
    if engine not in ALLOWED:
        raise SerpError(f"движок {engine} запрещён, можно только {sorted(ALLOWED)}")
    f = CACHE / engine / f"{hashlib.sha1(query.encode()).hexdigest()}.json"
    if f.exists() and (time.time() - f.stat().st_mtime) < max_age_days * 86400:
        return json.loads(f.read_text(encoding="utf-8"))
    
    # ЗАДЕРЖКА ПЕРЕД ЗАПРОСОМ (добавь эту строку)
    time.sleep(2.0)  # 2 секунды паузы перед каждым запросом
    
    params = {"text": query, "limit": limit, "lang": LANG,
              "region": YLR if engine == "yandex" else GREG}
    params["raw"] = "true"
    hdr = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
    r = requests.get(f"{BASE}/{engine}/search", params=params, headers=hdr, timeout=90)
    r.raise_for_status(); doc = r.json()
    failed = doc.get("meta", {}).get("engines_failed") or []
    if failed:
        raise SerpError(f"{engine}: engines_failed={failed} (РєР°РїС‡Р°/Р±Р»РѕРє? РїРѕРїСЂРѕР±СѓР№ РїСЂРѕРєСЃРё РёР»Рё РїРѕР·Р¶Рµ)")
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
    q = " ".join(sys.argv[2:]) or "РїРµСЃРєРѕСЃС‚СЂСѓР№РЅР°СЏ РѕР±СЂР°Р±РѕС‚РєР° СЃРїР±"
    print(json.dumps(fetch(e, q), ensure_ascii=False, indent=2)[:1200])