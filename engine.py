import random
from players import players

LABELS = ["dot","1","2","4","6","W"]
# Base probabilities for Normal Deliveries
BASE_LENGTH = {
    "Slow": {
        "Drive":  [25, 35, 15, 15, 5, 5],
        "Pull":   [20, 30, 10, 20, 15, 5],
        "Cut":    [30, 40, 10, 10, 5, 5],
        "Loft":   [15, 15, 5, 25, 30, 10],
        "Defend": [50, 45, 0, 0, 0, 5]
    },
    "Fast": {
        "Drive":  [30, 30, 10, 20, 5, 5],
        "Pull":   [25, 25, 10, 20, 15, 5],
        "Cut":    [35, 35, 10, 15, 0, 5],
        "Loft":   [20, 15, 5, 20, 25, 15],
        "Defend": [60, 35, 0, 0, 0, 5]
    }
}
# Additive Variation Modifiers
VARIATION_MOD = {
    "Yorker":       {"dot": +15, "1": -5, "2": -5, "4": -10, "6": -15, "W": +10},
    "Bouncer":      {"dot": +10, "1": -5, "2": +5, "4": -10, "6": +10, "W": +10},
    "Wide Yorker":  {"dot": +15, "1": +5, "2": 0, "4": -5, "6": -10, "W": +5},
    "Good Length":  {"dot": +10, "1": +5, "2": -5, "4": -10, "6": -5, "W": +5},
    "Full Length":  {"dot": -10, "1": +5, "2": +5, "4": +10, "6": +10, "W": -5},
    "Back of Length": {"dot": +10, "1": +5, "2": -5, "4": -10, "6": -10, "W": +10}
}
# Base probabilities for Swing Deliveries
BASE_SWING = {
    "Inswinger": {
        "Drive":  [35, 25, 10, 15, 5, 10],
        "Pull":   [30, 25, 10, 15, 10, 10],
        "Cut":    [40, 30, 10, 10, 0, 10],
        "Loft":   [25, 10, 5, 20, 20, 20],
        "Defend": [60, 35, 0, 0, 0, 5]
    },
    "Outswinger": {
        "Drive":  [35, 25, 10, 15, 5, 10],
        "Pull":   [30, 25, 10, 15, 10, 10],
        "Cut":    [40, 30, 10, 10, 0, 10],
        "Loft":   [25, 10, 5, 20, 20, 20],
        "Defend": [50, 45, 0, 0, 0, 5]
    }
}

def normalize(probs):
    total = sum(probs)
    if total <= 0: return [100, 0, 0, 0, 0, 0]
    return [round((p / total) * 100, 2) for p in probs]

def get_final_weights(base_weights, variation_name, shot_name):
    """
    Helper function to apply variation modifiers and normalize to 100.
    Includes safety overrides for the 'Defend' shot to keep it realistic.
    """
    mod = VARIATION_MOD.get(variation_name, {})
    final = list(base_weights)
    
    for i, label in enumerate(LABELS):
        change = mod.get(label, 0)
        
        # SPECIAL CASE: DEFEND SHOT SAFETY
        if shot_name == "Defend":
            # 1. Defend should never increase scoring chances (1, 2, 4, 6)
            if label in ["1", "2", "4", "6"] and change > 0:
                change = 0
            # 2. Prevent boundaries entirely for Defend
            if label in ["4", "6"]:
                final[i] = 0
                change = 0
                
        final[i] += change
        
        # Global floors
        if final[i] < 0: 
            final[i] = 0
            
    # Cap Wicket chance for Defend to 10% max so it stays 'safe'
    if shot_name == "Defend":
        wicket_idx = LABELS.index("W")
        if final[wicket_idx] > 10:
            final[wicket_idx] = 10
        
    # Re-normalize to 100
    total = sum(final)
    if total == 0: return base_weights
    
    return [round((w / total) * 100, 2) for w in final]

def apply_mod(probs, mod):
    probs = probs.copy()
    for i, label in enumerate(LABELS):
        if label in mod:
            probs[i] += mod[label]
    return normalize(probs)

