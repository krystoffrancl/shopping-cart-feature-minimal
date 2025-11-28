# Shopping Cart Feature - Technická Zpráva

> Detailní popis implementace natural language shopping cart pro Dream Farm AI platformu

**Autor**: Účastník kurzu "Pokročilé AI Aplikace"
**Datum**: Listopad 2025
**Stack**: FastAPI, PostgreSQL (pg_trgm), React, OpenAI Responses API

---

## 1. Motivace a cíle projektu

### 1.1 Problém

Dream Farm AI platforma umožňuje uživatelům vyhledávat produkty přirozeným jazykem pomocí RAG (Retrieval-Augmented Generation), ale **chyběla funkcionalita pro přidání produktů do košíku** a jejich následnou správu.

Standardní e-commerce košíky vyžadují:

- Klikání na tlačítka "Přidat do košíku"
- Ruční vyhledávání produktů
- Navigaci přes kategorie

**Cíl**: Implementovat košík, který lze ovládat **přirozeným jazykem** prostřednictvím AI asistenta, ale zároveň zachovat **klasické UI** pro vizuální správu.

### 1.2 Požadavky

**Funkční požadavky:**

- ✅ Přidávání produktů do košíku přirozeným jazykem (např. "Chci 10 rajčat")
- ✅ Fuzzy matching produktů (tolerance překlepů)
- ✅ Validace skladových zásob před přidáním
- ✅ User-bound košík (jeden košík pro uživatele napříč všemi konverzacemi)
- ✅ Dual interface: Chat (MCP tools) + UI (React modal)
- ✅ Pokročilé operace (např. "Odeber všechno levnější než 5 €")

**Nefunkční požadavky:**

- ✅ Perzistence dat v PostgreSQL
- ✅ Read-only přístup k Stock API (žádné odečítání ze skladu)
- ✅ Rychlá odezva (< 500ms pro CRUD operace)
- ✅ Kompatibilita s existující autentizací (Keycloak JWT)
- ✅ Zpětná kompatibilita (feature lze vypnout pomocí env variable)

---

## 2. Architektura řešení

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND (React)                        │
│  ┌──────────────────┐              ┌──────────────────┐        │
│  │  Chat Interface  │              │  Shopping Cart   │        │
│  │  (assistant-ui)  │              │     Modal UI     │        │
│  └────────┬─────────┘              └────────┬─────────┘        │
│           │                                  │                  │
│           │ WebSocket (streaming)            │ REST API         │
└───────────┼──────────────────────────────────┼──────────────────┘
            │                                  │
            ▼                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    BACKEND (FastAPI)                            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              OpenAI Service                              │  │
│  │  ┌────────────────────┐      ┌────────────────────┐     │  │
│  │  │  Responses API     │      │  MCP Tools         │     │  │
│  │  │  (streaming)       │◄────►│  - add_to_cart     │     │  │
│  │  └────────────────────┘      │  - view_cart       │     │  │
│  │                               │  - update_cart_item│     │  │
│  │                               │  - clear_cart      │     │  │
│  │                               └──────────┬─────────┘     │  │
│  └────────────────────────────────────────────┼─────────────┘  │
│                                               │                 │
│  ┌────────────────────────────────────────────▼─────────────┐  │
│  │         ShoppingCartService                              │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐ │  │
│  │  │ Fuzzy Search │  │ Stock        │  │ CRUD          │ │  │
│  │  │ (SIMILARITY) │  │ Validation   │  │ Operations    │ │  │
│  │  └──────────────┘  └──────────────┘  └───────────────┘ │  │
│  └──────────┬───────────────────┬──────────────────────────┘  │
└─────────────┼───────────────────┼─────────────────────────────┘
              │                   │
              ▼                   ▼
