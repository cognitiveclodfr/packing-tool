import os
import sys
import pandas as pd
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont
import io
import json
from PySide6.QtCore import QObject, Signal
from typing import List, Dict, Any, Tuple

REQUIRED_COLUMNS = ['Order_Number', 'SKU', 'Product_Name', 'Quantity', 'Courier']
STATE_FILE_NAME = "packing_state.json"

class PackerLogic(QObject):
    """
    Handles the core business logic of the Packer's Assistant application.

    This class is responsible for loading and processing packing lists,
    generating barcodes, managing the state of the packing process (what has
    been packed), and handling the logic for scanning items. It operates
    independently of the UI, communicating changes via Qt signals.

    Attributes:
        item_packed (Signal): A signal emitted when an item is packed, providing
                              real-time progress updates.
        barcode_dir (str): The directory where generated barcodes and session
                           state files are stored.
        packing_list_df (pd.DataFrame): The original, unprocessed DataFrame
                                        loaded from the Excel file.
        processed_df (pd.DataFrame): The DataFrame after column mapping and
                                     validation.
        orders_data (Dict): A dictionary containing details for each order,
                            including its barcode path and item list.
        barcode_to_order_number (Dict[str, str]): A mapping from barcode content
                                                  to the original order number.
        current_order_number (str | None): The order number currently being packed.
        current_order_state (Dict): The detailed packing state for the current
                                    order (required vs. packed counts for each SKU).
        session_packing_state (Dict): The packing state for the entire session,
                                      including in-progress and completed orders.
    """
    item_packed = Signal(str, int, int)  # order_number, packed_count, required_count

    def __init__(self, barcode_dir: str):
        """
        Initializes the PackerLogic instance.

        Args:
            barcode_dir (str): The directory for storing session files.
        """
        super().__init__()
        self.barcode_dir = barcode_dir
        self.packing_list_df = None
        self.processed_df = None
        self.orders_data = {}
        self.barcode_to_order_number = {}
        self.current_order_number = None
        self.current_order_state = {}
        self.session_packing_state = {'in_progress': {}, 'completed_orders': []}
        self.sku_map = {}
        self._load_session_state()

    def set_sku_map(self, sku_map: Dict[str, str]):
        """
        Sets the SKU map and creates a normalized version for quick lookups.

        The barcode (key) is normalized to ensure consistent matching with
        scanner input. The SKU (value) is left as is.

        Args:
            sku_map (Dict[str, str]): The Barcode-to-SKU mapping.
        """
        self.sku_map = {self._normalize_sku(k): v for k, v in sku_map.items()}

    def _get_state_file_path(self) -> str:
        """Returns the absolute path for the session state file."""
        return os.path.join(self.barcode_dir, STATE_FILE_NAME)

    def _load_session_state(self):
        """Loads the packing state for the session from a JSON file."""
        state_file = self._get_state_file_path()
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r') as f:
                    data = json.load(f)
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

    def _normalize_sku(self, sku: Any) -> str:
        """
        Normalizes an SKU for consistent comparison.

        Removes all non-alphanumeric characters and converts the string to
        lowercase. This makes the matching process robust against variations
        in barcode scanner output or data entry.

        Args:
            sku (Any): The SKU to normalize, typically a string or number.

        Returns:
            str: The normalized SKU string.
        """
        return ''.join(filter(str.isalnum, str(sku))).lower()

    def load_packing_list_from_file(self, file_path: str) -> pd.DataFrame:
        """
        Loads a packing list from an Excel file into a pandas DataFrame.

        Args:
            file_path (str): The path to the .xlsx file.

        Returns:
            pd.DataFrame: The loaded data as a DataFrame.

        Raises:
            ValueError: If the file cannot be read or is empty.
        """
        try:
            df = pd.read_excel(file_path, dtype=str).fillna('')
        except Exception as e:
            raise ValueError(f"Could not read the Excel file: {e}")

        if df.empty:
            raise ValueError("The file is empty or contains no data.")

        self.packing_list_df = df
        return self.packing_list_df

    def process_data_and_generate_barcodes(self, column_mapping: Dict[str, str] = None) -> int:
        """
        Processes the loaded DataFrame and generates barcodes for each order.

        This method validates columns, applies user-defined mappings, and then
        iterates through each unique order to generate a printable barcode image.
        The image includes the order number, courier, and the barcode itself.

        Args:
            column_mapping (Dict[str, str], optional): A mapping from required
                column names to the actual names in the file. Defaults to None.

        Returns:
            int: The total number of unique orders processed.

        Raises:
            ValueError: If the packing list is not loaded or columns are missing.
            RuntimeError: If a critical error occurs during barcode generation.
        """
        if self.packing_list_df is None:
            raise ValueError("Packing list not loaded.")

        df = self.packing_list_df.copy()
        if column_mapping:
            inverted_mapping = {v: k for k, v in column_mapping.items()}
            df.rename(columns=inverted_mapping, inplace=True)

        missing_final = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if missing_final:
            raise ValueError(f"The file is missing required columns: {', '.join(missing_final)}")

        self.processed_df = df
        self.orders_data = {}
        self.barcode_to_order_number = {}
        code128 = barcode.get_barcode_class('code128')

        DPI = 203
        LABEL_WIDTH_MM, LABEL_HEIGHT_MM = 65, 35
        LABEL_WIDTH_PX = int((LABEL_WIDTH_MM / 25.4) * DPI)
        LABEL_HEIGHT_PX = int((LABEL_HEIGHT_MM / 25.4) * DPI)
        TEXT_AREA_HEIGHT = 80
        BARCODE_HEIGHT_PX = LABEL_HEIGHT_PX - TEXT_AREA_HEIGHT

        font, font_bold = None, None
        try:
            font = ImageFont.truetype("arial.ttf", 32)
            font_bold = ImageFont.truetype("arialbd.ttf", 32)
        except IOError:
            print("Warning: Arial fonts not found. Falling back to default.")
            font = ImageFont.load_default()
            font_bold = font

        try:
            grouped = df.groupby('Order_Number')
            for order_number, group in grouped:
                safe_barcode_content = "".join(c for c in str(order_number) if c.isalnum() or c in '-_').rstrip()
                if not safe_barcode_content:
                    safe_barcode_content = f"unnamed_order_{len(self.orders_data)}"

                # Use a normalized (lowercase) key for the lookup dictionary
                self.barcode_to_order_number[safe_barcode_content.lower()] = order_number

                barcode_obj = code128(safe_barcode_content, writer=ImageWriter())
                buffer = io.BytesIO()
                barcode_obj.write(buffer, {'module_height': 15.0, 'write_text': False, 'quiet_zone': 2})
                buffer.seek(0)
                barcode_img = Image.open(buffer)

                aspect_ratio = barcode_img.width / barcode_img.height
                new_h = BARCODE_HEIGHT_PX
                new_w = min(int(new_h * aspect_ratio), LABEL_WIDTH_PX)
                barcode_img = barcode_img.resize((new_w, new_h), Image.LANCZOS)

                label_img = Image.new('RGB', (LABEL_WIDTH_PX, LABEL_HEIGHT_PX), 'white')
                barcode_x = (LABEL_WIDTH_PX - new_w) // 2
                label_img.paste(barcode_img, (barcode_x, 0))

                draw = ImageDraw.Draw(label_img)
                order_text = str(order_number)
                courier_name = str(group['Courier'].iloc[0])
                order_bbox = draw.textbbox((0, 0), order_text, font=font)
                courier_bbox = draw.textbbox((0, 0), courier_name, font=font_bold)

                order_x = (LABEL_WIDTH_PX - (order_bbox[2] - order_bbox[0])) / 2
                order_y = new_h + 5
                draw.text((order_x, order_y), order_text, font=font, fill='black')

                courier_x = (LABEL_WIDTH_PX - (courier_bbox[2] - courier_bbox[0])) / 2
                courier_y = order_y + (order_bbox[3] - order_bbox[1]) + 5
                draw.text((courier_x, courier_y), courier_name, font=font_bold, fill='black')

                barcode_path = os.path.join(self.barcode_dir, f"{safe_barcode_content}.png")
                label_img.save(barcode_path)

                self.orders_data[order_number] = {
                    'barcode_path': barcode_path,
                    'items': group.to_dict('records')
                }
            return len(self.orders_data)
        except Exception as e:
            raise RuntimeError(f"Error during barcode generation: {e}")

    def start_order_packing(self, scanned_text: str) -> Tuple[List[Dict] | None, str]:
        """
        Starts or resumes packing an order based on a scanned barcode.

        It looks up the order number, validates its status (e.g., not already
        completed), and loads its packing state into memory.

        Args:
            scanned_text (str): The content from the scanned order barcode.

        Returns:
            Tuple[List[Dict] | None, str]: A tuple containing the list of items
                                           for the order and a status string
                                           ("ORDER_LOADED", "ORDER_NOT_FOUND",
                                           "ORDER_ALREADY_COMPLETED").
        """
        # Normalize the scanned text for case-insensitive lookup
        normalized_scanned_text = scanned_text.strip().lower()

        if normalized_scanned_text not in self.barcode_to_order_number:
            return None, "ORDER_NOT_FOUND"

        original_order_number = self.barcode_to_order_number[normalized_scanned_text]

        if original_order_number in self.session_packing_state['completed_orders']:
            return None, "ORDER_ALREADY_COMPLETED"

        self.current_order_number = original_order_number
        items = self.orders_data[original_order_number]['items']

        if original_order_number in self.session_packing_state['in_progress']:
            self.current_order_state = self.session_packing_state['in_progress'][original_order_number]
        else:
            self.current_order_state = {}
            for i, item in enumerate(items):
                sku = item.get('SKU')
                if not sku: continue
                try:
                    quantity = int(float(item.get('Quantity', 0)))
                except (ValueError, TypeError):
                    quantity = 1
                normalized_sku = self._normalize_sku(sku)
                self.current_order_state[normalized_sku] = {
                    'original_sku': sku, 'required': quantity, 'packed': 0, 'row': i
                }
            self.session_packing_state['in_progress'][original_order_number] = self.current_order_state
            self._save_session_state()

        return items, "ORDER_LOADED"

    def process_sku_scan(self, sku: str) -> Tuple[Dict | None, str]:
        """
        Processes a scanned SKU for the currently active order.

        It normalizes the SKU, checks if it's part of the order, updates the
        packed count, and determines if the item or the entire order is complete.
        The packing state is saved after every valid scan.

        Args:
            sku (str): The content from the scanned product SKU barcode.

        Returns:
            Tuple[Dict | None, str]: A tuple containing a result dictionary
                                     (with row index and packed count) and a
                                     status string ("SKU_OK", "SKU_NOT_FOUND",
                                     "ORDER_COMPLETE", "SKU_EXTRA").
        """
        if not self.current_order_number:
            return None, "NO_ACTIVE_ORDER"

        normalized_scan = self._normalize_sku(sku)

        # Core logic change: Check if the scanned barcode has a mapped SKU.
        # If so, use the mapped SKU. If not, use the scanned code itself.
        # This ensures backward compatibility.
        final_sku = self.sku_map.get(normalized_scan, normalized_scan)

        # The rest of the logic uses the potentially translated SKU.
        normalized_final_sku = self._normalize_sku(final_sku)

        if normalized_final_sku in self.current_order_state:
            state = self.current_order_state[normalized_final_sku]
            if state['packed'] < state['required']:
                state['packed'] += 1
                is_complete = state['packed'] == state['required']
                self.session_packing_state['in_progress'][self.current_order_number] = self.current_order_state

                all_items_complete = all(s['packed'] == s['required'] for s in self.current_order_state.values())

                if all_items_complete:
                    status = "ORDER_COMPLETE"
                    del self.session_packing_state['in_progress'][self.current_order_number]
                    if self.current_order_number not in self.session_packing_state['completed_orders']:
                        self.session_packing_state['completed_orders'].append(self.current_order_number)
                else:
                    status = "SKU_OK"
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
        """Clears the currently active order from memory."""
        self.current_order_number = None
        self.current_order_state = {}

    def end_session_cleanup(self):
        """Removes the session state file upon graceful session termination."""
        state_file = self._get_state_file_path()
        if os.path.exists(state_file):
            try:
                os.remove(state_file)
            except OSError as e:
                print(f"Warning: Could not remove state file {state_file}. Reason: {e}")
