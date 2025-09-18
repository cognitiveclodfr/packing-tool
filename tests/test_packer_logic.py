import unittest
import sys
import os
import tempfile
import shutil
import pandas as pd

# Add the path to src to be able to import packer_logic
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from packer_logic import PackerLogic

class TestPackerLogic(unittest.TestCase):

    def setUp(self):
        """Set up a temporary directory for tests."""
        self.test_dir = tempfile.mkdtemp()
        self.logic = PackerLogic(barcode_dir=self.test_dir)
        # Helper to create a dummy excel file
        self.dummy_file_path = os.path.join(self.test_dir, 'test_list.xlsx')

    def tearDown(self):
        """Remove the temporary directory after tests."""
        shutil.rmtree(self.test_dir)

    def _create_dummy_excel(self, data, file_path=None):
        """Helper to create an Excel file for testing."""
        if file_path is None:
            file_path = self.dummy_file_path
        df = pd.DataFrame(data)
        df.to_excel(file_path, index=False)
        return file_path

    def test_load_file_not_found(self):
        """Test loading a non-existent file."""
        with self.assertRaisesRegex(ValueError, "Не вдалося прочитати Excel файл"):
            self.logic.load_packing_list_from_file('non_existent_file.xlsx')

    def test_process_with_missing_column_mapping(self):
        """Test processing data when a required column is not mapped."""
        dummy_data = {'Order': ['1'], 'Identifier': ['A-1'], 'Name': ['Prod A'], 'Amount': [1]}
        file_path = self._create_dummy_excel(dummy_data)
        self.logic.load_packing_list_from_file(file_path)

        mapping = {
            'Order_Number': 'Order',
            'SKU': 'Identifier',
            'Quantity': 'Amount'
            # 'Product_Name' is missing
        }

        with self.assertRaisesRegex(ValueError, "Не всі необхідні колонки були зіставлені"):
            self.logic.process_data_and_generate_barcodes(mapping)

    def test_successful_processing_and_barcode_generation(self):
        """Test successful data processing and barcode generation."""
        dummy_data = {
            'Order_Number': ['1001', '1001', '1002'],
            'SKU': ['A-1', 'B-2', 'A-1'],
            'Product_Name': ['Product A', 'Product B', 'Product A'],
            'Quantity': [1, 2, 3]
        }
        file_path = self._create_dummy_excel(dummy_data)
        self.logic.load_packing_list_from_file(file_path)

        num_orders = self.logic.process_data_and_generate_barcodes()
        self.assertEqual(num_orders, 2)

        self.assertTrue(os.path.exists(os.path.join(self.test_dir, '1001.png')))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, '1002.png')))

        self.assertIn('1001', self.logic.orders_data)
        self.assertEqual(len(self.logic.orders_data['1001']['items']), 2)
        self.assertIn('1002', self.logic.orders_data)
        self.assertEqual(len(self.logic.orders_data['1002']['items']), 1)

    def test_packing_logic_flow(self):
        """Test the entire packing flow for a single order."""
        dummy_data = {
            'Order_Number': ['1001', '1001'],
            'SKU': ['A-1', 'B-2'],
            'Product_Name': ['Product A', 'Product B'],
            'Quantity': [1, 2]
        }
        file_path = self._create_dummy_excel(dummy_data)
        self.logic.load_packing_list_from_file(file_path)
        self.logic.process_data_and_generate_barcodes()

        # Start packing with a valid barcode
        items, status = self.logic.start_order_packing('1001')
        self.assertEqual(status, "ORDER_LOADED")
        self.assertIsNotNone(items)
        self.assertEqual(len(items), 2)

        # Scan correct SKU
        result, status = self.logic.process_sku_scan('A-1')
        self.assertEqual(status, "SKU_OK")
        self.assertEqual(result['packed'], 1)
        self.assertTrue(result['is_complete'])

        # Scan another correct SKU
        result, status = self.logic.process_sku_scan('B-2')
        self.assertEqual(status, "SKU_OK")
        self.assertEqual(result['packed'], 1)
        self.assertFalse(result['is_complete'])

        # Scan the second item of the same SKU
        result, status = self.logic.process_sku_scan('B-2')
        self.assertEqual(status, "ORDER_COMPLETE")
        self.assertEqual(result['packed'], 2)
        self.assertTrue(result['is_complete'])

    def test_packing_with_extra_and_unknown_skus(self):
        """Test scanning extra and unknown SKUs."""
        dummy_data = {'Order_Number': ['1001'], 'SKU': ['A-1'], 'Product_Name': ['A'], 'Quantity': [1]}
        file_path = self._create_dummy_excel(dummy_data)
        self.logic.load_packing_list_from_file(file_path)
        self.logic.process_data_and_generate_barcodes()

        self.logic.start_order_packing('1001')

        # Complete the item
        self.logic.process_sku_scan('A-1')

        # Scan extra SKU
        result, status = self.logic.process_sku_scan('A-1')
        self.assertEqual(status, "SKU_EXTRA")
        self.assertIsNone(result)

        # Scan unknown SKU
        result, status = self.logic.process_sku_scan('C-3')
        self.assertEqual(status, "SKU_NOT_FOUND")
        self.assertIsNone(result)

    def test_start_packing_unknown_order(self):
        """Test starting to pack an order that does not exist."""
        items, status = self.logic.start_order_packing('UNKNOWN_ORDER')
        self.assertEqual(status, "ORDER_NOT_FOUND")
        self.assertIsNone(items)

    def test_sku_normalization(self):
        """Test that SKUs are normalized correctly for matching."""
        dummy_data = {
            'Order_Number': ['1001'],
            'SKU': ['A-1'],
            'Product_Name': ['Product A'],
            'Quantity': [1]
        }
        file_path = self._create_dummy_excel(dummy_data)
        self.logic.load_packing_list_from_file(file_path)
        self.logic.process_data_and_generate_barcodes()

        self.logic.start_order_packing('1001')

        # Scan with a normalized SKU (no hyphen, different case)
        result, status = self.logic.process_sku_scan('a1')
        self.assertEqual(status, "ORDER_COMPLETE")
        self.assertIsNotNone(result)

    def test_invalid_quantity_in_excel(self):
        """Test that invalid quantities are handled gracefully."""
        dummy_data = {
            'Order_Number': ['1001'],
            'SKU': ['A-1'],
            'Product_Name': ['Product A'],
            'Quantity': ['invalid_string'] # Invalid quantity
        }
        file_path = self._create_dummy_excel(dummy_data)
        self.logic.load_packing_list_from_file(file_path)
        self.logic.process_data_and_generate_barcodes()

        self.logic.start_order_packing('1001')
        # The logic should treat 'invalid_string' as a quantity of 1
        self.assertEqual(self.logic.current_order_state['a1']['required'], 1)

        # Scan the item, should complete the order
        result, status = self.logic.process_sku_scan('A-1')
        self.assertEqual(status, "ORDER_COMPLETE")

    def test_scan_sku_for_wrong_order(self):
        """Test scanning an SKU that belongs to a different order."""
        dummy_data = {
            'Order_Number': ['1001', '1002'],
            'SKU': ['A-1', 'B-2'],
            'Product_Name': ['Product A', 'Product B'],
            'Quantity': [1, 1]
        }
        file_path = self._create_dummy_excel(dummy_data)
        self.logic.load_packing_list_from_file(file_path)
        self.logic.process_data_and_generate_barcodes()

        # Start packing order 1001
        self.logic.start_order_packing('1001')

        # Scan an SKU from order 1002
        result, status = self.logic.process_sku_scan('B-2')
        self.assertEqual(status, "SKU_NOT_FOUND")
        self.assertIsNone(result)

    def test_clear_current_order(self):
        """Test that the current order state is cleared properly."""
        dummy_data = {'Order_Number': ['1001'], 'SKU': ['A-1'], 'Product_Name': ['A'], 'Quantity': [1]}
        file_path = self._create_dummy_excel(dummy_data)
        self.logic.load_packing_list_from_file(file_path)
        self.logic.process_data_and_generate_barcodes()

        self.logic.start_order_packing('1001')
        self.assertIsNotNone(self.logic.current_order_number)
        self.assertNotEqual(self.logic.current_order_state, {})

        self.logic.clear_current_order()
        self.assertIsNone(self.logic.current_order_number)
        self.assertEqual(self.logic.current_order_state, {})

    def test_empty_sku_in_data(self):
        """Test that rows with empty SKUs are handled gracefully."""
        dummy_data = {
            'Order_Number': ['1001', '1001'],
            'SKU': ['A-1', ''], # One SKU is empty
            'Product_Name': ['Product A', 'Product B'],
            'Quantity': [1, 1]
        }
        file_path = self._create_dummy_excel(dummy_data)
        self.logic.load_packing_list_from_file(file_path)
        self.logic.process_data_and_generate_barcodes()

        self.logic.start_order_packing('1001')
        # The state should only contain the valid SKU, keyed by its normalized form
        self.assertIn('a1', self.logic.current_order_state)
        self.assertNotIn('', self.logic.current_order_state)
        self.assertEqual(len(self.logic.current_order_state), 1)

if __name__ == '__main__':
    unittest.main(verbosity=2)
