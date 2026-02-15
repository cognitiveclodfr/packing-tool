"""
Unit tests for src/worker_selection_dialog.py — WorkerCard and WorkerSelectionDialog.

Uses pytest-qt (qtbot) and unittest.mock to isolate from the file system.

Tests cover:
- WorkerCard initialization and _format_stats()
- WorkerCard mousePressEvent → clicked signal emits worker_id
- WorkerSelectionDialog initialization
- _load_workers() — cards created for each worker
- _load_workers() with empty list — informational message shown
- _on_worker_selected() — selected_worker_id set, dialog accepted
- get_selected_worker_id() — returns stored worker_id
"""

import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

# Imports from src/ (added to sys.path by conftest.py)
from worker_selection_dialog import WorkerCard, WorkerSelectionDialog
from shared.worker_manager import WorkerProfile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_profile(worker_id: str = "worker_001", name: str = "Alice",
                 total_sessions: int = 5, total_orders: int = 120) -> WorkerProfile:
    """Create a minimal WorkerProfile for testing."""
    return WorkerProfile(
        id=worker_id,
        name=name,
        created_at="2025-01-01T10:00:00+00:00",
        total_sessions=total_sessions,
        total_orders=total_orders,
    )


def make_manager(workers=None):
    """Return a mocked WorkerManager."""
    manager = MagicMock()
    manager.get_all_workers.return_value = workers if workers is not None else []
    return manager


# ============================================================================
# WorkerCard
# ============================================================================

class TestWorkerCard:
    def test_card_created(self, qtbot):
        profile = make_profile()
        card = WorkerCard(profile)
        qtbot.addWidget(card)
        assert card is not None

    def test_format_stats_small_orders(self, qtbot):
        profile = make_profile(total_sessions=3, total_orders=50)
        card = WorkerCard(profile)
        qtbot.addWidget(card)
        stats = card._format_stats()
        assert "Sessions: 3" in stats
        assert "Orders: 50" in stats

    def test_format_stats_large_orders(self, qtbot):
        """Orders >= 1000 should be shown as e.g. 1.5K."""
        profile = make_profile(total_sessions=10, total_orders=1500)
        card = WorkerCard(profile)
        qtbot.addWidget(card)
        stats = card._format_stats()
        assert "1.5K" in stats

    def test_click_emits_worker_id(self, qtbot):
        profile = make_profile(worker_id="worker_007")
        card = WorkerCard(profile)
        qtbot.addWidget(card)

        received = []
        card.clicked.connect(received.append)

        # Simulate a left-mouse-button press
        QTest.mouseClick(card, Qt.LeftButton)

        assert received == ["worker_007"]


# ============================================================================
# WorkerSelectionDialog — initialization
# ============================================================================

class TestWorkerSelectionDialogInit:
    def test_dialog_creates(self, qtbot):
        manager = make_manager()
        dialog = WorkerSelectionDialog(manager)
        qtbot.addWidget(dialog)
        assert dialog is not None

    def test_window_title(self, qtbot):
        manager = make_manager()
        dialog = WorkerSelectionDialog(manager)
        qtbot.addWidget(dialog)
        assert "Profile" in dialog.windowTitle()

    def test_selected_worker_id_initially_none(self, qtbot):
        manager = make_manager()
        dialog = WorkerSelectionDialog(manager)
        qtbot.addWidget(dialog)
        assert dialog.selected_worker_id is None

    def test_get_selected_worker_id_initially_none(self, qtbot):
        manager = make_manager()
        dialog = WorkerSelectionDialog(manager)
        qtbot.addWidget(dialog)
        assert dialog.get_selected_worker_id() is None


# ============================================================================
# WorkerSelectionDialog — _load_workers
# ============================================================================

