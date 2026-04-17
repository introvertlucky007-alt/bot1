"""
Simulate complete 20-over match on green pitch with 90 OVR teams
"""
import random
from engine import (
    play_pace_ball, play_offspin_ball, play_legspin_ball,
    generate_pitch, apply_ovr_effect, apply_pitch_effect, normalize
)
from players import players

# Teams using real players
TEAM_A_BATTERS = [
    players['virat_kohli'],
    players['rohit_sharma'],
    players['shubman_gill'],
    players['suryakumar_yadav'],
    players['yashasvi_jaiswal'],
    players['abhishek_sharma'],
    players['hardik_pandya'],  # assuming all-rounder
    players['ravindra_jadeja'],
    players['kuldeep_yadav'],
    players['jasprit_bumrah'],
    players['mohammed_shami'],
    players['digvesh_rathi']  # added
]

TEAM_B_BATTERS = [
    players['steve_smith'],
    players['travis_head'],
    players['kane_williamson'],
    players['babar_azam'],
    players['mitchell_marsh'],
    players['aiden_markram'],
    players['harry_brook'],
    players['daryl_mitchell'],
    players['dewald_brevis'],
    players['shimron_hetmyer'],
    players['pathum_nissanka'],
    players['khaleel_ahmed']  # added
]

# Bowling attacks
def get_bowling_attack(team_batters):
    bowlers = [p for p in team_batters if p['bowl_ovr'] > 50]
    bowlers.sort(key=lambda x: x['bowl_ovr'], reverse=True)
    return [{"name": p["name"], "bowl_ovr": p["bowl_ovr"], "style": {'fast': 'pace', 'fast_med': 'pace', 'med': 'pace', 'off': 'offspin', 'leg': 'legspin'}.get(p.get('type', ''), 'pace')} for p in bowlers[:5]]

BOWLING_ATTACK_A = get_bowling_attack(TEAM_A_BATTERS)
BOWLING_ATTACK_B = get_bowling_attack(TEAM_B_BATTERS)

BALL_LIBRARY = {
    "pace": [
        {"style": "pace", "type": "Pace", "length": "Good Length", "variation": "None", "swing": "None"},
        {"style": "pace", "type": "Pace", "length": "Good Length", "variation": "None", "swing": "Out"},
        {"style": "pace", "type": "Pace", "length": "Full Length", "variation": "None", "swing": "None"},
        {"style": "pace", "type": "Pace", "length": "Short", "variation": "None", "swing": "None"},
        {"style": "pace", "type": "Fast York", "length": "Full Length", "variation": "Yorker", "swing": "None"},
    ],
    "offspin": [
        {"style": "offspin", "type": "OffSpin", "length": "Good Length"},
        {"style": "offspin", "type": "OffSpin", "length": "Full Length"},
    ],
    "legspin": [
        {"style": "legspin", "type": "LegSpin", "length": "Good Length"},
        {"style": "legspin", "type": "LegSpin", "length": "Full Length"},
    ]
}

SHOTS = ["Defend", "Drive", "Cut", "Pull", "Loft"]

