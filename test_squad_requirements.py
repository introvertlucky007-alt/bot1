#!/usr/bin/env python3
"""Test script to verify squad requirements are working correctly."""

import sys
sys.path.insert(0, r'c:\CCBOT')

from players import players
from views import get_player_role

# Test cases based on the conversation
# Issue 1: User with 4 batters in CCxi got reported as 2 batters
# Issue 2: User with 3 bowlers got reported as 0 bowlers

def test_player_role_detection():
    """Test if player roles are detected correctly."""
    print("=" * 60)
    print("TEST 1: Player Role Detection")
    print("=" * 60)
    
    test_players = [
        "Virat Kohli",      # Batter
        "Jasprit Bumrah",   # Bowler
        "Hardik Pandya",    # Allrounder
        "MS Dhoni",         # Wicketkeeper
        "V Chakravarthy",   # Bowler (abbreviated first name)
    ]
    
    for test_player in test_players:
        role = get_player_role(test_player)
        print(f"Player: {test_player:20} -> Role: {role}")
    
    print()

def count_roles_by_type():
    """Count how many of each role are available."""
    print("=" * 60)
    print("TEST 2: Available Players by Role")
    print("=" * 60)
    
    roles = {"Batter": 0, "Bowler": 0, "Allrounder": 0, "Wicketkeeper": 0, "Unknown": 0}
    
    for player_key, player_data in players.items():
        if player_data:
            role = player_data.get("role", "Unknown")
            roles[role] = roles.get(role, 0) + 1
    
    print(f"Total Players: {sum(roles.values())}")
    for role, count in sorted(roles.items(), key=lambda x: -x[1]):
        print(f"  {role}: {count}")
    
    print()

def simulate_xi_requirement_check(test_squads):
    """Simulate the squad requirement check on test XI compositions."""
    print("=" * 60)
    print("TEST 3: Simulating XI Requirement Checks")
    print("=" * 60)
    
    for squad_name, xi_players in test_squads.items():
        print(f"\nSquad: {squad_name}")
        print(f"Players: {xi_players}")
        
        roles = {"bat": 0, "bowl": 0, "alr": 0, "wk": 0}
        
        for p in xi_players:
            role = get_player_role(p)
            print(f"  {p:25} -> {role}", end="")
            
            if role == "Batter":
                roles["bat"] += 1
                print(" ✓")
            elif role == "Bowler":
                roles["bowl"] += 1
                print(" ✓")
            elif role == "Allrounder":
                roles["alr"] += 1
                print(" ✓")
            elif role == "Wicketkeeper":
                roles["wk"] += 1
                print(" ✓")
            else:
                print(" ✗ (Unknown role)")
        
        print(f"\nRole Summary:")
        print(f"  Batters (3-5):        {roles['bat']} {'✓' if 3 <= roles['bat'] <= 5 else '✗'}")
        print(f"  Bowlers (3-5):        {roles['bowl']} {'✓' if 3 <= roles['bowl'] <= 5 else '✗'}")
        print(f"  All-rounders (1-3):   {roles['alr']} {'✓' if 1 <= roles['alr'] <= 3 else '✗'}")
        print(f"  Wicketkeepers (1-2):  {roles['wk']} {'✓' if 1 <= roles['wk'] <= 2 else '✗'}")
        
        all_valid = (
            3 <= roles['bat'] <= 5 and
            3 <= roles['bowl'] <= 5 and
            1 <= roles['alr'] <= 3 and
            1 <= roles['wk'] <= 2
        )
        print(f"  Overall: {'✓ VALID' if all_valid else '✗ INVALID'}")

# Test squads
test_squads = {
    "Valid XI - Typical": [
        "Virat Kohli",
        "Rohit Sharma",
        "Suryakumar Yadav",
        "KL Rahul",
        "Hardik Pandya",
        "Sunil Narine",
        "Ben Stokes",
        "Jasprit Bumrah",
        "Mohammed Siraj",
        "Kuldeep Yadav",
        "MS Dhoni"
    ],
    "Issue Case - 4 Batters Reported as 2": [
        "Virat Kohli",
        "Rohit Sharma",
        "Suryakumar Yadav",
        "KL Rahul",
        "Jasprit Bumrah",
        "Mohammed Siraj",
        "Kuldeep Yadav",
        "Adam Zampa",
        "Arshdeep Singh",
        "MS Dhoni",
        "Rishabh Pant"
    ],
    "Issue Case - 3 Bowlers Reported as 0": [
        "Virat Kohli",
        "Rohit Sharma",
        "Suryakumar Yadav",
        "KL Rahul",
        "Sunil Narine",
        "Ben Stokes",
        "Hardik Pandya",
        "Jasprit Bumrah",
        "Mohammed Siraj",
        "Kuldeep Yadav",
        "MS Dhoni"
    ]
}

if __name__ == "__main__":
    test_player_role_detection()
    count_roles_by_type()
    simulate_xi_requirement_check(test_squads)
    print("\n" + "=" * 60)
    print("TEST COMPLETED")
    print("=" * 60)
