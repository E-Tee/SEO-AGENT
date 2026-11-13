"""РћС‚РґРµР»СЊРЅС‹Р№ SEO-Р°РіРµРЅС‚: СЃРєРёР»Р» notfair + С‚СѓР»Р·С‹ + KIE. Р—Р°РїСѓСЃРє: python seo/run.py [--skill РРњРЇ] Р·Р°РґР°С‡Р°"""
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
    return "\n\n---\n\n".join(parts) or f"(СЃРєРёР»Р» {name} РЅРµ РЅР°Р№РґРµРЅ РІ vendor)"

def main():
    argv = sys.argv[1:]
    skill = None
    if argv[:1] == ["--skill"]:
        skill, argv = argv[1], argv[2:]
    task = " ".join(argv) or "keyword-research РїРѕ data/raw/keywords.xlsx"
    system = (Path("agents/seo/AGENT.md")).read_text(encoding="utf-8")
    if skill:
        system += f"\n\n# РђРљРўРР’РќР«Р™ РЎРљРР›Р›: {skill}\nР’С‹РїРѕР»РЅСЏР№ РµРіРѕ workflow РїРѕС€Р°РіРѕРІРѕ.\n\n" + skill_text(skill)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": task + "\n\nРђСЂС‚РµС„Р°РєС‚С‹: data/processed/. Р’С‹РґР°С‡Р°: С‚РѕР»СЊРєРѕ serp_search. Р¤Р°Р№Р»С‹ СЏРґСЂР° Рё СЌРєСЃРїРѕСЂС‚С‹: data/raw/."},
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
        messages.append({"role": "assistant", "content": res["text"] or "(РІС‹Р·С‹РІР°СЋ С‚СѓР»Р·С‹)"})
        for c in res["calls"]:
            messages.append(c["raw"])
        for c in res["calls"]:
            args = json.loads(c["arguments"]) if isinstance(c["arguments"], str) else c["arguments"]
            messages.append({"type": "function_call_output", "call_id": c["id"],
                             "output": tools_seo.run(c["name"], args)[:12000]})
    (run / "log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    (run / "answer.md").write_text(res["text"], encoding="utf-8")
    print(res["text"][:4000])
    print(f"\n[Р»РѕРіРё] {run}  [РєСЂРµРґРёС‚С‹] {sum(x['credits'] or 0 for x in log):.3f}")

if __name__ == "__main__":
    main()