import os
import json

class StatisticsManager:
    def __init__(self):
        config_dir = os.path.expanduser("~/.packers_assistant")
        if not os.path.exists(config_dir):
            try:
                os.makedirs(config_dir)
            except OSError as e:
                print(f"Warning: Could not create config directory: {e}")

        self.stats_file = os.path.join(config_dir, "stats.json")
        self.stats = {
            "processed_order_ids": [],
            "completed_order_ids": [],
        }
        self.load_stats()

    def load_stats(self):
        if os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, 'r') as f:
                    loaded_stats = json.load(f)
                    if isinstance(loaded_stats, dict) and "processed_order_ids" in loaded_stats:
                        # For backward compatibility, add completed_order_ids if it's missing
                        if "completed_order_ids" not in loaded_stats:
                            loaded_stats["completed_order_ids"] = []
                        self.stats.update(loaded_stats)
                    else:
                        print("Warning: Statistics file format is outdated. Starting fresh.")
            except (json.JSONDecodeError, IOError, TypeError):
                print(f"Warning: Could not load or parse statistics file at {self.stats_file}. Starting fresh.")

    def save_stats(self):
        try:
            with open(self.stats_file, 'w') as f:
                json.dump(self.stats, f, indent=4)
        except IOError as e:
            print(f"Warning: Could not save statistics file to {self.stats_file}. Reason: {e}")

    def record_new_orders(self, order_ids: list):
        """Records new orders, ensuring uniqueness."""
        processed_set = set(self.stats["processed_order_ids"])
        new_orders = [oid for oid in order_ids if oid not in processed_set]

        if new_orders:
            self.stats["processed_order_ids"].extend(new_orders)
            self.save_stats()

    def record_order_completion(self, order_id):
        """Records a completed order, ensuring uniqueness."""
        if order_id not in self.stats["completed_order_ids"]:
            self.stats["completed_order_ids"].append(order_id)
            self.save_stats()

    def get_display_stats(self):
        """Returns a dictionary of formatted stats ready for display."""
        total_orders = len(self.stats["processed_order_ids"])
        completed_orders = len(self.stats["completed_order_ids"])

        return {
            "Total Unique Orders": total_orders,
            "Total Completed": completed_orders,
        }
