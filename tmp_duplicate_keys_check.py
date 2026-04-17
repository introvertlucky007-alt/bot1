from pathlib import Path
from collections import Counter
import re
text = Path('players.py').read_text(encoding='utf-8')
keys = re.findall(r'"([^\"]+)"\s*:\s*\{', text)
counts = Counter(keys)
dups = [(k,c) for k,c in counts.items() if c>1]
print('duplicate keys:', len(dups))
for k,c in dups:
    print(k,c)