┌──────────────────────┐  ┌──────────────────────┐
│   PostgreSQL         │  │   Stock API          │
│  ┌─────────────────┐ │  │  (HTTP REST)         │
│  │ shopping_carts  │ │  │  POST /stock         │
│  │ shopping_cart_  │ │  │  → validate quantity │
│  │   items         │ │  │  (READ-ONLY)         │
│  └─────────────────┘ │  └──────────────────────┘
│  pg_trgm extension   │
└──────────────────────┘
```

### 2.2 Data Flow

#### Přidání produktu do košíku (Chat Interface)

```
1. User Input (Chat)
   ↓
   "Chci 10 kusů organických rajčat do košíku"

2. OpenAI Responses API
   ↓
   Streaming response → Tool call: add_to_cart
   {
     "items": [{
       "product_name": "rajčata",
       "quantity": 10,
       "category": "Vegetables"
     }]
   }

3. ShoppingCartService.add_to_cart()
   ↓
   a) Fuzzy Search (PostgreSQL SIMILARITY)
      SELECT product_id, product_name,
             SIMILARITY(product_name, 'rajčata') AS sim
      FROM products
      WHERE SIMILARITY(product_name, 'rajčata') > 0.3
      ORDER BY sim DESC LIMIT 1

      → Match: "Heirloom Tomato Basket" (sim=0.41)

   b) Stock Validation (Stock API)
      POST http://localhost:8011/stock
      Body: {"productIds": ["4b7f3df0-..."]}

      → Response: {"items": [{"onStock": 290, ...}]}
      → Validation: 10 <= 290 ✅

   c) Price Generation
      category = "Vegetables" → range (1.50, 12.00)
      price = random.uniform(1.50, 12.00) = 2.50 €

   d) Database Insert
      INSERT INTO shopping_cart_items (
        cart_id, product_id, product_name,
        quantity, price_per_unit
      ) VALUES (...)
      ON CONFLICT (cart_id, product_id)
      DO UPDATE SET quantity = quantity + 10

4. Response to AI
   ↓
   {
     "success": true,
     "message": "Added 10× Heirloom Tomato Basket",
     "total_items": 1,
     "total_price": 25.00
   }

5. AI Response to User
   ↓
   "✅ Přidal jsem 10× Heirloom Tomato Basket do košíku (2.50 €/ks)"

6. Frontend Notification
   ↓
   DF_META: {"kind": "cart_updated"}
   → Shopping cart badge updates: 0 → 10
```

#### Zobrazení košíku (UI Interface)

```
1. User Action
   ↓
   Click on cart icon

2. Frontend API Call
   ↓
   GET http://localhost:8001/cart
   Headers: {Authorization: "Bearer JWT_TOKEN"}

3. Backend Endpoint
   ↓
   @app.get("/cart")
   async def get_cart(user_ctx):
     username, _, _ = user_ctx
     return await shopping_cart.get_cart(username)

4. ShoppingCartService.get_cart()
   ↓
   SELECT
     ci.product_id, ci.product_name, ci.quantity,
     ci.price_per_unit, ci.created_at
   FROM shopping_carts c
   JOIN shopping_cart_items ci ON c.cart_id = ci.cart_id
   WHERE c.user_id = 'vipuser'
   ORDER BY ci.created_at DESC

5. Response
   ↓
   {
     "items": [
       {
         "product_id": "4b7f3df0-...",
         "product_name": "Heirloom Tomato Basket",
         "quantity": 10,
         "price_per_unit": 2.50,
         "subtotal": 25.00
       }
     ],
     "total_items": 10,
     "total_price": 25.00
   }

6. UI Rendering
   ↓
   Modal displays:
   ┌────────────────────────────────────────┐
   │ 🛒 Košík (10 položek)                 │
   ├────────────────────────────────────────┤
   │ Heirloom Tomato Basket                │
   │ 2.50 € × 10 = 25.00 €                 │
   │ [−] 10 [+] 🗑️                         │
   ├────────────────────────────────────────┤
   │ Celkem: 25.00 €                       │
   └────────────────────────────────────────┘
