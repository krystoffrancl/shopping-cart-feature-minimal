# Dream Farm AI - Shopping Cart Extension

## O projektu

Dream Farm je AI platforma z kurzu "Pokročilé AI Aplikace" - virtuální farmářské tržiště s RAG, multi-agent systémy, grafovou databází a enterprise observability.

**Tato verze přidává novou funkcionalitu: 🛒 Shopping Cart s natural language interface**

---

## 🛒 Shopping Cart Feature

Plně funkční nákupní košík, který umožňuje přidávat produkty **přirozeným jazykem** i přes **vizuální UI**. Košík je user-bound (vázán na uživatele, ne na thread), perzistentní v PostgreSQL a integrovaný s Stock API pro validaci dostupnosti.

### Co je nového

✅ **Natural language shopping**: "Chci 10 kusů organických rajčat do košíku"
✅ **Fuzzy product matching**: Tolerance překlepů pomocí PostgreSQL SIMILARITY
✅ **Stock validation**: Real-time kontrola dostupnosti (POUZE čtení, žádné odečítání)
✅ **User-bound košík**: Jeden košík pro všechny konverzace uživatele
✅ **Dual interface**: Chat (MCP tools) + UI (React modal)
✅ **Perzistentní data**: PostgreSQL tabulky `shopping_carts` + `shopping_cart_items`

### Architektura

**Flow přidání produktu:**

```text
User: "Přidej 10 rajčat do košíku"
  ↓
AI agent → add_to_cart tool
  ↓
ShoppingCartService:
  1. Fuzzy search: SIMILARITY('rajčata', product_name) > 0.3
  2. Stock check: POST /stock → {"productIds": [...]}
  3. Price generation: Random cena podle kategorie
  4. Save to DB: INSERT INTO shopping_cart_items
  ↓
Response + DF_META event → Frontend refresh
```

**Komponenty:**

```text
Backend:
├── src/services/shopping_cart_service.py
│   ├── add_to_cart(user_id, items, is_vip)
│   ├── get_cart(user_id)
│   ├── update_cart_item(user_id, product_id, qty)
│   ├── clear_cart(user_id)
│   └── _search_product() → SIMILARITY fuzzy match
│
├── src/main.py
│   ├── GET /cart → Získat košík
│   ├── PUT /cart/item → Upravit množství
│   └── DELETE /cart → Vyprázdnit košík
│
Database (PostgreSQL):
├── shopping_carts (cart_id, user_id)
└── shopping_cart_items (item_id, cart_id, product_id, quantity, price)

Frontend:
├── components/shopping-cart.tsx → UI modal
└── services/api.ts → Backend API client
```

### Databázové schéma

```sql
-- Extension pro fuzzy matching
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- User carts (one per user)
CREATE TABLE shopping_carts (
    cart_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Cart items (many per cart)
CREATE TABLE shopping_cart_items (
    item_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cart_id UUID REFERENCES shopping_carts(cart_id) ON DELETE CASCADE,
    product_id UUID NOT NULL,
    product_name VARCHAR(500) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    price_per_unit NUMERIC(10,2) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(cart_id, product_id)
);

CREATE INDEX idx_cart_user ON shopping_carts(user_id);
CREATE INDEX idx_cart_items_cart ON shopping_cart_items(cart_id);
```

### Konfigurace

**.env (backend):**

```bash
# Shopping Cart
SHOPPING_CART_ENABLED=true
STOCK_API_URL=http://localhost:8011

# PostgreSQL
PGHOST=localhost
PGPORT=5432
PGDATABASE=aidb
PGUSER=admin
PGPASSWORD=admin123
```

### Spuštění

```bash
# 1. PostgreSQL + pg_trgm extension
cd deploy/local && docker-compose up -d
cd ../../agents/dreamfarm-agent
uv run python -c "import psycopg; conn = psycopg.connect('postgresql://admin:admin123@localhost:5432/aidb'); conn.autocommit = True; conn.cursor().execute('CREATE EXTENSION IF NOT EXISTS pg_trgm'); conn.close()"

# 2. Create cart tables
cd ../../data/scripts
psql -h localhost -U admin -d aidb -f create_cart_tables.sql

# 3. Start services
cd ../../tools/api_stock && uv run uvicorn main:app --reload --port 8011 &
cd ../../agents/dreamfarm-agent && uv run uvicorn src.main:app --reload --port 8001 &
cd ../../frontend && npm run dev
```

### API endpointy

| Endpoint | Metoda | Popis |
|----------|--------|-------|
| `/cart` | GET | Získat košík aktuálního uživatele |
| `/cart/item` | PUT | Upravit množství položky: `{"product_id": "...", "quantity": 5}` |
| `/cart` | DELETE | Vyprázdnit košík |

### MCP Tools (Chat interface)

```python
add_to_cart(items: List[CartItem])
# items = [{"product_name": "rajčata", "quantity": 10, "category": "Vegetables"}]

view_cart()
# Zobrazí obsah košíku

update_cart_item(product_id: UUID, quantity: int)
# Upraví množství (0 = remove)

clear_cart()
# Vyprázdní košík
```

### Fuzzy Product Search

PostgreSQL SIMILARITY s pg_trgm extension:

```sql
SELECT
    product_id,
    product_name,
    SIMILARITY(product_name, 'rajčata') AS sim
FROM products
WHERE (is_vip = false OR $user_is_vip = true)
  AND SIMILARITY(product_name, 'rajčata') > 0.3
ORDER BY sim DESC
LIMIT 1;
```

