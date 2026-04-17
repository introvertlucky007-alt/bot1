#!/usr/bin/env python
"""Test the intelligent player role matching"""

from players import players

def get_player_role(player_name):
    """
    Get player role with intelligent name matching.
    Handles:
    - Direct exact match (normalized)
    - Last name matching (for abbreviations like V Chakravarthy)
    - Substring/partial matching (for common variations)
    Returns role string or "Unknown"
    """
    if not player_name:
        return "Unknown"
    
    player_name_normalized = player_name.strip().lower()
    
    # Strategy 1: Exact normalized match
    for key, pdata in players.items():
        if not pdata:
            continue
        pdata_name = pdata.get("name", "").strip().lower()
        if pdata_name == player_name_normalized:
            return pdata.get("role", "Unknown")
    
    # Strategy 2: Last name match (handles "Varun Chakravarthy" vs "V Chakravarthy")
    player_parts = player_name_normalized.split()
    if len(player_parts) > 1:
        last_name = player_parts[-1]
        for key, pdata in players.items():
            if not pdata:
                continue
            pdata_name = pdata.get("name", "").strip().lower()
            pdata_parts = pdata_name.split()
            if len(pdata_parts) > 1 and pdata_parts[-1] == last_name:
                # Last name matches - check if first name is a substring or abbreviation
                first_part = player_parts[0]
                pdata_first = pdata_parts[0]
                if first_part in pdata_first or pdata_first in first_part:
                    return pdata.get("role", "Unknown")
    
    # Strategy 3: Check if player name contains or is contained in a players dict entry
    for key, pdata in players.items():
        if not pdata:
            continue
        pdata_name = pdata.get("name", "").strip().lower()
        # If squad player name is part of dict entry or vice versa
        if player_name_normalized in pdata_name or pdata_name in player_name_normalized:
            return pdata.get("role", "Unknown")
    
    return "Unknown"

# Test cases
test_names = [
    ("Varun Chakravarthy", "Bowler"),  # Full name vs abbreviated
    ("V Chakravarthy", "Bowler"),       # Direct match
    ("Virat Kohli", "Batter"),          # Exact match
    ("Joe Root", "Batter"),             # Exact match
    ("Roston Chase", "Allrounder"),        # In database as Allrounder
    ("Unknown Player", "Unknown"),        # Not in database
    ("Mohammed Shami", "Bowler"),       # Exact match
    ("Ben Stokes", "Allrounder"),       # Exact match
]

print("Testing intelligent player name matching:\n")
for name, expected_role in test_names:
    matched_role = get_player_role(name)
    status = "✓" if matched_role == expected_role else "✗"
    print(f"{status} '{name}' -> {matched_role} (expected: {expected_role})")
