"""Overview Tab - Session metadata and summary"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLabel,
    QGroupBox
)
from PySide6.QtCore import Qt

from datetime import datetime


class OverviewTab(QWidget):
    """Tab showing session overview and metadata"""

    def __init__(self, details: dict, parent=None):
        """
        Initialize Overview Tab.

        Args:
            details: Dict with session details from SessionHistoryManager
            parent: Parent widget
        """
        super().__init__(parent)

        self.details = details
        self._init_ui()

    def _init_ui(self):
        """Initialize UI."""
        layout = QVBoxLayout(self)

        # Session Info Group
        session_group = QGroupBox("Session Information")
        session_form = QFormLayout()

        record = self.details.get('record')

        if record:
            session_form.addRow("Session ID:", QLabel(record.session_id))
            session_form.addRow("Client:", QLabel(f"CLIENT_{record.client_id}"))

            # Packing list
            if record.packing_list_path:
                from pathlib import Path
                list_name = Path(record.packing_list_path).stem
            else:
                list_name = "Unknown"
            session_form.addRow("Packing List:", QLabel(list_name))

            # Worker
            worker = record.worker_id or "Unknown"
            session_form.addRow("Worker:", QLabel(worker))

            # PC
            pc = record.pc_name or "Unknown"
            session_form.addRow("PC:", QLabel(pc))

        session_group.setLayout(session_form)
        layout.addWidget(session_group)

        # Timing Group
        timing_group = QGroupBox("Timing")
        timing_form = QFormLayout()

        if record:
            # Started
            started = self._format_datetime(record.start_time)
            timing_form.addRow("Started:", QLabel(started))

            # Completed
            completed = self._format_datetime(record.end_time)
            timing_form.addRow("Completed:", QLabel(completed))

            # Duration
            if record.duration_seconds:
                duration = self._format_duration(record.duration_seconds)
                timing_form.addRow("Duration:", QLabel(duration))

        timing_group.setLayout(timing_form)
        layout.addWidget(timing_group)

        # Progress Group
        progress_group = QGroupBox("Progress")
        progress_form = QFormLayout()

        if record:
            progress_form.addRow(
                "Orders:",
                QLabel(f"{record.completed_orders} / {record.total_orders}")
            )
            progress_form.addRow(
                "Items:",
                QLabel(str(record.total_items_packed))
            )

            # Status
            if record.completed_orders == record.total_orders:
                status = "✅ Complete"
            else:
                status = f"⚠️ Incomplete ({record.in_progress_orders} in progress)"
            progress_form.addRow("Status:", QLabel(status))

        progress_group.setLayout(progress_form)
        layout.addWidget(progress_group)

        layout.addStretch()

    def _format_datetime(self, dt) -> str:
        """Format datetime for display."""
        if not dt:
            return "N/A"

        if isinstance(dt, datetime):
            return dt.strftime("%Y-%m-%d %H:%M:%S")

        return str(dt)

    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format."""
        if not seconds:
            return "N/A"

        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"
