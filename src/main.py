import sys
import os
import json
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton, QVBoxLayout, QWidget, QFileDialog, QStackedWidget,
    QTableView, QHBoxLayout, QMessageBox, QHeaderView, QLineEdit
)
from PySide6.QtCore import QTimer, QUrl, Qt
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
from statistics_manager import StatisticsManager
from custom_filter_proxy_model import CustomFilterProxyModel

def find_latest_session_dir(base_dir="."):
    """Finds the most recent, valid, incomplete session directory."""
    session_pattern = "OrdersFulfillment_"
    session_dirs = []
    try:
        session_dirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d)) and d.startswith(session_pattern)]
    except FileNotFoundError:
        return None # No base directory yet

    valid_sessions = []
    for dirname in session_dirs:
        dirpath = os.path.join(base_dir, dirname)
        # A valid, incomplete session must have a session_info file.
        if os.path.exists(os.path.join(dirpath, "session_info.json")):
            valid_sessions.append(dirpath)

    if not valid_sessions:
        return None

    # Return the one that was most recently modified
    latest_session_dir = max(valid_sessions, key=os.path.getmtime)
    return latest_session_dir


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Packer's Assistant")
        self.resize(1024, 768)

        self.session_manager = SessionManager(base_dir=".")
        self.logic = None # Will be instantiated per session
        self.stats_manager = StatisticsManager()

        self._init_sounds()
        self._init_ui()

        if self.sounds_missing:
            self.status_label.setText(self.status_label.text() + "\nWarning: Sound files not found.")

        self._update_dashboard()

    def _init_ui(self):
        self.session_widget = QWidget()
        main_layout = QVBoxLayout(self.session_widget)

        # Dashboard
        dashboard_widget = QWidget()
        dashboard_widget.setObjectName("Dashboard")
        dashboard_layout = QHBoxLayout(dashboard_widget)
        main_layout.addWidget(dashboard_widget)

        self.total_orders_label = QLabel("Total Unique Orders: 0")
        self.completed_label = QLabel("Total Completed: 0")

        for label in [self.total_orders_label, self.completed_label]:
            label.setAlignment(Qt.AlignCenter)
            font = label.font()
            font.setPointSize(14)
            font.setBold(True)
            label.setFont(font)
            dashboard_layout.addWidget(label)

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

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by Order Number, SKU, or Status...")
        main_layout.addWidget(self.search_input)

        self.orders_table = QTableView()
        self.orders_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
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

    def _update_dashboard(self):
        stats = self.stats_manager.get_display_stats()
        self.total_orders_label.setText(f"Total Unique Orders: {stats['Total Unique Orders']}")
        self.completed_label.setText(f"Total Completed: {stats['Total Completed']}")

    def flash_border(self, color, duration_ms=500):
        """Flashes the border of the packer mode table's frame with a specific color."""
        # Apply the border to the frame wrapping the table by using a specific object name
        self.packer_mode_widget.table_frame.setStyleSheet(f"QFrame#TableFrame {{ border: 2px solid {color}; }}")

        # Set a timer to remove the border
        QTimer.singleShot(duration_ms, lambda: self.packer_mode_widget.table_frame.setStyleSheet(""))

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

    def start_session(self, file_path=None, restore_dir=None):
        if self.session_manager.is_active():
            self.status_label.setText("A session is already active. Please end it first.")
            return

        # Defensively clear the table model to prevent state issues.
        self.orders_table.setModel(None)

        if not file_path:
            file_path, _ = QFileDialog.getOpenFileName(self, "Select Packing List", "", "Excel Files (*.xlsx)")
            if not file_path:
                self.status_label.setText("Session start cancelled.")
                return

        self.session_manager.start_session(file_path, restore_dir=restore_dir)
        self.logic = PackerLogic(self.session_manager.get_output_dir())
        self.logic.item_packed.connect(self._on_item_packed)

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

        if self.logic:
            self.logic.end_session_cleanup()

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

            self.setup_order_table() # Call this first to have order_summary_df

            order_ids = self.order_summary_df['Order_Number'].tolist()
            self.stats_manager.record_new_orders(order_ids)
            self._update_dashboard()

            self.status_label.setText(f"Successfully processed {order_count} orders for session '{session_id}'.")

            self.start_session_button.setEnabled(False)
            self.end_session_button.setEnabled(True)
            self.print_button.setEnabled(True)
            self.packer_mode_button.setEnabled(True)

        except (ValueError, RuntimeError) as e:
            print("--- A known error occurred ---")
            traceback.print_exc()
            self.status_label.setText(f"Error: {e}")
            self.end_session()
        except Exception as e:
            print("--- An unexpected error occurred ---")
            traceback.print_exc()
            self.status_label.setText(f"An unexpected error occurred: {e}")
            self.end_session()

    def setup_order_table(self):
        df = self.logic.processed_df
        extra_cols = [col for col in df.columns if col not in REQUIRED_COLUMNS]

        agg_dict = {
            'SKU': 'nunique',
            'Quantity': lambda x: pd.to_numeric(x, errors='coerce').sum()
        }
        for col in extra_cols:
            agg_dict[col] = 'first'

        order_summary = df.groupby('Order_Number').agg(agg_dict).reset_index()
        order_summary.rename(columns={'SKU': 'Total_SKUs', 'Quantity': 'Total_Quantity'}, inplace=True)

        final_cols = ['Order_Number'] + extra_cols + ['Total_SKUs', 'Total_Quantity']
        order_summary = order_summary[final_cols]

        order_summary['Packing Progress'] = "0 / " + order_summary['Total_Quantity'].astype(int).astype(str)
        order_summary['Status'] = 'New'
        order_summary['Completed At'] = ''

        # Update progress and status from loaded session state
        completed_orders = self.logic.session_packing_state.get('completed_orders', [])
        in_progress_orders = self.logic.session_packing_state.get('in_progress', {})

        for index, row in order_summary.iterrows():
            order_number = row['Order_Number']
            total_required = order_summary.at[index, 'Total_Quantity']

            if order_number in completed_orders:
                order_summary.at[index, 'Status'] = 'Completed'
                order_summary.at[index, 'Packing Progress'] = f"{int(total_required)} / {int(total_required)}"
            elif order_number in in_progress_orders:
                order_state = in_progress_orders[order_number]
                total_packed = sum(s['packed'] for s in order_state.values())

                order_summary.at[index, 'Packing Progress'] = f"{total_packed} / {int(total_required)}"
                if total_packed > 0:
                    order_summary.at[index, 'Status'] = 'In Progress'

        self.order_summary_df = order_summary
        self.table_model = OrderTableModel(self.order_summary_df)

        # Set up the proxy model for filtering
        self.proxy_model = CustomFilterProxyModel()
        self.proxy_model.setSourceModel(self.table_model)
        self.proxy_model.set_processed_df(self.logic.processed_df)
        self.orders_table.setModel(self.proxy_model)

        # Connect search input to the proxy model's filter
        self.search_input.textChanged.connect(self.proxy_model.setFilterFixedString)

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
        self.packer_mode_widget.update_raw_scan_display(text)
        self.packer_mode_widget.show_notification("", "black")

        if self.logic.current_order_number is None:
            # This is an order barcode scan
            order_number_from_scan = self.logic.barcode_to_order_number.get(text)
            if not order_number_from_scan:
                self.packer_mode_widget.show_notification("ORDER NOT FOUND", "red")
                self.flash_border("red")
                self.error_sound.play()
                return

            # Check if order is already completed
            if order_number_from_scan in self.logic.session_packing_state.get('completed_orders', []):
                self.packer_mode_widget.show_notification(f"ORDER {order_number_from_scan} ALREADY COMPLETED", "orange")
                self.flash_border("orange")
                self.error_sound.play()
                return

            items, status = self.logic.start_order_packing(text)
            if status == "ORDER_LOADED":
                self.packer_mode_widget.add_order_to_history(order_number_from_scan)
                self.packer_mode_widget.display_order(items, self.logic.current_order_state)
                self.update_order_status(order_number_from_scan, "In Progress")
            elif status == "ORDER_ALREADY_COMPLETED":
                # This is a redundant check, but good for safety
                self.packer_mode_widget.show_notification(f"ORDER {order_number_from_scan} ALREADY COMPLETED", "orange")
                self.flash_border("orange")
                self.error_sound.play()
            else: # Should not happen due to above checks, but as a fallback
                self.packer_mode_widget.show_notification("ORDER NOT FOUND", "red")
                self.flash_border("red")
                self.error_sound.play()
        else:
            result, status = self.logic.process_sku_scan(text)
            if status == "SKU_OK":
                self.packer_mode_widget.update_item_row(result["row"], result["packed"], result["is_complete"])
                self.flash_border("green")
                self.success_sound.play()
            elif status == "SKU_NOT_FOUND":
                self.packer_mode_widget.show_notification("INCORRECT ITEM!", "red")
                self.flash_border("red")
                self.error_sound.play()
            elif status == "ORDER_COMPLETE":
                current_order_num = self.logic.current_order_number
                self.stats_manager.record_order_completion(current_order_num)
                self._update_dashboard()

                self.packer_mode_widget.update_item_row(result["row"], result["packed"], result["is_complete"])
                self.packer_mode_widget.show_notification(f"ORDER {current_order_num} COMPLETE!", "green")
                self.flash_border("green")
                self.update_order_status(current_order_num, "Completed")
                self.victory_sound.play()
                self.packer_mode_widget.scanner_input.setEnabled(False) # Disable input
                self.logic.clear_current_order()
                QTimer.singleShot(3000, self.packer_mode_widget.clear_screen)

    def _on_item_packed(self, order_number, packed_count, required_count):
        """Slot to handle real-time progress updates from the logic layer."""
        try:
            row_index = self.order_summary_df.index[self.order_summary_df['Order_Number'] == order_number][0]
            progress_col_index = self.order_summary_df.columns.get_loc('Packing Progress')

            new_progress = f"{packed_count} / {required_count}"
            self.order_summary_df.iloc[row_index, progress_col_index] = new_progress

            # Emit dataChanged for the specific cell that was updated
            self.table_model.dataChanged.emit(
                self.table_model.index(row_index, progress_col_index),
                self.table_model.index(row_index, progress_col_index)
            )
        except (IndexError, KeyError):
            # This might happen in rare cases, can be ignored.
            pass

    def update_order_status(self, order_number, status):
        try:
            row_index = self.order_summary_df.index[self.order_summary_df['Order_Number'] == order_number][0]

            # Update Status
            status_col_index = self.order_summary_df.columns.get_loc('Status')
            self.order_summary_df.iloc[row_index, status_col_index] = status

            # Update Packing Progress column as well
            progress_col_index = self.order_summary_df.columns.get_loc('Packing Progress')
            if status == 'Completed':
                total_quantity = self.order_summary_df.iloc[row_index]['Total_Quantity']
                self.order_summary_df.iloc[row_index, progress_col_index] = f"{int(total_quantity)} / {int(total_quantity)}"

                completed_col_index = self.order_summary_df.columns.get_loc('Completed At')
                self.order_summary_df.iloc[row_index, completed_col_index] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            elif status == 'In Progress':
                # The _on_item_packed slot will provide more granular updates.
                # This just sets the initial progress if it's not already set.
                if order_number in self.logic.session_packing_state:
                    order_state = self.logic.session_packing_state[order_number]
                    total_packed = sum(s['packed'] for s in order_state.values())
                    total_required = sum(s['required'] for s in order_state.values())
                    self.order_summary_df.iloc[row_index, progress_col_index] = f"{total_packed} / {total_required}"

            self.table_model.dataChanged.emit(
                self.table_model.index(row_index, 0),
                self.table_model.index(row_index, self.table_model.columnCount() - 1)
            )
        except (IndexError, KeyError):
            print(f"Warning: Could not update status for order number {order_number}. Not found in summary table.")

