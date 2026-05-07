# Repository Notes

## Slide decks

- Use `uv run scripts/slides.py` for structural slide edits.
- Supported commands:
  - `uv run scripts/slides.py add <deck.html> <snippet.html> --after <n>`
  - `uv run scripts/slides.py remove <deck.html> <n>`
  - `uv run scripts/slides.py move <deck.html> <from> <to>`
- The script is generic for decks built from `<section class="slide" ...>` blocks.
- Prefer the script over hand-editing `data-slide`, `--total-slides`, or visible `X / N` counters.
- Slide snippets for `add` must contain exactly one slide block, with optional surrounding whitespace.