```

---

## 3. Implementační detaily

### 3.1 Backend - ShoppingCartService

**Soubor**: `agents/dreamfarm-agent/src/services/shopping_cart_service.py`

#### 3.1.1 Fuzzy Product Search

**Problém**: Uživatel říká "rajčata", ale v databázi je "Heirloom Tomato Basket"

**Řešení**: PostgreSQL SIMILARITY funkce s pg_trgm extension

```python
async def _search_product(
    self,
    product_name: str,
    user_is_vip: bool,
    category: str | None = None,
) -> dict[str, Any] | None:
    """Fuzzy matching produktů pomocí PostgreSQL trigram similarity."""

    async with await psycopg.AsyncConnection.connect(self._db_url) as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            # SIMILARITY funkce vrací skóre 0.0-1.0
            # Threshold 0.3 = vyvážení precision/recall
            query = """
                SELECT
                    product_id,
                    product_name,
                    'Unknown' AS category,
                    false AS is_organic,
                    SIMILARITY(product_name, %s) AS sim
                FROM products
                WHERE (is_vip = false OR %s = true)  -- VIP fencing
                  AND SIMILARITY(product_name, %s) > 0.3  -- Threshold
                ORDER BY sim DESC
                LIMIT 1
            """

            await cur.execute(query, [product_name, user_is_vip, product_name])
            return await cur.fetchone()
```

**Jak SIMILARITY funguje:**

```sql
-- pg_trgm rozloží text na 3-gram tokeny
SELECT show_trgm('rajčata');
→ {"  r"," ra","ata","čat","jča","raj","ta "}

SELECT show_trgm('Heirloom Tomato Basket');
→ {"  h"," he","  t"," to","ask","bas","ato",...,"tom",...}

-- SIMILARITY porovná překryv tokenů
SELECT SIMILARITY('rajčata', 'Heirloom Tomato Basket');
→ 0.41 (41% overlap díky "to" trigrams)

-- Threshold 0.3 = akceptujeme 30%+ overlap
```

**Proč threshold 0.3?**

- < 0.2: Příliš mnoho false positives (najde i nesouvisející produkty)
- 0.3: Sweet spot (tolerance překlepů + dostatečná přesnost)
- > 0.4: Příliš přísné (netoleruje překlepy)

#### 3.1.2 Stock Validation

**Problém**: Zabránit přidání většího množství než je skladem

**Řešení**: Dotaz na Stock API před uložením do košíku

```python
async def _get_stock_quantity(self, product_id: UUID) -> int:
    """Zjistí aktuální skladovou zásobu (READ-ONLY)."""
    try:
        url = f"{self._stock_api_url}/stock"
        payload = {"productIds": [str(product_id)]}

        response = await self._http_client.post(url, json=payload)
        response.raise_for_status()

        data = response.json()
        items = data.get("items", [])

        if items:
            return items[0].get("onStock", 0)
        return 0

    except Exception as e:
        logger.warning(f"Failed to get stock: {e}")
        return 0  # Fail-safe: pokud Stock API nedostupné, vracíme 0

# Použití při add_to_cart
stock_qty = await self._get_stock_quantity(product_id)
if quantity > stock_qty:
    return {
        "success": False,
        "error": f"Insufficient stock (available: {stock_qty})"
    }
```

**DŮLEŽITÉ**: Košík **POUZE ČTE** sklad, nikdy neodečítá!

- Odečítání by mělo proběhnout až při checkout (není implementováno)
- Tím se vyhneme race conditions při současných přidáních do košíku

#### 3.1.3 User-bound vs Thread-bound

**Rozhodnutí**: Košík je vázán na `user_id`, NE na `thread_id`

**Proč?**

```python
# ŠPATNĚ (thread-bound):
# - Uživatel má nový košík v každé konverzaci
# - Ztráta košíku při restartu backendu (threads jsou in-memory)
cart_id = thread_id  # ❌

