# Packer's Assistant

## Purpose

Packer's Assistant is a desktop application designed to streamline the order fulfillment process for small to medium-sized warehouses. It helps packers efficiently process orders from an Excel-based packing list, track their progress in real-time, and generate corresponding barcodes. Its key design goals are to minimize errors, increase productivity, and provide resilience against unexpected interruptions.

## Core Features

- **Robust Session Management:**
    - **Session-Based Workflow:** All work is organized into sessions. A session begins when a packing list is loaded and ends when the user manually closes it, ensuring that all related files are neatly organized in a timestamped folder (e.g., `OrdersFulfillment_YYYY-MM-DD_1`).
    - **Crash Recovery:** The application saves packing progress after every single scan. If the application closes unexpectedly, it will detect the incomplete session on the next startup and prompt the user to restore it, preventing any loss of work.

- **Intelligent Excel Import:**
    - **Easy Import:** Easily load your daily orders from a standard `.xlsx` file.
    - **Dynamic Column Mapping:** The application does not require a fixed column structure. On first load, it prompts the user to map the required fields (`Order_Number`, `SKU`, `Product_Name`, `Quantity`) to the corresponding columns in their file. These mappings are saved for future use with files of the same structure.
    - **Automatic Data Display:** The main order table automatically detects and displays all additional, non-required columns from the source Excel file, ensuring all relevant order information is visible.

- **Informative Real-Time UI:**
    - **Live Order Tracking:** The main window displays a table of all orders, showing the status of each (`New`, `In Progress`, `Completed`).
    - **Real-Time Packing Progress:** A "Packing Progress" column (e.g., "5/8") updates instantly after every scan, providing immediate feedback.
    - **Auto-Resizing Columns:** All tables automatically resize their columns to fit the content, ensuring data is never truncated.

- **Interactive Packer Mode:**
    - **Scanner-First Approach:** Designed to be used with a hardware barcode scanner for fast input.
    - **Visual Progress Restore:** When opening a partially packed order, the UI clearly shows which items have already been scanned and their packed quantities.
    - **Manual Confirmation:** Each item has a "Confirm Manually" button, allowing packers to proceed even if a barcode is damaged or unreadable.

- **Barcode Generation & Printing:**
    - **Custom Barcode Generation:** Automatically generates Code-128 barcodes for each unique order, sized for 65mm x 35mm thermal labels.
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

### Backend Architecture

The application's backend is designed to be modular and stateful, separating core logic from the user interface.

-   **`src/packer_logic.py` - `PackerLogic` class:**
    - This is the brain of the application. It inherits from `QObject` to emit signals for UI updates.
    - **Responsibilities:**
        - **Data Processing:** Uses **pandas** to load and parse data from `.xlsx` files.
        - **Barcode Generation:** Uses **python-barcode** and **Pillow** to create Code-128 barcodes in memory and save them as PNG files.
        - **Packing State Machine:** Manages the state of the currently active order (`current_order_state`), tracking the required vs. packed count for each SKU.
        - **State Persistence:** Manages the `packing_state.json` file. It saves the entire session's progress after every scan and loads it when a session is initialized.

-   **`src/session_manager.py` - `SessionManager` class:**
    - Handles the lifecycle of a packing session.
    - **Responsibilities:**
        - Creates unique, timestamped directories for each session.
        - Manages a `session_info.json` file within the session directory. This file's existence signals that a session is active or was left incomplete, which is key to the restoration feature.
        - Handles the cleanup of session files upon graceful termination.

-   **`src/main.py` - `MainWindow` class:**
    - The main application window and orchestrator.
    - **Responsibilities:**
        - Initializes the UI and all backend components.
        - Connects UI events (button clicks) to backend logic.
        - Implements the session restoration prompt at startup.
        - Listens for signals from `PackerLogic` (e.g., `item_packed`) to update the UI in real-time without tightly coupling the components.

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
