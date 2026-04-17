from pathlib import Path
import players

missing = []
for key, p in players.players.items():
    img = p.get('image')
    if img:
        path = Path(__file__).resolve().parent / img
        if not path.exists():
            missing.append((key, img, str(path)))
print('missing count', len(missing))
for i in missing[:50]:
    print(i)
