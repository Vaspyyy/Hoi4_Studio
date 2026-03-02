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
    import re
    
    ideas_file = mod_root / "common" / "national_ideas" / f"{tag.lower()}_ideas.txt"
    dynamic_ideas_file = mod_root / "common" / "national_ideas" / f"{tag.lower()}_dynamic_ideas.txt"
    
    ideas_data = {"static": [], "dynamic": []}
    
    # Read static ideas if file exists
    if ideas_file.exists():
        content = ideas_file.read_text(encoding="utf-8", errors="ignore")
        
        # Parse ideas using regex
        # Pattern to match idea blocks: idea_id = { ... }
        idea_pattern = r'^\s*([a-zA-Z0-9_]+)\s*=\s*\{([^}]*)\}'
        ideas_content = ""
        
        # Extract the content inside country_ideas = { ... }
        country_ideas_match = re.search(r'country_ideas\s*=\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', content, re.MULTILINE | re.DOTALL)
        if country_ideas_match:
            ideas_content = country_ideas_match.group(1)
        
        # Find all individual idea blocks
        idea_blocks = re.findall(r'^\s*([a-zA-Z0-9_]+)\s*=\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', ideas_content, re.MULTILINE | re.DOTALL)
        
        for idea_id, idea_body in idea_blocks:
            idea_obj = {"id": idea_id.strip()}
            
            # Extract icon if present
            icon_match = re.search(r'icon\s*=\s*([^\n\r]+)', idea_body)
            if icon_match:
                idea_obj["icon"] = icon_match.group(1).strip()
                
            # Extract modifier if present
            modifier_match = re.search(r'modifier\s*=\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', idea_body, re.DOTALL)
            if modifier_match:
                modifier_content = modifier_match.group(1)
                modifier = {}
                # Extract modifier properties
                mod_properties = re.findall(r'^\s*([a-zA-Z0-9_]+)\s*=\s*([^\n\r]+)', modifier_content, re.MULTILINE)
                for key, value in mod_properties:
                    # Convert value to appropriate type
                    value = value.strip().strip('"')
                    if value.lower() in ['yes', 'no']:
                        modifier[key.strip()] = value.lower() == 'yes'
                    elif '.' in value or 'inf' in value.lower() or '-inf' in value.lower():
                        try:
                            modifier[key.strip()] = float(value)
                        except ValueError:
                            modifier[key.strip()] = value
                    elif value.isdigit() or (value.startswith('-') and value[1:].isdigit()):
                        try:
                            modifier[key.strip()] = int(value)
                        except ValueError:
                            modifier[key.strip()] = value
                    else:
                        modifier[key.strip()] = value
                idea_obj["modifier"] = modifier
            
            ideas_data["static"].append(idea_obj)
    
    # Read dynamic ideas if file exists
    if dynamic_ideas_file.exists():
        content = dynamic_ideas_file.read_text(encoding="utf-8", errors="ignore")
        
        # Parse dynamic ideas using regex
        idea_pattern = r'^\s*([a-zA-Z0-9_]+)\s*=\s*\{([^}]*)}'
        ideas_content = ""
        
        # Extract the content inside dynamic_country_ideas = { ... }
        dynamic_ideas_match = re.search(r'dynamic_country_ideas\s*=\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', content, re.MULTILINE | re.DOTALL)
        if dynamic_ideas_match:
            ideas_content = dynamic_ideas_match.group(1)
        
        # Find all individual idea blocks
        idea_blocks = re.findall(r'^\s*([a-zA-Z0-9_]+)\s*=\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', ideas_content, re.MULTILINE | re.DOTALL)
        
        for idea_id, idea_body in idea_blocks:
            idea_obj = {"id": idea_id.strip()}
            
            # Extract potential if present
            potential_match = re.search(r'potential\s*=\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', idea_body, re.DOTALL)
            if potential_match:
                potential_content = potential_match.group(1)
                potential = {}
                # Extract potential properties
                pot_properties = re.findall(r'^\s*([a-zA-Z0-9_]+)\s*=\s*([^\n\r]+)', potential_content, re.MULTILINE)
                for key, value in pot_properties:
                    value = value.strip().strip('"')
                    if value.lower() in ['yes', 'no']:
                        potential[key.strip()] = value.lower() == 'yes'
                    elif '.' in value or 'inf' in value.lower() or '-inf' in value.lower():
                        try:
                            potential[key.strip()] = float(value)
                        except ValueError:
                            potential[key.strip()] = value
                    elif value.isdigit() or (value.startswith('-') and value[1:].isdigit()):
                        try:
                            potential[key.strip()] = int(value)
                        except ValueError:
                            potential[key.strip()] = value
                    else:
                        potential[key.strip()] = value
                idea_obj["potential"] = potential
            
            # Extract available if present
            available_match = re.search(r'available\s*=\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', idea_body, re.DOTALL)
            if available_match:
                available_content = available_match.group(1)
                available = {}
                # Extract available properties
                avail_properties = re.findall(r'^\s*([a-zA-Z0-9_]+)\s*=\s*([^\n\r]+)', available_content, re.MULTILINE)
                for key, value in avail_properties:
                    value = value.strip().strip('"')
                    if value.lower() in ['yes', 'no']:
                        available[key.strip()] = value.lower() == 'yes'
                    elif '.' in value or 'inf' in value.lower() or '-inf' in value.lower():
                        try:
                            available[key.strip()] = float(value)
                        except ValueError:
                            available[key.strip()] = value
                    elif value.isdigit() or (value.startswith('-') and value[1:].isdigit()):
                        try:
                            available[key.strip()] = int(value)
                        except ValueError:
                            available[key.strip()] = value
                    else:
                        available[key.strip()] = value
                idea_obj["available"] = available
                
            # Extract modifier if present
            modifier_match = re.search(r'modifier\s*=\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', idea_body, re.DOTALL)
            if modifier_match:
                modifier_content = modifier_match.group(1)
                modifier = {}
                # Extract modifier properties
                mod_properties = re.findall(r'^\s*([a-zA-Z0-9_]+)\s*=\s*([^\n\r]+)', modifier_content, re.MULTILINE)
                for key, value in mod_properties:
                    # Convert value to appropriate type
                    value = value.strip().strip('"')
                    if value.lower() in ['yes', 'no']:
                        modifier[key.strip()] = value.lower() == 'yes'
                    elif '.' in value or 'inf' in value.lower() or '-inf' in value.lower():
                        try:
                            modifier[key.strip()] = float(value)
                        except ValueError:
                            modifier[key.strip()] = value
                    elif value.isdigit() or (value.startswith('-') and value[1:].isdigit()):
                        try:
                            modifier[key.strip()] = int(value)
                        except ValueError:
                            modifier[key.strip()] = value
                    else:
                        modifier[key.strip()] = value
                idea_obj["modifier"] = modifier
            
            ideas_data["dynamic"].append(idea_obj)
    
    return ideas_data