BALL_TYPES = [
    "Yorker",
    "Bouncer",
    "Fast",
    "Slow",
    "Wide Yorker"
]

SHOT_TYPES = [
    "Drive",
    "Pull",
    "Cut",
    "Loft",
    "Defend"
]

def get_ovr(player_name):
    if not player_name:
        return 80, 80
    key = player_name.lower().replace(" ", "_")
    p = players.get(key)
    if not p:
        return 80, 80
    bat = p.get("bat_ovr") or p.get("ovr") or 80
    bowl = p.get("bowl_ovr") or p.get("ovr") or 80
    return bat, bowl


def generate_pitch():
    return random.choice([
        {"type": "green", "name": "🟢 Green Pitch"},
        {"type": "dry", "name": "🟤 Dry Pitch"},
        {"type": "flat", "name": "⚪ Flat Pitch"}
    ])


def apply_ovr_effect(probs, batter_ovr, bowler_ovr):
    """
    Skill gap scaling. Affects outcomes more realistically by weighting
    wicket, dot and boundary probabilities non-linearly.
    """
    gap = (batter_ovr - bowler_ovr) / 100.0
    momentum = abs(gap)
    new_probs = list(probs)

    if gap >= 0:
        new_probs[4] *= 1.0 + gap * (1.3 + 0.4 * momentum)
        new_probs[3] *= 1.0 + gap * (1.0 + 0.2 * momentum)
        new_probs[5] *= 1.0 - gap * (0.8 + 0.3 * momentum)
        new_probs[0] *= 1.0 - gap * (0.4 + 0.2 * momentum)
        new_probs[1] *= 1.0 + gap * 0.15
        new_probs[2] *= 1.0 + gap * 0.08
    else:
        pressure = -gap
        new_probs[4] *= max(0.1, 1.0 - pressure * (1.3 + 0.4 * momentum))
        new_probs[3] *= max(0.1, 1.0 - pressure * (1.0 + 0.2 * momentum))
        new_probs[5] *= 1.0 + pressure * (1.1 + 0.4 * momentum)
        new_probs[0] *= 1.0 + pressure * (0.7 + 0.3 * momentum)
        new_probs[1] *= max(0.05, 1.0 - pressure * 0.1)
        new_probs[2] *= max(0.05, 1.0 - pressure * 0.05)

    return normalize([max(0, p) for p in new_probs])

def apply_pitch_effect(probs, pitch, ball, over):
    """
    Adjusts probabilities based on pitch type and wear.
    Green: Pacer paradise.
    Dry: Spinner paradise.
    Flat: Batter paradise.
    """
    new_probs = list(probs)
    style = ball.get("style", "pace") # 'pace', 'offspin', 'legspin'
    
    # 1. GREEN PITCH (Grass, Seam, Swing)
    if pitch["type"] == "green":
        if style == "pace":
            new_probs[5] += 4.0  # +4% Wicket for pacers
            new_probs[0] += 5.0  # +5% Dots (beaten by swing)
            new_probs[3] -= 3.0  # Harder to hit 4s
        else:
            new_probs[5] -= 1.0  # Spinners less effective on grass
            new_probs[4] += 2.0  # Spinners go for more 6s on green decks

    # 2. DRY PITCH (Dusty, Cracking, Turning)
    elif pitch["type"] == "dry":
        if "spin" in style:
            new_probs[5] += 5.0  # Massive wicket boost for spinners
            new_probs[0] += 6.0  # Harder to rotate strike
            new_probs[3] -= 4.0  # Boundaries very hard
        else:
            new_probs[5] += 1.0  # Reverse swing possible
            new_probs[0] += 2.0

    # 3. FLAT PITCH (Road, Cement-like)
    elif pitch["type"] == "flat":
        new_probs[5] -= 3.0  # Bowlers struggle
        new_probs[3] += 5.0  # 4s everywhere
        new_probs[4] += 3.0  # 6s easier
        new_probs[0] -= 5.0  # Fewer dots

    return normalize([max(0, p) for p in new_probs])

