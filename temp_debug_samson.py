from bot import find_player_key_and_variant, players

for cat in ['N', 'S']:
    key, entry = find_player_key_and_variant('Sanju Samson', cat)
    print(cat, 'key=', key, 'category=', entry.get('category') if entry else None, 'ovr=', entry.get('ovr') if entry else None)
print('players dict entry:', players.get('sanju_samson'))
