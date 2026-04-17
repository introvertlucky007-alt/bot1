from pathlib import Path
import players
from bot import get_player_card_paths
import card_generator

for key in ['sanju_samson_S', 'david_warner_S', 'finn_allen_S']:
    p = players.players.get(key)
    print('\nKEY:', key)
    print('exists?', p is not None)
    if p:
        paths = get_player_card_paths(key, p, player_id=0)
        print('paths:', paths)
        for path in paths:
            print('  ', path, Path(path).exists())
        if p.get('image'):
            custom_path = Path(card_generator.__file__).resolve().parent / p.get('image')
            print('custom path', custom_path, custom_path.exists())
