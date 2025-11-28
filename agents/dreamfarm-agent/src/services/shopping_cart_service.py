"""Shopping cart service for DreamFarm Agent.

User-bound shopping cart with stock validation and random pricing.
"""

import logging
import os
import random
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
import psycopg
from psycopg.rows import dict_row

from src.services.config_service import AppConfig

logger = logging.getLogger(__name__)


# Price ranges by category (min, max) in EUR
PRICE_RANGES = {
    "Vegetables": (2.0, 8.0),
    "Fruits": (3.0, 10.0),
    "Dairy": (1.0, 5.0),
    "Meat": (8.0, 25.0),
    "Bakery": (2.0, 6.0),
    "Seafood": (10.0, 30.0),
    "Beverages": (1.5, 8.0),
    "Grains": (1.5, 6.0),
    "Snacks": (2.0, 8.0),
    "Condiments": (1.5, 7.0),
}
DEFAULT_PRICE_RANGE = (2.0, 10.0)


class ShoppingCartService:
    """Service for managing user shopping carts."""

    def __init__(self, config: AppConfig, stock_api_url: str):
        """Initialize shopping cart service.

        Args:
            config: Application configuration (not used, kept for compatibility)
            stock_api_url: Base URL for stock API (e.g., http://localhost:8011)
        """
        self._config = config
        self._stock_api_url = stock_api_url.rstrip("/")
        self._http_client = httpx.AsyncClient(timeout=10.0)

        # Build PostgreSQL connection string from environment variables
        db_host = os.getenv("PGHOST", "localhost")
        db_port = os.getenv("PGPORT", "5432")
        db_name = os.getenv("PGDATABASE", "aidb")
        db_user = os.getenv("PGUSER", "admin")
        db_password = os.getenv("PGPASSWORD", "")

        self._db_url = (
            f"postgresql://{db_user}:{db_password}"
            f"@{db_host}:{db_port}/{db_name}"
        )
        logger.info(
            "Initialized ShoppingCartService (stock_api=%s, db=%s@%s:%s)",
            self._stock_api_url,
            db_name,
            db_host,
            db_port,
        )

    async def close(self):
        """Close HTTP client."""
        await self._http_client.aclose()

    def _generate_price(self, category: str | None) -> Decimal:
        """Generate random price based on product category.

        Args:
            category: Product category (e.g., "Vegetables", "Fruits")

        Returns:
            Random price as Decimal with 2 decimal places
        """
        min_price, max_price = PRICE_RANGES.get(category or "", DEFAULT_PRICE_RANGE)
        price = random.uniform(min_price, max_price)
        return Decimal(str(round(price, 2)))

    async def _get_stock_quantity(self, product_id: UUID) -> int:
        """Get current stock quantity for a product.

        Args:
            product_id: UUID of the product

        Returns:
            Current stock quantity (0 if not available or error)
        """
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
            logger.warning("Failed to get stock for product %s: %s", product_id, e)
            return 0

    async def _search_product(
        self,
        product_name: str,
        user_is_vip: bool,
        category: str | None = None,
        is_organic: bool | None = None,
    ) -> dict[str, Any] | None:
        """Search for a product by name with optional filters.

        Uses PostgreSQL SIMILARITY function for fuzzy matching.

        Args:
            product_name: Product name to search for
            user_is_vip: Whether user has VIP access
            category: Optional category filter
            is_organic: Optional organic filter

        Returns:
            Product dict with keys: product_id, product_name, category, is_organic
            None if no match found
        """
        async with await psycopg.AsyncConnection.connect(
            self._db_url, row_factory=dict_row
        ) as conn:
            async with conn.cursor() as cur:
                # Build query with VIP fencing (simplified - no categories table)
                query = """
                    SELECT
                        product_id,
                        product_name,
                        'Unknown' AS category,
                        false AS is_organic,
                        SIMILARITY(product_name, %s) AS sim
                    FROM products
                    WHERE (is_vip = false OR %s = true)
                      AND SIMILARITY(product_name, %s) > 0.3
                    ORDER BY sim DESC
                    LIMIT 1
                """
                params: list[Any] = [product_name, user_is_vip, product_name]

                await cur.execute(query, params)
                result = await cur.fetchone()

                if result:
                    logger.info(
                        "Found product: %s (similarity=%.2f)",
                        result["product_name"],
                        result["sim"],
                    )
                return result

    async def add_to_cart(
        self,
        user_id: str,
        items: list[dict[str, Any]],
        user_is_vip: bool = False,
    ) -> dict[str, Any]:
        """Add one or more products to user's shopping cart.

        Args:
            user_id: User ID (from Keycloak)
            items: List of items, each with:
                - product_name: str (required)
                - quantity: int (required)
                - category: str (optional filter)
                - is_organic: bool (optional filter)
            user_is_vip: Whether user has VIP access

        Returns:
            Dict with:
                - success: bool
                - added_items: list of successfully added items
                - failed_items: list of items that failed with reasons
                - cart_total: float (total cart value)
                - total_items: int (total number of items in cart)
        """
        added_items = []
        failed_items = []

        async with await psycopg.AsyncConnection.connect(self._db_url) as conn:
            async with conn.cursor() as cur:
                # Ensure cart exists for user
                await cur.execute(
                    """
                    INSERT INTO shopping_carts (user_id, created_at, updated_at)
                    VALUES (%s, NOW(), NOW())
                    ON CONFLICT (user_id) DO UPDATE SET updated_at = NOW()
                    RETURNING id
                    """,
                    (user_id,),
                )
                cart_result = await cur.fetchone()
                cart_id = cart_result[0] if cart_result else None

                if not cart_id:
                    return {
                        "success": False,
                        "error": "Failed to create or retrieve cart",
                        "added_items": [],
                        "failed_items": items,
                    }

                # Process each item
                for item in items:
                    product_name = item.get("product_name", "").strip()
                    quantity = item.get("quantity", 1)
                    category_filter = item.get("category")
                    is_organic_filter = item.get("is_organic")

                    if not product_name:
                        failed_items.append(
                            {
                                "product_name": product_name,
                                "error": "Product name is required",
                            }
                        )
                        continue

                    if quantity <= 0:
                        failed_items.append(
                            {
                                "product_name": product_name,
                                "error": "Quantity must be positive",
                            }
                        )
                        continue

                    # Search for product
                    product = await self._search_product(
                        product_name, user_is_vip, category_filter, is_organic_filter
                    )

                    if not product:
                        failed_items.append(
                            {
                                "product_name": product_name,
                                "error": "Product not found",
                                "requested_quantity": quantity,
                            }
                        )
                        continue

                    product_id = product["product_id"]

                    # Check stock availability
                    available_stock = await self._get_stock_quantity(product_id)
                    if quantity > available_stock:
                        failed_items.append(
                            {
                                "product_name": product["product_name"],
                                "product_id": str(product_id),
                                "requested_quantity": quantity,
                                "available_stock": available_stock,
                                "error": f"Insufficient stock (only {available_stock} available)",
                            }
                        )
                        continue

                    # Generate price (only on first add)
                    unit_price = self._generate_price(product.get("category"))

                    # Add or update cart item
                    await cur.execute(
                        """
                        INSERT INTO shopping_cart_items
                            (cart_id, product_id, quantity, unit_price, added_at, updated_at)
                        VALUES (%s, %s, %s, %s, NOW(), NOW())
                        ON CONFLICT (cart_id, product_id)
                        DO UPDATE SET
                            quantity = shopping_cart_items.quantity + EXCLUDED.quantity,
                            updated_at = NOW()
                        RETURNING quantity, unit_price
                        """,
                        (cart_id, product_id, quantity, unit_price),
                    )
                    result = await cur.fetchone()
                    final_quantity = result[0] if result else quantity
                    final_price = result[1] if result else unit_price

                    # Re-check stock after potential increment
                    if final_quantity > available_stock:
                        # Rollback this item (set to available stock)
                        await cur.execute(
                            """
                            UPDATE shopping_cart_items
                            SET quantity = %s, updated_at = NOW()
                            WHERE cart_id = %s AND product_id = %s
                            """,
                            (available_stock, cart_id, product_id),
                        )
                        failed_items.append(
                            {
                                "product_name": product["product_name"],
                                "product_id": str(product_id),
                                "requested_quantity": quantity,
                                "available_stock": available_stock,
                                "error": f"Reduced quantity to available stock ({available_stock})",
                            }
                        )
                        final_quantity = available_stock

                    added_items.append(
                        {
                            "product_id": str(product_id),
                            "product_name": product["product_name"],
                            "quantity": quantity,
                            "unit_price": float(final_price),
                            "total_price": float(final_price * final_quantity),
                        }
                    )

                await conn.commit()

        # Get cart totals
        cart_summary = await self.get_cart(user_id)

        return {
            "success": len(failed_items) == 0,
            "added_items": added_items,
            "failed_items": failed_items,
            "cart_total": cart_summary.get("total_price", 0.0),
            "total_items": cart_summary.get("total_items", 0),
        }

    async def get_cart(self, user_id: str) -> dict[str, Any]:
        """Get user's shopping cart contents.

        Args:
            user_id: User ID

        Returns:
            Dict with:
                - items: list of cart items
                - total_items: int (total quantity across all products)
                - total_price: float
                - currency: str ("EUR")
        """
        async with await psycopg.AsyncConnection.connect(
            self._db_url, row_factory=dict_row
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT
                        sci.product_id,
                        p.product_name,
                        sci.quantity,
                        sci.unit_price,
                        (sci.quantity * sci.unit_price) AS total_price,
                        sci.added_at,
                        sci.updated_at
                    FROM shopping_carts sc
                    JOIN shopping_cart_items sci ON sci.cart_id = sc.id
                    JOIN products p ON p.product_id = sci.product_id
                    WHERE sc.user_id = %s
                    ORDER BY sci.added_at DESC
                    """,
                    (user_id,),
                )
                rows = await cur.fetchall()

                items = []
                total_items = 0
                total_price = Decimal(0)

                for row in rows:
                    # Get current stock for each item
                    stock = await self._get_stock_quantity(row["product_id"])

                    item = {
                        "product_id": str(row["product_id"]),
                        "product_name": row["product_name"],
                        "quantity": row["quantity"],
                        "unit_price": float(row["unit_price"]),
                        "total_price": float(row["total_price"]),
                        "available_stock": stock,
                        "added_at": row["added_at"].isoformat(),
                        "updated_at": row["updated_at"].isoformat(),
                    }
                    items.append(item)
                    total_items += row["quantity"]
                    total_price += row["total_price"]

                return {
                    "items": items,
                    "total_items": total_items,
                    "total_price": float(total_price),
                    "currency": "EUR",
                }

    async def update_cart_item(
        self, user_id: str, product_id: str, quantity: int
    ) -> dict[str, Any]:
        """Update quantity of item in cart.

        Args:
            user_id: User ID
            product_id: Product UUID
            quantity: New quantity (0 to remove)

        Returns:
            Dict with success status and cart summary
        """
        try:
            product_uuid = UUID(product_id)
        except ValueError:
            return {"success": False, "error": "Invalid product ID"}

        if quantity < 0:
            return {"success": False, "error": "Quantity cannot be negative"}

        # Check stock if increasing
        if quantity > 0:
            available_stock = await self._get_stock_quantity(product_uuid)
            if quantity > available_stock:
                return {
                    "success": False,
                    "error": f"Insufficient stock (only {available_stock} available)",
                    "available_stock": available_stock,
                }

        async with await psycopg.AsyncConnection.connect(self._db_url) as conn:
            async with conn.cursor() as cur:
                # Get cart_id
                await cur.execute(
                    "SELECT id FROM shopping_carts WHERE user_id = %s", (user_id,)
                )
                cart_result = await cur.fetchone()
                if not cart_result:
                    return {"success": False, "error": "Cart not found"}

                cart_id = cart_result[0]

                if quantity == 0:
                    # Remove item
                    await cur.execute(
                        """
                        DELETE FROM shopping_cart_items
                        WHERE cart_id = %s AND product_id = %s
                        """,
                        (cart_id, product_uuid),
                    )
                else:
                    # Update quantity
                    await cur.execute(
                        """
                        UPDATE shopping_cart_items
                        SET quantity = %s, updated_at = NOW()
                        WHERE cart_id = %s AND product_id = %s
                        """,
                        (quantity, cart_id, product_uuid),
                    )

                await conn.commit()

        cart_summary = await self.get_cart(user_id)
        return {"success": True, "cart": cart_summary}

    async def remove_from_cart(self, user_id: str, product_id: str) -> dict[str, Any]:
        """Remove specific product from cart.

        Args:
            user_id: User ID
            product_id: Product UUID

        Returns:
            Dict with success status and cart summary
        """
        return await self.update_cart_item(user_id, product_id, 0)

    async def clear_cart(self, user_id: str) -> dict[str, Any]:
        """Remove all items from cart.

        Args:
            user_id: User ID

        Returns:
            Dict with success status
        """
        async with await psycopg.AsyncConnection.connect(self._db_url) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    DELETE FROM shopping_cart_items
                    WHERE cart_id IN (
                        SELECT id FROM shopping_carts WHERE user_id = %s
                    )
                    """,
                    (user_id,),
                )
                await conn.commit()

        return {"success": True, "message": "Cart cleared"}
