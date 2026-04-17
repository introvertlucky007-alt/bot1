from pathlib import Path
import players
from card_generator import generate_card

all_player_entries = list(players.players.items())

def get_player_card_paths(player_key, player, player_id=None):
    paths = []
    image = player.get('image')
    if image:
        image_path = Path(image)
        if not image_path.is_absolute():
            image_path = Path(__file__).resolve().parent / image
        if image_path.exists() and str(image_path) not in paths:
            paths.append(str(image_path))
    try:
        if player_id is None:
            player_id = next((idx for idx,(k,e) in enumerate(all_player_entries) if k==player_key), 0)
        generated_path = generate_card(player_id, player, player_key=player_key)
        if generated_path and generated_path not in paths:
            paths.append(generated_path)
    except Exception as e:
        print('generate_card failed', player_key, e)
    return paths

for key in ['sanju_samson_S', 'david_warner_S', 'finn_allen_S', 'bhuvaneshwar_kumar_S']:
    p = players.players.get(key)
    print('\nKEY:', key, 'exists?', p is not None)
    if p:
        image_path = p.get('image')
        print('image field:', image_path)
        if image_path:
            path = Path(__file__).resolve().parent / image_path
            print('custom exists', path.exists(), path)
        paths = get_player_card_paths(key, p, player_id=0)
        print('paths:', paths)
        for path in paths:
            print('    exists?', Path(path).exists(), path)
