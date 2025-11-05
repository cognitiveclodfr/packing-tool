"""
Migration Script: 2Packing-tool -> 0UFulfilment

This script migrates data from the old 2Packing-tool structure to the new
unified 0UFulfilment architecture.

Usage:
    python migrate_to_0ufulfilment.py [--dry-run] [--client CLIENT_ID]

Options:
    --dry-run       Show what would be done without making changes
    --client        Migrate only specific client (e.g., M, A, R)
"""
import argparse
import json
import shutil
import sys
from pathlib import Path
from datetime import datetime


# Paths
OLD_BASE = Path(r"\\192.168.88.101\Z_GreenDelivery\WAREHOUSE\2Packing-tool")
NEW_BASE = Path(r"\\192.168.88.101\Z_GreenDelivery\WAREHOUSE\0UFulfilment")


def print_status(message, level="INFO"):
    """Print status message."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")


def check_paths():
    """Check if source and destination paths are accessible."""
    if not OLD_BASE.exists():
        print_status(f"ERROR: Source path not found: {OLD_BASE}", "ERROR")
        return False

    if not NEW_BASE.parent.exists():
        print_status(f"ERROR: Destination parent path not found: {NEW_BASE.parent}", "ERROR")
        return False

    return True


def create_directory_structure(dry_run=False):
    """Create the new 0UFulfilment directory structure."""
    print_status("Creating directory structure...")

    directories = [
        NEW_BASE / "Clients",
        NEW_BASE / "Sessions",
        NEW_BASE / "Workers",
        NEW_BASE / "Stats",
        NEW_BASE / "Logs" / "packing_tool",
    ]

    for directory in directories:
        if dry_run:
            print_status(f"[DRY-RUN] Would create: {directory}")
        else:
            directory.mkdir(parents=True, exist_ok=True)
            print_status(f"Created: {directory}")


def migrate_client(client_id, dry_run=False):
    """
    Migrate a single client from old structure to new.

    Old structure:
        2Packing-tool/CLIENTS/CLIENT_{ID}/config.json
        2Packing-tool/CLIENTS/CLIENT_{ID}/sku_mapping.json

    New structure:
        0UFulfilment/Clients/CLIENT_{ID}/packer_config.json
        0UFulfilment/Clients/CLIENT_{ID}/client_config.json
    """
    print_status(f"Migrating client: {client_id}")

    old_client_dir = OLD_BASE / "CLIENTS" / f"CLIENT_{client_id}"
    new_client_dir = NEW_BASE / "Clients" / f"CLIENT_{client_id}"

    if not old_client_dir.exists():
        print_status(f"WARNING: Client directory not found: {old_client_dir}", "WARNING")
        return False

    # Create new client directory
    if dry_run:
        print_status(f"[DRY-RUN] Would create: {new_client_dir}")
    else:
        new_client_dir.mkdir(parents=True, exist_ok=True)

    # Load old config.json
    old_config_path = old_client_dir / "config.json"
    old_config = {}

    if old_config_path.exists():
        try:
            with open(old_config_path, 'r', encoding='utf-8') as f:
                old_config = json.load(f)
            print_status(f"Loaded config.json for {client_id}")
        except Exception as e:
            print_status(f"ERROR: Failed to load config.json: {e}", "ERROR")
            return False

    # Load old sku_mapping.json
    old_sku_mapping_path = old_client_dir / "sku_mapping.json"
    sku_mappings = {}

    if old_sku_mapping_path.exists():
        try:
            with open(old_sku_mapping_path, 'r', encoding='utf-8') as f:
                sku_data = json.load(f)
                sku_mappings = sku_data.get('mappings', {})
            print_status(f"Loaded {len(sku_mappings)} SKU mappings for {client_id}")
        except Exception as e:
            print_status(f"WARNING: Failed to load sku_mapping.json: {e}", "WARNING")

    # Create new packer_config.json (merged config + SKU mapping)
    packer_config = {
        "client_id": client_id,
        "client_name": old_config.get('client_name', client_id),
        "created_at": old_config.get('created_at', datetime.now().isoformat()),
        "barcode_label": old_config.get('barcode_label', {
            "width_mm": 65,
            "height_mm": 35,
            "dpi": 203,
            "show_quantity": False,
            "show_client_name": False,
            "font_size": 10
        }),
        "courier_deadlines": old_config.get('courier_deadlines', {}),
        "required_columns": old_config.get('required_columns', {
            "order_number": "Order_Number",
            "sku": "SKU",
            "product_name": "Product_Name",
            "quantity": "Quantity",
            "courier": "Courier"
        }),
        "sku_mapping": sku_mappings,
        "barcode_settings": {
            "auto_generate": True,
            "format": "CODE128"
        },
        "packing_rules": {},
        "last_updated": datetime.now().isoformat(),
        "updated_by": "migration_script"
    }

    # Save packer_config.json
    packer_config_path = new_client_dir / "packer_config.json"
    if dry_run:
        print_status(f"[DRY-RUN] Would create: {packer_config_path}")
        print_status(f"[DRY-RUN] Content: {json.dumps(packer_config, indent=2)[:200]}...")
    else:
        try:
            with open(packer_config_path, 'w', encoding='utf-8') as f:
                json.dump(packer_config, f, indent=2, ensure_ascii=False)
            print_status(f"Created packer_config.json for {client_id}")
        except Exception as e:
            print_status(f"ERROR: Failed to create packer_config.json: {e}", "ERROR")
            return False

    # Create client_config.json (for Shopify Tool compatibility)
    client_config = {
        "client_id": client_id,
        "client_name": old_config.get('client_name', client_id),
        "created_at": old_config.get('created_at', datetime.now().isoformat())
    }

    client_config_path = new_client_dir / "client_config.json"
    if dry_run:
        print_status(f"[DRY-RUN] Would create: {client_config_path}")
    else:
        try:
            with open(client_config_path, 'w', encoding='utf-8') as f:
                json.dump(client_config, f, indent=2, ensure_ascii=False)
            print_status(f"Created client_config.json for {client_id}")
        except Exception as e:
            print_status(f"ERROR: Failed to create client_config.json: {e}", "ERROR")
            return False

    # Copy backups directory if exists
    old_backups = old_client_dir / "backups"
    new_backups = new_client_dir / "backups"

    if old_backups.exists():
        if dry_run:
            print_status(f"[DRY-RUN] Would copy backups directory")
        else:
            try:
                shutil.copytree(old_backups, new_backups, dirs_exist_ok=True)
                print_status(f"Copied backups directory for {client_id}")
            except Exception as e:
                print_status(f"WARNING: Failed to copy backups: {e}", "WARNING")

    print_status(f"Successfully migrated client: {client_id}", "SUCCESS")
    return True


def migrate_sessions(client_id, dry_run=False):
    """
    Migrate sessions for a client.

    Old: 2Packing-tool/SESSIONS/CLIENT_{ID}/
    New: 0UFulfilment/Sessions/CLIENT_{ID}/
    """
    print_status(f"Migrating sessions for client: {client_id}")

    old_sessions_dir = OLD_BASE / "SESSIONS" / f"CLIENT_{client_id}"
    new_sessions_dir = NEW_BASE / "Sessions" / f"CLIENT_{client_id}"

    if not old_sessions_dir.exists():
        print_status(f"No sessions found for client {client_id}")
        return True

    if dry_run:
        print_status(f"[DRY-RUN] Would copy sessions from {old_sessions_dir} to {new_sessions_dir}")
        session_count = len(list(old_sessions_dir.iterdir()))
        print_status(f"[DRY-RUN] Would migrate {session_count} sessions")
    else:
        try:
            shutil.copytree(old_sessions_dir, new_sessions_dir, dirs_exist_ok=True)
            session_count = len(list(new_sessions_dir.iterdir()))
            print_status(f"Migrated {session_count} sessions for {client_id}")
        except Exception as e:
            print_status(f"ERROR: Failed to migrate sessions: {e}", "ERROR")
            return False

    return True


def migrate_stats(dry_run=False):
    """
    Migrate global statistics.

    Old: 2Packing-tool/STATS/stats.json
    New: 0UFulfilment/Stats/global_stats.json
    """
    print_status("Migrating statistics...")

    old_stats_path = OLD_BASE / "STATS" / "stats.json"
    new_stats_path = NEW_BASE / "Stats" / "global_stats.json"

    if not old_stats_path.exists():
        print_status("No statistics file found to migrate")
        return True

    if dry_run:
        print_status(f"[DRY-RUN] Would copy {old_stats_path} to {new_stats_path}")
    else:
        try:
            new_stats_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old_stats_path, new_stats_path)
            print_status("Migrated statistics")
        except Exception as e:
            print_status(f"ERROR: Failed to migrate statistics: {e}", "ERROR")
            return False

    return True


def get_clients_to_migrate(specific_client=None):
    """Get list of clients to migrate."""
    old_clients_dir = OLD_BASE / "CLIENTS"

    if not old_clients_dir.exists():
        print_status("No CLIENTS directory found in old structure", "ERROR")
        return []

    all_clients = []
    for client_dir in old_clients_dir.iterdir():
        if client_dir.is_dir() and client_dir.name.startswith("CLIENT_"):
            client_id = client_dir.name.replace("CLIENT_", "")
            all_clients.append(client_id)

    if specific_client:
        if specific_client in all_clients:
            return [specific_client]
        else:
            print_status(f"Client {specific_client} not found in old structure", "ERROR")
            return []

    return all_clients


def main():
    """Main migration function."""
    parser = argparse.ArgumentParser(
        description="Migrate Packing Tool from 2Packing-tool to 0UFulfilment"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        '--client',
        type=str,
        help="Migrate only specific client (e.g., M, A, R)"
    )

    args = parser.parse_args()

    print_status("=" * 60)
    print_status("Packing Tool Migration: 2Packing-tool -> 0UFulfilment")
    print_status("=" * 60)

    if args.dry_run:
        print_status("DRY-RUN MODE: No changes will be made", "WARNING")

    # Check paths
    if not check_paths():
        return 1

    # Create directory structure
    create_directory_structure(dry_run=args.dry_run)

    # Get clients to migrate
    clients = get_clients_to_migrate(args.client)
    if not clients:
        print_status("No clients to migrate", "ERROR")
        return 1

    print_status(f"Found {len(clients)} client(s) to migrate: {', '.join(clients)}")

    # Migrate each client
    success_count = 0
    for client_id in clients:
        print_status("-" * 60)
        if migrate_client(client_id, dry_run=args.dry_run):
            if migrate_sessions(client_id, dry_run=args.dry_run):
                success_count += 1

    # Migrate global stats
    migrate_stats(dry_run=args.dry_run)

    # Summary
    print_status("=" * 60)
    print_status(f"Migration complete: {success_count}/{len(clients)} clients migrated successfully")

    if args.dry_run:
        print_status("This was a DRY-RUN. Run without --dry-run to actually migrate.", "WARNING")

    print_status("=" * 60)

    return 0 if success_count == len(clients) else 1


if __name__ == "__main__":
    sys.exit(main())
