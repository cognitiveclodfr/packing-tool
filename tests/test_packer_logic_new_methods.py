"""
Tests for new PackerLogic methods:
  - cancel_sku_scan
  - force_complete_sku (replaces reset_sku_scan)
  - skip_order (now preserves in_progress state)
  - current_order_metadata
  - order metadata extraction in load_packing_list_json / load_from_shopify_analysis
"""
import json
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from packer_logic import PackerLogic


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_pm():
    pm = MagicMock()
    pm.load_sku_mapping.return_value = {}
    return pm


@pytest.fixture
def tmp_work(tmp_path):
    work = tmp_path / "packing" / "TestList"
    work.mkdir(parents=True)
    return work


@pytest.fixture
def logic(mock_pm, tmp_work):
    return PackerLogic(client_id="TEST", profile_manager=mock_pm, work_dir=str(tmp_work))


def _seed_order(logic_instance, order_number="ORD-001", sku="SKU-A", quantity=2):
    """Helper: directly populate orders_data and start packing."""
    logic_instance.orders_data = {
        order_number: {
            "items": [{"SKU": sku, "Quantity": str(quantity), "Product_Name": "Test Product",
                        "Order_Number": order_number, "Courier": "DHL"}],
            "metadata": {"courier": "DHL", "status": "Fulfillable"}
        }
    }
    logic_instance.session_packing_state = {
        "in_progress": {}, "completed_orders": [], "skipped_orders": []
    }
    items, status = logic_instance.start_order_packing(order_number)
    assert status == "ORDER_LOADED"
    return items


# ── cancel_sku_scan ───────────────────────────────────────────────────────────

class TestCancelSkuScan:
    def test_decrement_packed_count(self, logic):
        _seed_order(logic, sku="SKU-A", quantity=2)
        logic.process_sku_scan("SKU-A")

        result, status = logic.cancel_sku_scan("SKU-A")
        assert status == "SKU_CANCELLED"
        assert result is not None
        assert result["packed"] == 0
        assert result["is_complete"] is False

    def test_decrement_partial(self, logic):
        _seed_order(logic, sku="SKU-A", quantity=3)
        logic.process_sku_scan("SKU-A")
        logic.process_sku_scan("SKU-A")

        result, status = logic.cancel_sku_scan("SKU-A")
        assert status == "SKU_CANCELLED"
        assert result["packed"] == 1

    def test_undo_completed_item(self, logic):
        """Can decrement a fully-packed (completed) item back to in-progress."""
        _seed_order(logic, sku="SKU-A", quantity=2)
        logic.process_sku_scan("SKU-A")
        logic.process_sku_scan("SKU-A")
        # Item is now complete (packed=2, required=2)

        result, status = logic.cancel_sku_scan("SKU-A")
        assert status == "SKU_CANCELLED"
        assert result["packed"] == 1
        assert result["is_complete"] is False

    def test_already_zero(self, logic):
        _seed_order(logic, sku="SKU-A", quantity=2)
        result, status = logic.cancel_sku_scan("SKU-A")
        assert status == "SKU_ALREADY_ZERO"
        assert result is None

    def test_sku_not_found(self, logic):
        _seed_order(logic, sku="SKU-A", quantity=1)
        result, status = logic.cancel_sku_scan("NONEXISTENT")
        assert status == "SKU_NOT_FOUND"

    def test_no_active_order(self, logic):
        result, status = logic.cancel_sku_scan("SKU-A")
        assert status == "NO_ACTIVE_ORDER"


# ── force_complete_sku ────────────────────────────────────────────────────────