class TestLoadWorkers:
    def test_no_workers_shows_message(self, qtbot):
        manager = make_manager(workers=[])
        dialog = WorkerSelectionDialog(manager)
        qtbot.addWidget(dialog)

        # There should be a QLabel with informational text and no WorkerCards
        labels = dialog.cards_widget.findChildren(
            __import__("PySide6.QtWidgets", fromlist=["QLabel"]).QLabel
        )
        texts = [lbl.text() for lbl in labels]
        assert any("No workers" in t or "no worker" in t.lower() for t in texts)

    def test_worker_cards_created_for_each_worker(self, qtbot):
        workers = [make_profile("w001", "Alice"), make_profile("w002", "Bob")]
        manager = make_manager(workers=workers)
        dialog = WorkerSelectionDialog(manager)
        qtbot.addWidget(dialog)

        cards = dialog.cards_widget.findChildren(WorkerCard)
        assert len(cards) == 2

    def test_cards_are_sorted_by_last_active(self, qtbot):
        """Workers with more recent last_active appear first."""
        w_old = make_profile("w001", "Old Worker")
        w_old.last_active = "2025-01-01T10:00:00+00:00"
        w_new = make_profile("w002", "New Worker")
        w_new.last_active = "2025-12-01T10:00:00+00:00"

        manager = make_manager(workers=[w_old, w_new])
        dialog = WorkerSelectionDialog(manager)
        qtbot.addWidget(dialog)

        cards = dialog.cards_widget.findChildren(WorkerCard)
        # Most recent first
        assert cards[0].worker.id == "w002"
        assert cards[1].worker.id == "w001"


# ============================================================================
# WorkerSelectionDialog — _on_worker_selected
# ============================================================================

class TestOnWorkerSelected:
    def test_selecting_worker_sets_id(self, qtbot):
        workers = [make_profile("worker_42", "Charlie")]
        manager = make_manager(workers=workers)
        dialog = WorkerSelectionDialog(manager)
        qtbot.addWidget(dialog)

        # Directly call the slot
        dialog._on_worker_selected("worker_42")

        assert dialog.selected_worker_id == "worker_42"

    def test_selecting_worker_accepts_dialog(self, qtbot):
        manager = make_manager()
        dialog = WorkerSelectionDialog(manager)
        qtbot.addWidget(dialog)

        # Patch accept() to track calls
        dialog.accept = MagicMock()
        dialog._on_worker_selected("worker_99")

        dialog.accept.assert_called_once()

    def test_get_selected_worker_id_after_selection(self, qtbot):
        manager = make_manager()
        dialog = WorkerSelectionDialog(manager)
        qtbot.addWidget(dialog)

        dialog._on_worker_selected("worker_55")
        assert dialog.get_selected_worker_id() == "worker_55"


# ============================================================================
# WorkerSelectionDialog — _create_new_worker
# ============================================================================

class TestCreateNewWorker:
    def test_cancelled_input_does_nothing(self, qtbot):
        manager = make_manager()
        dialog = WorkerSelectionDialog(manager)
        qtbot.addWidget(dialog)

        with patch("worker_selection_dialog.QInputDialog.getText", return_value=("", False)):
            dialog._create_new_worker()

        manager.create_worker.assert_not_called()

    def test_empty_name_does_nothing(self, qtbot):
        manager = make_manager()
        dialog = WorkerSelectionDialog(manager)
        qtbot.addWidget(dialog)

        with patch("worker_selection_dialog.QInputDialog.getText", return_value=("", True)):
            dialog._create_new_worker()

        manager.create_worker.assert_not_called()

    def test_valid_name_calls_create_worker(self, qtbot):
        new_profile = make_profile("worker_new", "Dave")
        manager = make_manager()
        manager.create_worker.return_value = new_profile
        dialog = WorkerSelectionDialog(manager)
        qtbot.addWidget(dialog)

        with patch("worker_selection_dialog.QInputDialog.getText", return_value=("Dave", True)):
            with patch("worker_selection_dialog.QMessageBox.information"):
                dialog._create_new_worker()

        manager.create_worker.assert_called_once_with("Dave")

    def test_create_worker_reloads_list(self, qtbot):
        new_profile = make_profile("worker_new", "Dave")
        manager = make_manager()
        manager.create_worker.return_value = new_profile
        dialog = WorkerSelectionDialog(manager)
        qtbot.addWidget(dialog)

        with patch("worker_selection_dialog.QInputDialog.getText", return_value=("Dave", True)):
            with patch("worker_selection_dialog.QMessageBox.information"):
                dialog._create_new_worker()

        # get_all_workers called at least twice: once during init, once after creation
        assert manager.get_all_workers.call_count >= 2