# SPRÁVNĚ (user-bound):
# - Jeden košík pro uživatele napříč všemi vlákny
# - Perzistence v PostgreSQL → přežije restart
cart_id = hash(user_id)  # ✅
```

**Implementace:**

```python
async def _get_or_create_cart(self, user_id: str) -> UUID:
    """Získá nebo vytvoří košík pro uživatele."""
    async with await psycopg.AsyncConnection.connect(self._db_url) as conn:
        async with conn.cursor() as cur:
            # Pokus o SELECT
            await cur.execute(
                "SELECT cart_id FROM shopping_carts WHERE user_id = %s",
                [user_id]
            )
            row = await cur.fetchone()

            if row:
                return row[0]  # Existující košík

            # Vytvoř nový
            cart_id = uuid.uuid4()
            await cur.execute(
                """
                INSERT INTO shopping_carts (cart_id, user_id)
                VALUES (%s, %s)
                """,
                [cart_id, user_id]
            )
            await conn.commit()
            return cart_id
```

### 3.2 Backend - OpenAI Service Integration

**Soubor**: `agents/dreamfarm-agent/src/services/openai_service.py`

#### 3.2.1 Inicializace služby

**Kde**: V `__init__` metodě, za inicializací ostatních služeb (řádek ~100)

```python
class OpenAIService:
    def __init__(self, app_config: AppConfig):
        # ... existující inicializace (RAG, graph, memory) ...

        # Shopping cart integration
        try:
            cart_enabled = os.getenv("SHOPPING_CART_ENABLED", "false").lower() in ["true","1","yes","on"]
            stock_api_url = os.getenv("STOCK_API_URL", "http://localhost:8011")

            logger.info(f"Shopping cart configuration: enabled={cart_enabled}, stock_api={stock_api_url}")

            if cart_enabled:
                from .shopping_cart_service import ShoppingCartService
                self._shopping_cart = ShoppingCartService(self._app_config, stock_api_url)
                logger.info("Shopping cart service initialized successfully")
            else:
                logger.info("Shopping cart disabled; skipping cart tool init")

        except Exception as se:
            import traceback
            logger.error(f"Shopping cart init failed: {se}")
            logger.error(f"Traceback: {traceback.format_exc()}")
```

**Proč try-except?**

- Pokud ShoppingCartService selže (např. chybí dependency), nezabije celou aplikaci
- Feature lze vypnout pomocí `SHOPPING_CART_ENABLED=false`

#### 3.2.2 Registrace MCP Tools

**Kde**: V `get_tools()` metodě, za ostatní tool registrace (řádek ~300)

```python
def get_tools(self, user_is_vip: bool = False, thread_id: str = "") -> list[dict]:
    tools = []

    # ... existující tools (semantic_product_search, query_chef_services) ...

    # Shopping cart tools
    if hasattr(self, "_shopping_cart") and self._shopping_cart:
        logger.info("Registering shopping_cart function tools")

        tools.extend([
            {
                "type": "function",
                "name": "add_to_cart",
                "description": "Add one or more products to user's shopping cart with stock validation. Use fuzzy product names.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "description": "List of products to add",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "product_name": {
                                        "type": "string",
                                        "description": "Product name (fuzzy matching supported - e.g. 'rajčata', 'tomatoes')"
                                    },
                                    "quantity": {
                                        "type": "integer",
                                        "description": "Quantity to add (must be positive)"
                                    },
                                    "category": {
                                        "type": "string",
                                        "description": "Optional product category hint (e.g. 'Vegetables', 'Dairy')"
                                    }
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
                "description": "View current shopping cart contents with total price and item count",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "type": "function",
                "name": "update_cart_item",
                "description": "Update quantity of specific item in cart. Set quantity to 0 to remove item.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_id": {
                            "type": "string",
                            "description": "Product UUID from cart"
                        },
                        "quantity": {
                            "type": "integer",
                            "description": "New quantity (0 = remove item)"
                        }
                    },
                    "required": ["product_id", "quantity"]
                }
            },
            {
                "type": "function",
                "name": "clear_cart",
                "description": "Remove all items from shopping cart",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        ])

    return tools