class TestForceCompleteSku:
    def test_force_complete_sets_packed_to_required(self, logic):
        """Force-complete on a multi-SKU order returns SKU_FORCE_COMPLETED, not ORDER_COMPLETE."""
        # Seed order with two distinct SKUs so completing one doesn't end the order
        logic.orders_data = {
            "ORD-001": {
                "items": [
                    {"SKU": "SKU-A", "Quantity": "3", "Product_Name": "Prod A",
                     "Order_Number": "ORD-001", "Courier": "DHL"},
                    {"SKU": "SKU-B", "Quantity": "1", "Product_Name": "Prod B",
                     "Order_Number": "ORD-001", "Courier": "DHL"},
                ],
                "metadata": {"courier": "DHL"}
            }
        }
        logic.session_packing_state = {"in_progress": {}, "completed_orders": [], "skipped_orders": []}
        logic.start_order_packing("ORD-001")
        logic.process_sku_scan("SKU-A")  # packed=1 of 3

        result, status = logic.force_complete_sku("SKU-A")
        assert status == "SKU_FORCE_COMPLETED"
        assert result["packed"] == 3  # = required
        assert result["is_complete"] is True

    def test_force_complete_when_not_yet_scanned(self, logic):
        _seed_order(logic, sku="SKU-A", quantity=2)

        result, status = logic.force_complete_sku("SKU-A")
        assert status in ("SKU_FORCE_COMPLETED", "ORDER_COMPLETE")
        assert result["is_complete"] is True

    def test_force_complete_triggers_order_complete(self, logic):
        """Force-completing the last remaining SKU should complete the whole order."""
        _seed_order(logic, sku="SKU-A", quantity=1)

        result, status = logic.force_complete_sku("SKU-A")
        assert status == "ORDER_COMPLETE"
        assert "ORD-001" in logic.session_packing_state["completed_orders"]

    def test_force_complete_sku_not_found(self, logic):
        _seed_order(logic, sku="SKU-A", quantity=1)
        result, status = logic.force_complete_sku("NONEXISTENT")
        assert status == "SKU_NOT_FOUND"

    def test_force_complete_no_active_order(self, logic):
        result, status = logic.force_complete_sku("SKU-A")
        assert status == "NO_ACTIVE_ORDER"


# ── skip_order ────────────────────────────────────────────────────────────────

class TestSkipOrder:
    def test_skip_preserves_in_progress_state(self, logic):
        """Skipping an order must keep its scan state so it can be resumed."""
        _seed_order(logic, sku="SKU-A", quantity=3)
        logic.process_sku_scan("SKU-A")  # packed=1
        logic.skip_order()

        # In-progress state should still be there
        assert "ORD-001" in logic.session_packing_state["in_progress"]
        state = logic.session_packing_state["in_progress"]["ORD-001"]
        assert state[0]["packed"] == 1

    def test_skip_clears_current_order(self, logic):
        _seed_order(logic)
        logic.skip_order()
        assert logic.current_order_number is None
        assert logic.current_order_state == {}

    def test_skip_adds_to_skipped_orders(self, logic):
        _seed_order(logic)
        logic.skip_order()
        assert "ORD-001" in logic.session_packing_state["skipped_orders"]

    def test_skip_no_duplicates(self, logic):
        _seed_order(logic)
        logic.skip_order()
        _seed_order(logic)
        logic.skip_order()
        assert logic.session_packing_state["skipped_orders"].count("ORD-001") == 1

    def test_skip_clears_metadata(self, logic):
        _seed_order(logic)
        logic.skip_order()
        assert logic.current_order_metadata == {}

    def test_skip_no_active_order(self, logic):
        result = logic.skip_order()
        assert result == "NO_ACTIVE_ORDER"

    def test_skipped_order_not_in_completed(self, logic):
        _seed_order(logic)
        logic.skip_order()
        assert "ORD-001" not in logic.session_packing_state["completed_orders"]

    def test_resume_after_skip_restores_state(self, logic):
        """Scanning a skipped order again should restore its previous packed count."""
        _seed_order(logic, sku="SKU-A", quantity=3)
        logic.process_sku_scan("SKU-A")  # packed=1
        logic.skip_order()

        # Re-scan the order
        items, status = logic.start_order_packing("ORD-001")
        assert status == "ORDER_LOADED"
        assert logic.current_order_state[0]["packed"] == 1


# ── current_order_metadata ────────────────────────────────────────────────────

