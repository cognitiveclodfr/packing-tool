#!/usr/bin/env python3
"""
Test script for validating barcode size optimization for 68x38mm labels @ 203 DPI.

This script:
1. Creates a minimal test environment for PackerLogic
2. Generates test barcodes with the new settings
3. Validates dimensions against 68x38mm @ 203 DPI requirements
4. Reports results with detailed measurements

Usage:
    python test_barcode_size.py

Expected output:
    - Test barcode PNG file in test_output/barcodes/
    - Dimension validation report
    - Pass/fail status for size requirements
"""

import sys
import os
from pathlib import Path
import tempfile
import pandas as pd
from PIL import Image

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from packer_logic import PackerLogic


class MockProfileManager:
    """Mock ProfileManager for testing without full dependencies."""

    def load_sku_mapping(self, client_id):
        """Return empty SKU mapping for test."""
        return {}

    def save_sku_mapping(self, client_id, sku_map):
        """No-op save for test."""
        pass


def test_barcode_generation():
    """Test barcode generation with new 68x38mm settings."""

    print("=" * 80)
    print("BARCODE SIZE VALIDATION TEST")
    print("=" * 80)
    print()
    print("Testing barcode generation for 68mm x 38mm labels @ 203 DPI")
    print("Target printer: Citizen CL-E300")
    print()

    # Create temporary test directory
    test_dir = Path(__file__).parent / "test_output"
    test_dir.mkdir(exist_ok=True)

    print(f"Test output directory: {test_dir}")
    print()

    # Initialize PackerLogic with mock profile manager
    print("Initializing PackerLogic...")
    profile_mgr = MockProfileManager()
    logic = PackerLogic(
        client_id="TEST",
        profile_manager=profile_mgr,
        work_dir=str(test_dir)
    )

    # Create test packing list DataFrame
    print("Creating test packing list...")
    test_data = pd.DataFrame([
        {
            'Order_Number': 'TEST-ORDER-001',
            'SKU': 'TEST-SKU-001',
            'Product_Name': 'Test Product A',
            'Quantity': '2',
            'Courier': 'DHL'
        },
        {
            'Order_Number': 'TEST-ORDER-001',
            'SKU': 'TEST-SKU-002',
            'Product_Name': 'Test Product B',
            'Quantity': '1',
            'Courier': 'DHL'
        },
        {
            'Order_Number': 'TEST-ORDER-002',
            'SKU': 'TEST-SKU-001',
            'Product_Name': 'Test Product A',
            'Quantity': '3',
            'Courier': 'Speedy'
        }
    ])

    logic.packing_list_df = test_data
    logic.processed_df = test_data.copy()

    print(f"Created test packing list with {len(test_data)} items, 2 orders")
    print()

    # Generate barcodes
    print("Generating barcodes with new settings...")
    print("  - Label size: 68mm x 38mm")
    print("  - Printer DPI: 203")
    print("  - Module width: 0.4mm")
    print("  - Module height: 20.0mm")
    print("  - Quiet zone: 6.0mm")
    print()

    try:
        order_count = logic.process_data_and_generate_barcodes()
        print(f"✓ Successfully generated {order_count} barcodes")
        print()
    except Exception as e:
        print(f"✗ FAILED to generate barcodes: {e}")
        return False

    # Validate barcode dimensions
    print("=" * 80)
    print("DIMENSION VALIDATION")
    print("=" * 80)
    print()

    # Expected dimensions
    expected_width_px = int((68 / 25.4) * 203)  # ~543 pixels
    expected_height_label_px = int((38 / 25.4) * 203)  # ~303 pixels

    print(f"Expected label dimensions @ 203 DPI:")
    print(f"  - Width:  {expected_width_px} pixels (68mm)")
    print(f"  - Height: {expected_height_label_px} pixels (38mm)")
    print()

    # Check generated barcodes
    barcode_dir = test_dir / "barcodes"
    barcode_files = list(barcode_dir.glob("*.png"))

    if not barcode_files:
        print("✗ FAILED: No barcode files generated")
        return False

    print(f"Checking {len(barcode_files)} generated barcode(s):")
    print()

    all_passed = True

    for barcode_file in barcode_files:
        print(f"File: {barcode_file.name}")

        try:
            # Load and measure barcode
            img = Image.open(barcode_file)
            width_px, height_px = img.size

            # Convert to mm
            width_mm = width_px / 203 * 25.4
            height_mm = height_px / 203 * 25.4

            # Calculate file size
            file_size_kb = barcode_file.stat().st_size / 1024

            print(f"  Dimensions: {width_px} x {height_px} pixels")
            print(f"  Physical:   {width_mm:.1f} x {height_mm:.1f} mm @ 203 DPI")
            print(f"  File size:  {file_size_kb:.1f} KB")

            # Validate width (should be close to 543px / 68mm)
            width_ok = 500 <= width_px <= 600
            width_status = "✓" if width_ok else "✗"
            print(f"  {width_status} Width:  {width_px}px (expected ~543px, range: 500-600)")

            # Validate height (barcode + text, should fit in label)
            # Height should be less than full label height (303px) but substantial
            height_ok = 200 <= height_px <= 320
            height_status = "✓" if height_ok else "✗"
            print(f"  {height_status} Height: {height_px}px (expected ~240-280px, range: 200-320)")

            # Check if fits on 68x38mm label
            fits_width = width_mm <= 68
            fits_height = height_mm <= 38
            fits_status = "✓" if (fits_width and fits_height) else "✗"
            print(f"  {fits_status} Fits on 68x38mm label: {fits_width and fits_height}")

            if width_ok and height_ok and fits_width and fits_height:
                print("  ✓ PASSED all dimension checks")
            else:
                print("  ✗ FAILED dimension validation")
                all_passed = False

            print()

        except Exception as e:
            print(f"  ✗ ERROR reading barcode: {e}")
            all_passed = False
            print()

    # Final summary
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print()

    if all_passed:
        print("✓ ALL TESTS PASSED")
        print()
        print("Barcodes are correctly sized for 68x38mm labels @ 203 DPI")
        print("Ready for printing on Citizen CL-E300 printer")
        print()
        print("Next steps:")
        print("  1. Print a test label on Citizen CL-E300")
        print("  2. Measure physical dimensions with ruler")
        print("  3. Test scannability from 20-30cm distance")
        print("  4. Verify barcode fits properly on label stock")
    else:
        print("✗ SOME TESTS FAILED")
        print()
        print("Barcode dimensions are outside expected ranges.")
        print("Review barcode generation parameters in packer_logic.py")

    print()
    print(f"Test barcodes saved to: {barcode_dir}")
    print()

    return all_passed


if __name__ == '__main__':
    try:
        success = test_barcode_generation()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ TEST FAILED WITH ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
