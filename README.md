# Telegram Rent Finder — Collector

RU: Реальный сборщик объявлений с фото из Telegram + жёсткая фильтрация (Батуми, 2 спальни, $400–$500, помесячно).  

## Установка
Windows 10, Python 3.10:

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
copy .env.example .env
```

Заполните в `.env`: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_PHONE`.  
Ollama опционален: если недоступен — парсинг цен/спален работает по правилам.

## Запуск
```bash
python -m scripts.collector
```

- Первым запуском запросит код/пароль Telegram.
- Результат в `matches.csv` (его открывает `app/app.py`: `streamlit run app/app.py`).

## Политика отбора
- **Только посты с изображениями** (текст без фото — пропуск).
- Отклоняем: студии/1+1, посуточно/daily, вне Батуми (Gonio/Квариати/Сарпи/…),
  Magnolia/Alliance Magnolia, цена вне диапазона, нет явных 2+ спален.
- Приоритет улицам: Inasaridze/Kobaladze/Angisa (+1 к score).
