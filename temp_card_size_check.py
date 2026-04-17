from pathlib import Path
from PIL import Image

base = Path(r'c:\VCBOT')
for p in [base / 'templates' / 'card.png', base / 'templates' / 'IPL Legends' / 'david_warner.png']:
    try:
        with Image.open(p) as im:
            print(p.name, im.size)
    except Exception as e:
        print('ERR', p, e)
