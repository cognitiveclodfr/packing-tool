import sys
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout, QLabel, QPushButton, QScrollArea, QWidget
)
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtCore import QRectF, Qt
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from typing import Dict, Any

class PrintDialog(QDialog):
    """
    A dialog for previewing and printing generated barcode labels.

    This dialog displays a grid of all the barcode labels generated for the
    current session. It provides a "Print" button that opens the system's
    native print dialog to send the labels to a physical printer.

    Attributes:
        orders_data (Dict[str, Any]): A dictionary containing the data for all
                                      orders, including paths to their barcode
                                      images.
        scroll_content (QWidget): The widget inside the scroll area that holds
                                  the grid of barcode previews.
    """
    def __init__(self, orders_data: Dict[str, Any], parent: QWidget = None):
        """
        Initializes the PrintDialog.

        Args:
            orders_data (Dict[str, Any]): The dictionary of order data from
                                          PackerLogic.
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.setWindowTitle("Print Barcodes")
        self.setMinimumSize(800, 600)

        self.orders_data = orders_data

        main_layout = QVBoxLayout(self)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        main_layout.addWidget(scroll_area)

        self.scroll_content = QWidget()
        scroll_area.setWidget(self.scroll_content)

        grid_layout = QGridLayout(self.scroll_content)

        row, col = 0, 0
        for order_number, data in self.orders_data.items():
            barcode_path = data['barcode_path']
            item_widget = QWidget()
            item_layout = QVBoxLayout(item_widget)

            pixmap = QPixmap(barcode_path)
            barcode_label = QLabel()
            barcode_label.setPixmap(pixmap.scaledToWidth(200))  # Scale for display
            item_layout.addWidget(barcode_label)

            number_label = QLabel(order_number)
            item_layout.addWidget(number_label)

            grid_layout.addWidget(item_widget, row, col)

            col += 1
            if col >= 3:  # 3 barcodes per row
                col = 0
                row += 1

        print_button = QPushButton("Print")
        print_button.clicked.connect(self.print_widget)
        main_layout.addWidget(print_button)

    def print_widget(self):
        """
        Opens a print dialog and prints the barcode labels.

        This method is triggered by the "Print" button. It uses QPrinter and
        QPainter to lay out the barcode images onto the pages of the selected
        printer. The layout logic arranges the labels in a grid, handling page
        breaks automatically.
        """
        printer = QPrinter(QPrinter.HighResolution)
        dialog = QPrintDialog(printer, self)

        if dialog.exec() == QDialog.Accepted:
            printer.setDocName("Barcodes")
            painter = QPainter()
            painter.begin(printer)

            page_rect = printer.pageRect(QPrinter.Point)
            margin = 50
            x_pos, y_pos = margin, margin

            # Define label size in printer points (1 point = 1/72 inch)
            # This is an approximation for layout; the generated barcode image has the correct DPI.
            label_width, label_height = 300, 150
            x_spacing, y_spacing = 20, 20

            for order_number, data in self.orders_data.items():
                if x_pos + label_width > page_rect.width() - margin:
                    # Move to next row
                    x_pos = margin
                    y_pos += label_height + y_spacing

                if y_pos + label_height > page_rect.height() - margin:
                    # New page
                    printer.newPage()
                    x_pos, y_pos = margin, margin

                barcode_path = data['barcode_path']
                pixmap = QPixmap(barcode_path)

                target_rect = QRectF(x_pos, y_pos, label_width, label_height)
                painter.drawPixmap(target_rect, pixmap, pixmap.rect())

                x_pos += label_width + x_spacing

            painter.end()
