import logging
from collections import defaultdict
from functools import partial
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QLabel, QLineEdit, QHeaderView, QPushButton, QAbstractItemView, QFrame,
    QGroupBox, QProgressBar, QMessageBox, QApplication, QStyle
)
from PySide6.QtGui import QFont, QColor, QPalette, QIcon
from PySide6.QtCore import Qt, Signal, QSize
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class PackerModeWidget(QWidget):
    """
    The user interface for the main "Packer Mode" screen.

    This widget displays the items for the currently active order, provides
    visual feedback on scanning actions, and captures input from a barcode
    scanner. It is designed to be a dedicated, focused view for the packing
    process.

    Attributes:
        barcode_scanned (Signal): Emitted when a barcode is scanned.
        exit_packing_mode (Signal): Emitted when the user clicks the exit button.
        skip_order_requested (Signal): Emitted when the skip order button is clicked.
        cancel_item_requested (Signal[int]): Emitted with row index on -1 button press.
        force_confirm_requested (Signal[int]): Emitted with row index on Force Confirm.
        map_sku_requested (Signal[str]): Emitted with original SKU on Map SKU press.
        extra_confirmed (Signal[str]): Emitted with normalized_sku on Keep extra.
        extra_removed (Signal[str]): Emitted with normalized_sku on Remove extra.
        table_frame (QFrame): Frame around items table used for flashing visual feedback.
        table (QTableWidget): Table displaying the SKUs for the current order.
        session_progress_bar (QProgressBar): Shows completed/total orders for the session.
        status_label (QLabel): Shows current order status.
        notification_label (QLabel): Large label for prominent notifications.
        scanner_input (QLineEdit): Hidden line edit that captures barcode scanner input.
        raw_scan_label (QLabel): Shows raw text from the last scan.
        history_table (QTableWidget): History of scanned orders in this session.
    """
    barcode_scanned        = Signal(str)
    exit_packing_mode      = Signal()
    skip_order_requested   = Signal()
    cancel_item_requested  = Signal(int)   # row index
    force_confirm_requested = Signal(int)  # row index
    map_sku_requested      = Signal(str)   # original SKU string
    extra_confirmed        = Signal(str)   # normalized_sku
    extra_removed          = Signal(str)   # normalized_sku

    FRAME_DEFAULT_STYLE = "QFrame#TableFrame { border: 1px solid palette(mid); border-radius: 3px; }"

    def __init__(self, parent: QWidget = None, sim_mode: bool = False):
        """
        Initializes the PackerModeWidget and its UI components.

        Args:
            parent (QWidget, optional): The parent widget. Defaults to None.
            sim_mode (bool): When True, show a visible scan simulator panel for
                development/testing without a physical barcode scanner. Defaults to False.
        """
        super().__init__(parent)
        self._sim_mode = sim_mode

        main_layout = QHBoxLayout(self)

        # ─── LEFT PANEL ──────────────────────────────────────────────────────
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(4)

        # [B] Session progress bar
        self.session_progress_bar = QProgressBar()
        self.session_progress_bar.setFixedHeight(18)
        self.session_progress_bar.setTextVisible(True)
        self.session_progress_bar.setFormat("0 / 0 orders")
        self.session_progress_bar.setValue(0)
        self.session_progress_bar.setMaximum(1)
        left_layout.addWidget(self.session_progress_bar)

        # [A] Order metadata banner (hidden until an order is loaded)
        self.metadata_banner = QFrame()
        self.metadata_banner.setObjectName("MetadataBanner")
        self.metadata_banner.setStyleSheet(
            "QFrame#MetadataBanner { border: 1px solid palette(mid); border-radius: 3px; "
            "background-color: palette(alternate-base); }"
        )
        self.metadata_banner.setVisible(False)
        _mbl = QHBoxLayout(self.metadata_banner)
        _mbl.setContentsMargins(6, 3, 6, 3)
        _mbl.setSpacing(6)
        _chip_style = (
            "QLabel { border: 1px solid palette(mid); border-radius: 4px; "
            "padding: 2px 7px; background-color: palette(button); }"
        )
        self._meta_type_lbl    = QLabel()
        self._meta_courier_lbl = QLabel()
        self._meta_country_lbl = QLabel()
        self._meta_box_lbl     = QLabel()
        self._meta_tags_lbl    = QLabel()
        self._meta_notes_lbl   = QLabel()
        self._meta_notes_lbl.setWordWrap(True)
        for lbl in [self._meta_type_lbl, self._meta_courier_lbl,
                    self._meta_country_lbl, self._meta_box_lbl,
                    self._meta_tags_lbl, self._meta_notes_lbl]:
            f = lbl.font(); f.setPointSize(9); lbl.setFont(f)
            lbl.setStyleSheet(_chip_style)
            lbl.setVisible(False)
            _mbl.addWidget(lbl)
        # Notes label takes remaining space
        _mbl.setStretchFactor(self._meta_notes_lbl, 1)
        left_layout.addWidget(self.metadata_banner)

        # Items table inside a frame
        self.table_frame = QFrame()
        self.table_frame.setObjectName("TableFrame")
        self.table_frame.setFrameShape(QFrame.Shape.Box)
        self.table_frame.setFrameShadow(QFrame.Shadow.Plain)
        self.table_frame.setStyleSheet(self.FRAME_DEFAULT_STYLE)
        frame_layout = QVBoxLayout(self.table_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Product Name", "SKU", "Qty", "Status", "Actions"])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.Fixed)
        hdr.resizeSection(4, 135)
        hdr.setStretchLastSection(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)

        frame_layout.addWidget(self.table)
        left_layout.addWidget(self.table_frame)

        # Scanned Orders History — compact panel below the items table (left panel)
        _hist_title = QLabel("Scanned Orders History:")
        _hist_title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        _hf = _hist_title.font(); _hf.setPointSize(9); _hist_title.setFont(_hf)
        left_layout.addWidget(_hist_title)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(1)
        self.history_table.setHorizontalHeaderLabels(["Order #"])
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.history_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.history_table.setFocusPolicy(Qt.NoFocus)
        self.history_table.setMaximumHeight(90)
        left_layout.addWidget(self.history_table)

        # [D] Summary panel — deduped SKUs with summed quantities (hidden until order loaded)
        self.summary_frame = QFrame()
        self.summary_frame.setObjectName("SummaryFrame")
        self.summary_frame.setStyleSheet(
            "QFrame#SummaryFrame { border: 1px solid palette(mid); border-radius: 3px; }"
        )
        self.summary_frame.setVisible(False)
        _sfl = QVBoxLayout(self.summary_frame)
        _sfl.setContentsMargins(4, 2, 4, 2)
        _sfl.setSpacing(2)
        _sh = QLabel("Summary (unique SKUs):")
        _shf = _sh.font(); _shf.setPointSize(9); _sh.setFont(_shf)
        _sfl.addWidget(_sh)
        self.summary_table = QTableWidget()
        self.summary_table.setColumnCount(3)
        self.summary_table.setHorizontalHeaderLabels(["SKU", "Packed/Total", "Status"])
        self.summary_table.horizontalHeader().setStretchLastSection(True)
        self.summary_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.summary_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.summary_table.setFocusPolicy(Qt.NoFocus)
        _sfl.addWidget(self.summary_table)
        # summary_frame lives in the right panel (added there below)

        # ─── RIGHT PANEL ─────────────────────────────────────────────────────
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setAlignment(Qt.AlignCenter)

        # Dev mode: visible scan simulator panel (replaces physical barcode scanner)
        if self._sim_mode:
            sim_group = QGroupBox("Scan Simulator (Dev Mode)")
            sim_group.setStyleSheet(
                "QGroupBox { border: 2px dashed #e67e22; border-radius: 6px; "
                "margin-top: 6px; padding: 4px; color: #e67e22; font-weight: bold; }"
                "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
            )
            sim_layout = QHBoxLayout(sim_group)
            self.sim_input = QLineEdit()
            self.sim_input.setPlaceholderText("Type order number or SKU, press Enter to scan...")
            self.sim_input.returnPressed.connect(self._on_sim_scan)
            sim_btn = QPushButton("Scan")
            sim_btn.setFixedWidth(70)
            sim_btn.clicked.connect(self._on_sim_scan)
            sim_layout.addWidget(self.sim_input)
            sim_layout.addWidget(sim_btn)
            right_layout.addWidget(sim_group)

        self.status_label = QLabel("Scan an order barcode")
        font = QFont(); font.setPointSize(20)
        self.status_label.setFont(font)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)

        self.notification_label = QLabel("")
        notif_font = QFont(); notif_font.setPointSize(32); notif_font.setBold(True)
        self.notification_label.setFont(notif_font)
        self.notification_label.setAlignment(Qt.AlignCenter)
        self.notification_label.setWordWrap(True)

        right_layout.addWidget(self.status_label)
        right_layout.addWidget(self.notification_label)
        right_layout.addStretch()

        # [D] Summary panel — inserted here in the right panel
        right_layout.addWidget(self.summary_frame)

        # [J] Extra items panel (hidden by default, shown when extras detected)
        self.extras_panel = QFrame()
        self.extras_panel.setObjectName("ExtrasPanel")
        self.extras_panel.setStyleSheet(
            "QFrame#ExtrasPanel { border: 2px solid #b06020; border-radius: 3px; }"
        )
        self.extras_panel.setVisible(False)
        _epl = QVBoxLayout(self.extras_panel)
        _epl.setContentsMargins(4, 4, 4, 4)
        _epl.setSpacing(3)
        _et = QLabel("EXTRA ITEMS DETECTED")
        _et.setAlignment(Qt.AlignCenter)
        _et.setStyleSheet("color: #e67e22; font-weight: bold;")
        _epl.addWidget(_et)
        self.extras_table = QTableWidget()
        self.extras_table.setColumnCount(3)
        self.extras_table.setHorizontalHeaderLabels(["SKU", "×", "Action"])
        self.extras_table.horizontalHeader().setStretchLastSection(True)
        self.extras_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.extras_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.extras_table.setFocusPolicy(Qt.NoFocus)
        self.extras_table.setMaximumHeight(130)
        _epl.addWidget(self.extras_table)
        right_layout.addWidget(self.extras_panel)

        raw_scan_title = QLabel("Last Scan:")
        raw_scan_title.setAlignment(Qt.AlignCenter)
        self.raw_scan_label = QLabel("-")
        self.raw_scan_label.setAlignment(Qt.AlignCenter)
        self.raw_scan_label.setObjectName("RawScanLabel")
        self.raw_scan_label.setWordWrap(True)

        right_layout.addWidget(raw_scan_title)
        right_layout.addWidget(self.raw_scan_label)
        right_layout.addStretch()

        self.scanner_input = QLineEdit()
        self.scanner_input.setFixedSize(1, 1)
        self.scanner_input.returnPressed.connect(self._on_scan)
        right_layout.addWidget(self.scanner_input)

        # [E] Skip Order button (disabled until an order is loaded)
        self.skip_order_button = QPushButton("Skip Order →")
        self.skip_order_button.setFocusPolicy(Qt.NoFocus)
        self.skip_order_button.setEnabled(False)
        self.skip_order_button.clicked.connect(self.skip_order_requested.emit)
        right_layout.addWidget(self.skip_order_button)

        right_layout.addStretch()
        self.exit_button = QPushButton("<< Back to Menu")
        font = self.exit_button.font(); font.setPointSize(14)
        self.exit_button.setFont(font)
        self.exit_button.clicked.connect(self.exit_packing_mode.emit)
        right_layout.addWidget(self.exit_button)

        main_layout.addWidget(left_widget, stretch=2)
        main_layout.addWidget(right_widget, stretch=1)

    # ─── Scanner input handlers ───────────────────────────────────────────────

    def _on_scan(self):
        """
        Private slot to handle the returnPressed signal from the scanner input.
        It emits the public barcode_scanned signal with the input text.
        """
        text = self.scanner_input.text()
        self.scanner_input.clear()
        self.barcode_scanned.emit(text)

    def _on_sim_scan(self):
        """
        Private slot for the scan simulator panel (dev mode only).

        Reads text from the visible simulator input field and emits
        the same ``barcode_scanned`` signal as a physical scanner would,
        so all normal packing logic handles it unchanged.
        """
        text = self.sim_input.text().strip()
        if text:
            self.sim_input.clear()
            self.barcode_scanned.emit(text)

    # ─── Action button slots ──────────────────────────────────────────────────

    def _on_manual_confirm(self, sku: str):
        """
        Private slot for the 'Confirm Manually' button. Emits the
        barcode_scanned signal with the SKU for the corresponding row.
        """
        if sku:
            self.barcode_scanned.emit(sku)
        self.set_focus_to_scanner()

    def _on_cancel_item(self, row: int):
        """Show confirmation dialog then emit cancel_item_requested."""
        reply = QMessageBox.question(
            self, "Undo Scan",
            "Undo the last scan for this item?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.cancel_item_requested.emit(row)
        self.set_focus_to_scanner()

    def _on_force_confirm(self, row: int):
        """Show confirmation dialog then emit force_confirm_requested."""
        reply = QMessageBox.question(
            self, "Force Confirm",
            "Force-confirm ALL remaining quantity for this item?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.force_confirm_requested.emit(row)
        self.set_focus_to_scanner()

    def _on_map_sku_requested(self, sku: str):
        """Emit map_sku_requested with the original SKU string."""
        self.map_sku_requested.emit(sku)
        self.set_focus_to_scanner()

    def _on_extra_confirmed(self, norm_sku: str):
        """Emit extra_confirmed for the given normalized SKU."""
        self.extra_confirmed.emit(norm_sku)
        self.set_focus_to_scanner()

    def _on_extra_removed(self, norm_sku: str):
        """Emit extra_removed for the given normalized SKU."""
        self.extra_removed.emit(norm_sku)
        self.set_focus_to_scanner()

    # ─── Public display methods ───────────────────────────────────────────────

    def display_order(
        self,
        items: List[Dict[str, Any]],
        order_state: List[Dict[str, Any]],
        metadata: Dict[str, Any] = None,
        sku_map: Dict[str, str] = None,
    ):
        """
        Populates the items table with the details of the current order.

        Args:
            items: List of product dicts for the order.
            order_state: Current packing state (packed counts per row).
            metadata: Optional order-level metadata dict (tags, notes, etc.).
            sku_map: Optional normalized barcode→SKU mapping for Map SKU detection.
        """
        # [A] Show metadata banner if available
        self._update_metadata_banner(metadata)

        self.table.setRowCount(len(items))

        # First, populate the table with all items as 'Pending'
        for row, item in enumerate(items):
            sku = item.get('SKU', '')
            quantity_str = str(item.get('Quantity', ''))
            try:
                quantity_int = int(float(quantity_str))
            except (ValueError, TypeError):
                quantity_int = 1

            self.table.setItem(row, 0, QTableWidgetItem(item.get('Product_Name', '')))
            self.table.setItem(row, 1, QTableWidgetItem(sku))

            # [C] Amber highlight when quantity > 1
            qty_item = QTableWidgetItem(f"0 / {quantity_int}")
            if quantity_int > 1:
                qty_item.setBackground(QColor("#5a4000"))
                qty_item.setForeground(QColor("#f39c12"))
            self.table.setItem(row, 2, qty_item)

            status_item = QTableWidgetItem("Pending")
            palette = self.table.palette()
            pending_bg = palette.color(QPalette.ColorRole.Highlight).lighter(180)
            pending_fg = palette.color(QPalette.ColorRole.HighlightedText)
            status_item.setBackground(pending_bg)
            status_item.setForeground(pending_fg)
            self.table.setItem(row, 3, status_item)

            # Actions column: Confirm / -1 / Force / Map
            actions_widget = self._make_actions_widget(row, sku, quantity_int, sku_map or {})
            self.table.setCellWidget(row, 4, actions_widget)

        # Now update rows that have existing progress (e.g., resumed order)
        for state_item in order_state:
            row_index = state_item.get('row')
            packed_count = state_item.get('packed', 0)
            if row_index is not None and packed_count > 0 and row_index < self.table.rowCount():
                required_count = state_item.get('required', 1)
                is_complete = packed_count >= required_count
                self.update_item_row(row_index, packed_count, is_complete)

        # [D] Update summary panel
        self._update_summary_panel(items, order_state)

        # [E] Enable skip button now that an order is active
        self.skip_order_button.setEnabled(True)

        order_num = items[0].get('Order_Number', items[0].get('order_number', ''))
        self.status_label.setText(f"Order {order_num}\nIn Progress...")
        self.set_focus_to_scanner()

    def update_item_row(self, row: int, packed_count: int, is_complete: bool):
        """
        Updates a single row in the items table to reflect a new packed count.

        Args:
            row: The table row index to update.
            packed_count: The new number of items packed for that SKU.
            is_complete: Whether this SKU is now fully packed.
        """
        quantity_item = self.table.item(row, 2)
        if quantity_item is None:
            logger.warning(f"Cannot update row {row}: quantity item is None")
            return

        parts = quantity_item.text().split(' / ')
        required_str = parts[1] if len(parts) > 1 else '1'
        quantity_item.setText(f"{packed_count} / {required_str}")

        try:
            req_int = int(required_str)
        except ValueError:
            req_int = 1

        if is_complete:
            status_item = QTableWidgetItem("Packed")
            status_item.setBackground(QColor("#1e4d2b"))  # muted dark green
            status_item.setForeground(QColor("#43a047"))
            self.table.setItem(row, 3, status_item)
            # Clear amber on completion — use palette text color to avoid black-on-dark rendering
            quantity_item.setBackground(QColor())
            quantity_item.setForeground(
                self.table.palette().color(QPalette.ColorRole.Text)
            )
            # Disable Confirm and Force buttons; leave -1 active for possible undo
            cell_widget = self.table.cellWidget(row, 4)
            if cell_widget:
                for btn in cell_widget.findChildren(QPushButton):
                    tip = btn.toolTip()
                    if tip in ("Confirm Manually", "Force confirm all remaining quantity (qty > 5 only)"):  # noqa: E501
                        btn.setEnabled(False)
        else:
            # Re-apply amber highlight for multi-qty items still in progress
            if req_int > 1:
                quantity_item.setBackground(QColor("#5a4000"))
                quantity_item.setForeground(QColor("#f39c12"))

        # [Fix 8] Keep summary panel live during scanning
        self._refresh_summary_from_table()

    def show_notification(self, text: str, color_name: str):
        """
        Displays a large, colored notification message.

        Args:
            text: The message to display.
            color_name: The color string for the text (e.g., "#c0392b" or "red").
        """
        self.notification_label.setText(text)
        self.notification_label.setStyleSheet(f"color: {color_name};")

    def clear_screen(self):
        """
        Resets the widget to its initial state, ready for the next order.
        """
        self.table.clearContents()
        self.table.setRowCount(0)
        self.status_label.setText("Scan the next order's barcode")
        self.notification_label.setText("")
        self.scanner_input.clear()
        self.scanner_input.setEnabled(True)
        # [A] Hide metadata banner
        self.metadata_banner.setVisible(False)
        # [D] Hide summary panel
        self.summary_frame.setVisible(False)
        self.summary_table.setRowCount(0)
        # [E] Disable skip button
        self.skip_order_button.setEnabled(False)
        # [J] Hide extras panel
        self.extras_panel.setVisible(False)
        self.extras_table.setRowCount(0)
        self.set_focus_to_scanner()

    def set_focus_to_scanner(self):
        """
        Sets the keyboard focus to the hidden scanner input field.
        This is crucial for ensuring the barcode scanner's output is captured.
        """
        self.scanner_input.setFocus()

    def update_raw_scan_display(self, text: str):
        """
        Updates the label that shows the raw text from the last scan.

        Args:
            text: The text captured from the scanner.
        """
        self.raw_scan_label.setText(text)

    def add_order_to_history(self, order_number: str, status: str = ""):
        """
        Adds an order number to the top of the scan history table.

        Args:
            order_number: The order number that was just scanned.
            status: Optional status suffix, e.g. "[SKIPPED]".
        """
        self.history_table.insertRow(0)
        display_text = f"{order_number} {status}".strip()
        item = QTableWidgetItem(display_text)
        if status == "[SKIPPED]":
            item.setForeground(QColor("#b06020"))
        self.history_table.setItem(0, 0, item)

    # [B] Feature B ────────────────────────────────────────────────────────────

    def update_session_progress(self, completed: int, total: int):
        """
        Updates the session progress bar at the top of the left panel.

        Args:
            completed: Number of completed orders.
            total: Total orders in the session.
        """
        self.session_progress_bar.setMaximum(max(total, 1))
        self.session_progress_bar.setValue(completed)
        self.session_progress_bar.setFormat(f"{completed} / {total} orders")

    # [J] Feature J ────────────────────────────────────────────────────────────

    def show_extras_panel(self, extras: Dict[str, int]):
        """
        Populates and shows the extras panel with Keep/Remove buttons.

        Args:
            extras: Dict of {normalized_sku: extra_count}.
        """
        self.extras_table.setRowCount(len(extras))
        for i, (norm_sku, count) in enumerate(extras.items()):
            self.extras_table.setItem(i, 0, QTableWidgetItem(norm_sku))
            self.extras_table.setItem(i, 1, QTableWidgetItem(str(count)))

            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(2, 1, 2, 1)
            btn_layout.setSpacing(3)

            keep_btn = QPushButton("Keep")
            keep_btn.setFixedWidth(50)
            keep_btn.setFocusPolicy(Qt.NoFocus)
            keep_btn.clicked.connect(partial(self._on_extra_confirmed, norm_sku))

            remove_btn = QPushButton("Remove")
            remove_btn.setFixedWidth(60)
            remove_btn.setFocusPolicy(Qt.NoFocus)
            remove_btn.clicked.connect(partial(self._on_extra_removed, norm_sku))

            btn_layout.addWidget(keep_btn)
            btn_layout.addWidget(remove_btn)
            self.extras_table.setCellWidget(i, 2, btn_widget)

        self.extras_panel.setVisible(len(extras) > 0)

    # ─── Private helpers ──────────────────────────────────────────────────────

    def _make_actions_widget(
        self,
        row: int,
        sku: str,
        required_qty: int,
        sku_map: Dict[str, str],
    ) -> QWidget:
        """
        Builds the multi-button widget for the Actions column.

        Buttons included:
          OK   — Confirm Manually (always present)
          -1   — Undo last scan (always present; requires confirmation dialog)
          F✓   — Force confirm all qty (present, but enabled only when required_qty > 5)
          Map  — Open SKU mapping dialog (only when this SKU is not a value in sku_map)
        """
        container = QWidget()
        container.setFocusPolicy(Qt.NoFocus)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(2, 1, 2, 1)
        layout.setSpacing(3)

        _style = QApplication.instance().style()
        _icon_sz = QSize(16, 16)

        def _icon_btn(sp: QStyle.StandardPixmap, tip: str, w: int) -> QPushButton:
            btn = QPushButton()
            btn.setIcon(_style.standardIcon(sp))
            btn.setIconSize(_icon_sz)
            btn.setToolTip(tip)
            btn.setFixedWidth(w)
            btn.setFocusPolicy(Qt.NoFocus)
            return btn

        # ✓ — Confirm Manually (equivalent to scanning the SKU barcode)
        confirm_btn = _icon_btn(
            QStyle.StandardPixmap.SP_DialogApplyButton,
            "Confirm Manually",
            28,
        )
        confirm_btn.clicked.connect(partial(self._on_manual_confirm, sku))
        layout.addWidget(confirm_btn)

        # ← — Undo last scan
        minus_btn = _icon_btn(
            QStyle.StandardPixmap.SP_ArrowLeft,
            "Undo last scan for this item",
            28,
        )
        minus_btn.clicked.connect(partial(self._on_cancel_item, row))
        layout.addWidget(minus_btn)

        # ⏩ — Force confirm all qty (enabled only when qty > 5)
        force_btn = _icon_btn(
            QStyle.StandardPixmap.SP_MediaSkipForward,
            "Force confirm all remaining quantity (qty > 5 only)",
            28,
        )
        force_btn.setEnabled(required_qty > 5)
        force_btn.clicked.connect(partial(self._on_force_confirm, row))
        layout.addWidget(force_btn)

        # Map SKU — shown only when SKU has no barcode mapping
        norm_sku = self._normalize_sku(sku)
        sku_is_mapped = norm_sku in set(sku_map.values())
        if not sku_is_mapped:
            map_btn = QPushButton("Map")
            map_btn.setToolTip("Add barcode mapping for this SKU")
            map_btn.setFixedWidth(40)
            map_btn.setFocusPolicy(Qt.NoFocus)
            map_btn.clicked.connect(partial(self._on_map_sku_requested, sku))
            layout.addWidget(map_btn)

        layout.addStretch()
        return container

    def _update_metadata_banner(self, metadata: Dict[str, Any] = None):
        """Populate and show/hide the order metadata banner as chip labels."""
        if not metadata:
            self.metadata_banner.setVisible(False)
            return

        def _show_chip(lbl: QLabel, text: str):
            if text:
                lbl.setText(text)
                lbl.setVisible(True)
            else:
                lbl.setText("")
                lbl.setVisible(False)

        order_type = metadata.get('order_type', '')
        _show_chip(self._meta_type_lbl, f"Type: {order_type}" if order_type else "")

        courier = metadata.get('shipping_provider', '')
        _show_chip(self._meta_courier_lbl, f"Courier: {courier}" if courier else "")

        country = metadata.get('destination_country', '')
        _show_chip(self._meta_country_lbl, f"Dest: {country}" if country else "")

        box = metadata.get('order_min_box', '')
        _show_chip(self._meta_box_lbl, f"Box: {box}" if box else "")

        all_tags = list(metadata.get('tags') or []) + list(metadata.get('internal_tags') or [])
        tags_str = ", ".join(str(t) for t in all_tags if t is not None) if all_tags else ""
        _show_chip(self._meta_tags_lbl, f"Tags: {tags_str}" if tags_str else "")

        notes = metadata.get('notes') or metadata.get('system_note') or ''
        _show_chip(self._meta_notes_lbl, str(notes) if notes else "")

        has_anything = any([order_type, courier, country, box, tags_str, notes])
        self.metadata_banner.setVisible(has_anything)

    def _update_summary_panel(
        self,
        items: List[Dict[str, Any]],
        order_state: List[Dict[str, Any]],
    ):
        """
        Deduplicates items by SKU and updates the summary table with summed quantities.
        This handles duplicate SKU rows that can appear in Shopify exports.
        """
        sku_totals: Dict[str, int] = defaultdict(int)
        sku_packed: Dict[str, int] = defaultdict(int)

        for item in items:
            sku = item.get('SKU', item.get('sku', ''))
            try:
                qty = int(float(item.get('Quantity', item.get('quantity', 1))))
            except (ValueError, TypeError):
                qty = 1
            sku_totals[sku] += qty

        for state in order_state:
            orig = state.get('original_sku', '')
            sku_packed[orig] += state.get('packed', 0)

        unique_skus = sorted(sku_totals.keys())
        self.summary_table.setRowCount(len(unique_skus))

        for i, sku in enumerate(unique_skus):
            total = sku_totals[sku]
            packed = sku_packed.get(sku, 0)
            self.summary_table.setItem(i, 0, QTableWidgetItem(sku))
            self.summary_table.setItem(i, 1, QTableWidgetItem(f"{packed} / {total}"))
            status_text = "Done" if packed >= total else "Pending"
            status_item = QTableWidgetItem(status_text)
            if packed >= total:
                status_item.setForeground(QColor("#43a047"))
            self.summary_table.setItem(i, 2, status_item)

        self.summary_frame.setVisible(len(unique_skus) > 0)

    def _refresh_summary_from_table(self):
        """
        Rebuild the summary table by reading current row data directly from the
        items table. Called from update_item_row() so the summary stays live.
        Each table row has: col 1 = SKU, col 2 = "packed / total" text.
        """
        if not self.summary_frame.isVisible():
            return

        sku_packed: Dict[str, int] = defaultdict(int)
        sku_totals: Dict[str, int] = defaultdict(int)

        for r in range(self.table.rowCount()):
            sku_item = self.table.item(r, 1)
            qty_item  = self.table.item(r, 2)
            if sku_item is None or qty_item is None:
                continue
            sku = sku_item.text()
            parts = qty_item.text().split(' / ')
            try:
                packed = int(parts[0])
                total  = int(parts[1]) if len(parts) > 1 else 1
            except (ValueError, IndexError):
                packed, total = 0, 1
            sku_packed[sku] += packed
            sku_totals[sku] += total

        unique_skus = sorted(sku_totals.keys())
        self.summary_table.setRowCount(len(unique_skus))
        for i, sku in enumerate(unique_skus):
            total  = sku_totals[sku]
            packed = sku_packed.get(sku, 0)
            self.summary_table.setItem(i, 0, QTableWidgetItem(sku))
            self.summary_table.setItem(i, 1, QTableWidgetItem(f"{packed} / {total}"))
            status_text = "Done" if packed >= total else "Pending"
            status_item = QTableWidgetItem(status_text)
            if packed >= total:
                status_item.setForeground(QColor("#43a047"))
            self.summary_table.setItem(i, 2, status_item)

    @staticmethod
    def _normalize_sku(sku: str) -> str:
        """
        Normalize a SKU string for comparison purposes (Map SKU detection only).
        Matches the normalization used in PackerLogic._normalize_sku().
        """
        return ''.join(c for c in str(sku).lower() if c.isalnum() or c in '-_')