**Příklad matchingu:**

- Input: `"rajčata"` → Match: `"Heirloom Tomato Basket"` (sim=0.41)
- Input: `"organické brambory"` → Match: `"Organic Potato Medley"` (sim=0.38)
- Threshold 0.3 = vyvážení přesnosti a flexibility

### Stock Validation

**Košík POUZE čte sklad, nikdy neodečítá:**

```python
async def _get_stock_quantity(self, product_id: UUID) -> int:
    """Check stock availability (READ-ONLY)"""
    url = f"{self._stock_api_url}/stock"
    payload = {"productIds": [str(product_id)]}
    response = await self._http_client.post(url, json=payload)
    data = response.json()
    return data["items"][0]["onStock"]

# Before adding to cart
stock_qty = await self._get_stock_quantity(product_id)
if quantity > stock_qty:
    return {"success": False, "error": f"Insufficient stock (available: {stock_qty})"}
```

### UI Features

**Chat interface - přidání produktů:**

![Chat - přidání do košíku](imgs/vipScreen-chat.png)

**Základní operace:**

```text
User: Chci přidat 10 kusů organických rajčat do košíku
AI: ✅ Přidal jsem 10× Heirloom Tomato Basket do košíku (25 Kč/ks)

User: Co mám v košíku?
AI: 📦 Máte v košíku:
- Heirloom Tomato Basket (10 ks) - 25 €
Celkem: 25 €
```

**Pokročilé operace - filtrování podle kritérií:**

```text
User: Odeber z košíku všechny produkty, které jsou levnější než 5 €

AI: Hotovo! Z košíku jsem odebral všechny položky s cenou pod 5 €:
Odebrané:
• Egg Pasta Nests — 3.87 €
• Parmesan-Style Hard Cheese — 3.26 €
• Classic Roma Sauce Tomatoes — 4.75 €

Zůstává v košíku (vše ≥ 5 €):
• Whole Creamline Milk — 7.65 €
• Heavy Cream — 7.03 €
• Music Garlic (Bulb) — 8.34 €
• Unsalted Butter — 6.48 €
• Classic Basil Pesto — 9.50 €

Aktuální součet: 39.00 € za 5 položek.
```

**UI Modal - správa košíku:**

![Košík modal - VIP user](imgs/vipScreen-cart.png)

**Funkce:**

- Ikona košíku v pravém horním rohu (s badge počtu položek)
- Modal s tabulkou položek
- +/- tlačítka pro změnu množství
- Ikona koše pro odstranění položky
- Tlačítko "Vyprázdnit košík"
- Real-time cena a celková suma

### Technické detaily

**Key Implementation Decisions:**

1. **User-bound vs Thread-bound**: Košík je vázán na `user_id` (ne `thread_id`) → jeden košík napříč všemi konverzacemi
2. **Direct integration vs MCP**: Košík je FastAPI service (ne MCP server) → jednodušší synchronizace UI/Chat
3. **Stock API pattern**: POST `/stock` s `{"productIds": [...]}` → batch queries
4. **Fuzzy matching threshold**: 0.3 = balance mezi false positives/negatives
5. **Price generation**: Random cena z range podle kategorie (temporary - v produkci by šla z DB)

**Dependencies:**

```toml
# agents/dreamfarm-agent/pyproject.toml
dependencies = [
    "psycopg[binary]>=3.1.0",  # Async PostgreSQL
    "httpx>=0.27.0",           # Stock API client
    # ... existing deps
]
```

**Environment toggles:**

```bash
SHOPPING_CART_ENABLED=true  # Feature flag
STOCK_API_URL=http://localhost:8011  # Stock validation endpoint
```

### Testování

```bash
# 1. Přidat produkt přes chat
curl -X POST http://localhost:8001/threads/{thread_id}/messages/stream \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message": "Chci 10 rajčat do košíku"}'

# 2. Zobrazit košík přes API
curl http://localhost:8001/cart \
  -H "Authorization: Bearer $TOKEN"

# 3. Upravit množství
curl -X PUT http://localhost:8001/cart/item \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"product_id": "4b7f3df0-1c67-48d7-b1eb-e0530e11197c", "quantity": 5}'

# 4. Vyprázdnit košík
curl -X DELETE http://localhost:8001/cart \
  -H "Authorization: Bearer $TOKEN"
```

## Původní Dream Farm funkcionalita

Pro úplnost - původní kurz obsahoval:

- **RAG**: Sémantické vyhledávání produktů (pgvector + HNSW index)
- **Hybrid Retrieval**: Semantic + keyword + RRF fusion
- **Graph DB**: Apache AGE pro taxonomie a vztahy
- **Multi-Agent**: DreamFarm ↔ Chef agent spolupráce
- **Voice**: Realtime API pro hlasový chat
- **Auth**: Keycloak OAuth2/OIDC
- **Observability**: OpenTelemetry + Grafana Tempo
- **Deployment**: Kubernetes (AKS) + Terraform

📖 **[Kompletní dokumentace →](docs/Design.md)**

---

## Autor

Shopping Cart feature vytvořena jako rozšíření projektu z kurzu "Pokročilé AI Aplikace".

**Stack**: FastAPI, PostgreSQL (pg_trgm), React, OpenAI Responses API, Stock API integration
