# Facts, Trivia & Riddles for TRMNL

A daily brain snack for your [TRMNL](https://usetrmnl.com) e-ink display: one "Did you know?"
fact, one trivia question and one riddle, fresh every day, with answers printed upside down so
you can peek when you want.

![Full layout on the original TRMNL](assets/preview-full.png)

## What it shows

- **Fact**: a Wikipedia "Did you know?" hook most days, and an "On this day" anniversary for the
  current date about one day in six.
- **Trivia**: a question from the Open Trivia Database, with its category in the label.
- **Riddle**: a classic riddle.

Any section can be switched off, and you choose which one gets the large primary slot. Answers can
be shown upside down (the default), hidden until a time of your choosing, shown plainly, or never
shown.

Content is served from a daily feed built in this repository (see [How it works](#how-it-works)),
and every item is tracked so nothing repeats while unseen items remain. At the current pool sizes
a fact or trivia question takes years to come around again; riddles take a bit over a year.

## Layouts

All four TRMNL layouts are supported in landscape and portrait, on the original TRMNL and the
larger TRMNL X.

| Half horizontal | Half vertical | Quadrant |
|---|---|---|
| ![Half horizontal](assets/preview-half-horizontal.png) | ![Half vertical](assets/preview-half-vertical.png) | ![Quadrant](assets/preview-quadrant.png) |

![Full layout on TRMNL X](assets/preview-full-trmnl-x.png)

## Install

### As a recipe

The recipe is not published in the TRMNL recipe directory yet. Once it is, installing it from
**Plugins → Recipes** is the easiest route and needs no setup.

### As a private plugin

Use this if you want to run your own copy or tweak the templates.

<details>
<summary>Using trmnlp (recommended)</summary>

1. Install [trmnlp](https://github.com/usetrmnl/trmnlp) (`gem install trmnl_preview`, or use
   the Docker wrapper in `bin/trmnlp`).
2. Clone this repository and log in: `trmnlp login`.
3. Remove the `id:` line from `src/settings.yml` so a new plugin is created for your account,
   then run `trmnlp push`.

The plugin polls `https://eds123.github.io/trmnl-facts-trivia-riddles/data.json`, the feed built
by this repository. To host your own feed, fork the repo, enable GitHub Pages on the `gh-pages`
branch (the workflow creates it on its first run) and point `polling_url` at your fork.

</details>

<details>
<summary>Manually in the TRMNL dashboard</summary>

1. **Plugins → Private Plugin → New**. Set the strategy to **Polling** and the polling URL to
   `https://eds123.github.io/trmnl-facts-trivia-riddles/data.json`.
2. In the form builder, paste the `custom_fields` block from `src/settings.yml`.
3. Open **Edit Markup** and paste each file from `src/` into the matching tab: `full.liquid`,
   `half_horizontal.liquid`, `half_vertical.liquid`, `quadrant.liquid` and `shared.liquid`.
4. Save, then add the plugin to a playlist.

</details>

## Settings

| Setting | Options | Default | Notes |
|---|---|---|---|
| Show fact | on / off | on | |
| Show trivia | on / off | on | |
| Show riddle | on / off | on | |
| Primary section | Fact, Trivia, Riddle | Fact | Gets the large slot. Falls back to the first enabled section if the chosen one is off. |
| Answer display | Upside down, Reveal at a set time, Show plainly, Never show | Upside down | |
| Reveal time | time | 18:00 | Only used with "Reveal at a set time". Uses your account time zone. The device has to refresh after this time to pick up the answer. |

## How it works

```
GitHub Actions (daily, 03:17 UTC)
  scripts/build_data.py
    ├─ picks a fact, trivia question and riddle for every date up to 45 days ahead
    ├─ records every pick in history.json so nothing repeats while unseen items remain
    └─ publishes data.json + history.json to the gh-pages branch
GitHub Pages serves data.json
TRMNL polls it and the templates pick the entry for the user's local date
```

The feed is a JSON object keyed by date, covering the past week and the next 45 days:

```json
{
  "days": {
    "2026-09-22": {
      "fact":   { "kind": "dyk", "text": "…", "url": "https://en.wikipedia.org/wiki/…" },
      "trivia": { "category": "History", "difficulty": "hard", "question": "…", "answer": "…", "choices": ["…"] },
      "riddle": { "question": "…", "answer": "…" }
    }
  }
}
```

Because the feed is generated ahead of time, the plugin keeps working through short outages and
every device sees the same item on the same day. If the feed is unreachable the templates fall
back to a small built-in sample set.

Repeat avoidance: an item is never scheduled again while any unscheduled item remains in its
pool. When a pool runs dry, the least recently shown item is reused, so the gap between repeats
is always as long as the pool allows.

## Data sources and licences

| Section | Source | Licence |
|---|---|---|
| Trivia | [Open Trivia Database](https://opentdb.com) | CC BY-SA 4.0 |
| Facts | Wikipedia "Did you know?" hooks via [derenrich/enwiki-did-you-know](https://huggingface.co/datasets/derenrich/enwiki-did-you-know), and [Wikipedia "On this day"](https://en.wikipedia.org/api/rest_v1/) via the Wikimedia REST API | CC BY-SA 4.0 |
| Riddles | [crawsome/riddles](https://github.com/crawsome/riddles) | Unlicense (public domain) |

See [SOURCES.md](SOURCES.md) for details on how each source is filtered and attributed. The
generated `data.json` is published under CC BY-SA 4.0.

## Development

```sh
bin/trmnlp serve        # live preview at http://localhost:4567 (polls the real feed)
bin/trmnlp build        # renders each layout into _build/
```

To preview a specific day, override the clock in `.trmnlp.yml` with a Unix timestamp:

```yaml
variables:
  trmnl:
    system:
      timestamp_utc: 1790067600   # 2026-09-22 09:00 UTC
```

To build the feed locally (writes to `public/`, stdlib only):

```sh
python3 scripts/build_data.py                 # extend the schedule from today
python3 scripts/build_data.py 2026-10-01      # pretend today is another date
python3 scripts/build_data.py --reschedule-from 2026-09-14   # re-pick future days after a rule change
```

The GitHub workflow can be run by hand from the Actions tab. Its optional `reschedule_from`
input does the same as the flag above.

The facts pool in `data/facts.json` was imported once with `scripts/import_facts.py`, which needs
`pyarrow` and a local copy of the Hugging Face dataset. It does not run in CI.

## Licence

The templates and scripts are [MIT licensed](LICENSE). The content in `data/` and the generated
feed are licensed by their sources as listed above. Publishing the plugin as a TRMNL recipe also
places the markup under [CC BY 4.0](https://github.com/usetrmnl/plugin-license), as TRMNL
requires.
