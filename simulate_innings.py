"""
Simulate innings with random XI and bowling attack on all 3 pitches
"""
import random
from engine import (
    play_pace_ball, play_offspin_ball, play_legspin_ball,
    generate_pitch, apply_ovr_effect, apply_pitch_effect, normalize,
    choose_shot
)
from players import players

# Parse available players
all_players = list(players.values())
batters = [p for p in all_players if p["role"] == "Batter"]
bowlers = [p for p in all_players if p["role"] == "Bowler"]

# Determine bowling style based on type
def get_bowling_style(bowl_type):
    if "leg" in bowl_type.lower():
        return "legspin"
    elif "off" in bowl_type.lower():
        return "offspin"
    else:
        return "pace"

BALL_LIBRARY = {
    "pace": [
        {"style": "pace", "type": "Pace", "length": "Good Length", "variation": "None", "swing": "None"},
        {"style": "pace", "type": "Pace", "length": "Good Length", "variation": "None", "swing": "Out"},
        {"style": "pace", "type": "Pace", "length": "Full Length", "variation": "None", "swing": "None"},
        {"style": "pace", "type": "Pace", "length": "Short", "variation": "None", "swing": "None"},
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

def simulate_innings(overs, pitches_to_test, batting_xi, bowling_attack):
    """Simulate innings with given overs on specified pitches"""
    
    results = {}
    
    for pitch in pitches_to_test:
        print(f"\n{'='*60}")
        print(f"PITCH: {pitch['name']}")
        print(f"{'='*60}\n")
        
        runs = 0
        wickets = 0
        balls_bowled = 0
        batter_idx = 0
        bowler_idx = 0
        
        # Track stats
        ball_outcomes = []
        
        # Max balls = overs * 6
        max_balls = overs * 6
        
        while balls_bowled < max_balls and batter_idx < len(batting_xi):
            over_num = balls_bowled // 6 + 1
            ball_in_over = balls_bowled % 6 + 1
            
            batter = batting_xi[batter_idx]
            bowler = bowling_attack[bowler_idx % len(bowling_attack)]
            
            # Select ball based on bowler style
            ball = random.choice(BALL_LIBRARY[bowler["style"]])
            shot = choose_shot(ball, batter["bat_ovr"], bowler["bowl_ovr"], pitch, over_num)
            
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
            elif result == "1":
                runs_this_ball = 1
            elif result == "2":
                runs_this_ball = 2
            elif result == "4":
                runs_this_ball = 4
            elif result == "6":
                runs_this_ball = 6
            else:  # Wicket
                runs_this_ball = 0
                wickets += 1
                batter_idx += 1
                
            runs += runs_this_ball
            balls_bowled += 1
            
            ball_outcomes.append({
                "over": over_num,
                "ball": ball_in_over,
                "batter": batter["name"],
                "bowler": bowler["name"],
                "result": result,
                "runs": runs_this_ball
            })
            
            # Move bowler every 6 balls
            if ball_in_over == 6:
                bowler_idx += 1
        
        # Print summary
        print(f"Over {overs}: Final Score: {runs}/{wickets}")
        
        results[pitch["type"]] = {
            "name": pitch["name"],
            "runs": runs,
            "wickets": wickets,
            "overs": balls_bowled / 6,
            "outcomes": ball_outcomes
        }
    
    return results


# Run simulation on all 3 pitches for 20 overs
if __name__ == "__main__":
    pitches = [
        {"type": "green", "name": "🟢 GREEN PITCH (Seamer-Friendly)"},
        {"type": "dry", "name": "🟤 DRY PITCH (Spin-Friendly)"},
        {"type": "flat", "name": "⚪ FLAT PITCH (Batting-Friendly)"},
    ]

    # Use consistent 90 OVR teams for head-to-head comparison
    batting_xi = [
        {"name": "Batter 1", "bat_ovr": 90},
        {"name": "Batter 2", "bat_ovr": 90},
        {"name": "Batter 3", "bat_ovr": 90},
        {"name": "Batter 4", "bat_ovr": 90},
        {"name": "Batter 5", "bat_ovr": 90},
        {"name": "Batter 6", "bat_ovr": 90},
        {"name": "Batter 7", "bat_ovr": 90},
        {"name": "Batter 8", "bat_ovr": 90},
        {"name": "Batter 9", "bat_ovr": 90},
        {"name": "Batter 10", "bat_ovr": 90},
        {"name": "Batter 11", "bat_ovr": 90},
    ]

    bowling_attack = [
        {"name": "Pacer 1", "bowl_ovr": 90, "style": "pace"},
        {"name": "Pacer 2", "bowl_ovr": 90, "style": "pace"},
        {"name": "Spinner 1", "bowl_ovr": 90, "style": "offspin"},
        {"name": "Spinner 2", "bowl_ovr": 90, "style": "legspin"},
        {"name": "Pacer 3", "bowl_ovr": 90, "style": "pace"},
    ]

    print("=" * 60)
    print("90 OVR TEAM SIMULATION - 20 OVERS")
    print("=" * 60)
    print("\n🏏 BATTING XI:")
    for i, batter in enumerate(batting_xi, 1):
        print(f"  {i}. {batter['name']} ({batter['bat_ovr']} OVR)")

    print("\n🎯 BOWLING ATTACK:")
    for i, bowler in enumerate(bowling_attack, 1):
        print(f"  {i}. {bowler['name']} ({bowler['bowl_ovr']} OVR - {bowler['style'].upper()})")

    print("\n" + "=" * 60)

    results = simulate_innings(20, pitches, batting_xi, bowling_attack)

    # Summary
    print(f"\n{'='*60}")
    print("PITCH COMPARISON")
    print(f"{'='*60}")
    for pitch_type in ["green", "dry", "flat"]:
        r = results[pitch_type]
        print(f"\n{r['name']}")
        print(f"  Final Score: {r['runs']}/{r['wickets']} ({r['overs']:.1f} overs)")
        print(f"  Run Rate: {r['runs'] / r['overs']:.2f} runs/over")
