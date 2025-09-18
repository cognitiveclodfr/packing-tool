import sys
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout, QLabel, QPushButton, QScrollArea, QWidget
)
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtPrintSupport import QPrintDialog, QPrinter

class PrintDialog(QDialog):
    def __init__(self, orders_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Print Barcodes")
        self.setMinimumSize(800, 600)

        self.orders_data = orders_data

        main_layout = QVBoxLayout(self)

        # Create a scroll area in case there are many barcodes
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        main_layout.addWidget(scroll_area)

        # Widget that will contain the grid of barcodes
        self.scroll_content = QWidget()
        scroll_area.setWidget(self.scroll_content)

        grid_layout = QGridLayout(self.scroll_content)

        # Fill the grid with barcodes and order numbers
        row, col = 0, 0
        for order_number, data in self.orders_data.items():
            barcode_path = data['barcode_path']

            # Container for a single barcode item
            item_widget = QWidget()
            item_layout = QVBoxLayout(item_widget)

            # Barcode image
            pixmap = QPixmap(barcode_path)
            barcode_label = QLabel()
            barcode_label.setPixmap(pixmap.scaledToWidth(200)) # Scale for display
            item_layout.addWidget(barcode_label)

            # Order number text
            number_label = QLabel(order_number)
            item_layout.addWidget(number_label)

            grid_layout.addWidget(item_widget, row, col)

            col += 1
            if col >= 3: # 3 barcodes per row
                col = 0
                row += 1

        # Print button
        print_button = QPushButton("Print")
        print_button.clicked.connect(self.print_widget)
        main_layout.addWidget(print_button)

    def print_widget(self):
        printer = QPrinter(QPrinter.HighResolution)
        dialog = QPrintDialog(printer, self)

        if dialog.exec() == QDialog.Accepted:
            painter = QPainter()
            painter.begin(printer)

            # Render the scroll area content to the printer
            self.scroll_content.render(painter)

            painter.end()
