import sys
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout, QLabel, QPushButton, QScrollArea, QWidget,
    QMessageBox
)
from PySide6.QtGui import QPixmap, QPainter, QImage, QPageLayout, QPageSize
from PySide6.QtCore import QRectF, Qt, QSizeF, QMarginsF
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from typing import Dict, Any
from logger import logger

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

        This method prints each barcode label on a separate page at 1:1 scale
        for the Citizen CL-E300 label printer (68x38mm @ 203 DPI).

        The printer is configured to match the label specifications:
        - Page size: 68mm x 38mm
        - Resolution: 203 DPI
        - Full page mode (no margins)
        - One label per page

        Images are printed at their native resolution without any scaling,
        ensuring correct barcode dimensions for scanning.
        """
        try:
            # ========================================
            # 1. Create printer with correct settings
            # ========================================
            printer = QPrinter(QPrinter.HighResolution)

            # Set label size: 68mm x 38mm (matches Citizen CL-E300 label size)
            page_size = QPageSize(
                QSizeF(68, 38),  # Width x Height in mm
                QPageSize.Unit.Millimeter,
                "Label 68x38mm"
            )
            printer.setPageSize(page_size)

            # Set resolution to match printer
            printer.setResolution(203)  # 203 DPI - Citizen CL-E300

            # CRITICAL: Use full page (no margins!)
            printer.setFullPage(True)

            # Set to zero margins explicitly
            printer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)

            # Portrait orientation
            printer.setPageOrientation(QPageLayout.Orientation.Portrait)

            # Set document name
            printer.setDocName("Barcode Labels")

            # ========================================
            # 2. Show print dialog (user can select printer/preset)
            # ========================================
            dialog = QPrintDialog(printer, self)
            dialog.setWindowTitle("Print Barcode Labels")

            if dialog.exec() != QDialog.DialogCode.Accepted:
                logger.info("Print cancelled by user")
                return

            # ========================================
            # 3. Print each label on separate page at 1:1 scale
            # ========================================
            painter = QPainter()

            if not painter.begin(printer):
                raise RuntimeError("Failed to start printing")

            try:
                # Get printer page size in pixels
                page_rect = printer.pageRect(QPrinter.Unit.DevicePixel)
                logger.info(f"Printer page rect: {page_rect.width()}x{page_rect.height()}px @ {printer.resolution()} DPI")

                label_count = len(self.orders_data)
                current_label = 0

                for order_number, data in self.orders_data.items():
                    current_label += 1
                    barcode_path = data['barcode_path']

                    # Load image
                    image = QImage(barcode_path)

                    if image.isNull():
                        logger.error(f"Failed to load image: {barcode_path}")
                        continue

                    logger.info(f"Printing label {current_label}/{label_count}: {order_number} ({image.width()}x{image.height()}px)")

                    # ========================================
                    # 4. Print at 1:1 scale (NO SCALING!)
                    # ========================================
                    # Image is 543x303px @ 203 DPI = 68x38mm
                    # Printer is set to 203 DPI
                    # So we print at EXACT pixel size (1:1)

                    target_width = image.width()   # 543px
                    target_height = image.height() # 303px

                    # Center image on page (in case page is slightly larger)
                    x_offset = (page_rect.width() - target_width) / 2
                    y_offset = (page_rect.height() - target_height) / 2

                    # Ensure no negative offsets
                    x_offset = max(0, x_offset)
                    y_offset = max(0, y_offset)

                    # Draw image at 1:1 scale
                    painter.drawImage(
                        int(x_offset),
                        int(y_offset),
                        image
                    )

                    logger.info(f"Drew image at position ({x_offset:.1f}, {y_offset:.1f}), size: {target_width}x{target_height}px (1:1 scale)")

                    # Start new page for next label (except for last label)
                    if current_label < label_count:
                        printer.newPage()

            finally:
                painter.end()

            logger.info(f"Successfully printed {label_count} barcode label(s)")

            # Show success message
            QMessageBox.information(
                self,
                "Print Success",
                f"Successfully printed {label_count} barcode label(s)"
            )

        except Exception as e:
            logger.error(f"Failed to print barcodes: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Print Error",
                f"Failed to print barcodes:\n{str(e)}"
            )
