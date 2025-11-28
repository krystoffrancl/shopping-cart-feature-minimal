# Shopping Cart Feature - Instalační návod

Tento repozitář obsahuje pouze soubory nutné pro přidání shopping cart funkcionality do existujícího Dream Farm projektu.

## 📁 Struktura souborů

```
shopping-cart-feature-minimal/
├── agents/dreamfarm-agent/src/services/
│   └── shopping_cart_service.py       # ✨ NOVÝ - Shopping cart business logic
├── data/scripts/
│   └── create_cart_tables.sql         # ✨ NOVÝ - SQL schema pro košík
├── frontend/src/components/
│   └── shopping-cart.tsx              # ✨ NOVÝ - UI modal komponenta
├── imgs/                               # ✨ NOVÉ - Screenshoty
│   ├── AliceScreen-Cart.png
│   ├── vipScreen-cart.png
│   └── vipScreen-chat.png
├── docs/                               # 🔧 Patche pro existující soubory
│   ├── main.py.patch
│   ├── openai_service.py.patch
│   ├── pyproject.toml.patch
│   ├── api.ts.patch
│   └── App.tsx.patch
├── README.md                           # 📖 Kompletní dokumentace
└── INSTALLATION.md                     # 📋 Tento soubor
```

## 🚀 Instalace do existujícího Dream Farm projektu

### Předpoklady

- ✅ Fungující Dream Farm projekt (z kurzu "Pokročilé AI Aplikace")
- ✅ PostgreSQL s pgvector rozšířením
- ✅ Stock API běžící na portu 8011
- ✅ Python 3.12+ s `uv` package managerem
- ✅ Node.js + npm pro frontend

---

### Krok 1: Zkopírování nových souborů

```bash
# Předpokládá se, že jste v root složce Dream Farm projektu
# a shopping-cart-feature-minimal je v nadřazené složce nebo jinde

FEATURE_DIR="../shopping-cart-feature-minimal"  # Upravte podle umístění

# 1. Nový shopping cart service
cp $FEATURE_DIR/agents/dreamfarm-agent/src/services/shopping_cart_service.py \
   agents/dreamfarm-agent/src/services/

# 2. SQL migrace pro košík
cp $FEATURE_DIR/data/scripts/create_cart_tables.sql \
   data/scripts/

# 3. Frontend košík komponenta
cp $FEATURE_DIR/frontend/src/components/shopping-cart.tsx \
   frontend/src/components/

# 4. Screenshoty (volitelné - pro dokumentaci)
mkdir -p imgs
cp $FEATURE_DIR/imgs/*.png imgs/
```

---

### Krok 2: Aplikování změn v existujících souborech

Máte dvě možnosti: **A) Automaticky přes patch** nebo **B) Ručně**

#### Volba A: Automatické aplikování (doporučeno)

```bash
FEATURE_DIR="../shopping-cart-feature-minimal"

# Backend
cd agents/dreamfarm-agent
patch -p3 < $FEATURE_DIR/docs/pyproject.toml.patch
patch -p3 < $FEATURE_DIR/docs/openai_service.py.patch
patch -p3 < $FEATURE_DIR/docs/main.py.patch

# Frontend
cd ../../frontend/src
patch -p3 < $FEATURE_DIR/docs/api.ts.patch
patch -p3 < $FEATURE_DIR/docs/App.tsx.patch
```

Pokud patch selže (např. různé verze souborů), použijte **Volbu B**.

#### Volba B: Ruční integrace

##### B.1) `agents/dreamfarm-agent/pyproject.toml`

Přidej závislost:

```toml
dependencies = [
    # ... existující závislosti ...
    "psycopg[binary]>=3.1.0",  # 👈 PŘIDAT pro shopping cart
]
```

Spusť:
```bash
cd agents/dreamfarm-agent
uv sync
```

##### B.2) `agents/dreamfarm-agent/src/services/openai_service.py`

**Do `__init__` metody** (cca řádek 100, za inicializaci ostatních služeb):

