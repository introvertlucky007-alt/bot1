from collections import defaultdict
import players

names = defaultdict(list)
for k, v in players.players.items():
    names[v['name']].append((k, v.get('category')))

for name, vals in names.items():
    if len(vals) > 1:
        print(name, vals)
