# Packer's Assistant

## Purpose

Packer's Assistant is a desktop application designed to streamline the order fulfillment process for small to medium-sized warehouses. It helps packers efficiently process orders from an Excel-based packing list, track their progress in real-time, and generate corresponding barcodes. Its key design goals are to minimize errors, increase productivity, and provide resilience against unexpected interruptions.

## Core Features

- **Modern UI/UX:**
    - **Dark Theme:** The application features a clean, modern dark theme for comfortable use in various lighting conditions.
    - **Persistent Statistics Dashboard:** A dashboard at the top of the main window displays key performance indicators that persist across all sessions, including the total number of unique orders processed and the total number of orders completed.

- **Robust Session Management:**
    - **Session-Based Workflow:** All work is organized into sessions. A session begins when a packing list is loaded and ends when the user manually closes it, ensuring that all related files are neatly organized in a timestamped folder (e.g., `OrdersFulfillment_YYYY-MM-DD_1`).
    - **Crash Recovery:** The application saves packing progress after every single scan. If the application closes unexpectedly, it will detect the incomplete session on the next startup and prompt the user to restore it, preventing any loss of work.

- **Intelligent Excel Import:**
    - **Easy Import:** Easily load your daily orders from a standard `.xlsx` file.
    - **Dynamic Column Mapping:** The application does not require a fixed column structure. On first load, it prompts the user to map the required fields (`Order_Number`, `SKU`, `Product_Name`, `Quantity`, and `Courier`) to the corresponding columns in their file.
    - **Automatic Data Display:** The main order table automatically detects and displays all additional, non-required columns from the source Excel file.

- **Informative Real-Time UI:**
    - **Live Order Tracking:** The main window displays a table of all orders, showing the status of each (`New`, `In Progress`, `Completed`).
    - **Search and Filter:** A powerful search bar allows for instant filtering of the orders table by Order Number, SKU, or Status.
    - **Real-Time Packing Progress:** A "Packing Progress" column (e.g., "5/8") updates instantly after every scan.

- **Interactive Packer Mode:**
    - **Enhanced Visual Feedback:** The UI provides clear, non-disruptive feedback by flashing the border of the item table—green for a successful scan and red for an error.
    - **Scan History:** A history panel displays a running list of all scanned order barcodes for easy reference during a session.
    - **Raw Scan Display:** A technical display shows the raw, unfiltered text from the last scanned barcode, aiding in troubleshooting.
    - **Visual Progress Restore:** When opening a partially packed order, the UI clearly shows which items have already been scanned.

- **Barcode Generation & Printing:**
    - **Upgraded Label Layout:** Automatically generates Code-128 barcodes for each unique order. The printable label now includes the **Order Number**, the **Courier** name, and the barcode itself, all centered for a professional look.
    - **Integrated Printing:** A simple dialog allows for printing all generated barcodes to a selected thermal printer.


## Workflow

1.  **Launch the Application:** Run the `main.py` script.
2.  **Restore Session (If Prompted):** If the application was not closed properly, a dialog will ask if you want to restore the last session. Click "Yes" to continue where you left off.
3.  **Start a Session:** Click the "Start Session" button and select the `.xlsx` packing list you want to process.
4.  **Map Columns (If Necessary):** On first use of a new file structure, map the required columns.
5.  **Process and Review:** The main window will now display a summary of all orders, including any extra data from your file and the current packing progress.
6.  **Print Barcodes:** Click "Print Barcodes" to open the printing dialog.
7.  **Enter Packer Mode:** Click "Switch to Packer Mode".
8.  **Pack an Order:**
    - Scan an order's barcode. If it's a partially packed order, you will see your previous progress.
    - Scan each product's SKU barcode to mark it as packed.
9.  **Complete Order:** Once all items are packed, a success message appears. The main table updates the order's status to "Completed".
10. **End Session:** When all work is done, click "End Session". This closes the session gracefully and saves the final `_completed.xlsx` report.

## Technical Implementation

This is a Python application built with the **PySide6** GUI framework.

### Architecture

The application is designed to be modular and stateful, separating core business logic from the user interface. Key components include:

-   **`src/main.py` - `MainWindow`:** The main application window and central orchestrator. It initializes all UI components and backend managers, connects UI events to logic, and manages the application's different views.

-   **`src/packer_logic.py` - `PackerLogic`:** The core engine for all data processing and business logic. It handles loading Excel files, generating barcodes, managing the packing state machine, and persisting session progress after every scan.

-   **`src/session_manager.py` - `SessionManager`:** Manages the lifecycle of a packing session, including creating unique, timestamped session directories and handling the logic for the crash recovery feature.

-   **`src/statistics_manager.py` - `StatisticsManager`:** Handles persistent, cross-session application statistics, tracking metrics like total unique orders processed and completed over time.

-   **`src/packer_mode_widget.py` - `PackerModeWidget`:** The dedicated UI widget for the "Packer Mode" screen. It displays the items for the active order and captures barcode scanner input.

-   **`src/order_table_model.py` - `OrderTableModel`:** A `QAbstractTableModel` that serves as the bridge between the pandas DataFrame of order data and the `QTableView` in the UI.

-   **`src/custom_filter_proxy_model.py` - `CustomFilterProxyModel`:** A `QSortFilterProxyModel` subclass that provides advanced, multi-column live search functionality for the main orders table (by Order Number, Status, and SKU).

-   **`src/mapping_dialog.py` - `ColumnMappingDialog`:** A dialog that allows users to map the columns in their Excel file to the required data fields if the headers don't match the standard format.

-   **`src/print_dialog.py` - `PrintDialog`:** A dialog for previewing all generated barcodes and sending them to a printer.

-   **`src/styles.qss`:** A global Qt Stylesheet (QSS) file that defines the application's modern dark theme.

### State Management and Crash Recovery

The application's resilience is built around a JSON-based state file.

-   **`packing_state.json`:**
    - This file is stored in the root of the current session's directory.
    - It maintains a dictionary with two main keys:
        - `"in_progress"`: A dictionary where each key is an `Order_Number` and the value contains the detailed packing state for that order (required/packed counts for each SKU).
        - `"completed_orders"`: A simple list of `Order_Number` strings for all orders that have been fully packed during the session.
    - The file is overwritten after **every successful SKU scan**, ensuring minimal data loss.
    - When a session is restored, `PackerLogic` loads this file into memory. `MainWindow` then uses this restored state to rebuild the UI, showing which orders are in progress, which are completed, and what the packing progress is for each.

## Development Setup

### Prerequisites
- Python 3.8+
- For Linux environments, additional system libraries may be required:
  ```bash
  sudo apt-get install -y libpulse0 libxcb-cursor0
  ```

### Installation & Running

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd <repository_directory>
    ```
2.  **Install Python dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Run the application:**
    ```bash
    python src/main.py
    ```

### Testing
The project uses Python's built-in `unittest` framework for backend testing. To run the tests:
```bash
python -m unittest tests/test_packer_logic.py
```