def apply_match_context(probs, over, shot):
    """
    Death Overs (16-20) Logic: Higher aggression.
    """
    if over is None or over < 16:
        return probs
        
    new_probs = list(probs)
    # At the death, batsmen swing harder
    if shot != "Defend":
        new_probs[4] *= 1.4  # 40% boost to 6s
        new_probs[5] *= 1.2  # 20% increase in Wickets (slog risk)
        new_probs[0] *= 0.7  # Fewer dots (running hard/swinging)
        
    return normalize(new_probs)


SHOT_OPTIONS = ["Defend", "Drive", "Cut", "Pull", "Loft"]

SHOT_BASE_WEIGHTS = {
    "pace": {
        "default": {"Defend": 25, "Drive": 25, "Cut": 20, "Pull": 15, "Loft": 15},
        "Good Length": {"Defend": 25, "Drive": 30, "Cut": 25, "Pull": 10, "Loft": 10},
        "Full Length": {"Defend": 20, "Drive": 30, "Cut": 15, "Pull": 15, "Loft": 20},
        "Short": {"Defend": 15, "Drive": 15, "Cut": 15, "Pull": 25, "Loft": 30},
        "swing": {"Defend": 30, "Drive": 25, "Cut": 25, "Pull": 10, "Loft": 10},
        "Yorker": {"Defend": 30, "Drive": 25, "Cut": 15, "Pull": 10, "Loft": 20},
        "Bouncer": {"Defend": 10, "Drive": 15, "Cut": 10, "Pull": 30, "Loft": 35},
        "Wide Yorker": {"Defend": 35, "Drive": 20, "Cut": 15, "Pull": 10, "Loft": 20},
        "Back of Length": {"Defend": 20, "Drive": 25, "Cut": 20, "Pull": 15, "Loft": 20},
    },
    "offspin": {
        "default": {"Defend": 30, "Drive": 25, "Cut": 20, "Pull": 10, "Loft": 15},
        "Off Break": {"Defend": 30, "Drive": 25, "Cut": 20, "Pull": 10, "Loft": 15},
        "Doosra": {"Defend": 35, "Drive": 20, "Cut": 25, "Pull": 10, "Loft": 10},
        "Arm Ball": {"Defend": 30, "Drive": 25, "Cut": 20, "Pull": 10, "Loft": 15},
        "Flighted": {"Defend": 25, "Drive": 20, "Cut": 20, "Pull": 15, "Loft": 20},
        "Quicker One": {"Defend": 15, "Drive": 20, "Cut": 15, "Pull": 20, "Loft": 30},
    },
    "legspin": {
        "default": {"Defend": 30, "Drive": 25, "Cut": 25, "Pull": 10, "Loft": 10},
        "Leg Break": {"Defend": 30, "Drive": 25, "Cut": 25, "Pull": 10, "Loft": 10},
        "Top Spinner": {"Defend": 30, "Drive": 20, "Cut": 25, "Pull": 10, "Loft": 15},
        "Googly": {"Defend": 35, "Drive": 20, "Cut": 30, "Pull": 5, "Loft": 10},
        "Flipper": {"Defend": 35, "Drive": 20, "Cut": 25, "Pull": 10, "Loft": 10},
        "Slider": {"Defend": 30, "Drive": 25, "Cut": 25, "Pull": 10, "Loft": 10},
    },
}


