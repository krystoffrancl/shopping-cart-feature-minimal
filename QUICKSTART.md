# 🚀 Quick Start Guide

> **Pro rychlou integraci shopping cart feature do Dream Farm projektu**

## Co tohle je?

Minimální repozitář obsahující **pouze shopping cart funkce** pro Dream Farm AI platformu z kurzu "Pokročilé AI Aplikace".

## ⚡ 5-minutová instalace

### 1️⃣ Zkopíruj 3 nové soubory

```bash
# Z tohoto repo do tvého Dream Farm projektu:
cp agents/dreamfarm-agent/src/services/shopping_cart_service.py YOUR_PROJECT/agents/dreamfarm-agent/src/services/
cp data/scripts/create_cart_tables.sql YOUR_PROJECT/data/scripts/
cp frontend/src/components/shopping-cart.tsx YOUR_PROJECT/frontend/src/components/
```

### 2️⃣ Aplikuj 5 patches

**Automaticky:**

```bash
cd YOUR_PROJECT
patch -p3 < PATH_TO_THIS_REPO/docs/pyproject.toml.patch
patch -p3 < PATH_TO_THIS_REPO/docs/openai_service.py.patch
patch -p3 < PATH_TO_THIS_REPO/docs/main.py.patch
patch -p3 < PATH_TO_THIS_REPO/docs/api.ts.patch
patch -p3 < PATH_TO_THIS_REPO/docs/App.tsx.patch
```

**Nebo ručně** - viz [INSTALLATION.md](INSTALLATION.md) krok 3.2

### 3️⃣ Instalace dependencies

```bash
cd agents/dreamfarm-agent
uv sync
```

### 4️⃣ PostgreSQL setup

```bash
# Enable pg_trgm extension
uv run python -c "import psycopg; conn = psycopg.connect('postgresql://admin:admin123@localhost:5432/aidb', autocommit=True); conn.cursor().execute('CREATE EXTENSION IF NOT EXISTS pg_trgm'); conn.close()"

# Create tables
cd ../../data/scripts
psql -h localhost -U admin -d aidb -f create_cart_tables.sql
```

### 5️⃣ Konfigurace

```bash
# agents/dreamfarm-agent/.env
echo "SHOPPING_CART_ENABLED=true" >> .env
echo "STOCK_API_URL=http://localhost:8011" >> .env
```

### 6️⃣ Restart služeb

```bash
# Backend
cd agents/dreamfarm-agent
uv run uvicorn src.main:app --reload --port 8001

# Frontend (v novém terminálu)
cd frontend
npm run dev
```

### 7️⃣ Test

```
User: "Chci 5 rajčat do košíku"
AI: ✅ Přidal jsem 5× Heirloom Tomato Basket do košíku

Klikni na košík ikonu v UI → modal s položkami
```

---

## 📚 Kompletní dokumentace

| Soubor | Kdy použít |
|--------|------------|
| **[README.md](README.md)** | Přehled feature, screenshots, architektura |
| **[INSTALLATION.md](INSTALLATION.md)** | Detailní instalační návod krok-za-krokem |
| **[TECHNICAL_REPORT.md](TECHNICAL_REPORT.md)** | Technický rozbor pro VŠ spolužáky |
| **[QUICKSTART.md](QUICKSTART.md)** | Tento soubor - 5min rychlý start |

---

## ❓ Troubleshooting

**Problém**: `function similarity() does not exist`
**Řešení**: `CREATE EXTENSION IF NOT EXISTS pg_trgm;`

**Problém**: `401 Unauthorized`
**Řešení**: Refresh JWT token nebo `AUTH_ENABLED=false`

**Problém**: `ModuleNotFoundError: psycopg`
**Řešení**: `cd agents/dreamfarm-agent && uv sync`

**Více v [INSTALLATION.md](INSTALLATION.md) sekce Troubleshooting**

---

## 🎯 Co dostaneš

✅ **Natural language shopping** - "Chci 10 rajčat" → AI přidá do košíku
✅ **Fuzzy matching** - "rajčata" najde "Heirloom Tomato Basket"
✅ **Stock validation** - Nelze přidat více než je skladem
✅ **Dual interface** - Chat (MCP tools) + UI (React modal)
✅ **Advanced AI ops** - "Odeber produkty levnější než 5 €"
✅ **User-bound persistence** - Košík přetrvá restart backendu

---

## 📊 Statistiky

- **3 nové soubory** (~750 řádků kódu)
- **5 upravených souborů** (~150 řádků změn)
- **2 nové databázové tabulky**
- **1 PostgreSQL extension** (pg_trgm)
- **4 MCP tools** (add_to_cart, view_cart, update_cart_item, clear_cart)
- **3 REST endpointy** (GET /cart, PUT /cart/item, DELETE /cart)

---

## 🤝 Pro koho je tohle

- ✅ **Účastníci kurzu** "Pokročilé AI Aplikace"
- ✅ **Kdo už má Dream Farm projekt** z kurzu
- ✅ **Kdo chce přidat shopping cart funkci** bez kompletního forku

---

**Stack**: FastAPI, PostgreSQL (pg_trgm), React, OpenAI Responses API
**Autor**: Kryštof Francl
**Licence**: Extension projektu z kurzu

---

**Happy coding! 🎉**
