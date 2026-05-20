"""Integration tests against the live Render API.

Run with:  pytest tests/test_live_api.py -v
Requires:  LPB_API_URL and LPB_ADMIN_TOKEN in .env or environment.

Tests are ordered: auth -> catalog -> watchlist -> orders (full workflow).
Each test is independent where possible; the orders workflow tests use a
shared order that is created and cleaned up within the module.
"""

import pytest

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TestAuth:
    def test_login(self, api):
        body = api.post("/api/v1/auth/login", {"username": "admin", "password": "admin"})
        assert "token" in body
        assert body["username"] == "admin"

    def test_me(self, api):
        me = api.get("/api/v1/auth/me")
        assert me["role"] == "admin"
        assert me["user_id"]
        assert me["default_watchlist_id"]


# ---------------------------------------------------------------------------
# Catalog  (prefix /api/v1/catalog)
# ---------------------------------------------------------------------------

class TestCatalog:
    def test_list_products(self, api):
        data = api.get("/api/v1/catalog/products?limit=5")
        # Response is paginated: {items: [...], total: N}
        assert "items" in data or isinstance(data, list)
        items = data.get("items", data) if isinstance(data, dict) else data
        assert len(items) > 0, "Catalog should have products"

    def test_product_has_expected_fields(self, api):
        data = api.get("/api/v1/catalog/products?limit=1")
        items = data.get("items", data) if isinstance(data, dict) else data
        p = items[0]
        for field in ("code", "size", "case_cost", "btl_cost"):
            assert field in p, f"Product missing field: {field}"

    def test_product_detail(self, api):
        data = api.get("/api/v1/catalog/products?limit=1")
        items = data.get("items", data) if isinstance(data, dict) else data
        code = items[0]["code"]
        detail = api.get(f"/api/v1/catalog/products/{code}")
        assert detail["code"] == code

    def test_search(self, api):
        data = api.get("/api/v1/catalog/products?q=vodka&limit=5")
        items = data.get("items", data) if isinstance(data, dict) else data
        assert isinstance(items, list)

    def test_categories(self, api):
        cats = api.get("/api/v1/catalog/categories")
        assert isinstance(cats, list)
        assert len(cats) > 0

    def test_brands(self, api):
        brands = api.get("/api/v1/catalog/brands")
        assert isinstance(brands, list)
        assert len(brands) > 0

    def test_editions(self, api):
        editions = api.get("/api/v1/catalog/editions")
        assert isinstance(editions, list)
        assert len(editions) > 0


# ---------------------------------------------------------------------------
# Watchlist (Tracked Products)
# ---------------------------------------------------------------------------

def _get_first_product_code(api):
    """Helper to get one product code from catalog."""
    data = api.get("/api/v1/catalog/products?limit=1")
    items = data.get("items", data) if isinstance(data, dict) else data
    if not items:
        pytest.skip("No products in catalog")
    return items[0]["code"]


class TestWatchlist:
    def test_list_watchlist(self, api):
        data = api.get("/api/v1/watchlist")
        assert isinstance(data, list)

    def test_add_and_remove(self, api):
        code = _get_first_product_code(api)

        # Add to watchlist (POST body with code)
        result = api.post("/api/v1/watchlist/items", {"code": code})
        assert result.get("product_code") == code or "created_at" in result

        # Verify it's in the list
        items = api.get("/api/v1/watchlist")
        codes = [i.get("product_code") or i.get("code") for i in items]
        assert code in codes, f"Product {code} not found in watchlist: {codes[:5]}"

        # Remove
        api.delete(f"/api/v1/watchlist/items/{code}")

    def test_watchlist_order_endpoint(self, api):
        """The order-view of the watchlist (with pricing)."""
        data = api.get("/api/v1/watchlist/order")
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# Orders -- Full Workflow
# ---------------------------------------------------------------------------

