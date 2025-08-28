"""
CLI Configuration Manager for Library CLI
Manages user preferences, defaults, and aliases
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from rich.console import Console

console = Console()

class CLIConfig:
    """Manages CLI configuration and user preferences."""
    
    def __init__(self):
        self.config_dir = Path.home() / ".library-cli"
        self.config_file = self.config_dir / "config.json"
        self.config: Dict[str, Any] = {}
        self.load_config()
    
    def load_config(self) -> None:
        """Load configuration from file or create default."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                console.print(f"[dim]📄 Config loaded from {self.config_file}[/]")
            except Exception as e:
                console.print(f"[yellow]⚠️  Could not load config: {e}[/]")
                self.create_default_config()
        else:
            self.create_default_config()
    
    def create_default_config(self) -> None:
        """Create default configuration."""
        self.config = {
            "preferences": {
                "default_export_format": "csv",
                "default_search_limit": 10,
                "show_progress_bars": True,
                "auto_confirm_operations": False,
                "cache_enabled": True,
                "color_theme": "default"
            },
            "aliases": {
                "l": "list",
                "a": "add", 
                "r": "remove",
                "f": "find",
                "s": "search",
                "st": "stats",
                "exp": "export"
            },
            "api_settings": {
                "timeout": 10,
                "retry_attempts": 3,
                "batch_size": 50
            },
            "ui_settings": {
                "table_style": "rich",
                "show_emojis": True,
                "confirm_deletions": True
            }
        }
        self.save_config()
        console.print(f"[green]✅ Default config created at {self.config_file}[/]")
    
    def save_config(self) -> None:
        """Save current configuration to file."""
        self.config_dir.mkdir(exist_ok=True)
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            console.print(f"[red]❌ Could not save config: {e}[/]")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation (e.g., 'preferences.default_export_format')."""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value using dot notation."""
        keys = key.split('.')
        config = self.config
        
        # Navigate to the parent dictionary
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        # Set the value
        config[keys[-1]] = value
        self.save_config()
    
    def get_alias(self, command: str) -> str:
        """Get full command name from alias."""
        aliases = self.get("aliases", {})
        return aliases.get(command, command)
    
    def add_alias(self, alias: str, command: str) -> None:
        """Add a new command alias."""
        aliases = self.get("aliases", {})
        aliases[alias] = command
        self.set("aliases", aliases)
        console.print(f"[green]✅ Added alias '{alias}' -> '{command}'[/]")
    
    def remove_alias(self, alias: str) -> bool:
        """Remove a command alias."""
        aliases = self.get("aliases", {})
        if alias in aliases:
            del aliases[alias]
            self.set("aliases", aliases)
            console.print(f"[green]✅ Removed alias '{alias}'[/]")
            return True
        return False
    
    def list_aliases(self) -> Dict[str, str]:
        """Get all configured aliases."""
        return self.get("aliases", {})
    
    def reset_to_default(self) -> None:
        """Reset configuration to default values."""
        self.create_default_config()
        console.print("[green]✅ Configuration reset to default values[/]")
    
    def show_config(self) -> None:
        """Display current configuration."""
        from rich.tree import Tree
        from rich.json import JSON
        
        tree = Tree("📄 Library CLI Configuration", style="bold blue")
        
        for section, values in self.config.items():
            section_tree = tree.add(f"[bold cyan]{section.title()}[/]")
            if isinstance(values, dict):
                for key, value in values.items():
                    section_tree.add(f"[yellow]{key}[/]: [white]{value}[/]")
            else:
                section_tree.add(f"[white]{values}[/]")
        
        console.print(tree)
        console.print(f"\n[dim]Config file: {self.config_file}[/]")

# Global config instance
cli_config = CLIConfig()