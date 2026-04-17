import random

class Match:
    def __init__(self, p1, p2, overs, team1, team2):
        self.p1 = p1
        self.p2 = p2
        self.max_overs = overs
        self.max_balls = overs * 6
        self.innings = 1
        self.batting = None
        self.bowling = None
        self.striker = None
        self.non_striker = None
        self.current_bowler = None
        self.previous_bowler = None
        self.bowler_overs = {}
        self.target = None
        self.runs = 0
        self.wickets = 0
        self.balls = 0
        self.partnership_runs = 0
        self.partnership_balls = 0
        self.dismissed = set()
        self.batters = []
        self.timeline = []
        self.team1 = team1
        self.team2 = team2
        self.toss_allowed_user = None
        self.first_innings_score = None
        self.first_innings_overs = None
        self.first_innings_batting = {}
        self.first_innings_bowling = {}
        self.first_innings_striker = None
        self.first_innings_non_striker = None
        self.total_batting_stats = {}
        self.total_bowling_stats = {}
        self.batting_stats = {}
        self.bowling_stats = {}

        # Initialize stats for both teams
        for p in self.team1 + self.team2:
            self.batting_stats[p] = {"runs": 0, "balls": 0, "fours": 0, "sixes": 0}
            self.bowling_stats[p] = {"runs": 0, "balls": 0, "wickets": 0, "dots": 0}

    def start_second_innings(self):
        # Store 1st innings summary
        self.first_innings_score = f"{self.runs}/{self.wickets}"
        self.first_innings_overs = self.over()
        self.target = self.runs + 1
        self.innings = 2

        # Preserve first innings stats and strike state
        self.first_innings_batting = {p: stats.copy() for p, stats in self.batting_stats.items()}
        self.first_innings_bowling = {p: stats.copy() for p, stats in self.bowling_stats.items()}
        self.first_innings_striker = self.striker
        self.first_innings_non_striker = self.non_striker
        self.first_innings_current_bowler = self.current_bowler
        
        # Reset current stats
        self.runs = 0
        self.wickets = 0
        self.balls = 0
        self.previous_bowler = None
        self.bowler_overs = {}
        self.timeline = []
        self.partnership_runs = 0
        self.partnership_balls = 0
        self.dismissed = set()
        self.batters = []
        
        # Swap teams
        self.batting, self.bowling = self.bowling, self.batting
        self.striker = None
        self.non_striker = None
        self.current_bowler = None

    def record_delivery(self, runs=0, is_wicket=False):
        if not self.striker or not self.current_bowler:
            return

        self.balls += 1
        self.partnership_balls += 1
        
        # Update Batter Stats
        b_stats = self.batting_stats[self.striker]
        b_stats["balls"] += 1
        
        # Update Bowler Stats
        bowl_stats = self.bowling_stats[self.current_bowler]
        bowl_stats["balls"] += 1

        if is_wicket:
            self.wickets += 1
            bowl_stats["wickets"] += 1
            self.timeline.append("W")
            self.dismissed.add(self.striker)
            self.reset_partnership()
            return

        # Handle Runs
        self.runs += runs
        self.partnership_runs += runs
        b_stats["runs"] += runs
        bowl_stats["runs"] += runs

        if runs == 0:
            bowl_stats["dots"] += 1
            self.timeline.append("0")
        elif runs == 4:
            b_stats["fours"] += 1
            self.timeline.append("4")
        elif runs == 6:
            b_stats["sixes"] += 1
            self.timeline.append("6")
        else:
            self.timeline.append(str(runs))

        if runs % 2 == 1:
            self.swap_strike()

    def over(self):
        return f"{self.balls // 6}.{self.balls % 6}"

    def swap_strike(self):
        self.striker, self.non_striker = self.non_striker, self.striker

    def reset_partnership(self):
        self.partnership_runs = 0
        self.partnership_balls = 0

    def innings_over(self):
        """Return current innings/match end status."""
        if self.innings == 1:
            if self.wickets >= 10 or self.balls >= self.max_balls:
                return "FIRST_DONE"
            return None

        # Innings 2: match is complete when target is reached, all out, or overs exhausted
        if self.target is not None and self.runs >= self.target:
            return "MATCH_DONE"
        if self.wickets >= 10 or self.balls >= self.max_balls:
            return "MATCH_DONE"
        return None

    def over_end(self):
        """Return True when the current over has just completed."""
        return self.balls > 0 and self.balls % 6 == 0

    @property
    def batting_team_name(self):
        return self.batting.name if hasattr(self.batting, 'name') else "Team 1"

    @property
    def bowling_team_name(self):
        return self.bowling.name if hasattr(self.bowling, 'name') else "Team 2"