def restore_session(window):
    latest_dir = find_latest_session_dir()
    if not latest_dir:
        return

    session_info_path = os.path.join(latest_dir, "session_info.json")
    state_path = os.path.join(latest_dir, "packing_state.json")

    # The check for session_info_path is already in find_latest_session_dir
    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Question)
    msg_box.setText("An incomplete session was found.")
    msg_box.setInformativeText(f"Would you like to restore session '{os.path.basename(latest_dir)}'?")
    msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    msg_box.setDefaultButton(QMessageBox.Yes)

    reply = msg_box.exec()

    if reply == QMessageBox.Yes:
        try:
            with open(session_info_path, 'r') as f:
                session_info = json.load(f)
            packing_list_path = session_info.get('packing_list_path')
            if packing_list_path and os.path.exists(packing_list_path):
                # Pass the restore_dir to start_session
                window.start_session(file_path=packing_list_path, restore_dir=latest_dir)
            else:
                QMessageBox.critical(window, "Error", "Could not restore session. The original packing list file was not found.")
        except Exception as e:
            QMessageBox.critical(window, "Error", f"An error occurred during session restoration: {e}")
    else:
        # User chose not to restore, so rename files to ignore them next time
        try:
            if os.path.exists(session_info_path):
                os.rename(session_info_path, session_info_path + ".ignored")
            if os.path.exists(state_path):
                os.rename(state_path, state_path + ".ignored")
        except OSError as e:
            QMessageBox.warning(window, "Cleanup Warning", f"Could not ignore all session files: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Load and apply stylesheet
    try:
        with open("src/styles.qss", "r") as f:
            app.setStyleSheet(f.read())
    except FileNotFoundError:
        print("Warning: stylesheet 'src/styles.qss' not found.")

    window = MainWindow()

    # Check for abandoned sessions before showing the main window
    restore_session(window)

    window.show()
    sys.exit(app.exec())
