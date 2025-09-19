from PySide6.QtCore import QSortFilterProxyModel, Qt
import pandas as pd

class CustomFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._processed_df = None
        self.search_term = ""

    def set_processed_df(self, df: pd.DataFrame):
        self._processed_df = df

    def setFilterFixedString(self, text):
        """
        Overrides the default method to use our custom logic.
        The name is set to match the QSortFilterProxyModel API.
        """
        self.search_term = text.lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        if not self.search_term:
            return True

        source_model = self.sourceModel()
        if source_model is None:
            return True

        # Get column indices from the source model
        order_col = source_model.get_column_index('Order_Number')
        status_col = source_model.get_column_index('Status')

        if order_col == -1 or status_col == -1:
            return True

        # Get data for the current row
        order_number_index = source_model.index(source_row, order_col, source_parent)
        status_index = source_model.index(source_row, status_col, source_parent)

        order_number_str = source_model.data(order_number_index, Qt.DisplayRole).lower()
        status_str = source_model.data(status_index, Qt.DisplayRole).lower()

        # 1. Check Order Number and Status
        if self.search_term in order_number_str or self.search_term in status_str:
            return True

        # 2. Check SKU from the detailed processed_df
        if self._processed_df is not None:
            current_order_number = source_model.data(order_number_index, Qt.DisplayRole)

            # This can be slow on very large datasets, but should be acceptable for typical packing lists.
            # It finds all rows in the detailed df matching the order number.
            order_items = self._processed_df[self._processed_df['Order_Number'] == current_order_number]

            # It then checks if the search term is present in any of the SKUs for that order.
            if order_items['SKU'].str.lower().str.contains(self.search_term, na=False).any():
                return True

        return False
