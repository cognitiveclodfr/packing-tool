import os
import pandas as pd
import barcode
from barcode.writer import ImageWriter
from datetime import datetime

REQUIRED_COLUMNS = ['Order_Number', 'SKU', 'Product_Name', 'Quantity']

class PackerLogic:
    def __init__(self, barcode_dir):
        self.barcode_dir = barcode_dir
        self.packing_list_df = None
        self.orders_data = {}
        self.barcode_to_order_number = {}
        self.order_completion_status = {}
        self.current_order_number = None
        self.current_order_state = {}

    def _normalize_sku(self, sku):
        """Normalizes an SKU by removing non-alphanumeric characters and converting to lowercase."""
        return ''.join(filter(str.isalnum, sku)).lower()

    def load_packing_list_from_file(self, file_path):
        """Loads and processes the packing list from an Excel file."""
        self.clear_session_data() # Ensure a clean state
        try:
            df = pd.read_excel(file_path, dtype=str).fillna('')
        except Exception as e:
            raise ValueError(f"Failed to read Excel file: {e}")

        if df.empty:
            raise ValueError("File is empty or contains no data.")

        self.packing_list_df = df
        return self.packing_list_df

    def process_data_and_generate_barcodes(self, column_mapping=None):
        """Processes the loaded dataframe and generates barcodes."""
        if self.packing_list_df is None:
            raise ValueError("Packing list not loaded.")

        df = self.packing_list_df.copy()
        if column_mapping:
            # Check if all required columns are mapped
            mapped_cols = set(column_mapping.keys())
            required_cols = set(REQUIRED_COLUMNS)
            if not required_cols.issubset(mapped_cols):
                missing = required_cols - mapped_cols
                raise ValueError(f"Not all required columns were mapped. Missing: {', '.join(missing)}")

            inverted_mapping = {v: k for k, v in column_mapping.items()}
            df.rename(columns=inverted_mapping, inplace=True)

        # Check after potential renaming
        missing_final = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if missing_final:
            raise ValueError(f"The file is missing required columns: {', '.join(missing_final)}")

        self.orders_data = {}
        self.barcode_to_order_number = {}
        code128 = barcode.get_barcode_class('code128')

        try:
            grouped = df.groupby('Order_Number')
            unnamed_counter = 1
            for order_number, group in grouped:
                safe_barcode_content = "".join(c for c in order_number if c.isalnum() or c in ('-', '_')).rstrip()
                if not safe_barcode_content:
                    safe_barcode_content = f"unnamed_order_{unnamed_counter}"
                    unnamed_counter += 1

                self.barcode_to_order_number[safe_barcode_content] = order_number

                writer_options = {
                    'module_height': 15.0,
                    'font_size': 10,
                    'text_distance': 3.0,
                    'font_path': '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                }
                barcode_path = os.path.join(self.barcode_dir, f"{safe_barcode_content}.png")

                bc = code128(safe_barcode_content, writer=ImageWriter())

                with open(barcode_path, 'wb') as f:
                    bc.write(f, options=writer_options, text=order_number)

                self.orders_data[order_number] = {
                    'barcode_path': barcode_path,
                    'items': group.to_dict('records')
                }
            return len(self.orders_data)
        except Exception as e:
            raise RuntimeError(f"Error during barcode generation: {e}")

    def start_order_packing(self, scanned_text):
        """Starts packing an order based on a scanned barcode."""
        if scanned_text not in self.barcode_to_order_number:
            return None, "ORDER_NOT_FOUND"

        original_order_number = self.barcode_to_order_number[scanned_text]
        self.current_order_number = original_order_number
        items = self.orders_data[original_order_number]['items']

        self.current_order_state = {}
        for i, item in enumerate(items):
            sku = item.get('SKU')
            if not sku:
                continue

            try:
                quantity = int(float(item.get('Quantity', 0)))
            except (ValueError, TypeError):
                quantity = 1

            self.current_order_state[sku] = {
                'required': quantity,
                'packed': 0,
                'row': i
            }
        return items, "ORDER_LOADED"

    def process_sku_scan(self, sku):
        """Processes a scanned SKU for the current order, normalizing for comparison."""
        if not self.current_order_number:
            return None, "NO_ACTIVE_ORDER"

        normalized_scanned_sku = self._normalize_sku(sku)
        found_sku = None
        for original_sku in self.current_order_state.keys():
            if self._normalize_sku(original_sku) == normalized_scanned_sku:
                found_sku = original_sku
                break

        if found_sku:
            state = self.current_order_state[found_sku]
            if state['packed'] < state['required']:
                state['packed'] += 1
                is_complete = state['packed'] == state['required']

                all_items_complete = all(s['packed'] == s['required'] for s in self.current_order_state.values())

                if all_items_complete:
                    status = "ORDER_COMPLETE"
                    self.order_completion_status[self.current_order_number] = datetime.now()
                else:
                    status = "SKU_OK"

                return {"row": state['row'], "packed": state['packed'], "is_complete": is_complete}, status
            else:
                return None, "SKU_EXTRA"
        else:
            return None, "SKU_NOT_FOUND"

    def manual_confirm_item(self, sku_to_confirm):
        """Manually confirms one unit of a given SKU in the current order."""
        if not self.current_order_number:
            return None, "NO_ACTIVE_ORDER"

        if sku_to_confirm in self.current_order_state:
            state = self.current_order_state[sku_to_confirm]
            if state['packed'] < state['required']:
                state['packed'] += 1
                is_complete = state['packed'] == state['required']
                all_items_complete = all(s['packed'] == s['required'] for s in self.current_order_state.values())

                if all_items_complete:
                    status = "ORDER_COMPLETE"
                    self.order_completion_status[self.current_order_number] = datetime.now()
                else:
                    status = "SKU_OK"

                return {"row": state['row'], "packed": state['packed'], "is_complete": is_complete}, status
            else:
                return None, "SKU_EXTRA"
        else:
            return None, "SKU_NOT_FOUND"

    def clear_current_order(self):
        self.current_order_number = None
        self.current_order_state = {}

    def clear_session_data(self):
        """Clears all data related to the current session."""
        self.packing_list_df = None
        self.orders_data = {}
        self.barcode_to_order_number = {}
        self.order_completion_status = {}
        self.clear_current_order()
