from players import players
all_players = list(players.values())

# Count by OVR
ovr_count = {}
for p in all_players:
    ovr = int(p.get('ovr', 0))
    ovr_count[ovr] = ovr_count.get(ovr, 0) + 1

print('Total players by OVR:')
for ovr in sorted(ovr_count.keys()):
    print(f'{ovr} OVR: {ovr_count[ovr]} players')

# For reward XI ranges
ranges = {
    'Batters 75-80': lambda p: p['role'] == 'Batter' and 75 <= int(p.get('ovr', 0)) <= 80,
    'Bowlers 75-80': lambda p: p['role'] == 'Bowler' and 75 <= int(p.get('ovr', 0)) <= 80,
    'Allrounders 75-80': lambda p: p['role'] == 'Allrounder' and 75 <= int(p.get('ovr', 0)) <= 80,
    'Wicketkeepers 80-85': lambda p: p['role'] == 'Wicketkeeper' and 80 <= int(p.get('ovr', 0)) <= 85,
    'Any 85-90': lambda p: 85 <= int(p.get('ovr', 0)) <= 90
}

print('\nEligible counts and OVR distribution for reward XI:')
for name, cond in ranges.items():
    eligible = [p for p in all_players if cond(p)]
    count = len(eligible)
    print(f'\n{name}: {count} players')
    ovr_dist = {}
    for p in eligible:
        ovr = int(p.get('ovr', 0))
        ovr_dist[ovr] = ovr_dist.get(ovr, 0) + 1
    for ovr in sorted(ovr_dist.keys()):
        prob = ovr_dist[ovr] / count * 100
        print(f'  {ovr} OVR: {ovr_dist[ovr]} players ({prob:.1f}%)')