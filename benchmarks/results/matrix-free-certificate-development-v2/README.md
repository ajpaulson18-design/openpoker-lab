# Saved-certificate integration controls

56 controls in normal and assertions-disabled Python; exact return codes and
durations are in the raw logs/statuses. Source pins cover the actual matrix-free
scripts/tests, not a full committed source closure. These are development
controls, not the saved 28-policy acceptance run. The older v1 evidence remains
unchanged. No saved study was evaluated by these controls.

Review corrected integer metric parsing and distinguished raw compact-input
fingerprints from the legacy expanded/normalized fingerprints. A new all-in
parent-flow fixture first failed because its in-memory stack tuple differed
from JSON's list; the fixture now round-trips JSON before binding its raw input.
That initial failure is retained in the chat tool output, not a separate file.
