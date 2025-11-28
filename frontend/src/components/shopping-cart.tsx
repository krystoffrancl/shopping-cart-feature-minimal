import { useState, useEffect } from 'react';
import { getCart, updateCartItem } from '../services/api';

interface CartItem {
  product_id: string;
  product_name: string;
  quantity: number;
  unit_price: number;
  total_price: number;
  available_stock: number;
}

interface CartData {
  items: CartItem[];
  total_items: number;
  total_price: number;
  currency: string;
}

export function ShoppingCartButton() {
  const [isOpen, setIsOpen] = useState(false);
  const [cartData, setCartData] = useState<CartData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch cart data when modal opens
  useEffect(() => {
    if (isOpen) {
      loadCart();
    }
  }, [isOpen]);

  // Listen for cart updates from chat
  useEffect(() => {
    const handleCartUpdate = () => {
      if (isOpen) {
        loadCart();
      }
    };
    window.addEventListener('df-cart-updated', handleCartUpdate);
    return () => window.removeEventListener('df-cart-updated', handleCartUpdate);
  }, [isOpen]);

  const loadCart = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getCart();
      setCartData(data);
    } catch (err: any) {
      setError(err.message || 'Failed to load cart');
      console.error('Failed to load cart:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateQuantity = async (productId: string, newQuantity: number) => {
    try {
      await updateCartItem(productId, newQuantity);
      await loadCart(); // Reload cart after update
      // Notify chat about cart change
      window.dispatchEvent(new CustomEvent('df-cart-updated'));
    } catch (err: any) {
      alert(`Failed to update cart: ${err.message}`);
    }
  };

  const handleRemoveItem = async (productId: string) => {
    await handleUpdateQuantity(productId, 0);
  };

  return (
    <>
      {/* Cart Icon Button */}
      <button
        onClick={() => setIsOpen(true)}
        className="relative flex items-center gap-2 px-3 py-1.5 border rounded-md hover:bg-gray-100 transition"
        aria-label="Shopping cart"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-5 w-5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z"
          />
        </svg>
        {cartData && cartData.total_items > 0 && (
          <span className="absolute -top-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full bg-green-600 text-xs text-white font-semibold">
            {cartData.total_items}
          </span>
        )}
      </button>

      {/* Cart Modal */}
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b">
              <h2 className="text-xl font-semibold">Shopping Cart</h2>
              <button
                onClick={() => setIsOpen(false)}
                className="text-gray-500 hover:text-gray-700"
                aria-label="Close"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="h-6 w-6"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4">
              {loading && (
                <div className="text-center text-gray-600 py-8">Loading cart...</div>
              )}

              {error && (
                <div className="text-center text-red-600 py-8">{error}</div>
              )}

              {!loading && !error && cartData && cartData.items.length === 0 && (
                <div className="text-center text-gray-600 py-8">
                  <p>Your cart is empty</p>
                  <p className="text-sm mt-2">Add products by chatting with the assistant!</p>
                </div>
              )}

              {!loading && !error && cartData && cartData.items.length > 0 && (
                <div className="space-y-3">
                  {cartData.items.map((item) => (
                    <div
                      key={item.product_id}
                      className="flex items-center gap-4 p-3 border rounded-lg hover:bg-gray-50"
                    >
                      <div className="flex-1">
                        <h3 className="font-medium text-gray-900">{item.product_name}</h3>
                        <p className="text-sm text-gray-600">
                          {item.unit_price.toFixed(2)} {cartData.currency} / unit
                        </p>
                        <p className="text-xs text-gray-500">
                          Available stock: {item.available_stock}
                        </p>
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleUpdateQuantity(item.product_id, item.quantity - 1)}
                          disabled={item.quantity <= 1}
                          className="px-2 py-1 border rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                          aria-label="Decrease quantity"
                        >
                          −
                        </button>
                        <span className="w-12 text-center font-medium">{item.quantity}</span>
                        <button
                          onClick={() => handleUpdateQuantity(item.product_id, item.quantity + 1)}
                          disabled={item.quantity >= item.available_stock}
                          className="px-2 py-1 border rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                          aria-label="Increase quantity"
                        >
                          +
                        </button>
                      </div>

                      <div className="text-right min-w-[80px]">
                        <p className="font-semibold text-gray-900">
                          {item.total_price.toFixed(2)} {cartData.currency}
                        </p>
                      </div>

                      <button
                        onClick={() => handleRemoveItem(item.product_id)}
                        className="text-red-600 hover:text-red-800 p-1"
                        aria-label="Remove item"
                      >
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          className="h-5 w-5"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                          />
                        </svg>
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Footer with Total */}
            {!loading && !error && cartData && cartData.items.length > 0 && (
              <div className="border-t p-4 bg-gray-50">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-gray-700">Total ({cartData.total_items} items):</span>
                  <span className="text-2xl font-bold text-green-600">
                    {cartData.total_price.toFixed(2)} {cartData.currency}
                  </span>
                </div>
                <button
                  onClick={() => setIsOpen(false)}
                  className="w-full px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 transition font-medium"
                >
                  Continue Shopping
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
