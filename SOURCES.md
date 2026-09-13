# Data sources

The plugin polls `https://eds123.github.io/trmnl-facts-trivia-riddles/data.json`, which is
rebuilt daily by `.github/workflows/data.yml` running `scripts/build_data.py`.

| Section | Source | Licence | Notes |
|---|---|---|---|
| Trivia | [Open Trivia Database](https://opentdb.com) | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | Fetched via the public API. Questions that only work with the multiple-choice options shown are skipped; true/false questions are prefixed "True or false:". |
| Facts | [Wikipedia "On this day"](https://en.wikipedia.org/api/rest_v1/) via the Wikimedia REST API | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | Each fact links to its Wikipedia article. Events involving violence or disasters are filtered out. |
| Riddles | [crawsome/riddles](https://github.com/crawsome/riddles) | [Unlicense](https://unlicense.org/) (public domain) | Bundled in `data/riddles.json` with light clean-up. |

The generated `data.json` and `history.json` are therefore published under CC BY-SA 4.0.
The plugin templates and scripts in this repository are MIT licensed (see `LICENSE`).

## Repeat avoidance

`history.json` records every item ever scheduled. An item is never shown again while any
unshown item remains in its pool; when a pool runs dry the least recently shown item is
reused. Facts are drawn per calendar date, so a given day's fact rotates through that
date's events over the years.
