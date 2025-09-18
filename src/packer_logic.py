import os
import sys
import pandas as pd
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont
import io
import json
from PySide6.QtCore import QObject, Signal

REQUIRED_COLUMNS = ['Order_Number', 'SKU', 'Product_Name', 'Quantity']
STATE_FILE_NAME = "packing_state.json"

class PackerLogic(QObject):
    item_packed = Signal(str, int, int) # order_number, packed_count, required_count

    def __init__(self, barcode_dir):
        super().__init__()
        self.barcode_dir = barcode_dir
        self.packing_list_df = None
        self.orders_data = {}
        self.barcode_to_order_number = {}
        self.current_order_number = None
        self.current_order_state = {}
        self.session_packing_state = {'in_progress': {}, 'completed_orders': []}
        self._load_session_state()

    def _get_state_file_path(self):
        """Returns the absolute path for the session state file."""
        return os.path.join(self.barcode_dir, STATE_FILE_NAME)

    def _load_session_state(self):
        """Loads the packing state for the entire session from a JSON file."""
        state_file = self._get_state_file_path()
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r') as f:
                    data = json.load(f)
                    # Ensure both keys exist for compatibility with older state files
                    self.session_packing_state['in_progress'] = data.get('in_progress', {})
                    self.session_packing_state['completed_orders'] = data.get('completed_orders', [])
            except (json.JSONDecodeError, IOError):
                 self.session_packing_state = {'in_progress': {}, 'completed_orders': []}
        else:
            self.session_packing_state = {'in_progress': {}, 'completed_orders': []}

    def _save_session_state(self):
        """Saves the current session's packing state to a JSON file."""
        state_file = self._get_state_file_path()
        try:
            with open(state_file, 'w') as f:
                json.dump(self.session_packing_state, f, indent=4)
        except IOError as e:
            print(f"Error: Could not save session state to {state_file}. Reason: {e}")

    def _normalize_sku(self, sku):
        """Normalizes an SKU by removing non-alphanumeric characters and converting to lowercase."""
        return ''.join(filter(str.isalnum, str(sku))).lower()

    def load_packing_list_from_file(self, file_path):
        """Loads and processes the packing list from an Excel file."""
        try:
            df = pd.read_excel(file_path, dtype=str).fillna('')
        except Exception as e:
            raise ValueError(f"Не вдалося прочитати Excel файл: {e}")

        if df.empty:
            raise ValueError("The file is empty or contains no data.")

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
                raise ValueError(f"Не всі необхідні колонки були зіставлені. Відсутні: {', '.join(missing)}")

            inverted_mapping = {v: k for k, v in column_mapping.items()}
            df.rename(columns=inverted_mapping, inplace=True)

        # Verify columns after potential renaming
        missing_final = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if missing_final:
            raise ValueError(f"The file is missing required columns: {', '.join(missing_final)}")

        self.processed_df = df
        self.orders_data = {}
        self.barcode_to_order_number = {}
        code128 = barcode.get_barcode_class('code128')

        # Barcode dimensions
        DPI = 203
        LABEL_WIDTH_MM = 65
        LABEL_HEIGHT_MM = 35
        LABEL_WIDTH_PX = int((LABEL_WIDTH_MM / 25.4) * DPI)
        LABEL_HEIGHT_PX = int((LABEL_HEIGHT_MM / 25.4) * DPI)

        TEXT_AREA_HEIGHT = 50 # Approximate height for text
        BARCODE_HEIGHT_PX = LABEL_HEIGHT_PX - TEXT_AREA_HEIGHT

        font = None
        try:
            # Use a common system font like Arial, which is likely to be on Windows
            font = ImageFont.truetype("arial.ttf", 32)
        except IOError:
            print(f"Warning: Arial font not found. Falling back to default font.")
            font = ImageFont.load_default() # Load Pillow's default font as a fallback
        except Exception as e:
            print(f"CRITICAL: An unexpected error occurred during font loading: {e}.")
            # Font remains None, text will not be rendered

        try:
            grouped = df.groupby('Order_Number')
            unnamed_counter = 1
            for order_number, group in grouped:
                safe_barcode_content = "".join(c for c in str(order_number) if c.isalnum() or c in ('-', '_')).rstrip()
                if not safe_barcode_content:
                    safe_barcode_content = f"unnamed_order_{unnamed_counter}"
                    unnamed_counter += 1

                self.barcode_to_order_number[safe_barcode_content] = order_number

                # Generate barcode in memory
                barcode_obj = code128(safe_barcode_content, writer=ImageWriter())

                options = {
                    'module_height': 15.0,
                    'write_text': False,
                    'quiet_zone': 2,
                }

                buffer = io.BytesIO()
                barcode_obj.write(buffer, options)
                buffer.seek(0)

                barcode_img = Image.open(buffer)

                barcode_aspect_ratio = barcode_img.width / barcode_img.height
                new_barcode_height = BARCODE_HEIGHT_PX
                new_barcode_width = int(new_barcode_height * barcode_aspect_ratio)

                if new_barcode_width > LABEL_WIDTH_PX:
                    new_barcode_width = LABEL_WIDTH_PX
                    new_barcode_height = int(new_barcode_width / barcode_aspect_ratio)

                barcode_img = barcode_img.resize((new_barcode_width, new_barcode_height), Image.LANCZOS)

                label_img = Image.new('RGB', (LABEL_WIDTH_PX, LABEL_HEIGHT_PX), 'white')

                barcode_x = (LABEL_WIDTH_PX - new_barcode_width) // 2
                barcode_y = 0
                label_img.paste(barcode_img, (barcode_x, barcode_y))

                # Add text, but only if the font was loaded successfully
                if font:
                    try:
                        draw = ImageDraw.Draw(label_img)
                        text_to_draw = str(order_number)
                        text_bbox = draw.textbbox((0, 0), text_to_draw, font=font)
                        text_width = text_bbox[2] - text_bbox[0]
                        text_x = (LABEL_WIDTH_PX - text_width) / 2
                        text_y = new_barcode_height + 5
                        draw.text((text_x, text_y), text_to_draw, font=font, fill='black')
                    except Exception as e:
                        print(f"Warning: Failed to draw text for order '{order_number}'. Error: {e}")

                barcode_path = os.path.join(self.barcode_dir, f"{safe_barcode_content}.png")
                label_img.save(barcode_path)

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

        # Check if order is already completed
        if original_order_number in self.session_packing_state['completed_orders']:
            return None, "ORDER_ALREADY_COMPLETED"

        self.current_order_number = original_order_number
        items = self.orders_data[original_order_number]['items']

        # Check if state already exists for this order
        if original_order_number in self.session_packing_state['in_progress']:
            self.current_order_state = self.session_packing_state['in_progress'][original_order_number]
        else:
            # If not, create a new state for it
            self.current_order_state = {}
            for i, item in enumerate(items):
                sku = item.get('SKU')
                if not sku:
                    continue

                try:
                    quantity = int(float(item.get('Quantity', 0)))
                except (ValueError, TypeError):
                    quantity = 1

                # Use normalized SKU as the key for consistency
                normalized_sku = self._normalize_sku(sku)
                self.current_order_state[normalized_sku] = {
                    'original_sku': sku,
                    'required': quantity,
                    'packed': 0,
                    'row': i
                }
            # Immediately save the newly initialized state
            self.session_packing_state['in_progress'][original_order_number] = self.current_order_state
            self._save_session_state()

        return items, "ORDER_LOADED"

    def process_sku_scan(self, sku):
        """Processes a scanned SKU for the current order, normalizing for comparison."""
        if not self.current_order_number:
            return None, "NO_ACTIVE_ORDER"

        normalized_scanned_sku = self._normalize_sku(sku)

        if normalized_scanned_sku in self.current_order_state:
            state = self.current_order_state[normalized_scanned_sku]
            if state['packed'] < state['required']:
                state['packed'] += 1
                is_complete = state['packed'] == state['required']

                # Update the session state
                self.session_packing_state['in_progress'][self.current_order_number] = self.current_order_state

                all_items_complete = all(s['packed'] == s['required'] for s in self.current_order_state.values())

                if all_items_complete:
                    status = "ORDER_COMPLETE"
                    # Remove completed order from in_progress and add to completed_orders
                    del self.session_packing_state['in_progress'][self.current_order_number]
                    if self.current_order_number not in self.session_packing_state['completed_orders']:
                        self.session_packing_state['completed_orders'].append(self.current_order_number)
                else:
                    status = "SKU_OK"
                    # Emit signal for real-time table update
                    total_packed = sum(s['packed'] for s in self.current_order_state.values())
                    total_required = sum(s['required'] for s in self.current_order_state.values())
                    self.item_packed.emit(self.current_order_number, total_packed, total_required)

                self._save_session_state()
                return {"row": state['row'], "packed": state['packed'], "is_complete": is_complete}, status
            else:
                return None, "SKU_EXTRA"
        else:
            return None, "SKU_NOT_FOUND"

    def clear_current_order(self):
        """Clears the currently active order from memory (does not affect saved state)."""
        self.current_order_number = None
        self.current_order_state = {}

    def end_session_cleanup(self):
        """Cleans up session-related files, like the state file."""
        state_file = self._get_state_file_path()
        if os.path.exists(state_file):
            try:
                os.remove(state_file)
            except OSError as e:
                print(f"Warning: Could not remove state file {state_file}. Reason: {e}")