def choose_shot(ball, batter_ovr=80, bowler_ovr=80, pitch=None, over=None):
    style = ball.get("style", "pace")
    if style not in SHOT_BASE_WEIGHTS:
        style = "pace"

    variation = ball.get("variation", "")
    length = ball.get("length", "")
    swing = str(ball.get("swing", "")).lower()

    weights = SHOT_BASE_WEIGHTS[style].get(variation) or SHOT_BASE_WEIGHTS[style].get(length) or SHOT_BASE_WEIGHTS[style]["default"]
    weights = dict(weights)

    if style == "pace" and swing in {"in", "out", "inswinger", "outswinger"}:
        weights = dict(SHOT_BASE_WEIGHTS["pace"]["swing"])

    gap = (batter_ovr - bowler_ovr) / 100.0
    if gap > 0:
        attack_boost = min(0.5, gap * 1.2)
        weights["Loft"] *= 1 + attack_boost * 1.2
        weights["Pull"] *= 1 + attack_boost * 0.9
        weights["Drive"] *= 1 + attack_boost * 0.7
        weights["Defend"] *= max(0.5, 1 - attack_boost * 0.35)
    else:
        defense_boost = min(0.6, -gap * 1.4)
        weights["Defend"] *= 1 + defense_boost * 1.3
        weights["Cut"] *= 1 + defense_boost * 0.6
        weights["Loft"] *= max(0.2, 1 - defense_boost * 0.8)
        weights["Pull"] *= max(0.3, 1 - defense_boost * 0.4)

    if over is not None and over >= 16:
        weights["Loft"] *= 1.15
        weights["Pull"] *= 1.1
        weights["Drive"] *= 1.05
        weights["Defend"] *= 0.9

    if pitch:
        if pitch["type"] == "flat":
            weights["Loft"] *= 1.1
            weights["Drive"] *= 1.05
        elif pitch["type"] == "green" and style == "pace":
            weights["Defend"] *= 1.1
            weights["Cut"] *= 1.05
        elif pitch["type"] == "dry" and style in {"offspin", "legspin"}:
            weights["Defend"] *= 1.05
            weights["Cut"] *= 1.05

    final_weights = [max(0.1, weights.get(s, 1)) for s in SHOT_OPTIONS]
    return random.choices(SHOT_OPTIONS, weights=final_weights)[0]


def play_pace_ball(ball, shot, batter_ovr=80, bowler_ovr=80, pitch=None, over=None):

    length = ball.get("length")
    variation = ball.get("variation")
    swing = ball.get("swing")

    # BASE
    if swing:
        base = BASE_SWING.get(swing, BASE_LENGTH["Slow"])
    else:
        base = BASE_LENGTH.get(length, BASE_LENGTH["Slow"])
    base_weights = base.get(shot)

    if not base_weights:
        base_weights = [30,30,15,10,5,10]

    # APPLY VARIATION MOD AND NORMALIZE
    probs = get_final_weights(base_weights, variation, shot)

    # APPLY PITCH EFFECT
    if pitch:
        probs = apply_pitch_effect(probs, pitch, ball, over)

    # APPLY OVR EFFECT
    probs = apply_ovr_effect(probs, batter_ovr, bowler_ovr)

    # APPLY MATCH CONTEXT
    probs = apply_match_context(probs, over, shot)

    result = random.choices(LABELS, weights=probs)[0]

    return result

OFFSPIN_PROBS = {
    "Off Break": {
        "Drive":  [30, 35, 15, 10, 5, 5],
        "Pull":   [20, 25, 10, 20, 20, 5],
        "Cut":    [30, 30, 15, 15, 5, 5],
        "Loft":   [20, 15, 5, 25, 20, 15],
        "Defend": [40, 58, 0, 0, 0, 2] # 2% Wicket risk
    },
    "Doosra": {
        "Drive":  [35, 25, 15, 10, 5, 10], # Higher risk of edge
        "Pull":   [40, 20, 10, 10, 10, 10],
        "Cut":    [25, 30, 20, 15, 5, 5],  # Best shot vs Doosra
        "Loft":   [20, 10, 5, 20, 15, 30], # Very high risk
        "Defend": [53, 45, 0, 0, 0, 2]
    },
    "Arm Ball": {
        "Drive":  [25, 35, 20, 10, 5, 5],
        "Pull":   [35, 25, 10, 15, 10, 5],
        "Cut":    [40, 25, 10, 10, 5, 10], # Risky due to straight line
        "Loft":   [15, 15, 10, 25, 15, 20],
        "Defend": [35, 63, 0, 0, 0, 2]
    },
    "Flighted": {
        "Drive":  [15, 30, 20, 25, 5, 5],  # Good for runs
        "Pull":   [40, 25, 10, 10, 10, 5],
        "Cut":    [30, 30, 15, 15, 5, 5],
        "Loft":   [20, 10, 5, 30, 25, 10], # High reward
        "Defend": [58, 40, 0, 0, 0, 2]
    },
    "Quicker One": {
        "Drive":  [40, 25, 10, 15, 5, 5],
        "Pull":   [25, 25, 10, 20, 15, 5],
        "Cut":    [30, 35, 15, 10, 5, 5],
        "Loft":   [10, 15, 15, 25, 10, 25], # Hard to time
        "Defend": [63, 35, 0, 0, 0, 2]
    }
}

