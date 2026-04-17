import sqlite3
from players import players

db = sqlite3.connect('database.db')
cursor = db.cursor()

# Get all squad entries
cursor.execute("SELECT userid, player_key FROM squad")
squad_entries = cursor.fetchall()

for userid, player_name in squad_entries:
    # Find the player in players dict
    key = player_name.lower().replace(" ", "_")
    player_data = players.get(key)
    if player_data:
        new_ovr = player_data.get("ovr", 80)
        cursor.execute("UPDATE squad SET ovr = ? WHERE userid = ? AND player_key = ?", (new_ovr, userid, player_name))
        print(f"Updated {player_name} for user {userid} to OVR {new_ovr}")

db.commit()
db.close()
print("Squad OVRs updated.")