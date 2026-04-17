#!/usr/bin/env python3
"""Check actual user squad requirements from the database."""

import sys
sys.path.insert(0, r'c:\CCBOT')

import sqlite3
from players import players
from views import get_player_role

# Connect to database
conn = sqlite3.connect('CCbot.db')
cursor = conn.cursor()

def check_user_squad_xi(user_id):
    """Check a specific user's XI squad composition."""
    cursor.execute("SELECT player_key FROM squad WHERE userid=? ORDER BY rowid LIMIT 11", (user_id,))
    xi_players = [row[0] for row in cursor.fetchall()]
    
    if not xi_players:
        return None, None
    
    roles = {"bat": 0, "bowl": 0, "alr": 0, "wk": 0}
    role_details = []
    
    for p in xi_players:
        role = get_player_role(p)
        role_details.append((p, role))
        
        if role == "Batter":
            roles["bat"] += 1
        elif role == "Bowler":
            roles["bowl"] += 1
        elif role == "Allrounder":
            roles["alr"] += 1
        elif role == "Wicketkeeper":
            roles["wk"] += 1
    
    # Check if valid
    valid = (
        3 <= roles["bat"] <= 5 and
        3 <= roles["bowl"] <= 5 and
        1 <= roles["alr"] <= 3 and
        1 <= roles["wk"] <= 2
    )
    
    return roles, (valid, role_details)

def main():
    print("=" * 70)
    print("CHECKING USER XIs IN DATABASE")
    print("=" * 70)
    
    # Get all unique users
    cursor.execute("SELECT DISTINCT userid FROM squad ORDER BY userid")
    user_ids = [row[0] for row in cursor.fetchall()]
    
    if not user_ids:
        print("No users found in squad table.")
        return
    
    print(f"\nFound {len(user_ids)} users in database.")
    print("\nChecking XI Requirements for each user:\n")
    
    valid_count = 0
    invalid_count = 0
    
    for user_id in user_ids[:10]:  # Check first 10 users
        roles, details = check_user_squad_xi(user_id)
        
        if roles is None:
            continue
        
        valid, role_details = details
        valid_count += 1 if valid else 0
        invalid_count += 0 if valid else 1
        
        status = "✓ VALID" if valid else "✗ INVALID"
        print(f"User ID: {user_id} -> {status}")
        print(f"  Batters (3-5):        {roles['bat']} {'✓' if 3 <= roles['bat'] <= 5 else '✗'}")
        print(f"  Bowlers (3-5):        {roles['bowl']} {'✓' if 3 <= roles['bowl'] <= 5 else '✗'}")
        print(f"  All-rounders (1-3):   {roles['alr']} {'✓' if 1 <= roles['alr'] <= 3 else '✗'}")
        print(f"  Wicketkeepers (1-2):  {roles['wk']} {'✓' if 1 <= roles['wk'] <= 2 else '✗'}")
        
        if not valid:
            print(f"  Players:")
            for player, role in role_details:
                print(f"    - {player:25} ({role})")
        
        print()
    
    print("\n" + "=" * 70)
    print(f"SUMMARY: {valid_count} valid, {invalid_count} invalid (from checked users)")
    print("=" * 70)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()
