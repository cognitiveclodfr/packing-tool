"""
Tests for Shopify Tool integration (Phase 1.3.2).

Tests cover:
- Loading analysis_data.json from Shopify sessions
- Converting Shopify order format to packing list format
- Barcode generation from Shopify data
- Error handling for invalid/missing data
"""

import pytest
import json
import sys
import os
from pathlib import Path
from unittest.mock import Mock

# Add src to path to be able to import modules from there
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from packer_logic import PackerLogic


@pytest.fixture
def mock_profile_manager():
    """Create mock ProfileManager."""
    manager = Mock()
    manager.load_sku_mapping.return_value = {}
    return manager


@pytest.fixture
def barcode_dir(tmp_path):
    """Create temporary barcode directory."""
    barcodes = tmp_path / "barcodes"
    barcodes.mkdir()
    return str(barcodes)


@pytest.fixture
def shopify_session(tmp_path):
    """Create test Shopify session with analysis_data.json."""
    session_dir = tmp_path / "2025-11-04_1"
    session_dir.mkdir()

    analysis_dir = session_dir / "analysis"
    analysis_dir.mkdir()

    analysis_data = {
        "analyzed_at": "2025-11-04T10:30:00",
        "total_orders": 3,
        "fulfillable_orders": 3,
        "orders": [
            {
                "order_number": "ORDER-001",
                "courier": "DHL",
                "status": "Fulfillable",
                "items": [
                    {
                        "sku": "SKU-123",
                        "quantity": 2,
                        "product_name": "Product A"
                    },
                    {
                        "sku": "SKU-456",
                        "quantity": 1,
                        "product_name": "Product B"
                    }
                ]
            },
            {
                "order_number": "ORDER-002",
                "courier": "PostOne",
                "status": "Fulfillable",
                "items": [
                    {
                        "sku": "SKU-789",
                        "quantity": 3,
                        "product_name": "Product C"
                    }
                ]
            },
            {
                "order_number": "ORDER-003",
                "courier": "Speedy",
                "status": "Fulfillable",
                "items": [
                    {
                        "sku": "SKU-123",
                        "quantity": 1,
                        "product_name": "Product A"
                    }
                ]
            }
        ]
    }

    analysis_file = analysis_dir / "analysis_data.json"
    with open(analysis_file, 'w', encoding='utf-8') as f:
        json.dump(analysis_data, f, indent=2)

    return session_dir, analysis_data


