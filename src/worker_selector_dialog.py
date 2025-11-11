"""
Worker Selector Dialog - Dialog for selecting worker at session start.

This dialog allows workers to select their profile before starting a packing session.
Workers can also create new profiles if needed.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QListWidget, QListWidgetItem, QLabel, QMessageBox,
    QLineEdit, QFormLayout
)
from PySide6.QtCore import Qt

from worker_manager import WorkerManager
from logger import get_logger

logger = get_logger(__name__)


class WorkerSelectorDialog(QDialog):
    """
    Dialog для вибору працівника при старті сесії.

    Показує список всіх активних працівників.
    Можна створити нового працівника.
    """

    def __init__(self, worker_manager: WorkerManager, parent=None):
        super().__init__(parent)
        self.worker_manager = worker_manager
        self.selected_worker = None

        self.setWindowTitle("Select Worker")
        self.setMinimumSize(500, 600)
        self.setModal(True)

        self._setup_ui()
        self._load_workers()

    def _setup_ui(self):
        """Setup UI components."""
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("<h2>Select Your Worker Profile</h2>")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Instructions
        instructions = QLabel(
            "Select your name from the list below.\n"
            "All your packing sessions will be recorded under this profile."
        )
        instructions.setWordWrap(True)
        instructions.setAlignment(Qt.AlignCenter)
        instructions.setStyleSheet("color: gray; margin: 10px;")
        layout.addWidget(instructions)

        # Worker list
        list_label = QLabel("<b>Active Workers:</b>")
        layout.addWidget(list_label)

        self.worker_list = QListWidget()
        self.worker_list.itemDoubleClicked.connect(self._on_worker_selected)
        self.worker_list.setStyleSheet("""
            QListWidget {
                font-size: 14px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #e0e0e0;
            }
            QListWidget::item:selected {
                background-color: #2196F3;
                color: white;
            }
            QListWidget::item:hover {
                background-color: #f0f0f0;
            }
        """)
        layout.addWidget(self.worker_list)

        # Buttons
        button_layout = QHBoxLayout()

        self.new_worker_btn = QPushButton("New Worker")
        self.new_worker_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 16px;
                font-size: 14px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.new_worker_btn.clicked.connect(self._create_new_worker)
        button_layout.addWidget(self.new_worker_btn)

        button_layout.addStretch()

        self.select_btn = QPushButton("Select")
        self.select_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 8px 24px;
                font-size: 14px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.select_btn.clicked.connect(self._on_select_clicked)
        self.select_btn.setDefault(True)
        button_layout.addWidget(self.select_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 24px;
                font-size: 14px;
                border: 1px solid #ccc;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #f0f0f0;
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

    def _load_workers(self):
        """Load all active workers into list."""
        self.worker_list.clear()

        try:
            workers = self.worker_manager.list_workers()

            # Filter active workers
            active_workers = [w for w in workers if w.get('active', True)]

            if not active_workers:
                item = QListWidgetItem("No workers found. Click 'New Worker' to create one.")
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                self.worker_list.addItem(item)
                self.select_btn.setEnabled(False)
                logger.warning("No active workers found")
                return

            for worker in active_workers:
                worker_id = worker.get('worker_id', '')
                worker_name = worker.get('name', '')

                display_text = f"{worker_id} - {worker_name}"

                # Show stats if available
                stats = worker.get('stats', {})
                total_sessions = stats.get('total_sessions', 0)
                if total_sessions > 0:
                    display_text += f" ({total_sessions} sessions)"

                item = QListWidgetItem(display_text)
                item.setData(Qt.ItemDataRole.UserRole, worker)
                self.worker_list.addItem(item)

            # Select first item by default
            self.worker_list.setCurrentRow(0)
            self.select_btn.setEnabled(True)

            logger.info(f"Loaded {len(active_workers)} active workers")

        except Exception as e:
            logger.error(f"Error loading workers: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load workers:\n\n{e}"
            )

    def _on_worker_selected(self, item: QListWidgetItem):
        """Handle double-click on worker."""
        worker = item.data(Qt.ItemDataRole.UserRole)
        if worker:
            self.selected_worker = worker
            logger.info(f"Worker selected: {worker.get('name')} ({worker.get('worker_id')})")
            self.accept()

    def _on_select_clicked(self):
        """Handle Select button click."""
        current_item = self.worker_list.currentItem()
        if not current_item:
            QMessageBox.warning(
                self,
                "No Selection",
                "Please select a worker from the list."
            )
            return

        worker = current_item.data(Qt.ItemDataRole.UserRole)
        if worker:
            self.selected_worker = worker
            logger.info(f"Worker selected: {worker.get('name')} ({worker.get('worker_id')})")
            self.accept()

    def _create_new_worker(self):
        """Open dialog to create new worker."""
        dialog = NewWorkerDialog(self.worker_manager, self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Reload worker list
            self._load_workers()

            # Select the newly created worker
            created_id = dialog.created_worker_id
            if created_id:
                for i in range(self.worker_list.count()):
                    item = self.worker_list.item(i)
                    worker = item.data(Qt.ItemDataRole.UserRole)
                    if worker and worker.get('worker_id') == created_id:
                        self.worker_list.setCurrentItem(item)
                        logger.info(f"Auto-selected newly created worker: {created_id}")
                        break

    def get_selected_worker(self):
        """Get the selected worker profile."""
        return self.selected_worker


class NewWorkerDialog(QDialog):
    """
    Dialog для створення нового працівника.
    """

    def __init__(self, worker_manager: WorkerManager, parent=None):
        super().__init__(parent)
        self.worker_manager = worker_manager
        self.created_worker_id = None

        self.setWindowTitle("Create New Worker")
        self.setMinimumWidth(450)
        self.setModal(True)

        self._setup_ui()

    def _setup_ui(self):
        """Setup UI components."""
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("<h3>Create New Worker Profile</h3>")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Form
        form_layout = QFormLayout()

        self.id_input = QLineEdit()
        self.id_input.setPlaceholderText("e.g., 001, 002, 003")
        form_layout.addRow("Worker ID*:", self.id_input)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., Петро Іванов")
        form_layout.addRow("Full Name*:", self.name_input)

        self.role_input = QLineEdit()
        self.role_input.setText("Packer")
        form_layout.addRow("Role:", self.role_input)

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Optional")
        form_layout.addRow("Email:", self.email_input)

        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("Optional")
        form_layout.addRow("Phone:", self.phone_input)

        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("Optional notes")
        form_layout.addRow("Notes:", self.notes_input)

        layout.addLayout(form_layout)

        # Info label
        info = QLabel("* Required fields")
        info.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(info)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.create_btn = QPushButton("Create")
        self.create_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 24px;
                font-size: 14px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.create_btn.clicked.connect(self._create_worker)
        self.create_btn.setDefault(True)
        button_layout.addWidget(self.create_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 24px;
                font-size: 14px;
                border: 1px solid #ccc;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #f0f0f0;
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

    def _create_worker(self):
        """Validate and create new worker."""
        worker_id = self.id_input.text().strip()
        worker_name = self.name_input.text().strip()

        # Validation
        if not worker_id:
            QMessageBox.warning(self, "Validation Error", "Worker ID is required")
            self.id_input.setFocus()
            return

        if not worker_name:
            QMessageBox.warning(self, "Validation Error", "Worker name is required")
            self.name_input.setFocus()
            return

        # Check if worker already exists
        if self.worker_manager.worker_exists(worker_id):
            QMessageBox.warning(
                self,
                "Worker Exists",
                f"Worker with ID '{worker_id}' already exists.\n"
                f"Please use a different ID."
            )
            self.id_input.setFocus()
            self.id_input.selectAll()
            return

        # Create worker profile
        try:
            # Prepare optional fields
            kwargs = {}
            if self.role_input.text().strip():
                kwargs['role'] = self.role_input.text().strip()
            if self.email_input.text().strip():
                kwargs['email'] = self.email_input.text().strip()
            if self.phone_input.text().strip():
                kwargs['phone'] = self.phone_input.text().strip()
            if self.notes_input.text().strip():
                kwargs['notes'] = self.notes_input.text().strip()

            # Create worker
            success = self.worker_manager.create_worker_profile(
                worker_id=worker_id,
                name=worker_name,
                **kwargs
            )

            if success:
                self.created_worker_id = worker_id
                QMessageBox.information(
                    self,
                    "Success",
                    f"Worker '{worker_name}' (ID: {worker_id}) created successfully!"
                )
                logger.info(f"Created new worker: {worker_name} ({worker_id})")
                self.accept()
            else:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to create worker profile.\n"
                    f"Worker may already exist or there was a file system error."
                )

        except Exception as e:
            logger.error(f"Error creating worker profile: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to create worker profile:\n\n{e}\n\n"
                f"Check logs for details."
            )
