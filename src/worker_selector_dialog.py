"""
Worker Selector Dialog - UI for selecting worker at session start.

This dialog allows the user to:
- Select an existing worker from a list
- Create a new worker profile
- View worker information
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget,
    QListWidgetItem, QLabel, QLineEdit, QFormLayout, QDialogButtonBox,
    QMessageBox, QTextEdit
)
from PySide6.QtCore import Qt
from typing import Optional, Dict

from logger import get_logger
from worker_manager import WorkerManager

logger = get_logger(__name__)


class WorkerSelectorDialog(QDialog):
    """
    Dialog for selecting a worker from available profiles.

    This dialog displays all active workers and allows:
    - Selection via double-click or Select button
    - Creating new worker profiles
    - Viewing worker details
    """

    def __init__(self, worker_manager: WorkerManager, parent=None):
        """
        Initialize worker selector dialog.

        Args:
            worker_manager: WorkerManager instance for loading worker profiles
            parent: Parent widget
        """
        super().__init__(parent)

        self.worker_manager = worker_manager
        self.selected_worker = None

        self.setWindowTitle("Select Worker")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        self._init_ui()
        self._load_workers()

    def _init_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout(self)

        # Title
        title_label = QLabel("Select Worker for this Packing Session")
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # Instructions
        info_label = QLabel(
            "Choose the worker who will be packing orders in this session.\n"
            "Worker activity will be tracked for performance metrics."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; margin-bottom: 10px;")
        layout.addWidget(info_label)

        # Workers list
        self.workers_list = QListWidget()
        self.workers_list.itemDoubleClicked.connect(self._on_worker_double_clicked)
        self.workers_list.currentItemChanged.connect(self._on_selection_changed)
        layout.addWidget(self.workers_list)

        # Worker info panel
        info_group = QLabel("Worker Information:")
        info_group.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(info_group)

        self.worker_info_text = QTextEdit()
        self.worker_info_text.setReadOnly(True)
        self.worker_info_text.setMaximumHeight(100)
        self.worker_info_text.setStyleSheet("background-color: #f5f5f5; border: 1px solid #ccc;")
        layout.addWidget(self.worker_info_text)

        # Buttons
        button_layout = QHBoxLayout()

        self.new_worker_button = QPushButton("➕ New Worker")
        self.new_worker_button.clicked.connect(self._open_new_worker_dialog)
        self.new_worker_button.setToolTip("Create a new worker profile")
        button_layout.addWidget(self.new_worker_button)

        button_layout.addStretch()

        self.select_button = QPushButton("✓ Select")
        self.select_button.setEnabled(False)
        self.select_button.clicked.connect(self.accept)
        self.select_button.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        button_layout.addWidget(self.select_button)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        layout.addLayout(button_layout)

    def _load_workers(self):
        """Load and display all active workers."""
        logger.info("Loading workers for selection")

        self.workers_list.clear()
        self.worker_info_text.clear()

        try:
            workers = self.worker_manager.list_workers()

            if not workers:
                logger.warning("No workers found")
                self.workers_list.addItem("(No workers available - click 'New Worker' to create one)")
                return

            # Filter only active workers
            active_workers = [w for w in workers if w.get('active', True)]

            if not active_workers:
                self.workers_list.addItem("(No active workers - click 'New Worker' to create one)")
                return

            # Add workers to list
            for worker in active_workers:
                worker_id = worker.get('worker_id', 'Unknown')
                worker_name = worker.get('name', 'Unknown')

                # Create display text
                display_text = f"👤 {worker_name} (ID: {worker_id})"

                # Add stats if available
                stats = worker.get('stats', {})
                total_sessions = stats.get('total_sessions', 0)
                if total_sessions > 0:
                    display_text += f" - {total_sessions} sessions"

                # Create list item
                item = QListWidgetItem(display_text)
                item.setData(Qt.UserRole, worker)  # Store full worker data
                self.workers_list.addItem(item)

            logger.info(f"Loaded {len(active_workers)} active workers")

        except Exception as e:
            logger.error(f"Error loading workers: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load workers:\n\n{e}"
            )

    def _on_selection_changed(self, current: QListWidgetItem, previous: QListWidgetItem):
        """
        Handle worker selection change.

        Args:
            current: Currently selected item
            previous: Previously selected item
        """
        if not current:
            self.select_button.setEnabled(False)
            self.worker_info_text.clear()
            return

        # Get worker data
        worker = current.data(Qt.UserRole)

        if not worker:
            self.select_button.setEnabled(False)
            self.worker_info_text.clear()
            return

        # Enable select button
        self.select_button.setEnabled(True)

        # Display worker info
        self._display_worker_info(worker)

    def _display_worker_info(self, worker: Dict):
        """
        Display detailed worker information.

        Args:
            worker: Worker profile dictionary
        """
        worker_id = worker.get('worker_id', 'Unknown')
        name = worker.get('name', 'Unknown')
        created_at = worker.get('created_at', 'Unknown')

        # Format created date
        try:
            from datetime import datetime
            created_dt = datetime.fromisoformat(created_at)
            created_formatted = created_dt.strftime('%Y-%m-%d')
        except:
            created_formatted = created_at

        # Build info text
        info_lines = [
            f"<b>Name:</b> {name}",
            f"<b>Worker ID:</b> {worker_id}",
            f"<b>Created:</b> {created_formatted}",
        ]

        # Add stats
        stats = worker.get('stats', {})
        if stats:
            total_sessions = stats.get('total_sessions', 0)
            total_orders = stats.get('total_orders_packed', 0)
            avg_orders = stats.get('avg_orders_per_session', 0.0)

            info_lines.append("")
            info_lines.append(f"<b>Statistics:</b>")
            info_lines.append(f"  • Total Sessions: {total_sessions}")
            info_lines.append(f"  • Total Orders Packed: {total_orders}")
            info_lines.append(f"  • Avg Orders/Session: {avg_orders:.1f}")

        # Add optional fields
        if 'email' in worker:
            info_lines.append(f"<b>Email:</b> {worker['email']}")
        if 'department' in worker:
            info_lines.append(f"<b>Department:</b> {worker['department']}")

        self.worker_info_text.setHtml("<br>".join(info_lines))

    def _on_worker_double_clicked(self, item: QListWidgetItem):
        """
        Handle double-click on worker - immediately select and close.

        Args:
            item: Double-clicked list item
        """
        worker = item.data(Qt.UserRole)

        if worker:
            self.selected_worker = worker
            self.accept()

    def _open_new_worker_dialog(self):
        """Open dialog to create new worker."""
        logger.info("Opening new worker dialog")

        dialog = NewWorkerDialog(self.worker_manager, self)

        if dialog.exec() == QDialog.Accepted:
            logger.info(f"New worker created: {dialog.worker_id}")

            # Reload workers list
            self._load_workers()

            # Select newly created worker
            for i in range(self.workers_list.count()):
                item = self.workers_list.item(i)
                worker = item.data(Qt.UserRole)
                if worker and worker.get('worker_id') == dialog.worker_id:
                    self.workers_list.setCurrentItem(item)
                    break

            QMessageBox.information(
                self,
                "Worker Created",
                f"Worker '{dialog.worker_name}' created successfully!"
            )

    def get_selected_worker(self) -> Optional[Dict]:
        """
        Get the selected worker profile.

        Returns:
            Worker profile dictionary, or None if no selection
        """
        if self.selected_worker:
            return self.selected_worker

        # Get from current selection
        current_item = self.workers_list.currentItem()
        if current_item:
            return current_item.data(Qt.UserRole)

        return None

    def accept(self):
        """Handle dialog acceptance."""
        self.selected_worker = self.get_selected_worker()

        if not self.selected_worker:
            QMessageBox.warning(
                self,
                "No Selection",
                "Please select a worker or create a new one."
            )
            return

        logger.info(f"Worker selected: {self.selected_worker.get('worker_id')}")
        super().accept()


class NewWorkerDialog(QDialog):
    """
    Dialog for creating a new worker profile.

    Allows entering:
    - Worker ID (required)
    - Worker Name (required)
    - Email (optional)
    - Department (optional)
    - Notes (optional)
    """

    def __init__(self, worker_manager: WorkerManager, parent=None):
        """
        Initialize new worker dialog.

        Args:
            worker_manager: WorkerManager instance for creating profiles
            parent: Parent widget
        """
        super().__init__(parent)

        self.worker_manager = worker_manager
        self.worker_id = None
        self.worker_name = None

        self.setWindowTitle("Create New Worker")
        self.setMinimumWidth(450)

        self._init_ui()

    def _init_ui(self):
        """Initialize UI components."""
        layout = QFormLayout(self)

        # Instructions
        instructions = QLabel(
            "Create a new worker profile. Worker ID should be a short unique identifier (e.g., 001, 002).\n"
            "Worker name is the full name displayed in the system."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet("color: #666; margin-bottom: 10px;")
        layout.addRow(instructions)

        # Worker ID
        self.worker_id_input = QLineEdit()
        self.worker_id_input.setPlaceholderText("e.g., 001, 002, 003")
        self.worker_id_input.setMaxLength(10)
        self.worker_id_input.textChanged.connect(self._validate_inputs)
        layout.addRow("Worker ID (required):", self.worker_id_input)

        # Validation message
        self.validation_label = QLabel("")
        self.validation_label.setStyleSheet("color: red;")
        self.validation_label.setWordWrap(True)
        layout.addRow("", self.validation_label)

        # Worker Name
        self.worker_name_input = QLineEdit()
        self.worker_name_input.setPlaceholderText("e.g., John Doe, Jane Smith")
        self.worker_name_input.textChanged.connect(self._validate_inputs)
        layout.addRow("Worker Name (required):", self.worker_name_input)

        # Email (optional)
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("worker@example.com (optional)")
        layout.addRow("Email:", self.email_input)

        # Department (optional)
        self.department_input = QLineEdit()
        self.department_input.setPlaceholderText("e.g., Warehouse, Packaging (optional)")
        layout.addRow("Department:", self.department_input)

        # Notes (optional)
        self.notes_input = QTextEdit()
        self.notes_input.setPlaceholderText("Additional notes (optional)")
        self.notes_input.setMaximumHeight(80)
        layout.addRow("Notes:", self.notes_input)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok_button = button_box.button(QDialogButtonBox.Ok)
        self.ok_button.setText("Create Worker")
        self.ok_button.setEnabled(False)
        button_box.accepted.connect(self._create_worker)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

    def _validate_inputs(self):
        """Validate input fields and enable/disable OK button."""
        worker_id = self.worker_id_input.text().strip()
        worker_name = self.worker_name_input.text().strip()

        # Clear validation message
        self.validation_label.clear()

        # Check if both required fields are filled
        if not worker_id or not worker_name:
            self.ok_button.setEnabled(False)
            return

        # Check if worker ID already exists
        if self.worker_manager.worker_exists(worker_id):
            self.validation_label.setText(f"⚠ Worker ID '{worker_id}' already exists!")
            self.validation_label.setStyleSheet("color: red;")
            self.ok_button.setEnabled(False)
            return

        # Validation passed
        self.validation_label.setText("✓ Valid worker ID")
        self.validation_label.setStyleSheet("color: green;")
        self.ok_button.setEnabled(True)

    def _create_worker(self):
        """Create the worker profile."""
        worker_id = self.worker_id_input.text().strip()
        worker_name = self.worker_name_input.text().strip()

        if not worker_id or not worker_name:
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Please fill in Worker ID and Worker Name."
            )
            return

        logger.info(f"Creating worker: {worker_id} - {worker_name}")

        # Prepare optional fields
        optional_fields = {}

        if self.email_input.text().strip():
            optional_fields['email'] = self.email_input.text().strip()

        if self.department_input.text().strip():
            optional_fields['department'] = self.department_input.text().strip()

        if self.notes_input.toPlainText().strip():
            optional_fields['notes'] = self.notes_input.toPlainText().strip()

        try:
            success = self.worker_manager.create_worker_profile(
                worker_id,
                worker_name,
                **optional_fields
            )

            if success:
                self.worker_id = worker_id
                self.worker_name = worker_name
                logger.info(f"Successfully created worker {worker_id}")
                self.accept()
            else:
                QMessageBox.warning(
                    self,
                    "Error",
                    f"Worker '{worker_id}' already exists!"
                )

        except Exception as e:
            logger.error(f"Error creating worker: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to create worker profile:\n\n{e}"
            )
