"""
HOI4 Modding Studio - Ideas/National Spirit Management

This module handles the creation and management of national ideas and spirits for countries.
"""

from pathlib import Path
from typing import Dict, List, Any
import yaml


def write_ideas_file(mod_root: Path, tag: str, ideas_data: List[Dict[str, Any]]):
    """
    Write ideas/national spirit to the mod.
    
    Args:
        mod_root: Path to mod directory
        tag: Country tag
        ideas_data: List of dictionaries containing idea definitions
    """
    # Ensure the directory exists
    ideas_dir = mod_root / "common" / "national_ideas"
    ideas_dir.mkdir(parents=True, exist_ok=True)
    
    # Create the ideas file
    ideas_file = ideas_dir / f"{tag.lower()}_ideas.txt"
    
    with open(ideas_file, 'w', encoding='utf-8') as f:
        f.write(f"# National Ideas for {tag}\n")
        f.write(f"country_ideas = {{\n")
        f.write(f"\tname = {tag}_ideas\n")
        
        for idea in ideas_data:
            f.write(f"\t{idea['id']} = {{\n")
            if 'icon' in idea:
                f.write(f"\t\ticon = {idea['icon']}\n")
            
            # Write modifier if present
            if 'modifier' in idea:
                f.write("\t\tmodifier = {\n")
                for mod_key, mod_value in idea['modifier'].items():
                    if isinstance(mod_value, bool):
                        f.write(f"\t\t\t{mod_key} = {'yes' if mod_value else 'no'}\n")
                    elif isinstance(mod_value, (int, float)):
                        f.write(f"\t\t\t{mod_key} = {mod_value}\n")
                    else:
                        f.write(f"\t\t\t{mod_key} = \"{mod_value}\"\n")
                f.write("\t\t}\n")
            
            f.write(f"\t}}\n\n")
        
        f.write("}\n")


def write_dynamic_ideas_file(mod_root: Path, tag: str, dynamic_ideas_data: List[Dict[str, Any]]):
    """
    Write dynamic national ideas (like national focuses) to the mod.
    
    Args:
        mod_root: Path to mod directory
        tag: Country tag
        dynamic_ideas_data: List of dictionaries containing dynamic idea definitions
    """
    # Ensure the directory exists
    ideas_dir = mod_root / "common" / "national_ideas"
    ideas_dir.mkdir(parents=True, exist_ok=True)
    
    # Create the dynamic ideas file
    dynamic_ideas_file = ideas_dir / f"{tag.lower()}_dynamic_ideas.txt"
    
    with open(dynamic_ideas_file, 'w', encoding='utf-8') as f:
        f.write(f"# Dynamic National Ideas for {tag}\n")
        f.write(f"dynamic_country_ideas = {{\n")
        f.write(f"\tname = {tag}_dynamic_ideas\n")
        
        for idea in dynamic_ideas_data:
            f.write(f"\t{idea['id']} = {{\n")
            f.write(f"\t\tpotential = {{\n")
            if 'potential' in idea:
                for pot_key, pot_value in idea['potential'].items():
                    if isinstance(pot_value, bool):
                        f.write(f"\t\t\t{pot_key} = {'yes' if pot_value else 'no'}\n")
                    elif isinstance(pot_value, (int, float)):
                        f.write(f"\t\t\t{pot_key} = {pot_value}\n")
                    else:
                        f.write(f"\t\t\t{pot_key} = \"{pot_value}\"\n")
            f.write(f"\t\t}}\n")
            
            f.write(f"\t\tavailable = {{\n")
            if 'available' in idea:
                for avail_key, avail_value in idea['available'].items():
                    if isinstance(avail_value, bool):
                        f.write(f"\t\t\t{avail_key} = {'yes' if avail_value else 'no'}\n")
                    elif isinstance(avail_value, (int, float)):
                        f.write(f"\t\t\t{avail_key} = {avail_value}\n")
                    else:
                        f.write(f"\t\t\t{avail_key} = \"{avail_value}\"\n")
            f.write(f"\t\t}}\n")
            
            if 'modifier' in idea:
                f.write("\t\tmodifier = {\n")
                for mod_key, mod_value in idea['modifier'].items():
                    if isinstance(mod_value, bool):
                        f.write(f"\t\t\t{mod_key} = {'yes' if mod_value else 'no'}\n")
                    elif isinstance(mod_value, (int, float)):
                        f.write(f"\t\t\t{mod_key} = {mod_value}\n")
                    else:
                        f.write(f"\t\t\t{mod_key} = \"{mod_value}\"\n")
                f.write("\t\t}\n")
            
            f.write(f"\t}}\n\n")
        
        f.write("}\n")


def read_ideas_file(mod_root: Path, tag: str) -> Dict[str, Any]:
    """
    Read existing ideas from the mod.
    
    Args:
        mod_root: Path to mod directory
        tag: Country tag
        
    Returns:
        Dictionary with ideas information
    """
    ideas_file = mod_root / "common" / "national_ideas" / f"{tag.lower()}_ideas.txt"
    dynamic_ideas_file = mod_root / "common" / "national_ideas" / f"{tag.lower()}_dynamic_ideas.txt"
    
    ideas_data = {"static": [], "dynamic": []}
    
    # Read static ideas if file exists
    if ideas_file.exists():
        content = ideas_file.read_text(encoding="utf-8", errors="ignore")
        # This is a simplified parsing approach
        # A full parser would be more complex
        ideas_data["static"] = [{"id": f"{tag}_idea_1", "name": "Sample Idea"}]  # Placeholder
    
    # Read dynamic ideas if file exists
    if dynamic_ideas_file.exists():
        content = dynamic_ideas_file.read_text(encoding="utf-8", errors="ignore")
        # This is a simplified parsing approach
        ideas_data["dynamic"] = [{"id": f"{tag}_dynamic_idea_1", "name": "Sample Dynamic Idea"}]  # Placeholder
    
    return ideas_data