```python
# Shopping cart integration
try:
    cart_enabled = os.getenv("SHOPPING_CART_ENABLED", "false").lower() in ["true","1","yes","on"]
    stock_api_url = os.getenv("STOCK_API_URL", "http://localhost:8011")
    logger.info(f"Shopping cart configuration: enabled={cart_enabled}, stock_api={stock_api_url}")

    if cart_enabled:
        from .shopping_cart_service import ShoppingCartService
        self._shopping_cart = ShoppingCartService(self._app_config, stock_api_url)
        logger.info(f"Shopping cart service initialized successfully (stock_api={stock_api_url})")
    else:
        logger.info("Shopping cart disabled; skipping cart tool init")

except Exception as se:
    import traceback
    logger.error(f"Shopping cart init failed: {se}")
    logger.error(f"Traceback: {traceback.format_exc()}")
```

**Do `get_tools()` metody** (cca řádek 300, za ostatní tool registrace):

```python
# Shopping cart tools
if hasattr(self, "_shopping_cart") and self._shopping_cart:
    logger.info("Registering shopping_cart function tools (shopping_cart enabled)")

    tools.extend([
        {
            "type": "function",
            "name": "add_to_cart",
            "description": "Add one or more products to user's shopping cart with stock validation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "List of products to add",
                        "items": {
                            "type": "object",
                            "properties": {
                                "product_name": {"type": "string", "description": "Product name (fuzzy matching)"},
                                "quantity": {"type": "integer", "description": "Quantity to add"},
                                "category": {"type": "string", "description": "Optional product category hint"}
                            },
                            "required": ["product_name", "quantity"]
                        }
                    }
                },
                "required": ["items"]
            }
        },
        {
            "type": "function",
            "name": "view_cart",
            "description": "View current shopping cart contents with total price",
            "parameters": {"type": "object", "properties": {}}
        },
        {
            "type": "function",
            "name": "update_cart_item",
            "description": "Update quantity of item in cart (0 to remove)",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product UUID"},
                    "quantity": {"type": "integer", "description": "New quantity (0 = remove)"}
                },
                "required": ["product_id", "quantity"]
            }
        },
        {
            "type": "function",
            "name": "clear_cart",
            "description": "Remove all items from shopping cart",
            "parameters": {"type": "object", "properties": {}}
        }
    ])
```

##### B.3) `agents/dreamfarm-agent/src/main.py`

**Import** (přidat k ostatním imports, cca řádek 75):

```python
from .services.shopping_cart_service import CartItem
```

**REST API endpointy** (přidat před konec souboru):

```python
@app.get("/cart")
async def get_cart(user_ctx: tuple[str, bool, dict] = Depends(_require_user)):
    """Get current user's shopping cart contents."""
    username, user_is_vip, _ = user_ctx

    if not openai_service._shopping_cart:  # type: ignore[attr-defined]
        raise HTTPException(status_code=503, detail="Shopping cart service not available")

    try:
        cart_data = await openai_service._shopping_cart.get_cart(username)  # type: ignore[attr-defined]
        return cart_data
    except Exception as e:
        logger.error(f"Failed to get cart: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/cart/item")
async def update_cart_item(payload: dict, user_ctx: tuple[str, bool, dict] = Depends(_require_user)):
    """Update cart item quantity (0 to remove)."""
    username, _, _ = user_ctx

    if not openai_service._shopping_cart:  # type: ignore[attr-defined]
        raise HTTPException(status_code=503, detail="Shopping cart service not available")

    product_id = payload.get("product_id")
    quantity = payload.get("quantity", 0)

    try:
        result = await openai_service._shopping_cart.update_cart_item(username, product_id, quantity)  # type: ignore[attr-defined]
        return result
    except Exception as e:
        logger.error(f"Failed to update cart item: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/cart")
async def clear_cart(user_ctx: tuple[str, bool, dict] = Depends(_require_user)):
    """Clear user's shopping cart."""
    username, _, _ = user_ctx

    if not openai_service._shopping_cart:  # type: ignore[attr-defined]
        raise HTTPException(status_code=503, detail="Shopping cart service not available")

    try:
        result = await openai_service._shopping_cart.clear_cart(username)  # type: ignore[attr-defined]
        return result
    except Exception as e:
        logger.error(f"Failed to clear cart: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

**Streaming handler** (přidat do `send_message_stream` funkce, cca řádek 1720, za ostatní tool handlers):

```python
# Shopping Cart tools
elif name in ("add_to_cart", "view_cart", "update_cart_item", "clear_cart"):
    logger.info("🛒 SHOPPING CART: Model called %s", name)
    try:
        cart_service = getattr(openai_service, "_shopping_cart", None)
        if cart_service:
            raw_args = getattr(item, "arguments", "{}")
            try:
                parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else {}
            except Exception:
                parsed_args = {}

            cart_result = None
            if name == "add_to_cart":
                items = parsed_args.get("items", [])
                cart_result = await cart_service.add_to_cart(username, items, is_vip)
            elif name == "view_cart":
                cart_result = await cart_service.get_cart(username)
            elif name == "update_cart_item":
                product_id = parsed_args.get("product_id", "")
                quantity = parsed_args.get("quantity", 0)
                cart_result = await cart_service.update_cart_item(username, product_id, quantity)
            elif name == "clear_cart":
                cart_result = await cart_service.clear_cart(username)

            logger.info("✅ SHOPPING CART: %s completed", name)
            pending_outputs.append({
                "type": "function_call_output",
                "call_id": getattr(item, "call_id", getattr(item, "id", "")),
                "output": json.dumps(cart_result),
            })
            # Notify frontend about cart update
            yield "\nDF_META:" + json.dumps({"kind": "cart_updated"}, ensure_ascii=False) + "\n"

    except Exception as e:
        logger.error("❌ SHOPPING CART: %s execution failed: %s", name, e)
        pending_outputs.append({
            "type": "function_call_output",
            "call_id": getattr(item, "call_id", getattr(item, "id", "")),
            "output": json.dumps({"success": False, "error": str(e)}),
        })