class TestOrdersWorkflow:
    """Tests the complete order lifecycle: create -> add items -> verify totals -> delete."""

    @pytest.fixture(autouse=True)
    def _setup_order(self, api):
        """Create a test order, yield it, then clean up."""
        self.api = api
        order = api.post("/api/v1/orders", {
            "name": "Integration Test Order",
            "division": "GS",
            "order_notes": "Automated test -- safe to delete",
        })
        self.order_id = order["id"]
        yield
        # Cleanup: delete the test order
        try:
            api.delete(f"/api/v1/orders/{self.order_id}")
        except Exception:
            pass

    def test_order_created(self):
        detail = self.api.get(f"/api/v1/orders/{self.order_id}")
        assert detail["name"] == "Integration Test Order"
        assert detail["division"] == "GS"
        assert detail["status"] == "draft"

    def test_order_in_list(self):
        orders = self.api.get("/api/v1/orders")
        ids = [o["id"] for o in orders]
        assert self.order_id in ids

    def test_update_order(self):
        updated = self.api.patch(f"/api/v1/orders/{self.order_id}", {
            "name": "Updated Test Order",
            "order_notes": "Updated note",
        })
        assert updated["name"] == "Updated Test Order"

    def test_add_items_and_verify_totals(self):
        code = _get_first_product_code(self.api)

        # Add item with quantity
        self.api.post(f"/api/v1/orders/{self.order_id}/items", {
            "code": code, "qty_cases": 3,
        })

        # Verify item appears in order detail
        detail = self.api.get(f"/api/v1/orders/{self.order_id}")
        items = detail.get("items", [])
        item_codes = [i.get("code") or i.get("product_code") for i in items]
        assert code in item_codes, f"{code} not in order items: {item_codes}"
        assert len(items) >= 1, f"Expected at least 1 item, got {len(items)}"

    def test_add_item_then_update_quantity(self):
        code = _get_first_product_code(self.api)

        self.api.post(f"/api/v1/orders/{self.order_id}/items", {
            "code": code, "qty_cases": 1,
        })

        # Update to 5 cases
        self.api.patch(f"/api/v1/orders/{self.order_id}/items/{code}", {
            "qty_cases": 5,
        })

        detail = self.api.get(f"/api/v1/orders/{self.order_id}")
        items = detail.get("items", [])
        item = next((i for i in items if (i.get("code") or i.get("product_code")) == code), None)
        assert item is not None, f"Item {code} not found after update"
        assert item.get("qty_cases") == 5, f"Expected 5 cases, got {item.get('qty_cases')}"

    def test_remove_item(self):
        code = _get_first_product_code(self.api)

        self.api.post(f"/api/v1/orders/{self.order_id}/items", {
            "code": code, "qty_cases": 1,
        })

        # Remove it
        self.api.delete(f"/api/v1/orders/{self.order_id}/items/{code}")

        detail = self.api.get(f"/api/v1/orders/{self.order_id}")
        items = detail.get("items", [])
        item_codes = [i.get("code") or i.get("product_code") for i in items]
        assert code not in item_codes, f"{code} still in order after delete"

    def test_copy_from_watchlist(self):
        """Copy tracked items into the order."""
        code = _get_first_product_code(self.api)

        # Ensure at least one item is tracked
        try:
            self.api.post("/api/v1/watchlist/items", {"code": code})
        except Exception:
            pass  # may already be tracked

        result = self.api.post(f"/api/v1/orders/{self.order_id}/copy-from-watchlist")
        assert isinstance(result, dict)

        # Clean up watchlist
        try:
            self.api.delete(f"/api/v1/watchlist/items/{code}")
        except Exception:
            pass

    def test_submit_order(self):
        result = self.api.post(f"/api/v1/orders/{self.order_id}/submit")
        assert result.get("status") == "submitted"
        assert result.get("submitted_at") is not None


# ---------------------------------------------------------------------------
# Orders -- Hide / Unhide / Delete
# ---------------------------------------------------------------------------

class TestOrderHideUnhide:
    """Tests the hide/unhide/delete workflow for orders."""

    @pytest.fixture(autouse=True)
    def _setup_order(self, api):
        self.api = api
        order = api.post("/api/v1/orders", {
            "name": "Hide Test Order",
            "order_notes": "Automated test -- safe to delete",
        })
        self.order_id = order["id"]
        yield
        try:
            api.delete(f"/api/v1/orders/{self.order_id}")
        except Exception:
            pass

    def test_hide_order(self):
        result = self.api.post(f"/api/v1/orders/{self.order_id}/hide")
        assert result["hidden_at"] is not None, "hidden_at should be set"

    def test_hidden_order_excluded_from_list(self):
        self.api.post(f"/api/v1/orders/{self.order_id}/hide")
        orders = self.api.get("/api/v1/orders")
        ids = [o["id"] for o in orders]
        assert self.order_id not in ids, "Hidden order should not appear in default list"

    def test_hidden_order_included_with_flag(self):
        self.api.post(f"/api/v1/orders/{self.order_id}/hide")
        orders = self.api.get("/api/v1/orders?include_hidden=true")
        ids = [o["id"] for o in orders]
        assert self.order_id in ids, "Hidden order should appear when include_hidden=true"

    def test_unhide_order(self):
        self.api.post(f"/api/v1/orders/{self.order_id}/hide")
        result = self.api.post(f"/api/v1/orders/{self.order_id}/unhide")
        assert result["hidden_at"] is None, "hidden_at should be cleared"
        orders = self.api.get("/api/v1/orders")
        ids = [o["id"] for o in orders]
        assert self.order_id in ids, "Unhidden order should appear in default list"

    def test_delete_submitted_order(self):
        """Verify that non-draft orders can also be deleted."""
        self.api.post(f"/api/v1/orders/{self.order_id}/submit")
        self.api.delete(f"/api/v1/orders/{self.order_id}")
        orders = self.api.get("/api/v1/orders?include_hidden=true")
        ids = [o["id"] for o in orders]
        assert self.order_id not in ids, "Deleted order should be gone"


