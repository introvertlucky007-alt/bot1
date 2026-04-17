from collections import Counter
import re
with open('players.py', 'r', encoding='utf-8') as f:
    text = f.read()
pattern = re.compile(r'\s*"([^\"]+)"\s*:\s*\{')
keys = pattern.findall(text)
for key, count in Counter(keys).items():
    if count > 1:
        print(f'{key}: {count}')
