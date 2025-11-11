# Standard library imports
import os
import sys
import tempfile
import shutil

# Third-party imports for data processing
import pandas as pd  # Excel file handling and data manipulation

# Barcode generation libraries
import barcode
from barcode.writer import ImageWriter

# Image processing for label generation
from PIL import Image, ImageDraw, ImageFont
import io  # In-memory binary streams for barcode images

# Data persistence and utilities
import json
from pathlib import Path
from datetime import datetime

# Qt framework for signals/slots pattern
from PySide6.QtCore import QObject, Signal

# Type hints for better code documentation
from typing import List, Dict, Any, Tuple, Optional

# Local imports
from logger import get_logger

# Initialize module-level logger
logger = get_logger(__name__)

# Required columns in the Excel packing list
# These columns are mandatory for the application to function correctly
# - Order_Number: Unique identifier for each order
# - SKU: Product stock keeping unit code
# - Product_Name: Human-readable product description
# - Quantity: Number of items to pack for this SKU in this order
# - Courier: Shipping courier name (e.g., "PostOne", "Speedy", "DHL")
REQUIRED_COLUMNS = ['Order_Number', 'SKU', 'Product_Name', 'Quantity', 'Courier']

# Filename for session state persistence
# This file stores packing progress and is saved after every scan
# to enable crash recovery and session restoration
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
        Load SKU mapping from ProfileManager for the current client.

        SKU mappings allow barcodes from products to be translated to internal SKU codes.
        This is useful when:
        - Products have multiple barcode standards (EAN-13, UPC, manufacturer codes)
        - Supplier barcodes differ from internal SKU system
        - Same product has different barcodes from different suppliers

        For small warehouses, this is critical because products often come from
        multiple suppliers with different barcode systems, but need to be tracked
        under a single internal SKU.

        The method normalizes all barcode keys (lowercase, alphanumeric only) to ensure
        consistent matching regardless of scanner input variations.

        Returns:
            Dictionary of normalized barcode -> SKU mappings
            Example: {"7290018664100": "SKU-CREAM-01", "8809765431234": "SKU-SERUM-02"}
            Returns empty dict if loading fails (graceful degradation)
        """
        try:
            # Load raw mappings from centralized storage (file server)
            mappings = self.profile_manager.load_sku_mapping(self.client_id)

            # Normalize all barcode keys for consistent matching
            # This handles variations in scanner output (spaces, dashes, mixed case)
            # Original SKU values are preserved as-is
            normalized = {self._normalize_sku(k): v for k, v in mappings.items()}

            logger.debug(f"Loaded {len(normalized)} SKU mappings for client {self.client_id}")
            return normalized
        except Exception as e:
            # Graceful degradation: if SKU mapping fails to load, continue without it
            # Scanned barcodes will be matched directly against order SKUs
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
        Normalizes an SKU for consistent comparison across different input sources.

        This normalization is essential for small warehouse operations where SKUs/barcodes
        can come from multiple sources with inconsistent formatting:
        - Manual Excel entry: may include spaces, dashes, parentheses
        - Barcode scanners: may add prefixes/suffixes depending on configuration
        - Different suppliers: varying formatting conventions
        - Copy-paste from supplier websites: may include special characters

        The normalization algorithm:
        1. Convert to string (handles numeric SKUs like "12345")
        2. Remove all non-alphanumeric characters (spaces, dashes, dots, etc.)
        3. Convert to lowercase (handles case-insensitive matching)

        Examples:
            "SKU-123-A" -> "sku123a"
            "7290 0186 6410 0" -> "72900186641100"
            "Product (ABC)" -> "productabc"
            12345 -> "12345"

        Args:
            sku (Any): The SKU to normalize, typically a string or number.
                      Can be Excel cell value (str, int, float)

        Returns:
            str: The normalized SKU string (lowercase alphanumeric only)
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

        # Use Code-128 barcode symbology
        # Code-128 is chosen because:
        # - High density encoding (more data in less space)
        # - Supports full ASCII character set (alphanumeric + special chars)
        # - Industry standard for shipping labels
        # - Compatible with all common barcode scanners in warehouse environment
        code128 = barcode.get_barcode_class('code128')

        # === BARCODE LABEL DIMENSIONS ===
        # These values are configured for common thermal printers used in small warehouses
        # (Zebra, Brother, Dymo, TSC, and similar models)

        # DPI (Dots Per Inch) = 203
        # This is the standard resolution for entry-level thermal printers
        # More expensive printers use 300 DPI, but 203 DPI is sufficient for
        # barcode readability and is the most common resolution in small businesses
        DPI = 203

        # Label dimensions in millimeters
        # 65mm x 35mm is a common label size that:
        # - Fits standard thermal printer rolls (most printers support 50-80mm width)
        # - Large enough for barcode + text information
        # - Small enough to be cost-effective (label cost per unit)
        # - Fits well on shipping boxes without taking excessive space
        LABEL_WIDTH_MM = 65   # 2.56 inches
        LABEL_HEIGHT_MM = 35  # 1.38 inches

        # Convert millimeters to pixels for image generation
        # Formula: (mm / 25.4) * DPI
        # 25.4 mm = 1 inch, so we convert mm -> inches -> pixels
        LABEL_WIDTH_PX = int((LABEL_WIDTH_MM / 25.4) * DPI)    # ~520 pixels
        LABEL_HEIGHT_PX = int((LABEL_HEIGHT_MM / 25.4) * DPI)  # ~280 pixels

        # Reserve space for text below the barcode
        # This area displays:
        # - Order Number (Line 1)
        # - Courier Name (Line 2, bold)
        # 80 pixels is calculated as:
        #   32pt font ≈ 42 pixels per line (including line spacing)
        #   2 lines × 42px = 84px, rounded to 80px for aesthetic margins
        TEXT_AREA_HEIGHT = 80

        # Calculate remaining height for barcode itself
        # The barcode uses the top portion of the label
        BARCODE_HEIGHT_PX = LABEL_HEIGHT_PX - TEXT_AREA_HEIGHT  # ~200 pixels

        # === FONT CONFIGURATION ===
        # Font size 32pt is chosen based on real-world warehouse testing:
        # - Readable from ~60cm (arm's length) for warehouse workers
        # - Not too large (wastes label space)
        # - Not too small (hard to read in warehouse lighting conditions)
        # - Optimal for small thermal printer labels
        FONT_SIZE_PT = 32

        font, font_bold = None, None
        try:
            # Try to load Arial fonts from system
            # Arial is widely available on Windows and renders clearly on thermal printers
            font = ImageFont.truetype("arial.ttf", FONT_SIZE_PT)
            font_bold = ImageFont.truetype("arialbd.ttf", FONT_SIZE_PT)
        except IOError:
            # Fallback to PIL's default font if Arial is not available
            # Note: Default font is typically much smaller (~11pt) and may be harder to read
            # This fallback ensures the application works on systems without Arial
            logger.warning("Arial fonts not found, falling back to default font")
            logger.warning("Label text may be smaller and less readable with default font")
            font = ImageFont.load_default()
            font_bold = font

        try:
            # Group all order rows by Order_Number
            # Each order may have multiple rows (one per SKU/product)
            # but we generate one label per order
            grouped = df.groupby('Order_Number')

            for order_number, group in grouped:
                # === STEP 1: Create safe barcode content ===
                # Barcode content must be alphanumeric + limited special chars
                # Remove any characters that Code-128 might struggle with
                # Keep: letters, numbers, hyphens, underscores
                # Remove: spaces, quotes, special chars that could cause scanner issues
                safe_barcode_content = "".join(c for c in str(order_number) if c.isalnum() or c in '-_').rstrip()

                # Handle edge case: if order number becomes empty after sanitization
                # (e.g., order number was "###" or "...")
                if not safe_barcode_content:
                    safe_barcode_content = f"unnamed_order_{len(self.orders_data)}"

                # Store mapping from sanitized barcode content back to original order number
                # This is needed when scanning: barcode content -> original order number
                self.barcode_to_order_number[safe_barcode_content] = order_number

                # === STEP 2: Generate barcode image ===
                # Create Code-128 barcode object
                barcode_obj = code128(safe_barcode_content, writer=ImageWriter())

                # Generate barcode to in-memory buffer (not disk file)
                buffer = io.BytesIO()

                # Barcode generation parameters:
                # - module_height: 15.0mm = height of individual barcode bars
                #   15mm is chosen because it's:
                #   * Tall enough for reliable scanning (minimum ~10mm recommended)
                #   * Not too tall (wastes label space)
                #   * Standard for shipping labels in small warehouse operations
                #
                # - write_text: False = don't include human-readable text below bars
                #   We handle text rendering ourselves for better layout control
                #
                # - quiet_zone: 2 = minimum blank space on left/right of barcode (in modules)
                #   Quiet zones are required by barcode standards for reliable scanning
                #   2 modules is the minimum; we rely on label margins for additional space
                barcode_obj.write(buffer, {
                    'module_height': 15.0,    # Bar height in mm
                    'write_text': False,      # We'll add text manually
                    'quiet_zone': 2           # Minimum blank space on sides
                })

                # Rewind buffer to start for reading
                buffer.seek(0)

                # Load barcode image from buffer
                barcode_img = Image.open(buffer)

                # === STEP 3: Resize barcode to fit label ===
                # Calculate aspect ratio to maintain barcode proportions
                # (barcode width varies based on encoded content length)
                aspect_ratio = barcode_img.width / barcode_img.height

                # Set height to available space (label height minus text area)
                new_h = BARCODE_HEIGHT_PX

                # Calculate width maintaining aspect ratio
                # Use min() to ensure barcode doesn't exceed label width
                # (important for long order numbers)
                new_w = min(int(new_h * aspect_ratio), LABEL_WIDTH_PX)

                # Resize using LANCZOS (high-quality downsampling)
                # LANCZOS is chosen over BILINEAR/NEAREST for best quality
                # (important for barcode clarity and scanner reliability)
                barcode_img = barcode_img.resize((new_w, new_h), Image.LANCZOS)

                # === STEP 4: Create label canvas ===
                # Create blank white label image at full label dimensions
                # RGB mode for compatibility with all printers
                # White background ensures good contrast with black barcode/text
                label_img = Image.new('RGB', (LABEL_WIDTH_PX, LABEL_HEIGHT_PX), 'white')

                # Center barcode horizontally on label
                # This provides balanced appearance and equal quiet zones
                barcode_x = (LABEL_WIDTH_PX - new_w) // 2

                # Paste barcode at top of label (y=0)
                label_img.paste(barcode_img, (barcode_x, 0))

                # === STEP 5: Add text information ===
                # Create drawing context for adding text
                draw = ImageDraw.Draw(label_img)

                # Prepare text content
                order_text = str(order_number)
                courier_name = str(group['Courier'].iloc[0])  # Get courier from first row of order

                # Calculate text dimensions for centering
                # textbbox returns (left, top, right, bottom) coordinates
                order_bbox = draw.textbbox((0, 0), order_text, font=font)
                courier_bbox = draw.textbbox((0, 0), courier_name, font=font_bold)

                # Calculate X position for centered order number
                order_x = (LABEL_WIDTH_PX - (order_bbox[2] - order_bbox[0])) / 2

                # Y position: just below barcode with 5px margin
                order_y = new_h + 5

                # Draw order number (normal font)
                draw.text((order_x, order_y), order_text, font=font, fill='black')

                # Calculate X position for centered courier name
                courier_x = (LABEL_WIDTH_PX - (courier_bbox[2] - courier_bbox[0])) / 2

                # Y position: below order number with 5px spacing
                # Spacing = order_y + height of order text + 5px gap
                courier_y = order_y + (order_bbox[3] - order_bbox[1]) + 5

                # Draw courier name (bold font for emphasis)
                # Courier is important for sorting packages by delivery method
                draw.text((courier_x, courier_y), courier_name, font=font_bold, fill='black')

                # === STEP 6: Save label to disk ===
                # Save as PNG for lossless quality (important for barcode scanning)
                # Filename uses sanitized barcode content for easy identification
                barcode_path = os.path.join(self.barcode_dir, f"{safe_barcode_content}.png")
                label_img.save(barcode_path)

                # === STEP 7: Store order data for later use ===
                # Store both the barcode file path and all order items
                # This data is used during packing to:
                # - Display the barcode image in UI
                # - Show which items need to be packed
                # - Track packing progress
                self.orders_data[order_number] = {
                    'barcode_path': barcode_path,
                    'items': group.to_dict('records')  # Convert DataFrame group to list of dicts
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

        This is the core method called every time a warehouse worker scans a product
        barcode. It handles:
        1. SKU normalization (to handle different barcode formats)
        2. SKU mapping translation (manufacturer barcode -> internal SKU)
        3. Matching against order requirements
        4. Updating packing progress
        5. Detecting order completion
        6. Persisting state after every scan (crash recovery)

        The method implements a sophisticated matching logic that:
        - Tries to find the SKU in the current order
        - Supports multi-quantity items (scan same SKU multiple times)
        - Detects when an item is fully packed
        - Detects when entire order is complete
        - Handles error cases (wrong SKU, already packed, etc.)

        Args:
            sku (str): The raw content from the scanned product SKU barcode.
                      Can be any format (EAN-13, UPC, manufacturer code, internal SKU)

        Returns:
            Tuple[Dict | None, str]: A tuple containing:
                - Result dictionary with packing details (if successful)
                  {"row": int, "packed": int, "is_complete": bool}
                - Status string indicating what happened:
                  * "SKU_OK" - Item packed successfully, order still in progress
                  * "ORDER_COMPLETE" - Item packed and order is now complete
                  * "SKU_NOT_FOUND" - Scanned SKU is not in this order
                  * "SKU_EXTRA" - All items with this SKU are already packed
                  * "NO_ACTIVE_ORDER" - No order currently selected
        """
        # Safety check: ensure an order is actually loaded
        # This prevents errors if user somehow scans before loading an order
        if not self.current_order_number:
            return None, "NO_ACTIVE_ORDER"

        # === STEP 1: Normalize scanned barcode ===
        # Remove spaces, dashes, convert to lowercase
        # This handles variations in scanner configuration and barcode formats
        normalized_scan = self._normalize_sku(sku)

        # === STEP 2: SKU Mapping Translation (if configured) ===
        # This is a critical feature for small warehouses where:
        # - Products come from multiple suppliers with different barcodes
        # - Manufacturer barcodes don't match internal SKU system
        # - Same product has different barcodes from different batches
        #
        # Example scenarios:
        #   Scan: "7290018664100" (EAN-13 barcode)
        #   Map:  "7290018664100" -> "SKU-CREAM-01" (internal SKU)
        #   Use:  "SKU-CREAM-01" for matching
        #
        # Fallback behavior:
        #   If no mapping exists, use the scanned barcode directly
        #   This ensures backward compatibility with orders that use
        #   manufacturer barcodes directly in the packing list
        final_sku = self.sku_map.get(normalized_scan, normalized_scan)

        # Normalize the final SKU (whether mapped or direct)
        # This ensures consistent matching even if mapping returns non-normalized value
        normalized_final_sku = self._normalize_sku(final_sku)

        # The rest of the logic uses the potentially translated SKU.
        normalized_final_sku = self._normalize_sku(final_sku)

        # === STEP 3: Find matching item in current order ===
        # Search through all items in the order for a match
        # Important: we look for the FIRST item that:
        # 1. Matches the SKU
        # 2. Is not yet fully packed (packed < required)
        #
        # This handles multi-quantity items correctly:
        # Example: Order requires 3x "SKU-CREAM-01"
        # - First scan: packed=0 -> packed=1
        # - Second scan: packed=1 -> packed=2
        # - Third scan: packed=2 -> packed=3 (complete!)
        found_item = None
        for item_state in self.current_order_state:
            if item_state['normalized_sku'] == normalized_final_sku and item_state['packed'] < item_state['required']:
                found_item = item_state
                break

        # === STEP 4: Process successful match ===
        if found_item:
            # Increment packed count for this item
            found_item['packed'] += 1

            # Check if this specific item is now complete
            # (all required quantity for this SKU has been packed)
            is_complete = found_item['packed'] == found_item['required']

            # Update session state (in-memory)
            self.session_packing_state['in_progress'][self.current_order_number] = self.current_order_state

            # === Check if ENTIRE order is complete ===
            # An order is complete when ALL items have been packed
            # (not just the current item)
            all_items_complete = all(s['packed'] == s['required'] for s in self.current_order_state)

            if all_items_complete:
                # Order is complete!
                status = "ORDER_COMPLETE"

                # Move order from "in_progress" to "completed_orders"
                del self.session_packing_state['in_progress'][self.current_order_number]

                # Add to completed list (if not already there)
                # This check prevents duplicates in case of rare edge cases
                if self.current_order_number not in self.session_packing_state['completed_orders']:
                    self.session_packing_state['completed_orders'].append(self.current_order_number)
            else:
                # Order still in progress
                status = "SKU_OK"

                # Calculate overall progress for this order
                # (total items packed vs total items required)
                total_packed = sum(s['packed'] for s in self.current_order_state)
                total_required = sum(s['required'] for s in self.current_order_state)

                # Emit Qt signal to update UI progress display
                # This allows the UI to show "5/8 items packed" in real-time
                self.item_packed.emit(self.current_order_number, total_packed, total_required)

            # === CRITICAL: Save state to disk ===
            # This is called after EVERY successful scan to ensure:
            # - No data loss if application crashes
            # - Session can be restored exactly where we left off
            # - Multi-PC environments see consistent state
            self._save_session_state()

            # Return success with detailed information
            return {"row": found_item['row'], "packed": found_item['packed'], "is_complete": is_complete}, status

        # === STEP 5: Handle error cases ===
        # If we reach here, the scanned SKU didn't match any unpacked item

        # Check if SKU exists in order but all items are already packed
        is_sku_in_order = any(s['normalized_sku'] == normalized_final_sku for s in self.current_order_state)

        if is_sku_in_order:
            # SKU is in order, but all required quantity already packed
            # Example: Order needs 2x "SKU-CREAM-01", but user scanned it 3 times
            return None, "SKU_EXTRA"  # All items with this SKU are already packed
        else:
            # SKU is not in this order at all
            # Example: User scanned wrong product, or product from different order
            return None, "SKU_NOT_FOUND"

    def clear_current_order(self):
        """Clears the currently active order from memory."""
        self.current_order_number = None
        self.current_order_state = {}

    def load_packing_list_json(self, packing_list_path: Path) -> Tuple[int, str]:
        """
        Завантажити конкретний пакінг лист з JSON файлу.

        This method loads a specific packing list JSON file generated by Shopify Tool.
        Packing list JSONs are pre-filtered collections of orders ready for packing,
        typically organized by courier or delivery method.

        Expected JSON format:
        {
          "list_name": "DHL_Orders",
          "created_at": "2025-11-11T10:00:00",
          "courier": "DHL",  # Optional, if list is courier-specific
          "total_orders": 25,
          "orders": [
            {
              "order_number": "ORDER-001",
              "courier": "DHL",
              "items": [
                {"sku": "SKU-123", "quantity": 2, "product_name": "Product A"}
              ]
            }
          ]
        }

        Args:
            packing_list_path: Повний шлях до JSON файлу пакінг листа
                              (e.g., .../packing_lists/DHL_Orders.json)

        Returns:
            Tuple[int, str]: (кількість замовлень, назва листа)

        Raises:
            ValueError: Якщо файл не існує або невалідний JSON
            RuntimeError: If barcode generation fails
        """
        logger.info(f"Loading packing list from: {packing_list_path}")

        # Validate file exists
        packing_list_path = Path(packing_list_path)
        if not packing_list_path.exists():
            error_msg = f"Packing list file not found: {packing_list_path}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Extract list name from filename (without .json extension)
        list_name = packing_list_path.stem

        # Load JSON data
        try:
            with open(packing_list_path, 'r', encoding='utf-8') as f:
                packing_data = json.load(f)

            logger.debug(f"Loaded packing list: {packing_data.get('list_name', list_name)}")

        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON in packing list file: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        except Exception as e:
            error_msg = f"Error reading packing list file: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Extract orders list
        orders_list = packing_data.get('orders', [])
        if not orders_list:
            logger.warning(f"No orders found in packing list: {list_name}")
            return 0, packing_data.get('list_name', list_name)

        # Convert to DataFrame (packing list format)
        # Each order may have multiple items, need to flatten
        rows = []

        for order in orders_list:
            # Validate required order fields
            missing_fields = []
            if 'order_number' not in order:
                missing_fields.append('order_number')
            if 'courier' not in order or not order['courier']:
                missing_fields.append('courier')

            if missing_fields:
                error_msg = f"Missing required fields in order data: {missing_fields}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            order_number = order['order_number']
            courier = order['courier']
            items = order.get('items', [])

            if not items:
                logger.warning(f"Order {order_number} has no items, skipping")
                continue

            for item in items:
                row = {
                    'Order_Number': order_number,
                    'SKU': item.get('sku', ''),
                    'Product_Name': item.get('product_name', ''),
                    'Quantity': str(item.get('quantity', 1)),  # Convert to string for consistency
                    'Courier': courier
                }

                # Add any extra fields from order
                # (e.g., customer name, address, tracking number, etc.)
                for key, value in order.items():
                    if key not in ['order_number', 'courier', 'items']:
                        # Capitalize key to match packing list style
                        formatted_key = key.replace('_', ' ').title().replace(' ', '_')
                        row[formatted_key] = str(value)

                rows.append(row)

        # Create DataFrame
        df = pd.DataFrame(rows)

        if df.empty:
            logger.warning("No order items to process")
            return 0, packing_data.get('list_name', list_name)

        # Validate required columns
        missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if missing_cols:
            error_msg = f"Missing required columns in packing list: {missing_cols}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Store as packing_list_df and processed_df
        self.packing_list_df = df
        self.processed_df = df.copy()

        logger.info(f"Converted {len(df)} items from {len(orders_list)} orders to DataFrame")

        # Generate barcodes
        try:
            order_count = self.process_data_and_generate_barcodes(column_mapping=None)
            logger.info(f"Successfully loaded packing list '{list_name}': {order_count} orders")

            return order_count, packing_data.get('list_name', list_name)

        except Exception as e:
            error_msg = f"Error generating barcodes from packing list: {e}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg)

    def load_from_shopify_analysis(self, session_path: Path) -> Tuple[int, str]:
        """
        Load orders data from Shopify Tool's analysis_data.json.

        This method enables integration with Shopify Tool (Phase 1.3.2).
        It reads analysis_data.json from a Shopify session and converts it
        into the packing_list format expected by PackerLogic.

        Workflow:
        1. Read analysis_data.json from session/analysis/
        2. Convert Shopify order format to packing list DataFrame
        3. Generate barcodes for all orders
        4. Initialize orders_data structure

        Analysis data format (from Shopify Tool):
        {
          "analyzed_at": "2025-11-04T11:00:00",
          "total_orders": 150,
          "fulfillable_orders": 142,
          "orders": [
            {
              "order_number": "ORDER-001",
              "courier": "DHL",
              "status": "Fulfillable",
              "items": [
                {"sku": "SKU-123", "quantity": 2, "product_name": "Product A"}
              ]
            }
          ]
        }

        Args:
            session_path: Path to Shopify session directory
                         (e.g., Sessions/CLIENT_M/2025-11-04_1/)

        Returns:
            Tuple of (order_count, analysis_timestamp)

        Raises:
            ValueError: If analysis_data.json not found or invalid format
            RuntimeError: If barcode generation fails
        """
        logger.info(f"Loading data from Shopify session: {session_path}")

        # Locate analysis_data.json
        analysis_file = Path(session_path) / "analysis" / "analysis_data.json"

        if not analysis_file.exists():
            error_msg = f"analysis_data.json not found in {session_path}/analysis/"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Load analysis data
        try:
            with open(analysis_file, 'r', encoding='utf-8') as f:
                analysis_data = json.load(f)

            logger.debug(f"Loaded analysis data: {analysis_data.get('total_orders', 0)} orders")

        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON in analysis_data.json: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        except Exception as e:
            error_msg = f"Error reading analysis_data.json: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Extract orders list
        orders_list = analysis_data.get('orders', [])
        if not orders_list:
            logger.warning("No orders found in analysis_data.json")
            return 0, analysis_data.get('analyzed_at', 'Unknown')

        # Convert to DataFrame (packing list format)
        # Each order may have multiple items, need to flatten
        rows = []

        for order in orders_list:
            # Validate required order fields
            missing_fields = []
            if 'order_number' not in order:
                missing_fields.append('order_number')
            if 'courier' not in order or not order['courier']:
                missing_fields.append('courier')

            if missing_fields:
                error_msg = f"Missing required columns in order data: {missing_fields}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            order_number = order['order_number']
            courier = order['courier']
            items = order.get('items', [])

            for item in items:
                row = {
                    'Order_Number': order_number,
                    'SKU': item.get('sku', ''),
                    'Product_Name': item.get('product_name', ''),
                    'Quantity': str(item.get('quantity', 1)),  # Convert to string for consistency
                    'Courier': courier
                }

                # Add any extra fields from Shopify analysis
                # (e.g., customer name, address, etc.)
                for key, value in order.items():
                    if key not in ['order_number', 'courier', 'items', 'status']:
                        # Capitalize key to match packing list style
                        formatted_key = key.replace('_', ' ').title().replace(' ', '_')
                        row[formatted_key] = str(value)

                rows.append(row)

        # Create DataFrame
        df = pd.DataFrame(rows)

        if df.empty:
            logger.warning("No order items to process")
            return 0, analysis_data.get('analyzed_at', 'Unknown')

        # Validate required columns
        missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if missing_cols:
            error_msg = f"Missing required columns in analysis data: {missing_cols}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Store as packing_list_df and processed_df
        self.packing_list_df = df
        self.processed_df = df.copy()

        logger.info(f"Converted {len(df)} items from {len(orders_list)} orders to DataFrame")

        # Generate barcodes
        try:
            order_count = self.process_data_and_generate_barcodes(column_mapping=None)
            logger.info(f"Successfully loaded Shopify session: {order_count} orders")

            return order_count, analysis_data.get('analyzed_at', 'Unknown')

        except Exception as e:
            error_msg = f"Error generating barcodes from Shopify data: {e}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg)

    def end_session_cleanup(self):
        """Removes the session state file upon graceful session termination."""
        state_file = self._get_state_file_path()
        if os.path.exists(state_file):
            try:
                os.remove(state_file)
            except OSError as e:
                print(f"Warning: Could not remove state file {state_file}. Reason: {e}")