def play_offspin_ball(ball, shot, batter_ovr=80, bowler_ovr=80, pitch=None, over=None):
    base_type = ball.get("type", "Off Break")
    base = OFFSPIN_PROBS.get(base_type, OFFSPIN_PROBS["Off Break"])
    probs = list(base.get(shot, [30, 30, 15, 10, 5, 10]))

    # 1. APPLY PITCH EFFECT
    if pitch:
        probs = apply_pitch_effect(probs, pitch, ball, over)

    # 2. APPLY OVR EFFECT
    probs = apply_ovr_effect(probs, batter_ovr, bowler_ovr)

    # 3. APPLY MATCH CONTEXT
    probs = apply_match_context(probs, over, shot)

    # 4. FINAL CRICKET LOGIC OVERRIDE
    if shot == "Defend":
        wicket_idx = LABELS.index("W")
        # Ensure defend is always safe (max 2% regardless of OVR)
        if probs[wicket_idx] > 2.0:
            diff = probs[wicket_idx] - 2.0
            probs[0] += diff # Add the extra risk back to Dot balls
            probs[wicket_idx] = 2.0
        
        # Ensure no boundaries for defend
        probs[3] = 0 # 4s
        probs[4] = 0 # 6s

    result = random.choices(LABELS, weights=probs)[0]
    return result

# LEG SPIN SYSTEM
# Leg spin is higher risk/higher reward than off-spin. 
# Wicket chances are naturally higher for attacking shots due to drift and dip.

LEGSPIN_PROBS = {
    "Leg Break": {
        "Drive":  [25, 30, 15, 15, 5, 10], # Standard risk
        "Pull":   [20, 25, 10, 20, 15, 10], # Good vs short leg-break
        "Cut":    [25, 30, 20, 15, 5, 5],   # Safer to play with the spin
        "Loft":   [20, 15, 5, 20, 25, 15],  # High reward, chance of stumping
        "Defend": [58, 40, 0, 0, 0, 2]     # Strict 2% W rule
    },

    "Top Spinner": {
        "Drive":  [35, 25, 10, 15, 5, 10], # Extra bounce causes edges
        "Pull":   [30, 20, 10, 15, 10, 15], # Harder to pull due to bounce
        "Cut":    [30, 30, 10, 15, 5, 10], 
        "Loft":   [20, 10, 10, 25, 15, 20], 
        "Defend": [63, 35, 0, 0, 0, 2]
    },

    "Googly": {
        "Drive":  [40, 20, 10, 10, 5, 15], # Very dangerous to drive (inside edge/bowled)
        "Pull":   [25, 25, 15, 15, 5, 15], 
        "Cut":    [45, 20, 10, 5, 5, 15],  # Hardest shot vs Googly (wrong-un)
        "Loft":   [15, 10, 5, 20, 15, 35], # Massive risk of missing the ball
        "Defend": [43, 55, 0, 0, 0, 2]
    },

    "Flipper": {
        "Drive":  [30, 30, 15, 10, 5, 10],
        "Pull":   [40, 20, 10, 10, 5, 15], # Skids on, dangerous to pull
        "Cut":    [45, 25, 5, 10, 5, 10],  # Skids through, high LBW risk
        "Loft":   [10, 15, 10, 30, 15, 20],
        "Defend": [53, 45, 0, 0, 0, 2]
    },

    "Slider": {
        "Drive":  [25, 35, 20, 10, 5, 5],  # Best ball to drive (slides on)
        "Pull":   [35, 25, 10, 15, 10, 5], 
        "Cut":    [35, 30, 15, 10, 5, 5], 
        "Loft":   [20, 15, 10, 25, 20, 10], 
        "Defend": [50, 48, 0, 0, 0, 2]
    }
}

