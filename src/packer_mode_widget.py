from functools import partial
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QLabel, QLineEdit, QHeaderView, QPushButton, QAbstractItemView, QFrame
)
from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import Qt, Signal

class PackerModeWidget(QWidget):
    barcode_scanned = Signal(str)
    exit_packing_mode = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        main_layout = QHBoxLayout(self)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        # Create a frame to wrap the table, this will receive the flashing border
        self.table_frame = QFrame()
        self.table_frame.setObjectName("TableFrame")
        self.table_frame.setFrameShape(QFrame.Shape.NoFrame) # No default border
        self.table_frame.setFrameShadow(QFrame.Shadow.Plain)
        frame_layout = QVBoxLayout(self.table_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Product Name", "SKU", "Packed / Required", "Status", "Action"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)

        frame_layout.addWidget(self.table)
        left_layout.addWidget(self.table_frame)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setAlignment(Qt.AlignCenter)

        self.status_label = QLabel("Scan an order barcode")
        font = QFont()
        font.setPointSize(20)
        self.status_label.setFont(font)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)

        self.notification_label = QLabel("")
        notif_font = QFont()
        notif_font.setPointSize(32)
        notif_font.setBold(True)
        self.notification_label.setFont(notif_font)
        self.notification_label.setAlignment(Qt.AlignCenter)
        self.notification_label.setWordWrap(True)

        right_layout.addWidget(self.status_label)
        right_layout.addWidget(self.notification_label)
        right_layout.addStretch()

        # Raw Scan Display
        raw_scan_title = QLabel("Last Scan:")
        raw_scan_title.setAlignment(Qt.AlignCenter)
        self.raw_scan_label = QLabel("-")
        self.raw_scan_label.setAlignment(Qt.AlignCenter)
        self.raw_scan_label.setObjectName("RawScanLabel")
        self.raw_scan_label.setWordWrap(True)

        # History Table
        history_title = QLabel("Scanned Orders History:")
        history_title.setAlignment(Qt.AlignCenter)
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(1)
        self.history_table.setHorizontalHeaderLabels(["Order #"])
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.history_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.history_table.setFocusPolicy(Qt.NoFocus)

        # Group the new info widgets in a container
        info_container = QWidget()
        info_layout = QVBoxLayout(info_container)
        info_layout.setContentsMargins(0,0,0,0)
        info_layout.addWidget(raw_scan_title)
        info_layout.addWidget(self.raw_scan_label)
        info_layout.addWidget(history_title)
        info_layout.addWidget(self.history_table)

        right_layout.addWidget(info_container)
        right_layout.addStretch()

        self.scanner_input = QLineEdit()
        self.scanner_input.setFixedSize(1, 1)
        self.scanner_input.returnPressed.connect(self._on_scan)
        right_layout.addWidget(self.scanner_input)

        right_layout.addStretch()
        self.exit_button = QPushButton("<< Back to Menu")
        font = self.exit_button.font()
        font.setPointSize(14)
        self.exit_button.setFont(font)
        self.exit_button.clicked.connect(self.exit_packing_mode.emit)
        right_layout.addWidget(self.exit_button)

        main_layout.addWidget(left_widget, stretch=2)
        main_layout.addWidget(right_widget, stretch=1)

    def _on_scan(self):
        text = self.scanner_input.text()
        self.scanner_input.clear()
        self.barcode_scanned.emit(text)

    def _on_manual_confirm(self, sku):
        """Emits the barcode_scanned signal and resets focus."""
        if sku:
            self.barcode_scanned.emit(sku)
        self.set_focus_to_scanner()

    def display_order(self, items, order_state):
        self.table.setRowCount(len(items))

        # A mapping from original SKU to its table row
        sku_to_row_map = {}

        for row, item in enumerate(items):
            sku = item.get('SKU', '')
            sku_to_row_map[sku] = row
            quantity = str(item.get('Quantity', ''))

            self.table.setItem(row, 0, QTableWidgetItem(item.get('Product_Name', '')))
            self.table.setItem(row, 1, QTableWidgetItem(sku))
            self.table.setItem(row, 2, QTableWidgetItem(f"0 / {quantity}"))

            status_item = QTableWidgetItem("Pending")
            status_item.setBackground(QColor("yellow"))
            self.table.setItem(row, 3, status_item)

            confirm_button = QPushButton("Confirm Manually")
            confirm_button.clicked.connect(partial(self._on_manual_confirm, sku))
            self.table.setCellWidget(row, 4, confirm_button)

        # Now, update with the restored state
        for state in order_state.values():
            original_sku = state.get('original_sku')
            if original_sku in sku_to_row_map:
                row_index = sku_to_row_map[original_sku]
                packed_count = state.get('packed', 0)
                is_complete = packed_count >= state.get('required', 1)
                if packed_count > 0:
                    self.update_item_row(row_index, packed_count, is_complete)

        self.status_label.setText(f"Order {items[0]['Order_Number']}\nIn Progress...")
        self.set_focus_to_scanner()

    def update_item_row(self, row, packed_count, is_complete):
        required_quantity = self.table.item(row, 2).text().split(' / ')[1]
        self.table.item(row, 2).setText(f"{packed_count} / {required_quantity}")

        if is_complete:
            status_item = QTableWidgetItem("Packed")
            status_item.setBackground(QColor("lightgreen"))
            self.table.setItem(row, 3, status_item)
            # Disable the button once the item is fully packed
            self.table.cellWidget(row, 4).setEnabled(False)

    def show_notification(self, text, color_name):
        self.notification_label.setText(text)
        self.notification_label.setStyleSheet(f"color: {color_name};")

    def clear_screen(self):
        self.table.clearContents()
        self.table.setRowCount(0)
        self.status_label.setText("Scan the next order's barcode")
        self.notification_label.setText("")
        self.scanner_input.clear()
        self.scanner_input.setEnabled(True) # Re-enable input
        self.set_focus_to_scanner()

    def set_focus_to_scanner(self):
        self.scanner_input.setFocus()

    def update_raw_scan_display(self, text: str):
        self.raw_scan_label.setText(text)

    def add_order_to_history(self, order_number: str):
        self.history_table.insertRow(0)
        self.history_table.setItem(0, 0, QTableWidgetItem(str(order_number)))
