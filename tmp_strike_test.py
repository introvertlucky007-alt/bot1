from match import Match

class Dummy:
    pass

m = Match(Dummy(), Dummy(), 2, ['a', 'b'], ['c', 'd'])
m.striker = 'a'
m.non_striker = 'b'
m.current_bowler = 'c'
print('before', m.striker, m.non_striker, m.balls)
m.record_delivery(1)
print('after', m.striker, m.non_striker, m.balls, 'over_end', m.over_end())