def simulate_innings(batting_team, bowling_attack, pitch, overs=20):
    """Simulate one innings"""
    runs = 0
    wickets = 0
    balls_bowled = 0
    batter_idx = 0
    bowler_idx = 0
    last_batter = -1
    last_bowler = -1

    max_balls = overs * 6

    while balls_bowled < max_balls and batter_idx < len(batting_team):
        over_num = balls_bowled // 6 + 1
        ball_in_over = balls_bowled % 6 + 1

        batter = batting_team[batter_idx]
        bowler = bowling_attack[bowler_idx % len(bowling_attack)]

        if batter_idx != last_batter:
            print(f"✅ {batter['name']} comes to crease")
            last_batter = batter_idx

        if bowler_idx != last_bowler:
            print(f"\n{over_num}.{ball_in_over} {bowler['name']} to bowl")
            last_bowler = bowler_idx

        # Select ball based on bowler style
        ball = random.choice(BALL_LIBRARY[bowler["style"]])
        shot = random.choice(SHOTS)

        print(f"{bowler['name']} bowled {ball['type']}")

        # Get result
        if bowler["style"] == "pace":
            result = play_pace_ball(ball, shot, batter["bat_ovr"], bowler["bowl_ovr"], pitch, over_num)
        elif bowler["style"] == "offspin":
            result = play_offspin_ball(ball, shot, batter["bat_ovr"], bowler["bowl_ovr"], pitch, over_num)
        else:  # legspin
            result = play_legspin_ball(ball, shot, batter["bat_ovr"], bowler["bowl_ovr"], pitch, over_num)

        # Calculate runs
        if result == "dot":
            runs_this_ball = 0
            print("Dot ball")
        elif result == "1":
            runs_this_ball = 1
            print("1 run")
        elif result == "2":
            runs_this_ball = 2
            print("2 runs")
        elif result == "4":
            runs_this_ball = 4
            print("FOUR!")
        elif result == "6":
            runs_this_ball = 6
            print("SIX!")
        else:  # Wicket
            runs_this_ball = 0
            wickets += 1
            batter_idx += 1
            print("OUT!")

        runs += runs_this_ball
        balls_bowled += 1

        print(f"Score: {runs}/{wickets} ({balls_bowled//6}.{balls_bowled%6})")

        # Move bowler every 6 balls
        if ball_in_over == 6:
            bowler_idx += 1

    return runs, wickets, balls_bowled / 6

def simulate_match():
    """Simulate complete match on green pitch"""
    green_pitch = {"type": "green", "name": "🟢 GREEN PITCH (Seamer-Friendly)"}

    print("=" * 60)
    print("🏏 COMPLETE 20-OVER MATCH SIMULATION")
    print("🟢 GREEN PITCH (Heavy Pace)")
    print("Both Teams: 90 OVR")
    print("=" * 60)

    # Team A bats first
    print("\n🎯 FIRST INNINGS: Team A batting vs Team B bowling")
    team_a_score, team_a_wickets, team_a_overs = simulate_innings(TEAM_A_BATTERS, BOWLING_ATTACK_B, green_pitch, 20)
    print(f"Team A: {team_a_score}/{team_a_wickets} ({team_a_overs:.1f} overs)")

    # Team B bats second (chase)
    print("\n🎯 SECOND INNINGS: Team B batting vs Team A bowling")
    team_b_score, team_b_wickets, team_b_overs = simulate_innings(TEAM_B_BATTERS, BOWLING_ATTACK_A, green_pitch, 20)
    print(f"Team B: {team_b_score}/{team_b_wickets} ({team_b_overs:.1f} overs)")

    # Determine winner
    print("\n" + "=" * 60)
    print("🏆 MATCH RESULT")
    print("=" * 60)

    if team_a_score > team_b_score:
        margin = team_a_score - team_b_score
        print(f"🏆 Team A wins by {margin} runs!")
        print(f"Team A: {team_a_score}/{team_a_wickets}")
        print(f"Team B: {team_b_score}/{team_b_wickets}")
    elif team_b_score > team_a_score:
        if team_b_wickets < 10:  # Still have wickets remaining
            wickets_remaining = 10 - team_b_wickets
            print(f"🏆 Team B wins by {wickets_remaining} wickets!")
        else:  # All out but scored more
            margin = team_b_score - team_a_score
            print(f"🏆 Team B wins by {margin} runs!")
        print(f"Team B: {team_b_score}/{team_b_wickets}")
        print(f"Team A: {team_a_score}/{team_a_wickets}")
    else:
        print("🤝 Match tied!")
        print(f"Both teams: {team_a_score} runs")

    print(f"\n📊 Match Statistics:")
    print(f"Total Runs Scored: {team_a_score + team_b_score}")
    print(f"Total Wickets: {team_a_wickets + team_b_wickets}")
    print(f"Average Run Rate: {(team_a_score + team_b_score) / (team_a_overs + team_b_overs):.2f}")

if __name__ == "__main__":
    simulate_match()