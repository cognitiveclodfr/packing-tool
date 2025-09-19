import os
import json
from datetime import timedelta

class StatisticsManager:
    def __init__(self):
        # Ensure the config directory exists
        config_dir = os.path.expanduser("~/.packers_assistant")
        if not os.path.exists(config_dir):
            try:
                os.makedirs(config_dir)
            except OSError as e:
                print(f"Warning: Could not create config directory: {e}")

        self.stats_file = os.path.join(config_dir, "stats.json")
        self.stats = {
            "total_orders_loaded": 0,
            "total_orders_completed": 0,
            "total_items_packed": 0,
            "total_packing_time_seconds": 0,
        }
        self.load_stats()

    def load_stats(self):
        if os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, 'r') as f:
                    loaded_stats = json.load(f)
                    # Simple validation to ensure keys match
                    if all(key in loaded_stats for key in self.stats):
                        self.stats.update(loaded_stats)
                    else:
                        print(f"Warning: Statistics file format is outdated. Starting fresh.")
            except (json.JSONDecodeError, IOError, TypeError):
                print(f"Warning: Could not load or parse statistics file at {self.stats_file}. Starting fresh.")

    def save_stats(self):
        try:
            with open(self.stats_file, 'w') as f:
                json.dump(self.stats, f, indent=4)
        except IOError as e:
            print(f"Warning: Could not save statistics file to {self.stats_file}. Reason: {e}")

    def record_new_session(self, order_count):
        self.stats["total_orders_loaded"] += order_count
        self.save_stats()

    def record_order_completion(self, item_count, duration_seconds):
        self.stats["total_orders_completed"] += 1
        self.stats["total_items_packed"] += item_count
        self.stats["total_packing_time_seconds"] += duration_seconds
        self.save_stats()

    def get_display_stats(self):
        """Returns a dictionary of formatted stats ready for display."""

        # Completion Percentage
        if self.stats["total_orders_loaded"] > 0:
            completion_percentage = (self.stats["total_orders_completed"] / self.stats["total_orders_loaded"]) * 100
        else:
            completion_percentage = 0

        # Packing Speed (units per hour)
        if self.stats["total_packing_time_seconds"] > 0:
            hours = self.stats["total_packing_time_seconds"] / 3600
            packing_speed_uph = self.stats["total_items_packed"] / hours
        else:
            packing_speed_uph = 0

        return {
            "Total Orders": self.stats["total_orders_loaded"],
            "Completed": f"{self.stats['total_orders_completed']} ({completion_percentage:.1f}%)",
            "Packing Speed": f"{packing_speed_uph:.1f} units/hr"
        }
