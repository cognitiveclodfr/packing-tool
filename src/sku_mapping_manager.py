import os
import json
from typing import Dict

class SKUMappingManager:
    """
    Manages the persistence of the Barcode-to-SKU mapping.

    This class handles loading the mapping from a JSON file, saving it back,
    and providing access to the data. It ensures that the mapping persists
    across application sessions. The data is stored in a dedicated
    configuration directory in the user's home folder.
    """

    def __init__(self):
        """
        Initializes the manager, defines paths, and loads the initial map.
        """
        self.config_dir = os.path.join(os.path.expanduser("~"), ".packers_assistant")
        self.map_file_path = os.path.join(self.config_dir, "sku_map.json")
        os.makedirs(self.config_dir, exist_ok=True)
        self.sku_map = self.load_map()

    def load_map(self) -> Dict[str, str]:
        """
        Loads the SKU map from the JSON file.

        If the file does not exist or contains invalid JSON, it returns an
        empty dictionary.

        Returns:
            Dict[str, str]: The loaded Barcode-to-SKU mapping.
        """
        if not os.path.exists(self.map_file_path):
            return {}
        try:
            with open(self.map_file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    def save_map(self, sku_map: Dict[str, str]):
        """
        Saves the provided SKU map to the JSON file and updates the in-memory map.

        Args:
            sku_map (Dict[str, str]): The mapping to save.
        """
        self.sku_map = sku_map
        try:
            with open(self.map_file_path, 'w', encoding='utf-8') as f:
                json.dump(self.sku_map, f, indent=4, ensure_ascii=False)
        except IOError as e:
            print(f"Error: Could not save SKU map to {self.map_file_path}. Reason: {e}")

    def get_map(self) -> Dict[str, str]:
        """
        Returns the current in-memory version of the SKU map.

        Returns:
            Dict[str, str]: The current SKU mapping.
        """
        return self.sku_map