class TestShopifyIntegration:
    """Tests for Shopify Tool integration."""

    def test_load_from_shopify_analysis_success(self, mock_profile_manager, barcode_dir, shopify_session):
        """Test successful loading of Shopify session data."""
        session_dir, expected_data = shopify_session

        logic = PackerLogic(
            client_id="TEST",
            profile_manager=mock_profile_manager,
            barcode_dir=barcode_dir
        )

        # Load from Shopify analysis
        order_count, analyzed_at = logic.load_from_shopify_analysis(session_dir)

        # Verify counts
        assert order_count == 3
        assert analyzed_at == "2025-11-04T10:30:00"

        # Verify DataFrame was created
        assert logic.packing_list_df is not None
        assert logic.processed_df is not None

        # Verify row count (3 items in ORDER-001, 1 in ORDER-002, 1 in ORDER-003 = 4 total rows)
        assert len(logic.processed_df) == 4

        # Verify columns
        required_cols = ['Order_Number', 'SKU', 'Product_Name', 'Quantity', 'Courier']
        for col in required_cols:
            assert col in logic.processed_df.columns

        # Verify data content
        order_001_rows = logic.processed_df[logic.processed_df['Order_Number'] == 'ORDER-001']
        assert len(order_001_rows) == 2
        assert 'SKU-123' in order_001_rows['SKU'].values
        assert 'SKU-456' in order_001_rows['SKU'].values

        # Verify orders_data was populated
        assert len(logic.orders_data) == 3
        assert 'ORDER-001' in logic.orders_data
        assert 'ORDER-002' in logic.orders_data
        assert 'ORDER-003' in logic.orders_data

        # Verify barcode mapping
        assert len(logic.barcode_to_order_number) == 3

    def test_load_from_shopify_analysis_file_not_found(self, mock_profile_manager, barcode_dir, tmp_path):
        """Test error when analysis_data.json not found."""
        session_dir = tmp_path / "empty_session"
        session_dir.mkdir()

        logic = PackerLogic(
            client_id="TEST",
            profile_manager=mock_profile_manager,
            barcode_dir=barcode_dir
        )

        # Should raise ValueError
        with pytest.raises(ValueError, match="analysis_data.json not found"):
            logic.load_from_shopify_analysis(session_dir)

    def test_load_from_shopify_analysis_invalid_json(self, mock_profile_manager, barcode_dir, tmp_path):
        """Test error when analysis_data.json contains invalid JSON."""
        session_dir = tmp_path / "invalid_session"
        session_dir.mkdir()

        analysis_dir = session_dir / "analysis"
        analysis_dir.mkdir()

        # Write invalid JSON
        analysis_file = analysis_dir / "analysis_data.json"
        with open(analysis_file, 'w') as f:
            f.write("{ invalid json }")

        logic = PackerLogic(
            client_id="TEST",
            profile_manager=mock_profile_manager,
            barcode_dir=barcode_dir
        )

        # Should raise ValueError
        with pytest.raises(ValueError, match="Invalid JSON"):
            logic.load_from_shopify_analysis(session_dir)

    def test_load_from_shopify_analysis_empty_orders(self, mock_profile_manager, barcode_dir, tmp_path):
        """Test handling of session with no orders."""
        session_dir = tmp_path / "empty_orders_session"
        session_dir.mkdir()

        analysis_dir = session_dir / "analysis"
        analysis_dir.mkdir()

        # Analysis data with empty orders list
        analysis_data = {
            "analyzed_at": "2025-11-04T10:30:00",
            "total_orders": 0,
            "orders": []
        }

        analysis_file = analysis_dir / "analysis_data.json"
        with open(analysis_file, 'w', encoding='utf-8') as f:
            json.dump(analysis_data, f)

        logic = PackerLogic(
            client_id="TEST",
            profile_manager=mock_profile_manager,
            barcode_dir=barcode_dir
        )

        # Should return 0 orders
        order_count, analyzed_at = logic.load_from_shopify_analysis(session_dir)

        assert order_count == 0
        assert analyzed_at == "2025-11-04T10:30:00"

    def test_load_from_shopify_analysis_missing_required_columns(self, mock_profile_manager, barcode_dir, tmp_path):
        """Test error when orders are missing required columns."""
        session_dir = tmp_path / "invalid_columns_session"
        session_dir.mkdir()

        analysis_dir = session_dir / "analysis"
        analysis_dir.mkdir()

        # Analysis data missing 'courier' field
        analysis_data = {
            "analyzed_at": "2025-11-04T10:30:00",
            "total_orders": 1,
            "orders": [
                {
                    "order_number": "ORDER-001",
                    # Missing 'courier' field
                    "items": [
                        {
                            "sku": "SKU-123",
                            "quantity": 1,
                            "product_name": "Product A"
                        }
                    ]
                }
            ]
        }

        analysis_file = analysis_dir / "analysis_data.json"
        with open(analysis_file, 'w', encoding='utf-8') as f:
            json.dump(analysis_data, f)

        logic = PackerLogic(
            client_id="TEST",
            profile_manager=mock_profile_manager,
            barcode_dir=barcode_dir
        )

        # Should raise ValueError due to missing Courier column
        with pytest.raises(ValueError, match="Missing required columns"):
            logic.load_from_shopify_analysis(session_dir)

    def test_load_from_shopify_analysis_extra_fields(self, mock_profile_manager, barcode_dir, tmp_path):
        """Test handling of extra fields in Shopify data."""
        session_dir = tmp_path / "extra_fields_session"
        session_dir.mkdir()

        analysis_dir = session_dir / "analysis"
        analysis_dir.mkdir()

        # Analysis data with extra fields
        analysis_data = {
            "analyzed_at": "2025-11-04T10:30:00",
            "total_orders": 1,
            "orders": [
                {
                    "order_number": "ORDER-001",
                    "courier": "DHL",
                    "customer_name": "John Doe",
                    "shipping_address": "123 Main St",
                    "items": [
                        {
                            "sku": "SKU-123",
                            "quantity": 1,
                            "product_name": "Product A"
                        }
                    ]
                }
            ]
        }

        analysis_file = analysis_dir / "analysis_data.json"
        with open(analysis_file, 'w', encoding='utf-8') as f:
            json.dump(analysis_data, f)

        logic = PackerLogic(
            client_id="TEST",
            profile_manager=mock_profile_manager,
            barcode_dir=barcode_dir
        )

        # Should successfully load and include extra fields
        order_count, _ = logic.load_from_shopify_analysis(session_dir)

        assert order_count == 1

        # Check that extra fields were added to DataFrame
        df = logic.processed_df
        assert 'Customer_Name' in df.columns
        assert 'Shipping_Address' in df.columns
        assert df.loc[0, 'Customer_Name'] == 'John Doe'
        assert df.loc[0, 'Shipping_Address'] == '123 Main St'

    def test_load_from_shopify_analysis_multiple_items_per_order(self, mock_profile_manager, barcode_dir, shopify_session):
        """Test correct flattening of orders with multiple items."""
        session_dir, _ = shopify_session

        logic = PackerLogic(
            client_id="TEST",
            profile_manager=mock_profile_manager,
            barcode_dir=barcode_dir
        )

        logic.load_from_shopify_analysis(session_dir)

        # ORDER-001 has 2 items, should create 2 rows
        order_001_rows = logic.processed_df[logic.processed_df['Order_Number'] == 'ORDER-001']
        assert len(order_001_rows) == 2

        # Check both SKUs are present
        skus = set(order_001_rows['SKU'].values)
        assert skus == {'SKU-123', 'SKU-456'}

        # Check quantities
        sku_123_row = order_001_rows[order_001_rows['SKU'] == 'SKU-123']
        assert sku_123_row['Quantity'].values[0] == '2'

        sku_456_row = order_001_rows[order_001_rows['SKU'] == 'SKU-456']
        assert sku_456_row['Quantity'].values[0] == '1'

    def test_load_from_shopify_analysis_barcode_generation(self, mock_profile_manager, barcode_dir, shopify_session):
        """Test that barcodes are generated for all orders."""
        session_dir, _ = shopify_session

        logic = PackerLogic(
            client_id="TEST",
            profile_manager=mock_profile_manager,
            barcode_dir=barcode_dir
        )

        logic.load_from_shopify_analysis(session_dir)

        # Check barcode files were created
        barcode_path = Path(barcode_dir)
        barcode_files = list(barcode_path.glob("*.png"))

        # Should have 3 barcodes (one per order)
        assert len(barcode_files) == 3

        # Check that barcode_to_order_number mapping exists
        assert len(logic.barcode_to_order_number) == 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
