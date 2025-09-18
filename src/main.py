import sys
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton, QVBoxLayout, QWidget, QFileDialog, QStackedWidget,
    QTableView, QHBoxLayout
)
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtMultimedia import QSoundEffect
from datetime import datetime
from openpyxl.styles import PatternFill
import pandas as pd

from mapping_dialog import ColumnMappingDialog
from print_dialog import PrintDialog
from packer_mode_widget import PackerModeWidget
from packer_logic import PackerLogic, REQUIRED_COLUMNS
from session_manager import SessionManager
from order_table_model import OrderTableModel

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Packer's Assistant")
        self.resize(1024, 768)

        self.session_manager = SessionManager(base_dir=".")
        self.logic = None # Will be instantiated per session

        self._init_sounds()
        self._init_ui()

        if self.sounds_missing:
            self.status_label.setText(self.status_label.text() + "\nWarning: Sound files not found.")

    def _init_ui(self):
        self.session_widget = QWidget()
        main_layout = QVBoxLayout(self.session_widget)

        control_panel = QWidget()
        control_layout = QHBoxLayout(control_panel)
        main_layout.addWidget(control_panel)

        self.start_session_button = QPushButton("Start Session")
        self.start_session_button.clicked.connect(self.start_session)
        control_layout.addWidget(self.start_session_button)

        self.end_session_button = QPushButton("End Session")
        self.end_session_button.setEnabled(False)
        self.end_session_button.clicked.connect(self.end_session)
        control_layout.addWidget(self.end_session_button)

        control_layout.addStretch()

        self.print_button = QPushButton("Print Barcodes")
        self.print_button.setEnabled(False)
        self.print_button.clicked.connect(self.open_print_dialog)
        control_layout.addWidget(self.print_button)

        self.packer_mode_button = QPushButton("Switch to Packer Mode")
        self.packer_mode_button.setEnabled(False)
        self.packer_mode_button.clicked.connect(self.switch_to_packer_mode)
        control_layout.addWidget(self.packer_mode_button)

        self.orders_table = QTableView()
        main_layout.addWidget(self.orders_table)

        self.status_label = QLabel("Start a new session to load a packing list.")
        main_layout.addWidget(self.status_label)

        self.packer_mode_widget = PackerModeWidget()
        self.packer_mode_widget.barcode_scanned.connect(self.on_scanner_input)
        self.packer_mode_widget.exit_packing_mode.connect(self.switch_to_session_view)

        self.stacked_widget = QStackedWidget()
        self.stacked_widget.addWidget(self.session_widget)
        self.stacked_widget.addWidget(self.packer_mode_widget)
        self.setCentralWidget(self.stacked_widget)

    def _init_sounds(self):
        self.sounds_missing = False
        sound_files = {"success": "sounds/success.wav", "error": "sounds/error.wav", "victory": "sounds/victory.wav"}

        self.success_sound = QSoundEffect()
        if os.path.exists(sound_files["success"]): self.success_sound.setSource(QUrl.fromLocalFile(sound_files["success"]))
        else: self.sounds_missing = True

        self.error_sound = QSoundEffect()
        if os.path.exists(sound_files["error"]): self.error_sound.setSource(QUrl.fromLocalFile(sound_files["error"]))
        else: self.sounds_missing = True

        self.victory_sound = QSoundEffect()
        if os.path.exists(sound_files["victory"]): self.victory_sound.setSource(QUrl.fromLocalFile(sound_files["victory"]))
        else: self.sounds_missing = True

    def start_session(self, file_path=None):
        if self.session_manager.is_active():
            self.status_label.setText("A session is already active. Please end it first.")
            return

        if not file_path:
            file_path, _ = QFileDialog.getOpenFileName(self, "Select Packing List", "", "Excel Files (*.xlsx)")
            if not file_path:
                self.status_label.setText("Session start cancelled.")
                return

        self.session_manager.start_session(file_path)
        self.logic = PackerLogic(self.session_manager.get_output_dir())

        self.load_and_process_file(file_path)

    def end_session(self):
        if not self.session_manager.is_active():
            return

        try:
            output_dir = self.session_manager.get_output_dir()
            original_filename = os.path.basename(self.session_manager.packing_list_path)
            new_filename = f"{os.path.splitext(original_filename)[0]}_completed.xlsx"
            output_path = os.path.join(output_dir, new_filename)

            status_map = self.order_summary_df.set_index('Order_Number')['Status'].to_dict()
            completed_at_map = self.order_summary_df.set_index('Order_Number')['Completed At'].to_dict()

            final_df = self.logic.packing_list_df.copy()
            final_df['Status'] = final_df['Order_Number'].map(status_map).fillna('New')
            final_df['Completed At'] = final_df['Order_Number'].map(completed_at_map).fillna('')

            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                final_df.to_excel(writer, index=False, sheet_name='Sheet1')

                workbook = writer.book
                worksheet = writer.sheets['Sheet1']

                green_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")

                status_col_idx = final_df.columns.get_loc('Status') + 1

                for row_idx, row in enumerate(worksheet.iter_rows(min_row=2, max_row=worksheet.max_row)):
                    status_cell = worksheet.cell(row=row_idx + 2, column=status_col_idx)
                    if status_cell.value == 'Completed':
                        for cell in row:
                            cell.fill = green_fill

            self.status_label.setText(f"Session ended. Report saved to {output_path}")

        except Exception as e:
            self.status_label.setText(f"Could not save the report. Error: {e}")
            print(f"Error during end_session: {e}")

        self.session_manager.end_session()
        self.logic = None

        self.start_session_button.setEnabled(True)
        self.end_session_button.setEnabled(False)
        self.print_button.setEnabled(False)
        self.packer_mode_button.setEnabled(False)
        self.orders_table.setModel(None)
        self.status_label.setText("Session ended. Start a new session to begin.")

    def load_and_process_file(self, file_path):
        try:
            df = self.logic.load_packing_list_from_file(file_path)

            file_columns = list(df.columns)
            mapping = None
            if not all(col in file_columns for col in REQUIRED_COLUMNS):
                dialog = ColumnMappingDialog(REQUIRED_COLUMNS, file_columns, self)
                if not dialog.exec():
                    self.status_label.setText("File loading cancelled.")
                    self.end_session()
                    return
                mapping = dialog.get_mapping()

            session_id = self.session_manager.session_id
            self.status_label.setText(f"Session '{session_id}' started. Processing file...")
            order_count = self.logic.process_data_and_generate_barcodes(mapping)

            self.status_label.setText(f"Successfully processed {order_count} orders for session '{session_id}'.")

            self.setup_order_table()

            self.start_session_button.setEnabled(False)
            self.end_session_button.setEnabled(True)
            self.print_button.setEnabled(True)
            self.packer_mode_button.setEnabled(True)

        except (ValueError, RuntimeError) as e:
            self.status_label.setText(f"Error: {e}")
            self.end_session()
        except Exception as e:
            self.status_label.setText(f"An unexpected error occurred: {e}")
            self.end_session()

    def setup_order_table(self):
        df = self.logic.processed_df

        order_summary = df.groupby('Order_Number').agg(
            Total_SKUs=('SKU', 'nunique'),
            Total_Quantity=('Quantity', lambda x: pd.to_numeric(x, errors='coerce').sum())
        ).reset_index()

        order_summary['Status'] = 'New'
        order_summary['Completed At'] = ''

        self.order_summary_df = order_summary
        self.table_model = OrderTableModel(self.order_summary_df)
        self.orders_table.setModel(self.table_model)
        self.orders_table.resizeColumnsToContents()

    def switch_to_packer_mode(self):
        self.stacked_widget.setCurrentWidget(self.packer_mode_widget)
        self.packer_mode_widget.set_focus_to_scanner()

    def switch_to_session_view(self):
        self.logic.clear_current_order()
        self.packer_mode_widget.clear_screen()
        self.stacked_widget.setCurrentWidget(self.session_widget)

    def open_print_dialog(self):
        if not self.logic.orders_data:
            self.status_label.setText("No data to print.")
            return
        dialog = PrintDialog(self.logic.orders_data, self)
        dialog.exec()

    def on_scanner_input(self, text: str):
        self.packer_mode_widget.show_notification("", "black")

        if self.logic.current_order_number is None:
            items, status = self.logic.start_order_packing(text)
            if status == "ORDER_LOADED":
                self.packer_mode_widget.display_order(items)
                order_number = self.logic.current_order_number
                self.update_order_status(order_number, "In Progress")
            else:
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
                current_order_num = self.logic.current_order_number
                self.packer_mode_widget.update_item_row(result["row"], result["packed"], result["is_complete"])
                self.packer_mode_widget.show_notification(f"ORDER {current_order_num} COMPLETE!", "green")
                self.update_order_status(current_order_num, "Completed")
                self.victory_sound.play()
                self.logic.clear_current_order()
                QTimer.singleShot(3000, self.packer_mode_widget.clear_screen)

    def update_order_status(self, order_number, status):
        try:
            row_index = self.order_summary_df.index[self.order_summary_df['Order_Number'] == order_number][0]
            status_col_index = self.order_summary_df.columns.get_loc('Status')

            self.order_summary_df.iloc[row_index, status_col_index] = status
            if status == 'Completed':
                completed_col_index = self.order_summary_df.columns.get_loc('Completed At')
                self.order_summary_df.iloc[row_index, completed_col_index] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            self.table_model.dataChanged.emit(
                self.table_model.index(row_index, 0),
                self.table_model.index(row_index, self.table_model.columnCount() - 1)
            )
        except (IndexError, KeyError):
            print(f"Warning: Could not update status for order number {order_number}. Not found in summary table.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
