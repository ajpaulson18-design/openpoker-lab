# Contributing

Run locally with Python 3.11+ and run `python -m unittest discover -s tests -v`.
Keep new dependencies justified and avoid silently changing the game's rules.

For a bug, provide the cards, ranges, bet sizes, seed, expected behavior, actual
behavior, and Python version. Do not include personal opponent records or private
hand notes. Use synthetic examples whenever possible.

For model changes, document which probabilities are learned and which remain
assumptions. Add a regression case or a measurable statistical benchmark. A UI
percentage is not evidence that a strategy is equilibrium or that a model is
calibrated.

Do not commit `data/`, databases, credentials, proprietary solver output, or
copied commercial interfaces. Pull requests should explain the problem, change,
validation, and remaining limitations.
