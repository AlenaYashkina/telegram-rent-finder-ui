# Telegram Rent Finder UI

*RU summary:* Мини‑демо для отбора объявлений об аренде из Telegram‑каналов **только с фото**: импорт постов (офлайн пример), LLM‑нормализация полей (цена/район/метраж/контакты/ссылка), фильтрация и экспорт. Для первого релиза работает на локальном датасете без ключей и без Telegram‑сессии. Дальше подключим ваш реальный загрузчик.

---

## Overview
**Telegram Rent Finder UI** is a tiny end‑to‑end demo that turns messy Telegram housing posts **with images** into a clean, reviewable table:
- **Ingest**: load sample posts (JSON/CSV). Real Telegram scraper will be plugged in later.
- **Normalize (LLM)**: extract structured fields (price, district, area, contacts, link) into JSON (provider‑agnostic).
- **Filter & Review**: interactive UI to shortlist.
- **Export**: CSV/PDF with selected listings.

> Milestone 1 ships with **offline demo data** and a simple UI. Telegram and LLM providers are pluggable.

## Features (M1)
- Offline sample dataset (`/data/sample_listings.json`)
- LLM schema extraction to JSON (OpenAI or local Ollama)
- Streamlit UI with filters (price, district)
- Export to CSV/PDF
- Windows‑friendly setup (Python 3.10)
- **Images only** policy: posts without images are skipped by design

## Stack
- **Python 3.10**, **Streamlit**
- **pydantic** (schema), **pandas**
- **LLM provider** via environment (OpenAI or local **Ollama**)
- Optional: SQLite for saved shortlists

## Project Layout (planned)
```
telegram-rent-finder-ui/
  app/                # Streamlit UI
  normalizer/         # LLM prompts + schema extraction
  data/               # sample data for offline demo
  scripts/            # helpers (optional)
  .env.example
  requirements.txt
  README.md
```

## Quickstart (coming in next commits)
```bash
python -m venv .venv
. .venv/Scripts/activate      # Windows 10/11
pip install -r requirements.txt
streamlit run app/app.py
```

## Env vars
Copy `.env.example` to `.env` and set:
```
LLM_PROVIDER=openai|ollama
OPENAI_API_KEY=...
OLLAMA_MODEL=llama3
```

## Roadmap
- **M1:** offline demo + minimal UI (filters, export) — *this repo*
- **M2:** plug existing Telegram photo scraper (your code, with `.env` config)
- **M3:** prompt tuning, better dedup & contact parsing; optional SQLite

## License
MIT
