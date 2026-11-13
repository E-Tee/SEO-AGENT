"""
Правильная кластеризация: нормализация URL + объединение интентов + чистка мусора.
"""
import pandas as pd
from collections import defaultdict
from urllib.parse import urlparse
import json
import re

FILE = "data/raw/ключи конкурентов.xlsx"

# 1. Читаем все листы
all_data = []
xls = pd.ExcelFile(FILE)
for sheet in xls.sheet_names:
    df = pd.read_excel(FILE, sheet_name=sheet, header=None)
    # Находим строку с заголовком
    for i, row in df.iterrows():
        if "Ключ" in str(row.values) and "Страница" in str(row.values):
            df = pd.read_excel(FILE, sheet_name=sheet, header=i)
            break
    all_data.append(df)

df_all = pd.concat(all_data, ignore_index=True)

# 2. Оставляем только нужные колонки
df_all = df_all[['Ключ', 'Региональная общая частотность', 'Домен', 'Страница']].copy()
df_all.columns = ['kw', 'freq', 'domain', 'url']
df_all['freq'] = pd.to_numeric(df_all['freq'], errors='coerce').fillna(0)

# 3. Убираем брендовые запросы
brand_words = [
    'finikor', 'финикор', 'бласт сервис', 'blast-service', 'poroshkom', 'порошком',
    'порошок ру', 'renault', 'renewauto', 'уманский', 'софийская', 'кудрино',
    'малое карлино', 'шушары', 'приневская', 'рыбацкий', 'маршала казакова',
    'кудрово', 'торнадо', 'info poroshkom', 'ооо бласт', 'автоцентр finikor',
    'вакансии', 'авито', 'отзывы', 'фото'
]
pattern = '|'.join(brand_words)
df_all = df_all[~df_all['kw'].str.lower().str.contains(pattern, na=False)]

# 4. Нормализация URL
def normalize_url(url):
    if pd.isna(url) or not isinstance(url, str):
        return None
    try:
        parsed = urlparse(url)
        path = parsed.path.lower().rstrip('/')
        if not path:
            path = '/'
        # Убираем .html
        path = path.replace('.html', '')
        # Убираем общие префиксы
        path = path.replace('/uslugi/', '/').replace('/services/', '/').replace('/uslugi-i-ceny', '/price')
        return path
    except:
        return None

df_all['url_norm'] = df_all['url'].apply(normalize_url)
df_all = df_all[df_all['url_norm'].notna()]

