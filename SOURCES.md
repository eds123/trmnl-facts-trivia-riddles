# Data sources

The plugin polls `https://eds123.github.io/trmnl-facts-trivia-riddles/data.json`, which is
rebuilt daily by `.github/workflows/data.yml` running `scripts/build_data.py`.

| Section | Source | Licence | Notes |
|---|---|---|---|
| Trivia | [Open Trivia Database](https://opentdb.com) | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | Fetched via the public API. Questions that only work with the multiple-choice options shown are skipped; true/false questions are prefixed "True or false:". |
| Facts (most days) | Wikipedia "Did you know" hooks, via the [derenrich/enwiki-did-you-know](https://huggingface.co/datasets/derenrich/enwiki-did-you-know) dataset | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | Imported once by `scripts/import_facts.py` into `data/facts.json`: hooks from 2017 onwards whose article drew at least 1,000 views on the day, rewritten as plain statements. Each links to its Wikipedia article. |
| Facts (about one day in six) | [Wikipedia "On this day"](https://en.wikipedia.org/api/rest_v1/) via the Wikimedia REST API | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | Curated anniversaries for the calendar date, labelled "On this day" in the plugin. Events involving violence or disasters are filtered out. |
| Riddles | [crawsome/riddles](https://github.com/crawsome/riddles) | [Unlicense](https://unlicense.org/) (public domain) | Bundled in `data/riddles.json` with light clean-up. |

The generated `data.json` and `history.json` are therefore published under CC BY-SA 4.0.
The plugin templates and scripts in this repository are MIT licensed (see `LICENSE`).

## Repeat avoidance

`history.json` records every item ever scheduled. An item is never shown again while any
unshown item remains in its pool; when a pool runs dry the least recently shown item is
reused. Facts are drawn per calendar date, so a given day's fact rotates through that
date's events over the years.
