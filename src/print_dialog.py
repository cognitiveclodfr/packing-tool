import sys
import os
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QMessageBox, QCheckBox
)
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt
from typing import Dict, Any
from logger import get_logger

logger = get_logger(__name__)

class PrintDialog(QDialog):
    """
    A dialog for previewing and printing generated barcode labels.

    This dialog displays a grid of all the barcode labels generated for the
    current session. Users can select specific labels to print using checkboxes.

    For thermal label printers (like Citizen CL-E300), this dialog uses Windows
    shell printing which works better than QPrinter for label alignment.

    Attributes:
        orders_data (Dict[str, Any]): A dictionary containing the data for all
                                      orders, including paths to their barcode
                                      images.
        checkboxes (Dict[str, QCheckBox]): Checkboxes for selecting labels to print
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
        self.setMinimumSize(900, 700)

        self.orders_data = orders_data
        self.checkboxes = {}  # Store checkboxes for each order

        main_layout = QVBoxLayout(self)

        # === HEADER: Selection Controls ===
        header_layout = QHBoxLayout()

        header_label = QLabel("Select labels to print:")
        header_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        header_layout.addWidget(header_label)

        header_layout.addStretch()

        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self.select_all)
        header_layout.addWidget(select_all_btn)

        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.clicked.connect(self.deselect_all)
        header_layout.addWidget(deselect_all_btn)

        main_layout.addLayout(header_layout)

        # === SCROLL AREA: Barcode Previews ===
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        main_layout.addWidget(scroll_area)

        self.scroll_content = QWidget()
        scroll_area.setWidget(self.scroll_content)

        grid_layout = QGridLayout(self.scroll_content)
        grid_layout.setSpacing(15)

        # Create grid of barcode previews with checkboxes
        row, col = 0, 0
        for order_number, data in self.orders_data.items():
            barcode_path = data['barcode_path']

            # Item container
            item_widget = QWidget()
            item_widget.setStyleSheet("""
                QWidget {
                    border: 2px solid #ddd;
                    border-radius: 5px;
                    padding: 10px;
                    background-color: white;
                }
            """)
            item_layout = QVBoxLayout(item_widget)

            # Checkbox for selection
            checkbox = QCheckBox(f"Print {order_number}")
            checkbox.setChecked(True)  # Default: all selected
            checkbox.setStyleSheet("font-weight: bold;")
            self.checkboxes[order_number] = checkbox
            item_layout.addWidget(checkbox, alignment=Qt.AlignmentFlag.AlignCenter)

            # Barcode preview image
            pixmap = QPixmap(barcode_path)
            barcode_label = QLabel()
            barcode_label.setPixmap(pixmap.scaledToWidth(250))  # Larger preview
            barcode_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            item_layout.addWidget(barcode_label)

            # Order number label
            number_label = QLabel(order_number)
            number_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            number_label.setStyleSheet("font-size: 10pt; color: #555;")
            item_layout.addWidget(number_label)

            # Path label (for reference)
            path_label = QLabel(Path(barcode_path).name)
            path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            path_label.setStyleSheet("font-size: 8pt; color: #999;")
            item_layout.addWidget(path_label)

            grid_layout.addWidget(item_widget, row, col)

            col += 1
            if col >= 3:  # 3 barcodes per row
                col = 0
                row += 1

        # === FOOTER: Action Buttons ===
        footer_layout = QHBoxLayout()
        footer_layout.addStretch()

        # Print via Windows (recommended for thermal printers)
        print_windows_btn = QPushButton("🖨️ Print Selected (Windows)")
        print_windows_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                font-size: 11pt;
                padding: 10px 20px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        print_windows_btn.clicked.connect(self.print_via_windows)
        footer_layout.addWidget(print_windows_btn)

        # Cancel button
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("padding: 10px 20px;")
        cancel_btn.clicked.connect(self.reject)
        footer_layout.addWidget(cancel_btn)

        main_layout.addLayout(footer_layout)

        # Info label
        info_label = QLabel(
            "💡 Tip: 'Print Selected (Windows)' works best with thermal label printers.\n"
            "Each label will be printed separately to ensure correct alignment."
        )
        info_label.setStyleSheet("""
            QLabel {
                background-color: #E3F2FD;
                padding: 10px;
                border-radius: 5px;
                color: #1976D2;
                font-size: 9pt;
            }
        """)
        info_label.setWordWrap(True)
        main_layout.addWidget(info_label)

    def select_all(self):
        """Select all barcode checkboxes."""
        for checkbox in self.checkboxes.values():
            checkbox.setChecked(True)
        logger.info("Selected all barcodes for printing")

    def deselect_all(self):
        """Deselect all barcode checkboxes."""
        for checkbox in self.checkboxes.values():
            checkbox.setChecked(False)
        logger.info("Deselected all barcodes")

    def print_via_windows(self):
        """
        Print selected barcode labels using Windows shell.

        This method uses os.startfile() with "print" verb to send each label
        to the default printer. This approach works better with thermal label
        printers (like Citizen CL-E300) because:

        1. Uses Windows printer driver directly (no Qt abstraction)
        2. Respects DPI metadata in PNG files
        3. Each label printed separately (proper alignment)
        4. No page breaking issues
        5. User can select printer in Windows dialog

        For thermal printers, make sure:
        - Label size (68x38mm) is configured in printer driver
        - Printer is set as default or selected in dialog
        - Labels are loaded and printer is calibrated
        """
        # Get selected barcodes
        selected_orders = [
            order_number
            for order_number, checkbox in self.checkboxes.items()
            if checkbox.isChecked()
        ]

        if not selected_orders:
            QMessageBox.warning(
                self,
                "No Selection",
                "Please select at least one barcode to print."
            )
            return

        # Confirm print action
        reply = QMessageBox.question(
            self,
            "Confirm Print",
            f"Print {len(selected_orders)} selected label(s)?\n\n"
            f"Each label will be printed separately.\n"
            f"Make sure your printer is ready and has labels loaded.\n\n"
            f"Selected orders:\n" + "\n".join(f"  • {order}" for order in selected_orders[:10]) +
            (f"\n  ... and {len(selected_orders) - 10} more" if len(selected_orders) > 10 else ""),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            logger.info("Print cancelled by user")
            return

        try:
            # Print each selected label separately via Windows
            printed_count = 0
            failed_labels = []

            for order_number in selected_orders:
                try:
                    barcode_path = self.orders_data[order_number]['barcode_path']

                    # Check if file exists
                    if not os.path.exists(barcode_path):
                        raise FileNotFoundError(f"Barcode file not found: {barcode_path}")

                    logger.info(f"Sending to Windows print queue: {order_number} ({barcode_path})")

                    # Use Windows shell to print
                    # This opens the file with default application and sends to printer
                    os.startfile(barcode_path, "print")

                    printed_count += 1

                    # Note: os.startfile is non-blocking, so we can't detect print errors immediately
                    # The Windows print spooler will handle the actual printing

                except Exception as e:
                    logger.error(f"Failed to print {order_number}: {e}", exc_info=True)
                    failed_labels.append(f"{order_number}: {str(e)}")

            # Show result
            if failed_labels:
                QMessageBox.warning(
                    self,
                    "Partial Success",
                    f"Sent {printed_count} label(s) to print queue.\n\n"
                    f"Failed to print {len(failed_labels)} label(s):\n" +
                    "\n".join(f"  • {error}" for error in failed_labels[:5]) +
                    (f"\n  ... and {len(failed_labels) - 5} more" if len(failed_labels) > 5 else "")
                )
            else:
                logger.info(f"Successfully queued {printed_count} label(s) for printing")

                QMessageBox.information(
                    self,
                    "Print Queued",
                    f"✅ Successfully sent {printed_count} label(s) to Windows print queue!\n\n"
                    f"The Windows print dialog(s) will open shortly.\n"
                    f"Please select your printer (Citizen CL-E300) and confirm.\n\n"
                    f"Note: You may see multiple print dialogs (one per label).\n"
                    f"This ensures correct label alignment on thermal printers."
                )

            # Close dialog after successful print
            if printed_count > 0:
                self.accept()

        except Exception as e:
            logger.error(f"Print operation failed: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Print Error",
                f"Failed to print labels:\n\n{str(e)}\n\n"
                f"Please check:\n"
                f"  • Printer is turned on and connected\n"
                f"  • Labels are loaded\n"
                f"  • Printer driver is installed\n"
                f"  • You have permission to print"
            )
