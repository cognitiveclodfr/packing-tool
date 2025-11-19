"""
Worker Selection Dialog

Simple dialog for selecting worker profile at app startup.
No authentication - trust-based system.
"""

import logging
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QScrollArea, QWidget, QFrame, QMessageBox,
    QInputDialog
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from shared.worker_manager import WorkerManager, WorkerProfile

logger = logging.getLogger(__name__)


class WorkerCard(QFrame):
    """Clickable card for worker profile"""

    clicked = Signal(str)  # Emits worker_id

    def __init__(self, worker: WorkerProfile, parent=None):
        super().__init__(parent)
        self.worker = worker
        self._init_ui()

    def _init_ui(self):
        """Initialize UI"""
        self.setFrameStyle(QFrame.Box | QFrame.Raised)
        self.setLineWidth(2)
        self.setCursor(Qt.PointingHandCursor)

        # Hover effect
        self.setStyleSheet("""
            WorkerCard {
                background-color: #2b2b2b;
                border: 2px solid #444;
                border-radius: 8px;
                padding: 15px;
            }
            WorkerCard:hover {
                background-color: #363636;
                border: 2px solid #0d7377;
            }
        """)

        layout = QVBoxLayout(self)

        # Worker name (large)
        name_label = QLabel(f"👤 {self.worker.name}")
        name_font = QFont()
        name_font.setPointSize(16)
        name_font.setBold(True)
        name_label.setFont(name_font)
        layout.addWidget(name_label)

        # Stats
        stats_text = self._format_stats()
        stats_label = QLabel(stats_text)
        stats_label.setStyleSheet("color: #aaa;")
        layout.addWidget(stats_label)

        # Last active
        if self.worker.last_active:
            from datetime import datetime
            last_active = datetime.fromisoformat(self.worker.last_active)
            time_str = self._format_time_ago(last_active)
            active_label = QLabel(f"Last active: {time_str}")
            active_label.setStyleSheet("color: #888; font-size: 11px;")
            layout.addWidget(active_label)

    def _format_stats(self) -> str:
        """Format statistics string"""
        sessions = self.worker.total_sessions
        orders = self.worker.total_orders

        # Format orders (e.g., 2500 → 2.5K)
        if orders >= 1000:
            orders_str = f"{orders/1000:.1f}K"
        else:
            orders_str = str(orders)

        return f"Sessions: {sessions} | Orders: {orders_str}"

    def _format_time_ago(self, dt) -> str:
        """Format time ago string"""
        from datetime import datetime, timedelta

        now = datetime.now()
        delta = now - dt

        if delta < timedelta(minutes=1):
            return "Just now"
        elif delta < timedelta(hours=1):
            minutes = int(delta.total_seconds() / 60)
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        elif delta < timedelta(days=1):
            hours = int(delta.total_seconds() / 3600)
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif delta < timedelta(days=2):
            return "Yesterday"
        elif delta < timedelta(days=7):
            days = delta.days
            return f"{days} days ago"
        else:
            return dt.strftime("%b %d, %Y")

    def mousePressEvent(self, event):
        """Handle click"""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.worker.id)


class WorkerSelectionDialog(QDialog):
    """Worker selection dialog at app startup"""

    def __init__(self, worker_manager: WorkerManager, parent=None):
        super().__init__(parent)
        self.worker_manager = worker_manager
        self.selected_worker_id = None

        self.setWindowTitle("Select Your Profile")
        self.setModal(True)
        self.setMinimumSize(500, 400)

        self._init_ui()
        self._load_workers()

    def _init_ui(self):
        """Initialize UI"""
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("👤 Select Your Profile")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("Choose your worker profile to continue")
        subtitle.setStyleSheet("color: #888; margin-bottom: 20px;")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        # Scroll area for worker cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none;")

        self.cards_widget = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_widget)
        self.cards_layout.setSpacing(10)

        scroll.setWidget(self.cards_widget)
        layout.addWidget(scroll, stretch=1)

        # Create new worker button
        create_button = QPushButton("➕ Create New Worker")
        create_button.setStyleSheet("""
            QPushButton {
                background-color: #0d7377;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #14a085;
            }
        """)
        create_button.clicked.connect(self._create_new_worker)
        layout.addWidget(create_button)

    def _load_workers(self):
        """Load and display worker cards"""
        # Clear existing cards
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Get workers
        try:
            workers = self.worker_manager.get_all_workers()

            if not workers:
                # Show message if no workers
                msg = QLabel("No workers found. Create your first worker profile below.")
                msg.setStyleSheet("color: #888; padding: 20px;")
                msg.setAlignment(Qt.AlignCenter)
                self.cards_layout.addWidget(msg)
                return

            # Sort by last_active (most recent first)
            workers.sort(
                key=lambda w: w.last_active or "0000",
                reverse=True
            )

            # Create cards
            for worker in workers:
                card = WorkerCard(worker)
                card.clicked.connect(self._on_worker_selected)
                self.cards_layout.addWidget(card)

            # Add stretch at end
            self.cards_layout.addStretch()

        except Exception as e:
            logger.error(f"Failed to load workers: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load worker profiles:\n{str(e)}"
            )

    def _on_worker_selected(self, worker_id: str):
        """Handle worker selection

        Args:
            worker_id: Selected worker ID
        """
        logger.info(f"Worker selected: {worker_id}")
        self.selected_worker_id = worker_id
        self.accept()

    def _create_new_worker(self):
        """Create new worker profile"""
        # Ask for name
        name, ok = QInputDialog.getText(
            self,
            "Create Worker",
            "Enter worker name:",
            text=""
        )

        if not ok or not name:
            return

        try:
            # Create worker
            worker = self.worker_manager.create_worker(name)
            logger.info(f"Created new worker: {worker.id} ({worker.name})")

            # Reload workers
            self._load_workers()

            # Show success
            QMessageBox.information(
                self,
                "Success",
                f"Worker profile created: {worker.name}"
            )

        except ValueError as e:
            QMessageBox.warning(
                self,
                "Invalid Name",
                str(e)
            )
        except Exception as e:
            logger.error(f"Failed to create worker: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to create worker:\n{str(e)}"
            )

    def get_selected_worker_id(self) -> str:
        """Get selected worker ID

        Returns:
            str: Worker ID or None if dialog cancelled
        """
        return self.selected_worker_id
