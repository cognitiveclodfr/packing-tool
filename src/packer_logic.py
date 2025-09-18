import os
import sys
import pandas as pd
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont
import io

REQUIRED_COLUMNS = ['Order_Number', 'SKU', 'Product_Name', 'Quantity']

class PackerLogic:
    def __init__(self, barcode_dir):
        self.barcode_dir = barcode_dir
        self.packing_list_df = None
        self.orders_data = {}
        self.barcode_to_order_number = {}
        self.current_order_number = None
        self.current_order_state = {}

    def _normalize_sku(self, sku):
        """Normalizes an SKU by removing non-alphanumeric characters and converting to lowercase."""
        return ''.join(filter(str.isalnum, sku)).lower()

    def load_packing_list_from_file(self, file_path):
        """Loads and processes the packing list from an Excel file."""
        try:
            df = pd.read_excel(file_path, dtype=str).fillna('')
        except Exception as e:
            raise ValueError(f"Failed to read the Excel file: {e}")

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
                raise ValueError(f"Not all required columns were mapped. Missing: {', '.join(missing)}")

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

        # --- DEBUG: Temporarily disabled font loading and text drawing ---
        # font_path = self._get_font_path()
        # try:
        #     font = ImageFont.truetype(font_path, 32)
        # except IOError:
        #     font = ImageFont.load_default()
        #     print(f"Warning: Could not load custom font at {font_path}. Using default font.")


        try:
            grouped = df.groupby('Order_Number')
            unnamed_counter = 1
            for order_number, group in grouped:
                safe_barcode_content = "".join(c for c in order_number if c.isalnum() or c in ('-', '_')).rstrip()
                if not safe_barcode_content:
                    safe_barcode_content = f"unnamed_order_{unnamed_counter}"
                    unnamed_counter += 1

                self.barcode_to_order_number[safe_barcode_content] = order_number

                # Generate barcode in memory
                barcode_obj = code128(safe_barcode_content, writer=ImageWriter())

                # Setting module_height dynamically is tricky. Let's try to set the image height instead.
                # A common module height is ~15.0
                options = {
                    'module_height': 15.0,
                    'write_text': False, # Explicitly disable default text
                    'quiet_zone': 2,
                }

                buffer = io.BytesIO()
                barcode_obj.write(buffer, options)
                buffer.seek(0)

                # Create final label image with Pillow
                barcode_img = Image.open(buffer)

                # Resize barcode to fit allocated space, preserving aspect ratio
                barcode_aspect_ratio = barcode_img.width / barcode_img.height
                new_barcode_height = BARCODE_HEIGHT_PX
                new_barcode_width = int(new_barcode_height * barcode_aspect_ratio)

                if new_barcode_width > LABEL_WIDTH_PX:
                    new_barcode_width = LABEL_WIDTH_PX
                    new_barcode_height = int(new_barcode_width / barcode_aspect_ratio)

                barcode_img = barcode_img.resize((new_barcode_width, new_barcode_height), Image.LANCZOS)

                # Create a new image for the label
                label_img = Image.new('RGB', (LABEL_WIDTH_PX, LABEL_HEIGHT_PX), 'white')

                # Paste barcode onto the label
                barcode_x = (LABEL_WIDTH_PX - new_barcode_width) // 2
                barcode_y = 0
                label_img.paste(barcode_img, (barcode_x, barcode_y))

                # --- DEBUG: Temporarily disabled text drawing ---
                # draw = ImageDraw.Draw(label_img)
                # text_bbox = draw.textbbox((0, 0), order_number, font=font)
                # text_width = text_bbox[2] - text_bbox[0]
                # text_x = (LABEL_WIDTH_PX - text_width) / 2
                # text_y = new_barcode_height + 5 # Place text below barcode with padding
                # draw.text((text_x, text_y), order_number, font=font, fill='black')

                # Save the final image
                barcode_path = os.path.join(self.barcode_dir, f"{safe_barcode_content}.png")
                label_img.save(barcode_path)

                self.orders_data[order_number] = {
                    'barcode_path': barcode_path,
                    'items': group.to_dict('records')
                }
            return len(self.orders_data)
        except Exception as e:
            raise RuntimeError(f"Error during barcode generation: {e}")

    def _get_font_path(self):
        """Gets the path to the DejaVuSans.ttf font file."""
        # This makes the path relative to this file, which is more robust
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_path, 'assets', 'DejaVuSans.ttf')

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
