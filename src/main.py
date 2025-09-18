import sys
import os
import shutil
import pandas as pd
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QWidget,
    QFileDialog, QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QColor
from PySide6.QtMultimedia import QSoundEffect

from mapping_dialog import ColumnMappingDialog
from print_dialog import PrintDialog
from packer_mode_widget import PackerModeWidget
from packer_logic import PackerLogic, REQUIRED_COLUMNS

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Packer's Assistant")
        self.resize(1200, 800)

        self.logic = PackerLogic(barcode_dir="barcodes") # Temp dir for barcodes
        self.session_active = False

        self._init_sounds()
        self._init_ui()

        if self.sounds_missing:
            self.status_label.setText(self.status_label.text() + "\nWarning: Sound files not found.")

    def _init_ui(self):
        # --- Main Setup Screen ---
        self.setup_widget = QWidget()
        main_layout = QVBoxLayout(self.setup_widget)

        # Top button layout
        top_layout = QHBoxLayout()
        self.load_button = QPushButton("1. Load Packing List (.xlsx)")
        self.load_button.clicked.connect(self.open_file_dialog)
        self.start_session_button = QPushButton("2. Start Packing Session")
        self.start_session_button.setEnabled(False)
        self.start_session_button.clicked.connect(self.start_session)
        self.end_session_button = QPushButton("3. End Session & Save Report")
        self.end_session_button.setEnabled(False)
        self.end_session_button.clicked.connect(self.end_session)
        top_layout.addWidget(self.load_button)
        top_layout.addWidget(self.start_session_button)
        top_layout.addWidget(self.end_session_button)
        main_layout.addLayout(top_layout)

        # Packing list display table
        self.packing_list_table = QTableWidget()
        self.packing_list_table.setEditTriggers(QTableWidget.NoEditTriggers)
        main_layout.addWidget(self.packing_list_table)

        # Status label
        self.status_label = QLabel("Please load a packing list to begin.")
        main_layout.addWidget(self.status_label)

        # --- Packer Mode Screen ---
        self.packer_mode_widget = PackerModeWidget()
        self.packer_mode_widget.barcode_scanned.connect(self.on_scanner_input)
        self.packer_mode_widget.exit_packing_mode.connect(self.switch_to_setup_mode)
        self.packer_mode_widget.manual_confirm_requested.connect(self.on_manual_confirm)

        # --- Stacked Widget for switching screens ---
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.addWidget(self.setup_widget)
        self.stacked_widget.addWidget(self.packer_mode_widget)
        self.setCentralWidget(self.stacked_widget)

    def _init_sounds(self):
        self.sounds_missing = False
        sound_files = {"success": "sounds/success.wav", "error": "sounds/error.wav", "victory": "sounds/victory.wav"}
        for name, path in sound_files.items():
            sound = QSoundEffect()
            if os.path.exists(path):
                sound.setSource(QUrl.fromLocalFile(path))
            else:
                self.sounds_missing = True
            setattr(self, f"{name}_sound", sound)

    def open_file_dialog(self):
        if self.session_active:
            self.status_label.setText("Please end the current session before loading a new file.")
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Packing List", "", "Excel Files (*.xlsx)")
        if file_path:
            self.load_and_process_file(file_path)

    def load_and_process_file(self, file_path):
        try:
            df = self.logic.load_packing_list_from_file(file_path)
            if not self.handle_column_mapping(df):
                return

            self.status_label.setText("Processing file and generating barcodes...")
            QApplication.processEvents() # Update UI
            order_count = self.logic.process_data_and_generate_barcodes()

            self.display_packing_list(self.logic.packing_list_df)
            self.status_label.setText(f"Successfully processed {order_count} orders. Ready to start session.")
            self.start_session_button.setEnabled(True)

        except (ValueError, RuntimeError) as e:
            self.status_label.setText(f"Error: {e}")
        except Exception as e:
            self.status_label.setText(f"Unexpected error: {e}")

    def handle_column_mapping(self, df):
        file_columns = list(df.columns)
        if not all(col in file_columns for col in REQUIRED_COLUMNS):
            dialog = ColumnMappingDialog(REQUIRED_COLUMNS, file_columns, self)
            if not dialog.exec():
                self.status_label.setText("Loading cancelled.")
                return False
            self.logic.packing_list_df.rename(columns=dialog.get_mapping(), inplace=True)
        return True

    def display_packing_list(self, df):
        self.packing_list_table.setRowCount(len(df))
        self.packing_list_table.setColumnCount(len(df.columns) + 1)

        headers = df.columns.tolist() + ["Status"]
        self.packing_list_table.setHorizontalHeaderLabels(headers)

        for row in range(len(df)):
            for col, col_name in enumerate(df.columns):
                self.packing_list_table.setItem(row, col, QTableWidgetItem(str(df.iloc[row, col])))
            self.packing_list_table.setItem(row, len(df.columns), QTableWidgetItem("Pending"))

        self.packing_list_table.resizeColumnsToContents()
        self.packing_list_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

    def update_order_status_in_table(self, order_number, new_status):
        """Finds all rows for an order and updates their status and color."""
        status_col_idx = self.packing_list_table.columnCount() - 1
        for row in range(self.packing_list_table.rowCount()):
            order_item = self.packing_list_table.item(row, 0)
            if order_item and order_item.text() == order_number:
                self.packing_list_table.setItem(row, status_col_idx, QTableWidgetItem(new_status))
                for col in range(self.packing_list_table.columnCount()):
                    self.packing_list_table.item(row, col).setBackground(QColor("lightgreen"))


    def start_session(self):
        self.session_active = True
        self.status_label.setText("Session started. You can now switch to Packer Mode.")
        self.start_session_button.setEnabled(False)
        self.load_button.setEnabled(False)
        self.end_session_button.setEnabled(True)
        self.switch_to_packer_mode()


    def end_session(self):
        if not self.session_active:
            self.status_label.setText("No active session to end.")
            return

        self.status_label.setText("Ending session and generating report...")
        QApplication.processEvents()

        try:
            # 1. Prepare the report DataFrame
            report_df = self.logic.packing_list_df.copy()
            completion_map = self.logic.order_completion_status
            # Format timestamp to string for Excel
            report_df['Fulfilled'] = report_df['Order_Number'].map(completion_map).dt.strftime('%Y-%m-%d %H:%M:%S').fillna('Not Completed')

            # 2. Determine session folder name
            today_str = datetime.now().strftime('%Y-%m-%d')
            session_num = 1
            while True:
                folder_name = f"OrdersFulfillment_{today_str}_{session_num}"
                if not os.path.exists(folder_name):
                    break
                session_num += 1

            os.makedirs(folder_name)

            # 3. Move barcodes
            for data in self.logic.orders_data.values():
                barcode_path = data['barcode_path']
                if os.path.exists(barcode_path):
                    shutil.move(barcode_path, folder_name)

            # 4. Save the report
            report_filename = os.path.join(folder_name, "fulfillment_report.xlsx")
            report_df.to_excel(report_filename, index=False)

            self.status_label.setText(f"Session report saved to '{folder_name}'.")

        except Exception as e:
            self.status_label.setText(f"Error saving session report: {e}")

        # 5. Reset UI and state
        self.session_active = False
        self.start_session_button.setEnabled(False)
        self.end_session_button.setEnabled(False)
        self.load_button.setEnabled(True)
        self.packing_list_table.setRowCount(0)
        self.logic.clear_session_data()


    def switch_to_packer_mode(self):
        if not self.session_active:
            self.status_label.setText("Please start a session first.")
            return
        self.stacked_widget.setCurrentWidget(self.packer_mode_widget)
        self.packer_mode_widget.set_focus_to_scanner()

    def switch_to_setup_mode(self):
        """Switches the view back to the main setup screen."""
        self.logic.clear_current_order()
        self.packer_mode_widget.clear_screen()
        self.stacked_widget.setCurrentWidget(self.setup_widget)

    def on_scanner_input(self, text: str):
        # This logic will need to be updated to interact with the new session model
        # and update the main table view.
        self.packer_mode_widget.show_notification("", "black")

        if self.logic.current_order_number is None:
            items, status = self.logic.start_order_packing(text)
            if status == "ORDER_LOADED":
                self.packer_mode_widget.display_order(items)
            else: # ORDER_NOT_FOUND
                self.packer_mode_widget.show_notification("ORDER NOT FOUND", "red")
                self.error_sound.play()
        else:
            result, status = self.logic.process_sku_scan(text)
            if status == "SKU_OK":
                self.packer_mode_widget.update_item_row(result["row"], result["packed"], result["is_complete"])
                self.success_sound.play()
            elif status == "SKU_NOT_FOUND":
                self.packer_mode_widget.show_notification("INCORRECT ITEM!", "red")
                self.error_sound.play()
            elif status == "ORDER_COMPLETE":
                order_number = self.logic.current_order_number
                self.packer_mode_widget.update_item_row(result["row"], result["packed"], result["is_complete"])
                self.packer_mode_widget.show_notification(f"ORDER {order_number} COMPLETE!", "green")
                self.victory_sound.play()

                self.update_order_status_in_table(order_number, "Completed")

                self.logic.clear_current_order()
                QTimer.singleShot(2000, self.switch_to_setup_mode)

    def on_manual_confirm(self, row):
        """Handles the manual confirmation of an item."""
        sku_item = self.packer_mode_widget.table.item(row, 1)
        if not sku_item:
            return

        sku = sku_item.text()
        result, status = self.logic.manual_confirm_item(sku)

        if status == "SKU_OK":
            self.packer_mode_widget.update_item_row(result["row"], result["packed"], result["is_complete"])
            self.success_sound.play()
        elif status == "ORDER_COMPLETE":
            order_number = self.logic.current_order_number
            self.packer_mode_widget.update_item_row(result["row"], result["packed"], result["is_complete"])
            self.packer_mode_widget.show_notification(f"ORDER {order_number} COMPLETE!", "green")
            self.victory_sound.play()
            self.update_order_status_in_table(order_number, "Completed")
            self.logic.clear_current_order()
            QTimer.singleShot(2000, self.switch_to_setup_mode)
        elif status == "SKU_EXTRA":
            self.packer_mode_widget.show_notification("ITEM ALREADY PACKED", "orange")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
