from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QLabel, QLineEdit, QHeaderView
)
from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import Qt, Signal

class PackerModeWidget(QWidget):
    barcode_scanned = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        main_layout = QHBoxLayout(self)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Назва товару", "SKU", "Потрібно", "Зібрано", "Статус"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        left_layout.addWidget(self.table)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setAlignment(Qt.AlignCenter)

        self.status_label = QLabel("Відскануйте баркод замовлення")
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
        right_layout.addStretch()
        right_layout.addWidget(self.notification_label)
        right_layout.addStretch()

        self.scanner_input = QLineEdit()
        self.scanner_input.setFixedSize(1, 1)
        self.scanner_input.returnPressed.connect(self._on_scan)
        right_layout.addWidget(self.scanner_input)

        main_layout.addWidget(left_widget, stretch=2)
        main_layout.addWidget(right_widget, stretch=1)

    def _on_scan(self):
        text = self.scanner_input.text()
        self.scanner_input.clear()
        self.barcode_scanned.emit(text)

    def display_order(self, items):
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            self.table.setItem(row, 0, QTableWidgetItem(item.get('Product_Name', '')))
            self.table.setItem(row, 1, QTableWidgetItem(item.get('SKU', '')))
            self.table.setItem(row, 2, QTableWidgetItem(str(item.get('Quantity', ''))))
            self.table.setItem(row, 3, QTableWidgetItem("0"))

            status_item = QTableWidgetItem("Очікує")
            status_item.setBackground(QColor("yellow"))
            self.table.setItem(row, 4, status_item)

        self.status_label.setText(f"Замовлення #{items[0]['Order_Number']}\nВ роботі...")
        self.set_focus_to_scanner()

    def update_item_row(self, row, packed_count, is_complete):
        self.table.item(row, 3).setText(str(packed_count))
        if is_complete:
            status_item = QTableWidgetItem("Зібрано")
            status_item.setBackground(QColor("lightgreen"))
            self.table.setItem(row, 4, status_item)

    def show_notification(self, text, color_name):
        self.notification_label.setText(text)
        self.notification_label.setStyleSheet(f"color: {color_name};")

    def clear_screen(self):
        self.table.clearContents()
        self.table.setRowCount(0)
        self.status_label.setText("Відскануйте баркод наступного замовлення")
        self.notification_label.setText("")
        self.scanner_input.clear()
        self.set_focus_to_scanner()

    def set_focus_to_scanner(self):
        self.scanner_input.setFocus()
