"""Optional exhaustive oracle: all 2,598,960 distinct five-card poker hands."""
from collections import Counter
from itertools import combinations
from pokerlab.cards import DECK, rank_hand

EXPECTED = {0: 1302540, 1: 1098240, 2: 123552, 3: 54912, 4: 10200,
            5: 5108, 6: 3744, 7: 624, 8: 40}
actual = Counter(rank_hand(h)[0] for h in combinations(DECK, 5))
assert actual == EXPECTED, (actual, EXPECTED)
print('PASS: all 2,598,960 five-card hands match the known category counts.')