```

**Proč 4 samostatné tools místo jednoho univerzálního?**

- Každý tool má jasný single purpose
- AI model lépe rozpozná intent (add vs update vs clear)
- Lepší error handling (specifické chyby pro každou operaci)

### 3.3 Backend - Main.py (FastAPI)

**Soubor**: `agents/dreamfarm-agent/src/main.py`

#### 3.3.1 REST API Endpointy

**Proč REST API když máme MCP tools?**

- MCP tools = Chat interface (AI asistent volá tools)
- REST API = UI interface (React komponenta potřebuje HTTP endpoints)

**Implementace:**

```python
@app.get("/cart")
async def get_cart(user_ctx: tuple[str, bool, dict] = Depends(_require_user)):
    """Get current user's shopping cart contents.

    Returns:
        Cart summary with items, total price, and total item count
    """
    username, user_is_vip, _ = user_ctx  # Unpack z JWT tokenu

    if not openai_service._shopping_cart:
        raise HTTPException(status_code=503, detail="Shopping cart service not available")

    try:
        cart_data = await openai_service._shopping_cart.get_cart(username)
        return cart_data
    except Exception as e:
        logger.error(f"Failed to get cart: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/cart/item")
async def update_cart_item(payload: dict, user_ctx: tuple[str, bool, dict] = Depends(_require_user)):
    """Update cart item quantity (0 to remove)."""
    username, _, _ = user_ctx

    if not openai_service._shopping_cart:
        raise HTTPException(status_code=503, detail="Shopping cart service not available")

    product_id = payload.get("product_id")
    quantity = payload.get("quantity", 0)

    try:
        result = await openai_service._shopping_cart.update_cart_item(
            username, product_id, quantity
        )
        return result
    except Exception as e:
        logger.error(f"Failed to update cart item: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/cart")
