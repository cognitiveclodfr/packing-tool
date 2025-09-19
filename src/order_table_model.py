from PySide6.QtCore import QAbstractTableModel, Qt
from PySide6.QtGui import QColor
import pandas as pd

class OrderTableModel(QAbstractTableModel):
    def __init__(self, data: pd.DataFrame, parent=None):
        super().__init__(parent)
        self._data = data

    def rowCount(self, parent=None):
        return self._data.shape[0]

    def columnCount(self, parent=None):
        return self._data.shape[1]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()

        # For displaying text
        if role == Qt.DisplayRole:
            return str(self._data.iloc[row, col])

        # For background color
        if role == Qt.BackgroundRole:
            status_col_index = self._data.columns.get_loc('Status')
            if self._data.iloc[row, status_col_index] == 'Completed':
                return QColor('lightgreen')

        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return str(self._data.columns[section])
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.EditRole:
            row = index.row()
            col = index.column()
            self._data.iloc[row, col] = value
            self.dataChanged.emit(index, index)
            return True
        return False

    def flags(self, index):
        return super().flags(index) | Qt.ItemIsEditable

    def get_column_index(self, column_name):
        try:
            return self._data.columns.get_loc(column_name)
        except KeyError:
            return -1
