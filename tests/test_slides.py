from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import tempfile
import unittest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "slides.py"
SPEC = spec_from_file_location("slides_script", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Could not load {SCRIPT_PATH}")
SLIDES = module_from_spec(SPEC)
sys.modules[SPEC.name] = SLIDES
SPEC.loader.exec_module(SLIDES)


SAMPLE_DECK = """<!DOCTYPE html>
<html>
<head>
  <style>
    :root {
      --total-slides: 2;
    }
  </style>
</head>
<body>
    <!-- ===========================================
     SLIDE 1: TITLE
     =========================================== -->
    <section class="slide slide-dark" data-slide="0">
        <h2>First slide</h2>
        <span class="slide-number">1 / 2</span>
    </section>

    <!-- ===========================================
     SLIDE 2: SECOND
     =========================================== -->
    <section class="slide slide-light" data-slide="1">
        <h2>Second slide</h2>
        <span class="slide-number">2 / 2</span>
    </section>
</body>
</html>
"""

SNIPPET = """    <!-- ===========================================
     SLIDE 99: INSERTED
     =========================================== -->
    <section class="slide slide-dark" data-slide="99">
        <h2>Inserted slide</h2>
        <span class="slide-number">99 / 99</span>
    </section>
"""


class SlidesScriptTest(unittest.TestCase):
    def test_add_slide_renumbers_all_metadata(self) -> None:
        updated = SLIDES.add_slide(SAMPLE_DECK, SNIPPET, after=1)

        self.assertIn("--total-slides: 3;", updated)
        self.assertIn('data-slide="0"', updated)
        self.assertIn('data-slide="1"', updated)
        self.assertIn('data-slide="2"', updated)
        self.assertIn("SLIDE 2: INSERTED", updated)
        self.assertIn("1 / 3", updated)
        self.assertIn("2 / 3", updated)
        self.assertIn("3 / 3", updated)
        self.assertLess(updated.index("First slide"), updated.index("Inserted slide"))
        self.assertLess(updated.index("Inserted slide"), updated.index("Second slide"))

    def test_remove_slide_updates_total_and_order(self) -> None:
        updated = SLIDES.remove_slide(SAMPLE_DECK, position=1)

        self.assertIn("--total-slides: 1;", updated)
        self.assertNotIn("First slide", updated)
        self.assertIn("SLIDE 1: SECOND", updated)
        self.assertIn('data-slide="0"', updated)
        self.assertIn("1 / 1", updated)

    def test_move_slide_reorders_and_renumbers(self) -> None:
        three_slide_deck = SLIDES.add_slide(SAMPLE_DECK, SNIPPET, after=2)

        updated = SLIDES.move_slide(three_slide_deck, source=3, destination=1)

        self.assertLess(updated.index("Inserted slide"), updated.index("First slide"))
        self.assertLess(updated.index("First slide"), updated.index("Second slide"))
        self.assertIn("SLIDE 1: INSERTED", updated)
        self.assertIn("SLIDE 2: TITLE", updated)
        self.assertIn("SLIDE 3: SECOND", updated)

    def test_cli_remove_edits_file_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            deck_path = Path(temp_dir) / "deck.html"
            deck_path.write_text(SAMPLE_DECK)

            SLIDES.cli.main(args=["remove", str(deck_path), "2"], standalone_mode=False)
            updated = deck_path.read_text()
            self.assertIn("--total-slides: 1;", updated)
            self.assertNotIn("Second slide", updated)


if __name__ == "__main__":
    unittest.main()