```

##### B.4) `frontend/src/services/api.ts`

Přidej metody do `DreamFarmAPI` class (cca řádek 215):

```typescript
/**
 * Get current user's shopping cart
 */
async getCart() {
  const response = await fetch(`${this.baseUrl}/cart`, {
    headers: {
      ...this.getAuthHeader(),
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to get cart: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Update cart item quantity (set to 0 to remove)
 */
async updateCartItem(productId: string, quantity: number) {
  const response = await fetch(`${this.baseUrl}/cart/item`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...this.getAuthHeader(),
    },
    body: JSON.stringify({ product_id: productId, quantity }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to update cart item: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Clear shopping cart
 */
async clearCart() {
  const response = await fetch(`${this.baseUrl}/cart`, {
    method: 'DELETE',
    headers: {
      ...this.getAuthHeader(),
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to clear cart: ${response.statusText}`);
  }

  return response.json();
}
```

##### B.5) `frontend/src/App.tsx`

**Import** (přidat k ostatním imports):

```typescript
import { ShoppingCart } from './components/shopping-cart';
```

**Component** (přidat před closing `</div>` v return):

```tsx
<ShoppingCart />
```

---

### Krok 3: Konfigurace

#### Backend .env

```bash
cd agents/dreamfarm-agent

# Přidat do .env
cat >> .env << 'EOF'

# Shopping Cart (user-bound cart with stock validation)
SHOPPING_CART_ENABLED=true
STOCK_API_URL=http://localhost:8011
EOF
```

#### Ověření .env

Ujisti se, že máš správné PostgreSQL credentials:

```bash
PGHOST=localhost
PGPORT=5432
PGDATABASE=aidb  # nebo tvoje DB name
PGUSER=admin
PGPASSWORD=admin123  # nebo tvoje heslo
```

---

### Krok 4: Databázové schema

#### A) Enable pg_trgm extension

```bash
cd agents/dreamfarm-agent

uv run python -c "
import psycopg
import os
from dotenv import load_dotenv

load_dotenv('.env')

conn = psycopg.connect(
    host=os.getenv('PGHOST', 'localhost'),
    port=int(os.getenv('PGPORT', '5432')),
    dbname=os.getenv('PGDATABASE', 'aidb'),
    user=os.getenv('PGUSER', 'admin'),
    password=os.getenv('PGPASSWORD', ''),
    autocommit=True
)

conn.cursor().execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
print('✅ Extension pg_trgm enabled')
conn.close()
"
```

#### B) Create cart tables

```bash
cd ../../data/scripts

psql -h localhost -U admin -d aidb -f create_cart_tables.sql

# Nebo pokud máš jiné credentials:
# psql -h $PGHOST -U $PGUSER -d $PGDATABASE -f create_cart_tables.sql
```

---

### Krok 5: Instalace frontend dependencies

```bash
cd frontend

# Shopping cart komponenta používá stávající dependencies,
# ale ověř, že máš aktuální package.json:
npm install
```

---

### Krok 6: Restart služeb

```bash
# 1. Stock API (pokud není spuštěná)
cd tools/api_stock
uv run uvicorn main:app --reload --port 8011 &

# 2. DreamFarm Agent backend
cd ../../agents/dreamfarm-agent
uv run uvicorn src.main:app --reload --port 8001 &

# 3. Frontend
cd ../../frontend
npm run dev
```

---

## ✅ Ověření instalace

### 1. Test přes Chat UI

```
User: Chci přidat 5 rajčat do košíku
AI: ✅ Přidal jsem 5× Heirloom Tomato Basket do košíku (cena/ks)
```

### 2. Test přes UI Modal

- Klikni na **ikonu košíku** v pravém horním rohu
- Měl by se zobrazit modal s položkami
- Zkus změnit množství pomocí +/- tlačítek

### 3. Test přes REST API

```bash
# Get cart
curl http://localhost:8001/cart \
  -H "Authorization: Bearer YOUR_TOKEN"

# Update item
curl -X PUT http://localhost:8001/cart/item \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"product_id": "some-uuid", "quantity": 3}'

# Clear cart
curl -X DELETE http://localhost:8001/cart \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 🐛 Troubleshooting

### `function similarity() does not exist`

**Příčina**: Chybí PostgreSQL extension `pg_trgm`

**Řešení**:
```bash
psql -h localhost -U admin -d aidb -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
```

### `relation "shopping_carts" does not exist`

**Příčina**: Nespustil jsi SQL migraci

**Řešení**:
```bash
cd data/scripts
psql -h localhost -U admin -d aidb -f create_cart_tables.sql
```

### `401 Unauthorized` při GET /cart

**Příčina**: JWT token vypršel nebo autentizace je zapnutá

**Řešení**:
- **Option 1**: Přihlásit se znovu ve frontendu (obnovit token)
- **Option 2**: Dočasně vypnout auth pro testování:
  ```bash
  echo "AUTH_ENABLED=false" >> agents/dreamfarm-agent/.env
  ```

### `ModuleNotFoundError: No module named 'psycopg'`

**Příčina**: Chybí Python dependency

**Řešení**:
```bash
cd agents/dreamfarm-agent
uv sync
```

### Backend spadl po změnách

**Řešení**:
1. Zkontroluj syntax errors v upravených souborech
2. Zkontroluj logy: `cd agents/dreamfarm-agent && uv run uvicorn src.main:app --reload`
3. Ověř, že jsou všechny imports správně

### Shopping cart se neukazuje v UI

**Příčina**: Komponenta není importována v App.tsx

**Řešení**:
1. Zkontroluj, že `shopping-cart.tsx` je v `frontend/src/components/`
2. Ověř import v `App.tsx`: `import { ShoppingCart } from './components/shopping-cart';`
3. Ověř, že komponenta je v JSX: `<ShoppingCart />`

---

## 📋 Checklist instalace

- [ ] Zkopírované všechny nové soubory (shopping_cart_service.py, create_cart_tables.sql, shopping-cart.tsx)
- [ ] Aplikované patche nebo ruční změny v 5 souborech
- [ ] Přidána psycopg dependency do pyproject.toml
- [ ] Spuštěn `uv sync` v agents/dreamfarm-agent
- [ ] Enabled pg_trgm extension v PostgreSQL
- [ ] Vytvořeny cart tables přes SQL migraci
- [ ] Přidána konfigurace do .env (SHOPPING_CART_ENABLED=true)
- [ ] Restart všech služeb (Stock API, Backend, Frontend)
- [ ] Otestována funkcionalita přes chat i UI

---

## 📚 Další dokumentace

- **README.md** - Kompletní feature dokumentace
- **shopping_cart_service.py** - Source code s docstrings
- **create_cart_tables.sql** - SQL schema s indexy
- **docs/*.patch** - Diff soubory pro reference

---

## 💡 Tips

- Pro debugging zapni verbose logging v backendu: `LOG_LEVEL=DEBUG`
- Košík je user-bound, ne thread-bound - přežije restart backendu
- Stock API musí běžet na portu 8011 (nebo změň STOCK_API_URL)
- Pro test bez autentizace: `AUTH_ENABLED=false`

## 🎓 Original Project

Shopping cart je extension projektu **Dream Farm** z kurzu "Pokročilé AI Aplikace".

**Minimální požadavky**:
- Funkční Dream Farm backend s RAG
- PostgreSQL database
- Stock API endpoint
- Keycloak authentication (volitelné pro vývoj)
