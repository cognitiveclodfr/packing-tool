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

        # Open in Windows Photo Viewer (recommended approach)
        photo_viewer_btn = QPushButton("🖼️ Open in Photo Viewer")
        photo_viewer_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078D4;
                color: white;
                font-weight: bold;
                font-size: 11pt;
                padding: 10px 20px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #005A9E;
            }
        """)
        photo_viewer_btn.clicked.connect(self.open_in_photo_viewer)
        footer_layout.addWidget(photo_viewer_btn)

        # Open in Explorer (alternative)
        explorer_btn = QPushButton("📁 Open in Explorer")
        explorer_btn.setStyleSheet("padding: 10px 20px;")
        explorer_btn.clicked.connect(self.open_in_explorer)
        footer_layout.addWidget(explorer_btn)

        # Cancel button
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("padding: 10px 20px;")
        cancel_btn.clicked.connect(self.reject)
        footer_layout.addWidget(cancel_btn)

        main_layout.addLayout(footer_layout)

        # Info label
        info_label = QLabel(
            "💡 Workflow:\n"
            "1. Select orders using checkboxes\n"
            "2. Click 'Open in Photo Viewer' to view barcodes\n"
            "3. In Photo Viewer, press Ctrl+P to print\n"
            "4. Select your printer (Citizen CL-E300) and configure settings\n"
            "5. Click Print\n\n"
            "This gives you full control over printer selection and settings!"
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

    def open_in_photo_viewer(self):
        """
        Open selected barcode images in Windows Photo Viewer.

        CRITICAL FIX: Replaced silent printing with Photo Viewer approach for better
        reliability and user control. This gives warehouse workers full control over:
        - Printer selection (not just default)
        - Print settings (copies, orientation, etc.)
        - Print preview before printing
        - Familiar Windows interface

        Workflow:
        1. User selects orders with checkboxes
        2. Opens selected barcodes in Windows Photo Viewer
        3. In Photo Viewer, presses Ctrl+P to print
        4. Windows print dialog appears with full control
        5. User selects Citizen CL-E300 printer and prints

        Advantages:
        - Reliable (no driver issues)
        - User can preview before printing
        - Can adjust print settings per job
        - Works with any Windows-compatible printer
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
                "Please select at least one barcode to open."
            )
            return

        logger.info(f"Opening {len(selected_orders)} barcode(s) in Windows Photo Viewer")

        try:
            # Collect file paths
            file_paths = []
            for order_number in selected_orders:
                barcode_path = self.orders_data[order_number]['barcode_path']

                # Validate file exists
                if not os.path.exists(barcode_path):
                    logger.error(f"Barcode file not found: {barcode_path}")
                    QMessageBox.warning(
                        self,
                        "File Not Found",
                        f"Barcode file not found for {order_number}:\n{barcode_path}"
                    )
                    continue

                file_paths.append(os.path.abspath(barcode_path))

            if not file_paths:
                QMessageBox.warning(
                    self,
                    "No Files",
                    "No valid barcode files found for selected orders."
                )
                return

            # Open each file with default image viewer (Windows Photos or Photo Viewer)
            # Using os.startfile opens with default application for .png files
            for file_path in file_paths:
                try:
                    os.startfile(file_path)
                    logger.info(f"Opened in Photo Viewer: {file_path}")
                except Exception as e:
                    logger.error(f"Failed to open {file_path}: {e}", exc_info=True)

            # Show success message with instructions
            QMessageBox.information(
                self,
                "Barcodes Opened",
                f"✅ Opened {len(file_paths)} barcode image(s) in Windows Photo Viewer.\n\n"
                f"To print:\n"
                f"1. In the photo viewer, press Ctrl+P (or go to File → Print)\n"
                f"2. Select your printer (Citizen CL-E300)\n"
                f"3. Adjust settings:\n"
                f"   • Paper size: 68mm x 38mm (2.68\" x 1.5\")\n"
                f"   • Print quality: Best\n"
                f"   • Orientation: Portrait\n"
                f"4. Click Print\n\n"
                f"💡 Tip: You can print multiple images at once by keeping all windows open\n"
                f"and printing each one, or use the Explorer option to print multiple files."
            )

            # Close dialog after successful operation
            self.accept()

        except Exception as e:
            logger.error(f"Failed to open barcodes in Photo Viewer: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to open barcode images:\n\n{str(e)}\n\n"
                f"Make sure you have a default image viewer installed (Windows Photos or Photo Viewer)."
            )

    def open_in_explorer(self):
        """
        Open barcode folder in Windows Explorer with selected files highlighted.

        This is an alternative approach that allows users to:
        - See all barcode files in one place
        - Select multiple files manually
        - Right-click → Print to print multiple files at once
        - More control over batch printing

        Workflow:
        1. Opens Explorer with barcode folder
        2. User can select files (Ctrl+Click for multiple)
        3. Right-click → Print
        4. Windows print dialog appears
        5. Can print multiple labels in one job
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
                "Please select at least one barcode."
            )
            return

        logger.info(f"Opening Explorer for {len(selected_orders)} selected barcode(s)")

        try:
            # Get first selected file to determine folder
            first_order = selected_orders[0]
            first_path = self.orders_data[first_order]['barcode_path']

            if not os.path.exists(first_path):
                QMessageBox.warning(
                    self,
                    "File Not Found",
                    f"Barcode file not found:\n{first_path}"
                )
                return

            # Get folder path
            folder_path = str(Path(first_path).parent)

            # Open Explorer with first file selected
            import subprocess
            subprocess.Popen(['explorer', '/select,', os.path.abspath(first_path)])

            logger.info(f"Opened Explorer at: {folder_path}")

            # Show instructions
            QMessageBox.information(
                self,
                "Explorer Opened",
                f"✅ Opened barcode folder in Windows Explorer.\n\n"
                f"The first selected file is highlighted.\n\n"
                f"To print multiple labels:\n"
                f"1. Hold Ctrl and click on additional barcode files to select them\n"
                f"2. Right-click on selected files\n"
                f"3. Click 'Print' from the context menu\n"
                f"4. Select your printer (Citizen CL-E300)\n"
                f"5. Configure settings and click Print\n\n"
                f"💡 Tip: This method works well for printing many labels at once!"
            )

            # Close dialog
            self.accept()

        except Exception as e:
            logger.error(f"Failed to open Explorer: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to open Windows Explorer:\n\n{str(e)}"
            )
