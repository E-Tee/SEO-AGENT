"""Агент кластеризации: сам строит policy по твоему ядру, сам добивает остатки."""
import sys, json, datetime
from pathlib import Path
sys.path.insert(0, "core")
import llm, tools_cluster as T

TASK = """
Кластеризуй МОЁ ядро: data/raw/keywords.xlsx (role=core).
data/raw/ключи конкурентов.xlsx (role=comp) — только доказательная база: показывает,
на какие URL конкурентов ранжируется ключ. Это НЕ источник кластеров.

Порядок:
1. inspect оба файла, затем load core и load comp.
2. Построй policy по МОЕМУ ядру: интенты = услуги/объекты обработки, у каждого
   markers_any (токены-маркеры) и url вида /uslugi/<slug>/. Отдельно: главная,
   цены, контакты, инфо-статьи. В stop_patterns — бренды конкурентов, их адреса,
   вакансии/отзывы/авито, и услуги, которых нет в моём ядре.
3. apply_policy. Смотри by_intent, conflicts, unassigned_sample.
4. Уточняй policy и повторяй apply_policy, пока не останется крупных нераспознанных
   групп. Мелкие остатки добей через finalize.resolutions.
5. Правила: один интент = один URL; гео-запросы (шушары, кудрово) НЕ плодят страницы —
   идут в тот же интент; запросы про цену объекта — в интент объекта, общие цены — в /ceny/.
6. Финал: finalize. Если gate_errors непусты — исправь и повтори.
Никаких выдуманных частот. Опирайся на evidence из выдачи конкурентов.
"""

def main():
    extra = " ".join(sys.argv[1:])
    msgs = [{"role": "system", "content": Path("agents/seo/AGENT.md").read_text(encoding="utf-8")},
            {"role": "user", "content": TASK + "\n" + extra}]
    run = Path("runs") / ("cluster_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    run.mkdir(parents=True, exist_ok=True)
    log = []
    for step in range(30):
        res = llm.call("seo", msgs, tools=T.SCHEMAS)
        log.append({"step": step, "calls": [c["name"] for c in res["calls"]], "credits": res["credits"]})
        print(f"[{step}] {[c['name'] for c in res['calls']] or 'финал'}")
        if not res["calls"]: break
        msgs.append({"role": "assistant", "content": res["text"] or "(тулзы)"})
        for c in res["calls"]: msgs.append(c["raw"])
        for c in res["calls"]:
            a = json.loads(c["arguments"]) if isinstance(c["arguments"], str) else c["arguments"]
            out = T.run(c["name"], a)
            print("   →", out[:300])
            msgs.append({"type": "function_call_output", "call_id": c["id"], "output": out})
    (run / "log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    (run / "answer.md").write_text(res["text"], encoding="utf-8")
    print(res["text"][:3000])
    print(f"\nкредиты: {sum(x['credits'] or 0 for x in log):.3f} | логи: {run}")

if __name__ == "__main__":
    main()