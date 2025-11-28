-- Shopping Cart Tables for DreamFarm Agent
-- Created: 2025-11-27
-- Purpose: User-bound shopping cart with stock validation and random pricing

-- Main shopping carts table (one cart per user)
CREATE TABLE IF NOT EXISTS shopping_carts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL UNIQUE,  -- Keycloak user ID
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast user lookup
CREATE INDEX IF NOT EXISTS idx_shopping_carts_user_id ON shopping_carts(user_id);

-- Shopping cart items (products in cart)
CREATE TABLE IF NOT EXISTS shopping_cart_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cart_id UUID NOT NULL REFERENCES shopping_carts(id) ON DELETE CASCADE,
    product_id UUID NOT NULL,  -- References products.product_id (UUID column)
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(10, 2) NOT NULL CHECK (unit_price > 0),  -- Random price generated at add time
    added_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(cart_id, product_id),  -- One product can appear only once per cart
    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_cart_items_cart_id ON shopping_cart_items(cart_id);
CREATE INDEX IF NOT EXISTS idx_cart_items_product_id ON shopping_cart_items(product_id);

-- Trigger to update updated_at timestamp on shopping_carts
CREATE OR REPLACE FUNCTION update_shopping_cart_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE shopping_carts
    SET updated_at = NOW()
    WHERE id = NEW.cart_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_cart_timestamp
AFTER INSERT OR UPDATE OR DELETE ON shopping_cart_items
FOR EACH ROW
EXECUTE FUNCTION update_shopping_cart_timestamp();

-- Comment the tables
COMMENT ON TABLE shopping_carts IS 'User shopping carts - one cart per user_id';
COMMENT ON TABLE shopping_cart_items IS 'Items in shopping carts with quantities and prices';
COMMENT ON COLUMN shopping_cart_items.unit_price IS 'Random price generated when item first added to cart';