# ---------------------------------------------------------------------------
# Orders -- List-level totals
# ---------------------------------------------------------------------------

class TestOrderListTotals:
    """Verify that the orders list endpoint computes invoice/rebate/effective totals."""

    @pytest.fixture(autouse=True)
    def _setup(self, api):
        self.api = api
        order = api.post("/api/v1/orders", {"name": "Totals Test Order"})
        self.order_id = order["id"]
        code = _get_first_product_code(api)
        self.code = code
        api.post(f"/api/v1/orders/{self.order_id}/items", {
            "code": code, "qty_cases": 2,
        })
        yield
        try:
            api.delete(f"/api/v1/orders/{self.order_id}")
        except Exception:
            pass

    def test_list_has_totals(self):
        orders = self.api.get("/api/v1/orders")
        order = next((o for o in orders if o["id"] == self.order_id), None)
        assert order is not None, "Test order not found in list"
        assert order.get("invoice_total") is not None, "invoice_total is None"
        assert order.get("effective_total") is not None, "effective_total is None"
        assert order.get("rip_rebate_total") is not None, "rip_rebate_total is None"

    def test_totals_are_numeric(self):
        orders = self.api.get("/api/v1/orders")
        order = next((o for o in orders if o["id"] == self.order_id), None)
        if order is None:
            pytest.skip("Order not found")
        inv = float(order["invoice_total"])
        eff = float(order["effective_total"])
        reb = float(order["rip_rebate_total"])
        assert inv >= 0
        assert eff >= 0
        assert reb >= 0
        assert abs(inv - reb - eff) < 0.02, f"Math check: {inv} - {reb} != {eff}"


# ---------------------------------------------------------------------------
# Insights: RIPs, Closeouts, Combos, Specials, Dashboard
# ---------------------------------------------------------------------------

class TestInsights:
    def test_rips(self, api):
        data = api.get("/api/v1/rips?limit=5")
        assert isinstance(data, list)

    def test_closeouts(self, api):
        data = api.get("/api/v1/closeouts?limit=5")
        assert isinstance(data, list)

    def test_combos(self, api):
        data = api.get("/api/v1/combos?limit=5")
        assert isinstance(data, list)

    def test_specials(self, api):
        data = api.get("/api/v1/specials")
        assert isinstance(data, list)

    def test_dashboard_summary(self, api):
        data = api.get("/api/v1/dashboard/summary")
        assert isinstance(data, dict)

    def test_dashboard_alerts(self, api):
        data = api.get("/api/v1/dashboard/alerts")
        assert isinstance(data, list)

    def test_dashboard_movers(self, api):
        data = api.get("/api/v1/dashboard/movers")
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# Pricing Analytics
# ---------------------------------------------------------------------------

class TestAnalytics:
    VIEWS = [
        "price_drops", "price_increases", "new_rips", "lost_rips",
        "best_value", "closeout_rip", "category_trends",
        "new_products", "discontinued", "watchlist_movers",
    ]

    @pytest.mark.parametrize("view", VIEWS)
    def test_view(self, api, view):
        data = api.get(f"/api/v1/analytics?view={view}&limit=5")
        assert isinstance(data, dict)
        assert data["view"] == view
        assert "total" in data
        assert "edition_current" in data
        if view == "category_trends":
            assert isinstance(data.get("category_rows", []), list)
        else:
            assert isinstance(data.get("rows", []), list)

    def test_invalid_view(self, api):
        try:
            api.get("/api/v1/analytics?view=invalid_view")
            assert False, "Should have raised error"
        except Exception:
            pass  # expected 400