class TestOrderMetadata:
    def test_metadata_set_on_start_packing(self, logic):
        logic.orders_data = {
            "ORD-001": {
                "items": [{"SKU": "A", "Quantity": "1", "Product_Name": "P",
                            "Order_Number": "ORD-001", "Courier": "DHL"}],
                "metadata": {
                    "courier": "DHL",
                    "status": "Fulfillable",
                    "recommended_box": "Box S",
                    "tags": "VIP",
                    "internal_tags": "urgent",
                    "fulfillment_status": "partial",
                    "shipping_method": "Express"
                }
            }
        }
        logic.session_packing_state = {"in_progress": {}, "completed_orders": [], "skipped_orders": []}
        logic.start_order_packing("ORD-001")

        assert logic.current_order_metadata["courier"] == "DHL"
        assert logic.current_order_metadata["recommended_box"] == "Box S"
        assert logic.current_order_metadata["tags"] == "VIP"
        assert logic.current_order_metadata["internal_tags"] == "urgent"
        assert logic.current_order_metadata["fulfillment_status"] == "partial"
        assert logic.current_order_metadata["shipping_method"] == "Express"

    def test_metadata_cleared_on_skip(self, logic):
        _seed_order(logic)
        assert logic.current_order_metadata != {}
        logic.skip_order()
        assert logic.current_order_metadata == {}

    def test_metadata_missing_fields_graceful(self, logic):
        logic.orders_data = {
            "ORD-001": {
                "items": [{"SKU": "A", "Quantity": "1", "Product_Name": "P",
                            "Order_Number": "ORD-001", "Courier": "N/A"}],
                "metadata": {"courier": "N/A"}
            }
        }
        logic.session_packing_state = {"in_progress": {}, "completed_orders": [], "skipped_orders": []}
        logic.start_order_packing("ORD-001")
        assert logic.current_order_metadata.get("recommended_box") is None
        assert logic.current_order_metadata.get("tags") is None
        assert logic.current_order_metadata.get("internal_tags") is None


# ── Metadata extraction in load_packing_list_json ────────────────────────────

class TestLoadPackingListJsonMetadata:
    def test_metadata_extracted_from_json(self, logic, tmp_path):
        packing_list = {
            "list_name": "TestList",
            "courier": "DHL",
            "total_orders": 1,
            "orders": [
                {
                    "order_number": "ORD-001",
                    "courier": "DHL",
                    "status": "Fulfillable",
                    "fulfillment_status": "unfulfilled",
                    "recommended_box": "Box M",
                    "tags": "Priority",
                    "internal_tags": "fragile",
                    "shipping_method": "Standard",
                    "items": [{"sku": "SKU-A", "quantity": 1, "product_name": "Prod A"}]
                }
            ]
        }
        json_file = tmp_path / "test_list.json"
        json_file.write_text(json.dumps(packing_list))

        logic.load_packing_list_json(json_file)

        meta = logic.orders_data["ORD-001"]["metadata"]
        assert meta["courier"] == "DHL"
        assert meta["status"] == "Fulfillable"
        assert meta["fulfillment_status"] == "unfulfilled"
        assert meta["recommended_box"] == "Box M"
        assert meta["tags"] == "Priority"
        assert meta["internal_tags"] == "fragile"
        assert meta["shipping_method"] == "Standard"

    def test_metadata_defaults_when_fields_absent(self, logic, tmp_path):
        packing_list = {
            "list_name": "TestList",
            "courier": "DHL",
            "total_orders": 1,
            "orders": [
                {
                    "order_number": "ORD-001",
                    "courier": "DHL",
                    "items": [{"sku": "SKU-A", "quantity": 1, "product_name": "Prod A"}]
                }
            ]
        }
        json_file = tmp_path / "min_list.json"
        json_file.write_text(json.dumps(packing_list))

        logic.load_packing_list_json(json_file)

        meta = logic.orders_data["ORD-001"]["metadata"]
        assert meta["recommended_box"] is None
        assert meta["tags"] is None
        assert meta["internal_tags"] is None
        assert meta["fulfillment_status"] is None
        assert meta["shipping_method"] is None
