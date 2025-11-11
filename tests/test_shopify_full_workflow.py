"""
Integration test for complete Shopify → Packing Tool workflow.

This test simulates the full workflow from Shopify session creation
through packing completion, verifying all integration points.
"""

import pytest
import json
import sys
import os
from pathlib import Path
from unittest.mock import Mock
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from packer_logic import PackerLogic


@pytest.fixture
def mock_profile_manager():
    """Create mock ProfileManager."""
    manager = Mock()
    manager.load_sku_mapping.return_value = {}
    return manager


@pytest.fixture
def unified_work_dir(tmp_path):
    """
    Create unified work directory structure mimicking Shopify Tool output.

    Structure:
        CLIENT_TEST/
        └── 2025-11-10_1/
            ├── session_info.json
            ├── analysis/
            │   └── analysis_data.json
            └── packing_lists/
                └── DHL_Orders.json
    """
    # Create base directory structure
    client_dir = tmp_path / "CLIENT_TEST"
    client_dir.mkdir()

    session_dir = client_dir / "2025-11-10_1"
    session_dir.mkdir()

    # Create session_info.json
    session_info = {
        "session_id": "2025-11-10_1",
        "client_id": "TEST",
        "created_at": "2025-11-10T09:00:00",
        "work_directory": str(session_dir)
    }

    session_info_file = session_dir / "session_info.json"
    with open(session_info_file, 'w', encoding='utf-8') as f:
        json.dump(session_info, f, indent=2)

    # Create analysis directory and data
    analysis_dir = session_dir / "analysis"
    analysis_dir.mkdir()

    analysis_data = {
        "analyzed_at": "2025-11-10T09:15:00",
        "total_orders": 5,
        "fulfillable_orders": 5,
        "orders": [
            {
                "order_number": "DHL-001",
                "courier": "DHL",
                "status": "Fulfillable",
                "customer_name": "John Doe",
                "items": [
                    {
                        "sku": "PROD-001",
                        "quantity": 2,
                        "product_name": "Widget A"
                    },
                    {
                        "sku": "PROD-002",
                        "quantity": 1,
                        "product_name": "Widget B"
                    }
                ]
            },
            {
                "order_number": "DHL-002",
                "courier": "DHL",
                "status": "Fulfillable",
                "customer_name": "Jane Smith",
                "items": [
                    {
                        "sku": "PROD-001",
                        "quantity": 3,
                        "product_name": "Widget A"
                    }
                ]
            },
            {
                "order_number": "DHL-003",
                "courier": "DHL",
                "status": "Fulfillable",
                "customer_name": "Bob Johnson",
                "items": [
                    {
                        "sku": "PROD-003",
                        "quantity": 1,
                        "product_name": "Widget C"
                    },
                    {
                        "sku": "PROD-001",
                        "quantity": 1,
                        "product_name": "Widget A"
                    }
                ]
            },
            {
                "order_number": "DHL-004",
                "courier": "DHL",
                "status": "Fulfillable",
                "customer_name": "Alice Williams",
                "items": [
                    {
                        "sku": "PROD-002",
                        "quantity": 2,
                        "product_name": "Widget B"
                    }
                ]
            },
            {
                "order_number": "DHL-005",
                "courier": "DHL",
                "status": "Fulfillable",
                "customer_name": "Charlie Brown",
                "items": [
                    {
                        "sku": "PROD-003",
                        "quantity": 4,
                        "product_name": "Widget C"
                    }
                ]
            }
        ]
    }

    analysis_file = analysis_dir / "analysis_data.json"
    with open(analysis_file, 'w', encoding='utf-8') as f:
        json.dump(analysis_data, f, indent=2)

    # Create packing_lists directory (optional, may not exist initially)
    packing_lists_dir = session_dir / "packing_lists"
    packing_lists_dir.mkdir()

    return session_dir, analysis_data


