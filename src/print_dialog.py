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

    def _print_image_win32(self, image_path: str, printer_name: str = None) -> bool:
        """
        Print image using Windows GDI (Graphics Device Interface) API directly.

        This provides true silent printing without any dialogs, and works
        with thermal label printers by sending raw image data to printer.

        Args:
            image_path: Path to PNG image file
            printer_name: Printer name (None = default printer)

        Returns:
            True if print succeeded, False otherwise
        """
        try:
            # Try to use win32print if available
            import win32print
            import win32ui
            from PIL import Image, ImageWin
            import win32con

            # Open printer
            if printer_name is None:
                printer_name = win32print.GetDefaultPrinter()

            hprinter = win32print.OpenPrinter(printer_name)

            try:
                # Create device context
                hdc = win32ui.CreateDC()
                hdc.CreatePrinterDC(printer_name)

                # Start document
                hdc.StartDoc(image_path)
                hdc.StartPage()

                # Load image
                img = Image.open(image_path)

                # Get printer DPI
                printer_dpi = hdc.GetDeviceCaps(win32con.LOGPIXELSX)
                logger.info(f"Printer DPI: {printer_dpi}")

                # Convert PIL image to Windows DIB (Device Independent Bitmap)
                dib = ImageWin.Dib(img)

                # Calculate dimensions in device units
                # Image is 543x303px @ 203 DPI
                # For Citizen CL-E300 which is also 203 DPI, this should be 1:1
                width = img.width * printer_dpi // 203  # Scale from 203 DPI to printer DPI
                height = img.height * printer_dpi // 203

                logger.info(f"Printing at {width}x{height} device units")

                # Print image at top-left (0, 0)
                dib.draw(hdc.GetHandleOutput(), (0, 0, width, height))

                # End document
                hdc.EndPage()
                hdc.EndDoc()
                hdc.DeleteDC()

                logger.info(f"Successfully printed via win32print: {image_path}")
                return True

            finally:
                win32print.ClosePrinter(hprinter)

        except ImportError:
            logger.warning("win32print not available, falling back to PowerShell")
            return False
        except Exception as e:
            logger.error(f"win32print failed: {e}", exc_info=True)
            return False

    def print_via_windows(self):
        """
        Print selected barcode labels using best available method.

        Tries multiple methods in order:
        1. win32print (true silent printing) - BEST for batch printing
        2. PowerShell (may show dialogs) - FALLBACK

        Benefits for thermal label printers (like Citizen CL-E300):
        - Uses Windows printer driver directly
        - Respects DPI metadata in PNG files
        - Each label printed separately (proper alignment)
        - No page breaking issues
        - Silent printing when win32print available

        For thermal printers, make sure:
        - Citizen CL-E300 is set as DEFAULT printer in Windows
        - Label size (68x38mm) is configured in printer driver
        - Labels are loaded and printer is calibrated
        """
        import subprocess
        import time

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
            f"Labels will be sent to your DEFAULT printer.\n"
            f"Make sure Citizen CL-E300 is set as default printer!\n\n"
            f"Selected orders:\n" + "\n".join(f"  • {order}" for order in selected_orders[:10]) +
            (f"\n  ... and {len(selected_orders) - 10} more" if len(selected_orders) > 10 else ""),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            logger.info("Print cancelled by user")
            return

        # Try to detect if win32print is available
        try:
            import win32print
            has_win32print = True
            logger.info("win32print available - using silent printing")
        except ImportError:
            has_win32print = False
            logger.info("win32print not available - using PowerShell fallback")

        try:
            printed_count = 0
            failed_labels = []

            for order_number in selected_orders:
                try:
                    barcode_path = self.orders_data[order_number]['barcode_path']

                    # Check if file exists
                    if not os.path.exists(barcode_path):
                        raise FileNotFoundError(f"Barcode file not found: {barcode_path}")

                    # Convert to absolute path
                    abs_path = os.path.abspath(barcode_path)

                    logger.info(f"Sending to Windows print queue: {order_number} ({abs_path})")

                    success = False

                    # Try win32print first (silent, no dialogs)
                    if has_win32print:
                        success = self._print_image_win32(abs_path)

                    # Fallback to PowerShell if win32print not available or failed
                    if not success:
                        logger.info(f"Using PowerShell fallback for {order_number}")

                        # Use PowerShell to print
                        # Note: This may still show print dialogs
                        powershell_cmd = [
                            'powershell.exe',
                            '-NoProfile',
                            '-NonInteractive',
                            '-WindowStyle', 'Hidden',
                            '-Command',
                            f'Start-Process -FilePath "{abs_path}" -Verb Print -WindowStyle Hidden'
                        ]

                        subprocess.Popen(powershell_cmd, shell=False,
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)

                    # Small delay between prints
                    time.sleep(0.3)

                    printed_count += 1

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

                msg = f"✅ Successfully sent {printed_count} label(s) to print queue!\n\n"

                if has_win32print:
                    msg += "Labels are being printed silently on your default printer.\n"
                else:
                    msg += ("Labels are being sent to printer.\n"
                           "Note: You may see print dialogs.\n\n"
                           "To enable silent printing, install: pip install pywin32")

                msg += "\nCheck the printer for output."

                QMessageBox.information(self, "Print Success", msg)

            # DON'T close dialog automatically to prevent crash
            logger.info("Print dialog staying open - user can close manually")

        except Exception as e:
            logger.error(f"Print operation failed: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Print Error",
                f"Failed to print labels:\n\n{str(e)}\n\n"
                f"Please check:\n"
                f"  • Citizen CL-E300 is set as DEFAULT printer\n"
                f"  • Printer is turned on and connected\n"
                f"  • Labels are loaded\n"
                f"  • Printer driver is installed\n"
                f"  • You have permission to print"
            )
