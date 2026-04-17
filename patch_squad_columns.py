from pathlib import Path
import re
files = [Path('views.py'), Path('bot.py'), Path('check_user_xis.py'), Path('update_squad_ovr.py')]
replacements = [
    (re.compile(r"SELECT player FROM squad"), "SELECT player_key FROM squad"),
    (re.compile(r"INSERT INTO squad\(userid, player, ovr\) VALUES\(\?,\?,\?\)"), "INSERT INTO squad(userid, player_key, ovr) VALUES(?,?,?)"),
    (re.compile(r"WHERE userid=\? AND LOWER\(player\)=\?"), "WHERE userid=? AND LOWER(player_key)=?"),
]
for path in files:
    if not path.exists():
        continue
    text = path.read_text(encoding='utf-8')
    original = text
    for pattern, repl in replacements:
        text = pattern.sub(repl, text)
    if path.name == 'views.py':
        text = text.replace(
            'cursor.execute("INSERT INTO squad(userid, player, ovr) VALUES(?,?,?)",\n                (user_id, player.get("name", "Unknown"), int(player.get("ovr", 0)))\n            )',
            'cursor.execute("INSERT INTO squad(userid, player_key, ovr) VALUES(?,?,?)",\n                (user_id, get_player_key_from_name(player.get("name", "Unknown")) or player.get("name", "Unknown"), int(player.get("ovr", 0)))\n            )'
        )
    if text != original:
        path.write_text(text, encoding='utf-8')
        print('Updated', path)
