"""
Worker Selector Dialog - UI for selecting and creating worker profiles.

This module provides dialogs for:
- Selecting an existing worker profile
- Creating a new worker profile
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QFormLayout,
    QLineEdit, QTextEdit, QDialogButtonBox, QCheckBox
)
from PySide6.QtCore import Qt
from typing import Optional, Dict

from logger import get_logger
from worker_manager import WorkerManager

logger = get_logger(__name__)


class NewWorkerDialog(QDialog):
    """
    Dialog for creating a new worker profile.

    Provides a form with required and optional fields for worker information.
    """

    def __init__(self, worker_manager: WorkerManager, parent=None):
        """
        Initialize NewWorkerDialog.

        Args:
            worker_manager: WorkerManager instance for creating profiles
            parent: Parent widget
        """
        super().__init__(parent)
        self.worker_manager = worker_manager
        self.setWindowTitle("Create New Worker Profile")
        self.resize(500, 400)

        self._init_ui()

    def _init_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)

        # Header
        header_label = QLabel("<h2>Create New Worker Profile</h2>")
        layout.addWidget(header_label)

        # Form layout
        form_layout = QFormLayout()

        # Required fields
        self.worker_id_input = QLineEdit()
        self.worker_id_input.setPlaceholderText("e.g., 001, 002, 003")
        form_layout.addRow("Worker ID *:", self.worker_id_input)

        self.worker_name_input = QLineEdit()
        self.worker_name_input.setPlaceholderText("e.g., Петро Іванов")
        form_layout.addRow("Full Name *:", self.worker_name_input)

        # Optional fields
        self.role_input = QLineEdit()
        self.role_input.setPlaceholderText("e.g., Packer, Supervisor")
        form_layout.addRow("Role:", self.role_input)

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("e.g., worker@example.com")
        form_layout.addRow("Email:", self.email_input)

        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("e.g., +359123456789")
        form_layout.addRow("Phone:", self.phone_input)

        self.notes_input = QTextEdit()
        self.notes_input.setPlaceholderText("Additional notes (optional)")
        self.notes_input.setMaximumHeight(80)
        form_layout.addRow("Notes:", self.notes_input)

        self.active_checkbox = QCheckBox("Active")
        self.active_checkbox.setChecked(True)
        form_layout.addRow("Status:", self.active_checkbox)

        layout.addLayout(form_layout)

        # Required fields note
        note_label = QLabel("<i>* Required fields</i>")
        layout.addWidget(note_label)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_save(self):
        """Handle save button click."""
        # Validate required fields
        worker_id = self.worker_id_input.text().strip()
        worker_name = self.worker_name_input.text().strip()

        if not worker_id:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Worker ID is required!"
            )
            self.worker_id_input.setFocus()
            return

        if not worker_name:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Worker Name is required!"
            )
            self.worker_name_input.setFocus()
            return

        # Check if worker already exists
        if self.worker_manager.worker_exists(worker_id):
            QMessageBox.warning(
                self,
                "Worker Exists",
                f"Worker with ID '{worker_id}' already exists!\n"
                f"Please choose a different ID."
            )
            self.worker_id_input.setFocus()
            return

        # Collect optional fields
        kwargs = {}
        if self.role_input.text().strip():
            kwargs['role'] = self.role_input.text().strip()
        if self.email_input.text().strip():
            kwargs['email'] = self.email_input.text().strip()
        if self.phone_input.text().strip():
            kwargs['phone'] = self.phone_input.text().strip()
        if self.notes_input.toPlainText().strip():
            kwargs['notes'] = self.notes_input.toPlainText().strip()

        kwargs['active'] = self.active_checkbox.isChecked()

        # Create worker profile
        try:
            success = self.worker_manager.create_worker_profile(
                worker_id=worker_id,
                name=worker_name,
                **kwargs
            )

            if success:
                logger.info(f"Created new worker profile: {worker_id}")
                QMessageBox.information(
                    self,
                    "Success",
                    f"Worker profile created successfully!\n\n"
                    f"ID: {worker_id}\n"
                    f"Name: {worker_name}"
                )
                self.accept()
            else:
                QMessageBox.warning(
                    self,
                    "Creation Failed",
                    "Worker profile could not be created.\n"
                    "The worker may already exist."
                )

        except Exception as e:
            logger.error(f"Error creating worker profile: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to create worker profile:\n\n{str(e)}"
            )


class WorkerSelectorDialog(QDialog):
    """
    Dialog for selecting an existing worker or creating a new one.

    Displays a list of active workers and provides options to:
    - Select an existing worker
    - Create a new worker
    - View all workers (including inactive)
    """

    def __init__(self, worker_manager: WorkerManager, parent=None):
        """
        Initialize WorkerSelectorDialog.

        Args:
            worker_manager: WorkerManager instance
            parent: Parent widget
        """
        super().__init__(parent)
        self.worker_manager = worker_manager
        self.selected_worker = None
        self.show_inactive = False

        self.setWindowTitle("Select Worker")
        self.resize(500, 400)

        self._init_ui()
        self._load_workers()

    def _init_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)

        # Header
        header_label = QLabel("<h2>Select Worker</h2>")
        layout.addWidget(header_label)

        info_label = QLabel("Please select a worker to continue with packing:")
        layout.addWidget(info_label)

        # Show inactive checkbox
        self.show_inactive_checkbox = QCheckBox("Show inactive workers")
        self.show_inactive_checkbox.stateChanged.connect(self._on_filter_changed)
        layout.addWidget(self.show_inactive_checkbox)

        # Workers list
        self.workers_list = QListWidget()
        self.workers_list.itemDoubleClicked.connect(self._on_worker_double_clicked)
        layout.addWidget(self.workers_list)

        # Buttons
        buttons_layout = QHBoxLayout()

        self.new_worker_button = QPushButton("New Worker")
        self.new_worker_button.clicked.connect(self._on_new_worker)
        buttons_layout.addWidget(self.new_worker_button)

        buttons_layout.addStretch()

        self.select_button = QPushButton("Select")
        self.select_button.clicked.connect(self._on_select)
        self.select_button.setDefault(True)
        buttons_layout.addWidget(self.select_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        buttons_layout.addWidget(self.cancel_button)

        layout.addLayout(buttons_layout)

    def _load_workers(self):
        """Load workers list from WorkerManager."""
        self.workers_list.clear()

        workers = self.worker_manager.list_workers(
            active_only=not self.show_inactive
        )

        if not workers:
            # Add placeholder item
            item = QListWidgetItem("No workers found. Click 'New Worker' to create one.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.workers_list.addItem(item)
            self.select_button.setEnabled(False)
            return

        self.select_button.setEnabled(True)

        for worker in workers:
            worker_id = worker.get('worker_id', 'Unknown')
            worker_name = worker.get('name', 'Unknown')
            is_active = worker.get('active', True)

            # Format display text
            display_text = f"{worker_id} - {worker_name}"
            if not is_active:
                display_text += " (Inactive)"

            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, worker)

            # Gray out inactive workers
            if not is_active:
                item.setForeground(Qt.GlobalColor.gray)

            self.workers_list.addItem(item)

        # Select first item by default
        if self.workers_list.count() > 0:
            self.workers_list.setCurrentRow(0)

        logger.debug(f"Loaded {len(workers)} workers (show_inactive={self.show_inactive})")

    def _on_filter_changed(self, state):
        """Handle show inactive checkbox state change."""
        self.show_inactive = (state == Qt.CheckState.Checked.value)
        self._load_workers()

    def _on_new_worker(self):
        """Handle New Worker button click."""
        dialog = NewWorkerDialog(self.worker_manager, self)

        if dialog.exec():
            # Reload workers list
            self._load_workers()

    def _on_select(self):
        """Handle Select button click."""
        current_item = self.workers_list.currentItem()

        if not current_item:
            QMessageBox.warning(
                self,
                "No Selection",
                "Please select a worker from the list!"
            )
            return

        worker_data = current_item.data(Qt.ItemDataRole.UserRole)

        if not worker_data:
            QMessageBox.warning(
                self,
                "Invalid Selection",
                "Please select a valid worker!"
            )
            return

        self.selected_worker = worker_data
        logger.info(f"Selected worker: {worker_data.get('worker_id')} - {worker_data.get('name')}")
        self.accept()

    def _on_worker_double_clicked(self, item):
        """Handle double-click on worker item."""
        worker_data = item.data(Qt.ItemDataRole.UserRole)

        if worker_data:
            self.selected_worker = worker_data
            self.accept()

    def get_selected_worker(self) -> Optional[Dict]:
        """
        Get the selected worker profile.

        Returns:
            Dictionary with worker profile data, or None if no selection
        """
        return self.selected_worker
