# Packer's Assistant

## Purpose

Packer's Assistant is a desktop application designed to streamline the order fulfillment process for small to medium-sized warehouses. It helps packers efficiently process orders from an Excel-based packing list, generate corresponding barcodes for printing on thermal labels, and track their progress in real-time, minimizing errors and increasing productivity.

## Core Features

- **Session-Based Workflow:** All work is organized into sessions. A session begins when a packing list is loaded and ends when the user manually closes it, ensuring that all related files are neatly organized.
- **Excel Packing List Import:** Easily load your daily orders from a standard `.xlsx` file.
- **Dynamic Column Mapping:** The application does not require a fixed column structure for the input Excel file. On first load, it prompts the user to map the required fields (`Order_Number`, `SKU`, `Product_Name`, `Quantity`) to the corresponding columns in their file.
- **Custom Barcode Generation:** Automatically generates Code-128 barcodes for each unique order. The barcodes are:
    - Sized to fit a 65mm x 35mm thermal label at 203 DPI.
    - Include the full order number rendered as text below the barcode image using the standard Arial font for maximum compatibility.
- **Real-Time Order Tracking:** The main window displays a table of all orders from the packing list, showing the real-time status of each (`New`, `In Progress`, `Completed`). Completed orders are highlighted in green.
- **Interactive Packer Mode:** A dedicated UI for the packing process.
    - **Scanner-First Approach:** Designed to be used with a hardware barcode scanner for fast input.
    - **Manual Confirmation:** Each item in an order has a "Confirm Manually" button, allowing packers to proceed even if a barcode is damaged or unreadable.
- **Session Artifacts:** At the end of a session, the application creates a dedicated, timestamped folder (e.g., `OrdersFulfillment_YYYY-MM-DD_1`). This folder contains:
    - All barcode images generated during the session.
    - A new `_completed.xlsx` Excel file, which is a copy of the original packing list with two new columns: `Status` and `Completed At`. Rows for completed orders are highlighted in green.

## Workflow

1.  **Launch the Application:** Run the `main.py` script.
2.  **Start a Session:** Click the "Start Session" button. A file dialog will open.
3.  **Load Packing List:** Select the `.xlsx` packing list you want to process.
4.  **Map Columns (If Necessary):** If this is the first time using a file with this specific column structure, a "Column Mapping" dialog will appear. For each required field on the left, select the corresponding column name from your file in the dropdown list on the right. The application will remember these mappings for subsequent files with the same structure.
5.  **Process and Review:** The main window will now display a summary of all orders. At this point, barcodes have been generated in the session folder.
6.  **Print Barcodes:** Click the "Print Barcodes" button. A dialog will appear showing all the generated barcodes. Click "Print" and select your thermal printer.
7.  **Enter Packer Mode:** Click the "Switch to Packer Mode" button.
8.  **Pack an Order:**
    - Scan the barcode of the order you want to pack. The items for that order will appear in the table.
    - Scan the barcode of each individual product/SKU to mark it as packed.
    - If a product's barcode is unreadable, click the "Confirm Manually" button for that item's row.
9.  **Complete Order:** Once all items in an order are packed, a success message will appear, and the screen will clear after 3 seconds, ready for the next order. The main window's table will update the order's status to "Completed" and highlight the row in green.
10. **End Session:** Once all work is done, click the "End Session" button in the main window. This will save the final, updated Excel report and close the session. The application is now ready to start a new session.

## Technical Setup

This is a Python application built with the PySide6 GUI framework.

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