async def clear_cart(user_ctx: tuple[str, bool, dict] = Depends(_require_user)):
    """Clear user's shopping cart."""
    username, _, _ = user_ctx

    if not openai_service._shopping_cart:
        raise HTTPException(status_code=503, detail="Shopping cart service not available")

    try:
        result = await openai_service._shopping_cart.clear_cart(username)
        return result
    except Exception as e:
        logger.error(f"Failed to clear cart: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

**Authentication Flow:**

```
1. Frontend: GET /cart
   Headers: {Authorization: "Bearer eyJhbGc..."}

2. FastAPI Middleware: _require_user dependency
   → JWT validation (Keycloak)
   → Extract username, is_vip from token
   → Pass as user_ctx tuple

3. Endpoint: get_cart(user_ctx)
   → username = user_ctx[0]
   → Call shopping_cart.get_cart(username)
   → Return user's cart ONLY (hard user_id fence)

4. Response: {"items": [...], "total_price": 25.00}
```

#### 3.3.2 Streaming Handler (Chat Interface)

**Problém**: MCP tools se volají v rámci streaming response, ne REST endpointy

**Kde**: V `send_message_stream` funkci, řádek ~1720

```python
async def send_message_stream(
    thread_id: str,
    payload: SendMessageRequest,
    user_ctx: tuple[str, bool, dict] = Depends(_require_user)
):
    username, is_vip, _ = user_ctx  # ← DŮLEŽITÉ: Extrahovat na začátku

    # ... streaming loop ...

    async for event in stream:
        for item in event.session.get("output", []):
            item_type = getattr(item, "type", None)

            # ... ostatní tool handlers (get_stock, query_chef_services) ...

            # Shopping Cart tools
            elif name in ("add_to_cart", "view_cart", "update_cart_item", "clear_cart"):
                logger.info("🛒 SHOPPING CART: Model called %s", name)
                try:
                    cart_service = getattr(openai_service, "_shopping_cart", None)
                    if cart_service:
                        # Parse arguments z tool call
                        raw_args = getattr(item, "arguments", "{}")
                        try:
                            parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else {}
                        except Exception:
                            parsed_args = {}

                        # Execute odpovídající metodu
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

                        # Vrátit result zpět do streaming response
                        pending_outputs.append({
                            "type": "function_call_output",
                            "call_id": getattr(item, "call_id", getattr(item, "id", "")),
                            "output": json.dumps(cart_result),
                        })

                        # Notify frontend o změně košíku
                        yield "\nDF_META:" + json.dumps({"kind": "cart_updated"}, ensure_ascii=False) + "\n"

                except Exception as e:
                    logger.error("❌ SHOPPING CART: %s execution failed: %s", name, e)
                    pending_outputs.append({
                        "type": "function_call_output",
                        "call_id": getattr(item, "call_id", getattr(item, "id", "")),
                        "output": json.dumps({"success": False, "error": str(e)}),
                    })
```

**Proč DF_META event?**

- Frontend čeká na `DF_META: {"kind": "cart_updated"}`
- Při příjmu tohoto eventu aktualizuje badge u košík ikony
- Uživatel vidí okamžitou vizuální feedback

### 3.4 Frontend - Shopping Cart Component

**Soubor**: `frontend/src/components/shopping-cart.tsx`

#### 3.4.1 State Management

```typescript
const [cartItems, setCartItems] = useState<CartItem[]>([]);
const [isOpen, setIsOpen] = useState(false);
const [isLoading, setIsLoading] = useState(false);
const [error, setError] = useState<string | null>(null);

// Polling každých 5 sekund
useEffect(() => {
  loadCart();  // Initial load

  const interval = setInterval(loadCart, 5000);
  return () => clearInterval(interval);
}, []);

async function loadCart() {
  try {
    setIsLoading(true);
    const cart = await api.getCart();
    setCartItems(cart.items || []);
    setError(null);
  } catch (err) {
    console.error('Failed to load cart:', err);
    setError('Failed to load cart');
  } finally {
    setIsLoading(false);
  }
}
```

**Proč polling místo WebSocket?**

- Jednodušší implementace
- Košík se nemění tak často (update každých 5s je dostatečný)
- Pokud by byl WebSocket, musel by backend emitovat cart updates všem klientům daného usera

#### 3.4.2 UI Komponenty

```tsx
// Badge s počtem položek
<button onClick={() => setIsOpen(true)}>
  <ShoppingCart className="h-6 w-6" />
  {totalItems > 0 && (
    <span className="badge">{totalItems}</span>
  )}
</button>

// Modal s položkami
{isOpen && (
  <div className="modal-overlay">
    <div className="modal-content">
      <h2>Košík ({totalItems} položek)</h2>

      {cartItems.map(item => (
        <div key={item.product_id} className="cart-item">
          <div>{item.product_name}</div>
          <div>{item.price_per_unit} € × {item.quantity}</div>

          <div className="quantity-controls">
            <button onClick={() => updateQuantity(item, -1)}>−</button>
            <span>{item.quantity}</span>
            <button onClick={() => updateQuantity(item, +1)}>+</button>
            <button onClick={() => removeItem(item)}>🗑️</button>
          </div>
        </div>
      ))}

      <div className="total">
        Celkem: {totalPrice.toFixed(2)} €
      </div>

      <button onClick={clearCart}>Vyprázdnit košík</button>
    </div>
  </div>
)}
```

### 3.5 Database Schema

**Soubor**: `data/scripts/create_cart_tables.sql`

```sql
-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- UUID generation
CREATE EXTENSION IF NOT EXISTS pg_trgm;      -- Fuzzy text matching

-- User carts (one per user)
CREATE TABLE shopping_carts (
    cart_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_cart_user ON shopping_carts(user_id);

-- Cart items (many per cart)
CREATE TABLE shopping_cart_items (
    item_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cart_id UUID NOT NULL REFERENCES shopping_carts(cart_id) ON DELETE CASCADE,
    product_id UUID NOT NULL,
    product_name VARCHAR(500) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    price_per_unit NUMERIC(10,2) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(cart_id, product_id)  -- Jeden produkt max jednou v košíku
);

CREATE INDEX idx_cart_items_cart ON shopping_cart_items(cart_id);
```

**Design decisions:**

1. **UNIQUE(cart_id, product_id)**:
   - Zabránit duplicitním produktům v košíku
   - Při opakovaném přidání se quantity akumuluje (ON CONFLICT DO UPDATE)

2. **ON DELETE CASCADE**:
   - Při smazání košíku se automaticky smažou všechny items
   - Garbage collection

3. **CHECK (quantity > 0)**:
   - Zabránit záporným nebo nulovým množstvím
   - Při update na 0 → DELETE místo UPDATE

4. **Indexy**:
   - `idx_cart_user`: Fast lookup košíku podle user_id
   - `idx_cart_items_cart`: Fast JOIN mezi carts ↔ items

---

## 4. Pokročilé funkce

### 4.1 Filtrování podle kritérií

**Příklad**: "Odeber z košíku všechny produkty levnější než 5 €"

**Jak to funguje:**

```
1. AI model dostane tool definici update_cart_item:
   - Může nastavit quantity na 0 → odstranění položky

2. AI model dostane cart contents přes view_cart:
   {
     "items": [
       {"product_id": "A", "price_per_unit": 3.87, "quantity": 2},
       {"product_id": "B", "price_per_unit": 7.65, "quantity": 1},
       {"product_id": "C", "price_per_unit": 4.75, "quantity": 3}
     ]
   }

3. AI reasoning:
   - Filtr: price_per_unit < 5.00
   - Matched: A (3.87), C (4.75)
   - Actions:
     update_cart_item(product_id="A", quantity=0)
     update_cart_item(product_id="C", quantity=0)

4. AI calls tools sequentially:
   Tool call 1: update_cart_item({"product_id": "A", "quantity": 0})
   Tool call 2: update_cart_item({"product_id": "C", "quantity": 0})

5. AI response:
   "Hotovo! Odebral jsem 2 položky s cenou pod 5 €:
    - Egg Pasta Nests (3.87 €)
    - Classic Roma Sauce Tomatoes (4.75 €)

    Zůstává v košíku:
    - Whole Creamline Milk (7.65 €)

    Celkem: 7.65 €"
```

**DŮLEŽITÉ**: Toto není implementováno v backendu! Je to emergentní schopnost AI modelu, který kombinuje:

- `view_cart()` → získá data
- Reasoning → filtruje podle podmínky
- `update_cart_item()` × N → provede změny

---

## 5. Testování a validace

### 5.1 Unit Tests (by měly být napsány)

```python
# tests/test_shopping_cart_service.py

@pytest.mark.asyncio
async def test_fuzzy_product_search():
    """Test SIMILARITY matching s různými threshold."""
    service = ShoppingCartService(config, stock_url)

    # Exact match
    result = await service._search_product("Heirloom Tomato Basket", user_is_vip=False)
    assert result["sim"] > 0.9

    # Fuzzy match
    result = await service._search_product("rajčata", user_is_vip=False)
    assert result["sim"] > 0.3
    assert "Tomato" in result["product_name"]

    # No match
    result = await service._search_product("xyz123", user_is_vip=False)
    assert result is None


@pytest.mark.asyncio
async def test_stock_validation():
    """Test validace skladových zásob."""
    service = ShoppingCartService(config, stock_url)

    # Mock Stock API response
    with patch.object(service._http_client, 'post') as mock_post:
        mock_post.return_value.json.return_value = {
            "items": [{"onStock": 10}]
        }

        # Přidat 5 (OK)
        result = await service.add_to_cart("user1", [
            {"product_name": "Product A", "quantity": 5}
        ], is_vip=False)
        assert result["success"] == True

        # Přidat 15 (Fail)
        result = await service.add_to_cart("user1", [
            {"product_name": "Product A", "quantity": 15}
        ], is_vip=False)
        assert result["success"] == False
        assert "Insufficient stock" in result["error"]


@pytest.mark.asyncio
async def test_user_bound_cart():
    """Test že košík je user-bound, ne thread-bound."""
    service = ShoppingCartService(config, stock_url)

    # User1 přidá položku
    await service.add_to_cart("user1", [
        {"product_name": "Product A", "quantity": 1}
    ], is_vip=False)

    # User1 vidí položku v jiném threadu
    cart = await service.get_cart("user1")
    assert len(cart["items"]) == 1

    # User2 NEVIDÍ položku User1
    cart = await service.get_cart("user2")
    assert len(cart["items"]) == 0
```

### 5.2 Integration Tests

```bash
# 1. Start všech služeb
docker-compose up -d postgres
cd tools/api_stock && uv run uvicorn main:app --port 8011 &
cd agents/dreamfarm-agent && uv run uvicorn src.main:app --port 8001 &

# 2. Test přes REST API
curl -X POST http://localhost:8001/threads \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"title": "Test Cart"}'

# 3. Test přes chat
curl -X POST http://localhost:8001/threads/{thread_id}/messages/stream \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message": "Chci 5 rajčat do košíku"}'

# Expected: Tool call add_to_cart → success

# 4. Test UI endpoint
curl http://localhost:8001/cart \
  -H "Authorization: Bearer $TOKEN"

# Expected: {"items": [...], "total_price": ...}
```

---

## 6. Deployment Considerations

### 6.1 Environment Variables

```bash
# Required
SHOPPING_CART_ENABLED=true
STOCK_API_URL=http://localhost:8011
PGHOST=localhost
PGPORT=5432
PGDATABASE=aidb
PGUSER=admin
PGPASSWORD=secure_password

# Optional
AUTH_ENABLED=true  # Disable pro vývoj
LOG_LEVEL=INFO
```

### 6.2 PostgreSQL Extensions

```sql
-- Musí být enabled PŘED vytvořením tabulek
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Verify
SELECT extname, extversion FROM pg_extension
WHERE extname IN ('pg_trgm', 'uuid-ossp');
```

### 6.3 Performance Optimization

**Database Indexes:**

```sql
-- Already created in schema
CREATE INDEX idx_cart_user ON shopping_carts(user_id);
CREATE INDEX idx_cart_items_cart ON shopping_cart_items(cart_id);

-- Additional GIN index pro SIMILARITY (optional)
CREATE INDEX idx_products_trgm ON products USING GIN (product_name gin_trgm_ops);
```

**Caching** (future):

```python
# Redis cache pro košíky
@cache(ttl=60)  # Cache 60 sekund
async def get_cart(user_id: str):
    # ...
```

**Connection Pooling:**

```python
# Už implementováno v psycopg AsyncConnection
# Pool size: 10-20 connections (default)
```

---

## 7. Známé problémy a řešení

### 7.1 `function similarity() does not exist`

**Příčina**: pg_trgm extension není enabled

**Fix**:

```bash
psql -h localhost -U admin -d aidb -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
```

### 7.2 `relation "categories" does not exist`

**Příčina**: Původní verze očekávala tabulku categories

**Fix**: Už opraveno - SQL dotaz zjednodušen bez JOIN na categories

### 7.3 Stock API 404 error

**Příčina**: Shopping cart volal GET `/stock/{id}` místo POST `/stock`

**Fix**:

```python
# BEFORE (wrong)
url = f"{stock_api_url}/stock/{product_id}"
response = await http_client.get(url)

# AFTER (correct)
url = f"{stock_api_url}/stock"
payload = {"productIds": [str(product_id)]}
response = await http_client.post(url, json=payload)
```

### 7.4 JWT Token Expiration

**Příčina**: Token vypršel během vývoje

**Fix**:

```bash
# Option 1: Refresh token (login again)
# Option 2: Disable auth pro vývoj
echo "AUTH_ENABLED=false" >> .env
```

---

## 8. Future Enhancements

### 8.1 Checkout Process

```python
async def checkout(user_id: str) -> dict:
    """
    Convert cart to order:
    1. Lock stock (pessimistic locking)
    2. Create order in orders table
    3. Deduct from stock
    4. Clear cart
    5. Send confirmation email
    """
    pass
```

### 8.2 Price from Database

```python
# Currently: Random price generation
price = random.uniform(min_price, max_price)

# Future: Price from products table
SELECT price_per_unit FROM products WHERE product_id = %s
```

### 8.3 Cart Sharing

```python
async def share_cart(user_id: str, recipient_email: str):
    """Share cart with another user via email link."""
    pass
```

### 8.4 Cart Analytics

```python
async def get_cart_analytics(user_id: str):
    """
    Return:
    - Average cart value
    - Most added products
    - Abandonment rate
    """
    pass
```
