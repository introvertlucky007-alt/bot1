from pathlib import Path
import sys
sys.path.append(r'c:\VCBOT')
from bot import all_player_entries, get_player_card_paths, normalize_player_name, find_player_key_and_variant

for name in ['Sanju Samson', 'Sanju Samson S', 'Sanju Samson N']:
    normalized = normalize_player_name(name.replace('_', ' '))
    matches = [(k, e) for k,e in all_player_entries if e.get('name','').strip().lower() == normalized]
    print('\nINPUT:', name)
    print('EXACT matches:', len(matches))
    for k,e in matches:
        print('  key=', k, 'category=', e.get('category'), 'ovr=', e.get('ovr'), 'image=', e.get('image'))
        print('  paths=', get_player_card_paths(k, e, player_id=all_player_entries.index((k,e))))
    print('find_player_key_and_variant:', find_player_key_and_variant(name, 'S'))
    print('find_player_key_and_variant N:', find_player_key_and_variant(name, 'N'))
    print('find_player_key_and_variant none:', find_player_key_and_variant(name, None))
