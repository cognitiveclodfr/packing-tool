import os
import json
from typing import List, Dict, Any

class StatisticsManager:
    """
    Manages the persistent, cross-session statistics for the application.

    This class handles the loading, saving, and updating of application-wide
    statistics, such as the total number of unique orders processed and completed
    over the application's lifetime. The stats are stored in a JSON file in the
    user's home directory.

    Attributes:
        stats_file (str): The full path to the statistics JSON file.
        stats (Dict[str, List[str]]): A dictionary holding the loaded statistics,
                                      primarily lists of unique order IDs.
    """
    def __init__(self):
        """
        Initializes the StatisticsManager.

        This sets up the configuration directory and file path, and then
        immediately attempts to load any existing statistics from the file.
        """
        config_dir = os.path.expanduser("~/.packers_assistant")
        if not os.path.exists(config_dir):
            try:
                os.makedirs(config_dir)
            except OSError as e:
                print(f"Warning: Could not create config directory: {e}")

        self.stats_file = os.path.join(config_dir, "stats.json")
        self.stats: Dict[str, List[str]] = {
            "processed_order_ids": [],
            "completed_order_ids": [],
        }
        self.load_stats()

    def load_stats(self):
        """
        Loads statistics from the JSON file into memory.

        If the file doesn't exist or contains corrupted data, it gracefully
        resets to a default empty state. It also handles backward compatibility
        by adding new keys if they are missing from an older stats file.
        """
        if os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, 'r') as f:
                    loaded_stats = json.load(f)
                    if isinstance(loaded_stats, dict) and "processed_order_ids" in loaded_stats:
                        # For backward compatibility, add new keys if they are missing
                        if "completed_order_ids" not in loaded_stats:
                            loaded_stats["completed_order_ids"] = []
                        self.stats.update(loaded_stats)
                    else:
                        print("Warning: Statistics file format is outdated. Starting fresh.")
            except (json.JSONDecodeError, IOError, TypeError):
                print(f"Warning: Could not load or parse statistics file at {self.stats_file}. Starting fresh.")

    def save_stats(self):
        """Saves the current in-memory statistics to the JSON file."""
        try:
            with open(self.stats_file, 'w') as f:
                json.dump(self.stats, f, indent=4)
        except IOError as e:
            print(f"Warning: Could not save statistics file to {self.stats_file}. Reason: {e}")

    def record_new_orders(self, order_ids: List[str]):
        """
        Records a list of newly processed order IDs.

        It ensures that only unique order IDs are added to the persistent list,
        preventing duplicates if the same packing list is loaded multiple times.

        Args:
            order_ids (List[str]): A list of order IDs from a newly started session.
        """
        processed_set = set(self.stats["processed_order_ids"])
        new_orders = [oid for oid in order_ids if oid not in processed_set]

        if new_orders:
            self.stats["processed_order_ids"].extend(new_orders)
            self.save_stats()

    def record_order_completion(self, order_id: str):
        """
        Records a single completed order ID.

        It ensures the ID is not already in the list of completed orders
        before adding it and saving the stats.

        Args:
            order_id (str): The unique ID of the order that was completed.
        """
        if order_id not in self.stats["completed_order_ids"]:
            self.stats["completed_order_ids"].append(order_id)
            self.save_stats()

    def get_display_stats(self) -> Dict[str, Any]:
        """
        Returns a dictionary of formatted stats ready for display in the UI.

        Returns:
            Dict[str, Any]: A dictionary with human-readable keys and the
                            calculated total counts.
        """
        total_orders = len(self.stats["processed_order_ids"])
        completed_orders = len(self.stats["completed_order_ids"])

        return {
            "Total Unique Orders": total_orders,
            "Total Completed": completed_orders,
        }
