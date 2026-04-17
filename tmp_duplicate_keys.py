from pathlib import Path
import re
from collections import Counter
text = Path('players.py').read_text(encoding='utf-8')
keys = re.findall(r'"([^\"]+)"\s*:\s*\{', text)
for k, c in Counter(keys).items():
    if c > 1:
        print(k, c)