class TestShopifyPackingWorkflow:
    """Test complete Shopify → Packing integration workflow."""

    def test_full_workflow(self, mock_profile_manager, unified_work_dir):
        """
        Test complete workflow from Shopify session to packing completion.

        Steps:
        1. Setup mock Shopify session (via fixture)
        2. Load via Packing Tool
        3. Simulate packing orders
        4. Verify work directory structure
        5. Verify files created correctly
        6. Verify packing state persistence
        """
        session_dir, expected_data = unified_work_dir

        # Step 1: Verify Shopify session structure exists
        assert (session_dir / "session_info.json").exists()
        assert (session_dir / "analysis" / "analysis_data.json").exists()

        # Step 2: Create PackerLogic and load from Shopify session
        barcode_dir = session_dir / "packing" / "DHL_Orders" / "barcodes"
        barcode_dir.mkdir(parents=True, exist_ok=True)

        logic = PackerLogic(
            client_id="TEST",
            profile_manager=mock_profile_manager,
            barcode_dir=str(barcode_dir)
        )

        # Load analysis data
        order_count, analyzed_at = logic.load_from_shopify_analysis(session_dir)

        # Verify loading
        assert order_count == 5, "Should load all 5 orders"
        assert analyzed_at == "2025-11-10T09:15:00"
        assert logic.packing_list_df is not None
        assert len(logic.packing_list_df) == 8, "Should have 8 total items across orders"

        # Verify barcodes were generated
        barcode_files = list(barcode_dir.glob("*.png"))
        assert len(barcode_files) == 5, "Should generate 5 order barcodes"

        # Step 3: Simulate packing orders
        # Pack first order (DHL-001) completely
        order_items = logic.get_next_order()
        assert order_items is not None
        assert order_items[0]['Order_Number'] == 'DHL-001'

        # Scan each item in first order
        for item in order_items:
            sku = item['SKU']
            quantity = int(item['Quantity'])

            for _ in range(quantity):
                result = logic.process_scan(sku)
                assert result is not None
                assert result['status'] in ['item_packed', 'order_complete']

        # Verify first order is complete
        assert logic.order_states['DHL-001'] == 'completed'

        # Pack second order partially
        order_items = logic.get_next_order()
        assert order_items[0]['Order_Number'] == 'DHL-002'

        # Scan only 2 out of 3 items for PROD-001
        logic.process_scan('PROD-001')
        logic.process_scan('PROD-001')

        # Verify second order is still in progress
        assert logic.order_states['DHL-002'] == 'in_progress'

        # Step 4: Verify work directory structure
        packing_dir = session_dir / "packing" / "DHL_Orders"
        assert packing_dir.exists(), "Packing directory should exist"
        assert (packing_dir / "barcodes").exists(), "Barcodes directory should exist"

        # Step 5: Verify state file was created
        state_file = packing_dir / "packing_state.json"
        assert state_file.exists(), "Packing state file should exist"

        with open(state_file, 'r', encoding='utf-8') as f:
            state_data = json.load(f)

        # Verify state content
        assert 'order_states' in state_data
        assert state_data['order_states']['DHL-001'] == 'completed'
        assert state_data['order_states']['DHL-002'] == 'in_progress'
        assert state_data['order_states']['DHL-003'] == 'pending'

        # Verify item counts
        assert 'item_counts' in state_data
        # DHL-001 has PROD-001 (qty 2) and PROD-002 (qty 1)
        assert state_data['item_counts']['DHL-001']['PROD-001'] == 2
        assert state_data['item_counts']['DHL-001']['PROD-002'] == 1
        # DHL-002 has PROD-001 partially packed (2 out of 3)
        assert state_data['item_counts']['DHL-002']['PROD-001'] == 2

        # Step 6: Test state restoration
        # Create new PackerLogic instance with same barcode dir
        logic2 = PackerLogic(
            client_id="TEST",
            profile_manager=mock_profile_manager,
            barcode_dir=str(barcode_dir)
        )

        # Load same session
        logic2.load_from_shopify_analysis(session_dir)

        # Verify state was restored
        assert logic2.order_states['DHL-001'] == 'completed'
        assert logic2.order_states['DHL-002'] == 'in_progress'
        assert logic2.item_counts['DHL-001']['PROD-001'] == 2
        assert logic2.item_counts['DHL-002']['PROD-001'] == 2

        # Continue packing second order
        result = logic2.process_scan('PROD-001')  # Third item
        assert result['status'] == 'order_complete'
        assert logic2.order_states['DHL-002'] == 'completed'

    def test_work_directory_structure(self, mock_profile_manager, unified_work_dir):
        """Test that packing tool creates correct directory structure."""
        session_dir, _ = unified_work_dir

        barcode_dir = session_dir / "packing" / "PostOne_Orders" / "barcodes"
        barcode_dir.mkdir(parents=True, exist_ok=True)

        logic = PackerLogic(
            client_id="TEST",
            profile_manager=mock_profile_manager,
            barcode_dir=str(barcode_dir)
        )

        # Load and process
        logic.load_from_shopify_analysis(session_dir)

        # Verify directory structure
        packing_dir = session_dir / "packing" / "PostOne_Orders"
        assert packing_dir.exists()
        assert (packing_dir / "barcodes").exists()

        # After saving state, verify state file
        logic.save_state()
        assert (packing_dir / "packing_state.json").exists()

    def test_multiple_packing_lists_simultaneously(self, mock_profile_manager, unified_work_dir):
        """Test that multiple packing lists can be worked on simultaneously."""
        session_dir, _ = unified_work_dir

        # Create two separate packing work directories
        dhl_barcode_dir = session_dir / "packing" / "DHL_Orders" / "barcodes"
        dhl_barcode_dir.mkdir(parents=True, exist_ok=True)

        postone_barcode_dir = session_dir / "packing" / "PostOne_Orders" / "barcodes"
        postone_barcode_dir.mkdir(parents=True, exist_ok=True)

        # Work on DHL orders
        logic_dhl = PackerLogic(
            client_id="TEST",
            profile_manager=mock_profile_manager,
            barcode_dir=str(dhl_barcode_dir)
        )
        logic_dhl.load_from_shopify_analysis(session_dir)

        # Work on PostOne orders (simulated)
        logic_postone = PackerLogic(
            client_id="TEST",
            profile_manager=mock_profile_manager,
            barcode_dir=str(postone_barcode_dir)
        )
        logic_postone.load_from_shopify_analysis(session_dir)

        # Both should coexist
        dhl_packing_dir = session_dir / "packing" / "DHL_Orders"
        postone_packing_dir = session_dir / "packing" / "PostOne_Orders"

        assert dhl_packing_dir.exists()
        assert postone_packing_dir.exists()

        # Both should have their own state
        logic_dhl.save_state()
        logic_postone.save_state()

        assert (dhl_packing_dir / "packing_state.json").exists()
        assert (postone_packing_dir / "packing_state.json").exists()

    def test_audit_trail(self, mock_profile_manager, unified_work_dir):
        """Test that packing creates clear audit trail."""
        session_dir, _ = unified_work_dir

        barcode_dir = session_dir / "packing" / "DHL_Orders" / "barcodes"
        barcode_dir.mkdir(parents=True, exist_ok=True)

        logic = PackerLogic(
            client_id="TEST",
            profile_manager=mock_profile_manager,
            barcode_dir=str(barcode_dir)
        )

        # Load and pack
        logic.load_from_shopify_analysis(session_dir)

        # Pack one order
        order_items = logic.get_next_order()
        for item in order_items:
            sku = item['SKU']
            quantity = int(item['Quantity'])
            for _ in range(quantity):
                logic.process_scan(sku)

        # Save state
        logic.save_state()

        # Verify state file contains audit information
        state_file = session_dir / "packing" / "DHL_Orders" / "packing_state.json"
        with open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)

        # Should have timestamp
        assert 'last_updated' in state or 'saved_at' in state

        # Should track completed orders
        assert len([s for s in state['order_states'].values() if s == 'completed']) >= 1
