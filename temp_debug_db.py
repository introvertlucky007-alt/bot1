import sqlite3

db = sqlite3.connect('database.db')
c = db.cursor()
c.execute("SELECT rowid, userid, player_key, ovr, category FROM squad WHERE player_key='sanju_samson' ORDER BY rowid")
rows = c.fetchall()
print(rows)
db.close()
