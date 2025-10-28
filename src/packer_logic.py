import os
import sys
import tempfile
import shutil
import pandas as pd
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont
import io
import json
from pathlib import Path
from datetime import datetime
from PySide6.QtCore import QObject, Signal
from typing import List, Dict, Any, Tuple, Optional

from logger import get_logger

logger = get_logger(__name__)

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
        client_id (str): Client identifier for this session
        profile_manager (ProfileManager): Manager for client profiles and SKU mappings
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
        sku_map (Dict[str, str]): Normalized barcode-to-SKU mapping
    """
    item_packed = Signal(str, int, int)  # order_number, packed_count, required_count

    def __init__(self, client_id: str, profile_manager, barcode_dir: str):
        """
        Initialize PackerLogic instance for a specific client.

        Args:
            client_id: Client identifier (e.g., "M", "R")
            profile_manager: ProfileManager instance for loading/saving SKU mappings
            barcode_dir: Directory for storing session files and barcodes
        """
        super().__init__()

        self.client_id = client_id
        self.profile_manager = profile_manager
        self.barcode_dir = barcode_dir

        self.packing_list_df = None
        self.processed_df = None
        self.orders_data = {}
        self.barcode_to_order_number = {}
        self.current_order_number = None
        self.current_order_state = {}
        self.session_packing_state = {'in_progress': {}, 'completed_orders': []}

        # Load SKU mapping from ProfileManager
        self.sku_map = self._load_sku_mapping()

        # Load session state if exists
        self._load_session_state()

        logger.info(f"PackerLogic initialized for client {client_id}")
        logger.debug(f"Barcode directory: {barcode_dir}")
        logger.debug(f"Loaded {len(self.sku_map)} SKU mappings")

    def _load_sku_mapping(self) -> Dict[str, str]:
        """
        Load SKU mapping from ProfileManager.

        Returns:
            Dictionary of normalized barcode -> SKU mappings
        """
        try:
            mappings = self.profile_manager.load_sku_mapping(self.client_id)
            # Normalize keys for consistent matching
            normalized = {self._normalize_sku(k): v for k, v in mappings.items()}
            logger.debug(f"Loaded {len(normalized)} SKU mappings for client {self.client_id}")
            return normalized
        except Exception as e:
            logger.error(f"Error loading SKU mappings: {e}")
            return {}

    def set_sku_map(self, sku_map: Dict[str, str]):
        """
        Set the SKU map and save to ProfileManager.

        The barcode (key) is normalized to ensure consistent matching with
        scanner input. The SKU (value) is left as is. Changes are persisted
        to the centralized file server.

        Args:
            sku_map: The Barcode-to-SKU mapping

        Note:
            This method now saves to ProfileManager for cross-PC synchronization.
        """
        logger.info(f"Updating SKU mapping: {len(sku_map)} entries")

        # Normalize for in-memory use
        self.sku_map = {self._normalize_sku(k): v for k, v in sku_map.items()}

        # Save to ProfileManager (original keys, not normalized)
        try:
            self.profile_manager.save_sku_mapping(self.client_id, sku_map)
            logger.info("SKU mapping saved successfully")
        except Exception as e:
            logger.error(f"Failed to save SKU mapping: {e}")

    def _get_state_file_path(self) -> str:
        """Returns the absolute path for the session state file."""
        return os.path.join(self.barcode_dir, STATE_FILE_NAME)

    def _load_session_state(self):
        """Load the packing state for the session from JSON file."""
        state_file = self._get_state_file_path()

        if not os.path.exists(state_file):
            logger.debug("No existing session state found, starting fresh")
            self.session_packing_state = {'in_progress': {}, 'completed_orders': []}
            return

        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Handle both old and new format (with version)
            if isinstance(data, dict) and 'data' in data:
                # New format with version
                state_data = data['data']
            else:
                # Old format (direct state)
                state_data = data

            self.session_packing_state['in_progress'] = state_data.get('in_progress', {})
            self.session_packing_state['completed_orders'] = state_data.get('completed_orders', [])

            in_progress_count = len(self.session_packing_state['in_progress'])
            completed_count = len(self.session_packing_state['completed_orders'])

            logger.info(f"Session state loaded: {in_progress_count} in progress, {completed_count} completed")

        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading session state: {e}, starting fresh")
            self.session_packing_state = {'in_progress': {}, 'completed_orders': []}

    def _save_session_state(self):
        """
        Save the current session's packing state to JSON file with atomic write.

        Uses atomic write pattern to prevent corruption during crashes.
        Creates backup before overwriting.
        """
        state_file = self._get_state_file_path()

        # Create data with version and timestamp
        data = {
            'version': '1.0',
            'timestamp': datetime.now().isoformat(),
            'client_id': self.client_id,
            'data': self.session_packing_state
        }

        try:
            state_path = Path(state_file)
            state_dir = state_path.parent

            # Create backup if file exists
            if state_path.exists():
                backup_path = state_path.with_suffix('.json.backup')
                shutil.copy2(state_path, backup_path)
                logger.debug(f"Created backup: {backup_path}")

            # Atomic write: write to temp file first
            with tempfile.NamedTemporaryFile(
                mode='w',
                dir=state_dir,
                prefix='.tmp_state_',
                suffix='.json',
                delete=False,
                encoding='utf-8'
            ) as tmp_file:
                json.dump(data, tmp_file, indent=4)
                tmp_path = tmp_file.name

            # Atomic replace (works on Windows too)
            shutil.move(tmp_path, state_file)

            logger.debug("Session state saved successfully")

        except Exception as e:
            logger.error(f"CRITICAL: Failed to save session state: {e}", exc_info=True)

            # Try to restore from backup
            backup_path = Path(state_file).with_suffix('.json.backup')
            if backup_path.exists():
                try:
                    shutil.copy2(backup_path, state_file)
                    logger.warning("Restored session state from backup")
                except Exception as restore_error:
                    logger.error(f"Failed to restore from backup: {restore_error}")

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
        Load a packing list from an Excel file into a pandas DataFrame.

        Args:
            file_path: Path to the .xlsx file

        Returns:
            The loaded data as a DataFrame

        Raises:
            ValueError: If the file cannot be read or is empty
        """
        logger.info(f"Loading packing list from: {file_path}")

        try:
            df = pd.read_excel(file_path, dtype=str).fillna('')
            logger.debug(f"Loaded {len(df)} rows, {len(df.columns)} columns")
        except Exception as e:
            logger.error(f"Failed to read Excel file: {e}")
            raise ValueError(f"Could not read the Excel file: {e}")

        if df.empty:
            logger.error("Loaded Excel file is empty")
            raise ValueError("The file is empty or contains no data.")

        self.packing_list_df = df
        logger.info(f"Packing list loaded successfully: {len(df)} rows")
        return self.packing_list_df

    def process_data_and_generate_barcodes(self, column_mapping: Dict[str, str] = None) -> int:
        """
        Process the loaded DataFrame and generate barcodes for each order.

        This method validates columns, applies user-defined mappings, and then
        iterates through each unique order to generate a printable barcode image.
        The image includes the order number, courier, and the barcode itself.

        Args:
            column_mapping: Optional mapping from required column names to actual names in file

        Returns:
            Total number of unique orders processed

        Raises:
            ValueError: If the packing list is not loaded or columns are missing
            RuntimeError: If a critical error occurs during barcode generation
        """
        logger.info("Processing data and generating barcodes")

        if self.packing_list_df is None:
            logger.error("Cannot process data: packing list not loaded")
            raise ValueError("Packing list not loaded.")

        df = self.packing_list_df.copy()

        if column_mapping:
            logger.debug(f"Applying column mapping: {column_mapping}")
            inverted_mapping = {v: k for k, v in column_mapping.items()}
            df.rename(columns=inverted_mapping, inplace=True)

        missing_final = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if missing_final:
            logger.error(f"Missing required columns: {missing_final}")
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
            logger.warning("Arial fonts not found, falling back to default font")
            font = ImageFont.load_default()
            font_bold = font

        try:
            grouped = df.groupby('Order_Number')
            for order_number, group in grouped:
                safe_barcode_content = "".join(c for c in str(order_number) if c.isalnum() or c in '-_').rstrip()
                if not safe_barcode_content:
                    safe_barcode_content = f"unnamed_order_{len(self.orders_data)}"

                self.barcode_to_order_number[safe_barcode_content] = order_number

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

            order_count = len(self.orders_data)
            logger.info(f"Successfully generated {order_count} barcodes")
            return order_count

        except Exception as e:
            logger.error(f"Error during barcode generation: {e}", exc_info=True)
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
        if scanned_text not in self.barcode_to_order_number:
            return None, "ORDER_NOT_FOUND"

        original_order_number = self.barcode_to_order_number[scanned_text]

        if original_order_number in self.session_packing_state['completed_orders']:
            return None, "ORDER_ALREADY_COMPLETED"

        self.current_order_number = original_order_number
        items = self.orders_data[original_order_number]['items']

        if original_order_number in self.session_packing_state['in_progress']:
            self.current_order_state = self.session_packing_state['in_progress'][original_order_number]
        else:
            self.current_order_state = []
            for i, item in enumerate(items):
                sku = item.get('SKU')
                if not sku: continue
                try:
                    quantity = int(float(item.get('Quantity', 0)))
                except (ValueError, TypeError):
                    quantity = 1

                normalized_sku = self._normalize_sku(sku)
                self.current_order_state.append({
                    'original_sku': sku,
                    'normalized_sku': normalized_sku,
                    'required': quantity,
                    'packed': 0,
                    'row': i
                })
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

        # The rest of the logic uses the potentially translated SKU.
        normalized_final_sku = self._normalize_sku(final_sku)

        # Find the first matching item that is not yet fully packed
        found_item = None
        for item_state in self.current_order_state:
            if item_state['normalized_sku'] == normalized_final_sku and item_state['packed'] < item_state['required']:
                found_item = item_state
                break

        if found_item:
            found_item['packed'] += 1
            is_complete = found_item['packed'] == found_item['required']
            self.session_packing_state['in_progress'][self.current_order_number] = self.current_order_state

            all_items_complete = all(s['packed'] == s['required'] for s in self.current_order_state)

            if all_items_complete:
                status = "ORDER_COMPLETE"
                del self.session_packing_state['in_progress'][self.current_order_number]
                if self.current_order_number not in self.session_packing_state['completed_orders']:
                    self.session_packing_state['completed_orders'].append(self.current_order_number)
            else:
                status = "SKU_OK"
                total_packed = sum(s['packed'] for s in self.current_order_state)
                total_required = sum(s['required'] for s in self.current_order_state)
                self.item_packed.emit(self.current_order_number, total_packed, total_required)

            self._save_session_state()
            return {"row": found_item['row'], "packed": found_item['packed'], "is_complete": is_complete}, status

        # If no item was found above, it might be because all matching SKUs are already packed.
        # Let's check for that to return the correct status.
        is_sku_in_order = any(s['normalized_sku'] == normalized_final_sku for s in self.current_order_state)
        if is_sku_in_order:
            return None, "SKU_EXTRA"  # All items with this SKU are already packed
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