# 5. Маппинг интентов: нормализованный URL -> канонический интент
intent_map = {
    '/': 'home',
    '/price': 'price',
    '/contacts': 'contacts',
    '/video': 'video',
    # Автомобили
    '/peskostruj-diskov': 'disks',
    '/uslugi/peskostrujnaya-obrabotka-detalej-avtomobilya/peskostrujnaya-obrabotka-diskov': 'disks',
    '/antikorroziynaya_obrabotka_dnisha_avtomobilya': 'dnishe',
    '/uslugi/peskostrujnaya-obrabotka-detalej-avtomobilya/peskostrujnaya-obrabotka-dnishha-antikora': 'dnishe',
    '/peskostruy-avto.html': 'avto',
    '/peskostrujnaya-obrabotka-kuzova': 'avto',
    '/services/peskostrujnaya-obrabotka': 'dnishe',  # finikor смешивает
    # Дерево
    '/peskostruy-drevesina.html': 'derevo',
    '/peskostrujnaya-ochistka-sruba': 'derevo',
    '/restavracija_ochistka_dereva': 'derevo',
    # Кирпич
    '/peskostruy-kirpich.html': 'kirpich',
    '/peskostrujnaya-obrabotka-kirpicha': 'kirpich',
    # Металлоконструкции
    '/peskostruy-metal-structures.html': 'metallokonstrukcii',
    '/peskostrujnaya-obrabotka-metallokonstrukcij': 'metallokonstrukcii',
    # Фасады
    '/peskostruy-fasady.html': 'fasady',
    '/peskostrujnaya-obrabotka-fasadov': 'fasady',
    # Выездной
    '/viesdnoy-peskostruy': 'vyezdnoy',
    '/uslugi/vyezdnaya-peskostrujnaya-i-malyarnaya-rabota': 'vyezdnoy',
    # Порошковая покраска (если не делаешь — выкинем)
    '/services/pokraska-alyuminiya': 'poroshkovaya',
    '/services/pokraska-radiatorov-otopleniya': 'poroshkovaya',
    '/services/pokraska-metallicheskix-trub': 'poroshkovaya',
    '/services/pokraska-oczinkovannyix-poerxnostej': 'poroshkovaya',
    '/services/pokraska-vorot-i-kalitok': 'poroshkovaya',
    '/services/pokraska-vozduxovodov': 'poroshkovaya',
    '/services/pokraska-metallicheskix-dverej': 'poroshkovaya',
    '/colour/pokraska-pod-xrom': 'poroshkovaya',
    '/services_pokraska.html': 'poroshkovaya',
    # Мойка двигателя (выкидываем)
    '/services/washing': 'washing',
    # Антикор (выкидываем)
    '/services/antikorrozijnaja_obrabotka': 'antikor',
    # Мягкий бластинг
    '/myagkij-blasting': 'blasting',
    # Спецтехника
    '/obrabotka-i-pokraska-spectehniki': 'spectehnika',
    # Резервуары
    '/jomkostej-i-rezervuarov': 'rezervuary',
    '/uslugi/vyezdnaya-peskostrujnaya-i-malyarnaya-rabota/obrabotka-bakov-czistern': 'rezervuary',
    # Суда
    '/obrabotka-sudov-i-lodok': 'suda',
    '/obrkorpsud': 'suda',
    # Трубы
    '/obrtrub': 'truby',
    # Дробеструйная
    '/drobestrujnaya-ochistka': 'drobestruynaya',
    # СВА
    '/strujno-vihrevaya-abrazivnaya-ochistka-svao': 'svao',
    # Безвоздушная покраска
    '/bezvozdushnaya-pokraska': 'bezvozdushnaya',
}

df_all['intent'] = df_all['url_norm'].map(intent_map).fillna('other')

# 6. Группируем по интенту
clusters = defaultdict(list)
for _, row in df_all.iterrows():
    intent = row['intent']
    if intent in ('washing', 'antikor', 'poroshkovaya'):  # выкидываем
        continue
    clusters[intent].append({
        'keyword': row['kw'],
        'freq': row['freq'],
        'url': row['url_norm']
    })

# 7. Для каждого кластера выбираем primary_kw и secondary
results = []
for intent, keywords in clusters.items():
    if len(keywords) < 2:
        continue
    
    # Сортируем по частотности
    keywords.sort(key=lambda x: x['freq'], reverse=True)
    
    primary = keywords[0]
    secondary = [k['keyword'] for k in keywords[1:]]
    
    results.append({
        'intent': intent,
        'primary_kw': primary['keyword'],
        'primary_freq': primary['freq'],
        'secondary_kws': '; '.join(secondary),
        'total_keywords': len(keywords),
        'total_freq': sum(k['freq'] for k in keywords),
        'sample_urls': ', '.join(sorted(set(k['url'] for k in keywords)))
    })

# 8. Сортируем по общей частотности
results.sort(key=lambda x: x['total_freq'], reverse=True)

# 9. Сохраняем
import os
os.makedirs('data/processed', exist_ok=True)
df_results = pd.DataFrame(results)
df_results.to_csv('data/processed/clusters.csv', index=False, encoding='utf-8-sig')

with open('data/processed/clusters.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"Создано {len(results)} кластеров")
print(f"\nТоп-20:")
for i, r in enumerate(results[:20], 1):
    print(f"{i:2}. {r['intent']:20} | {r['primary_kw']:<50} | freq={r['primary_freq']:>6} | keys={r['total_keywords']:>3}")