def play_legspin_ball(ball, shot, batter_ovr=80, bowler_ovr=80, pitch=None, over=None):
    base_type = ball.get("type", "Leg Break")
    base = LEGSPIN_PROBS.get(base_type, LEGSPIN_PROBS["Leg Break"])
    probs = list(base.get(shot, [30, 30, 15, 10, 5, 10]))

    # 1. APPLY PITCH EFFECT
    if pitch:
        probs = apply_pitch_effect(probs, pitch, ball, over)

    # 2. APPLY OVR EFFECT
    probs = apply_ovr_effect(probs, batter_ovr, bowler_ovr)

    # 3. APPLY MATCH CONTEXT
    probs = apply_match_context(probs, over, shot)

    # 4. FINAL CRICKET LOGIC OVERRIDE
    if shot == "Defend":
        wicket_idx = 5 # LABELS.index("W")
        # Ensure defend is always safe (max 2% regardless of OVR/Pitch)
        if probs[wicket_idx] > 2.0:
            diff = probs[wicket_idx] - 2.0
            probs[0] += diff # Convert extra risk into dot ball
            probs[wicket_idx] = 2.0
        
        # Ensure no boundaries for defend
        probs[3] = 0 # 4s
        probs[4] = 0 # 6s

    result = random.choices(["dot", "1", "2", "4", "6", "W"], weights=probs)[0]
    return result

def play_ball(ball, shot, batter_ovr=80, bowler_ovr=80, pitch=None, over=None):
    """
    The Master Logic Function
    """
    style = ball.get("style", "pace")
    
    # 1. GET BASE WEIGHTS
    if style == "pace":
        length = ball.get("length", "Fast")
        variation = ball.get("variation", "Good Length")
        swing = ball.get("swing")
        
        if swing:
            base = BASE_SWING.get(swing, BASE_LENGTH["Fast"])
        else:
            base = BASE_LENGTH.get(length, BASE_LENGTH["Fast"])
            
        base_weights = base.get(shot, [30, 30, 15, 10, 5, 10])
        # Apply Variation (Yorker/Bouncer/etc)
        probs = get_final_weights(base_weights, variation, shot)
        
    else: # Spinner
        spin_system = OFFSPIN_PROBS if style == "offspin" else LEGSPIN_PROBS
        base_type = ball.get("type", "Off Break" if style == "offspin" else "Leg Break")
        base = spin_system.get(base_type, {})
        probs = list(base.get(shot, [30, 30, 15, 10, 5, 10]))

    # 2. APPLY ENVIRONMENTAL EFFECTS
    if pitch:
        probs = apply_pitch_effect(probs, pitch, ball, over)

    # 3. APPLY MATCH CONTEXT (Death overs)
    probs = apply_match_context(probs, over, shot)

    # 4. APPLY OVR EFFECT
    probs = apply_ovr_effect(probs, batter_ovr, bowler_ovr)

    # 5. THE 'DEFEND' MANDATE (Safety Check)
    if shot == "Defend":
        w_idx = 5
        # Force Defend to be safe (max 2% W)
        if probs[w_idx] > 2.0:
            surplus = probs[w_idx] - 2.0
            probs[0] += surplus # Move risk to Dot
            probs[w_idx] = 2.0
        # Force 0 boundaries for Defend
        probs[3] = 0
        probs[4] = 0

    # 6. FINAL RESULT
    result = random.choices(LABELS, weights=probs)[0]
    return result