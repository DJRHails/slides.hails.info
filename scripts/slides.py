# /// script
# requires-python = ">=3.13"
# dependencies = ["click"]
# ///

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import click


TOTAL_SLIDES_PATTERN = re.compile(
    r"""(?mx)                  # multiline, verbose
    (?P<prefix>--total-slides:\s*)
    (?P<count>\d+)
    (?P<suffix>\s*;)
    """
)

SECTION_PATTERN = re.compile(
    r"""(?msx)                 # multiline, dotall, verbose
    ^[ \t]* <section           # slide section start
    \s+ class="slide\b[^"]*" # class attribute beginning with slide
    [^>]* >                    # remaining attributes
    [\s\S]*?                  # slide contents
    ^[ \t]* </section>         # slide section end
    """
)

SLIDE_COMMENT_ONLY_PATTERN = re.compile(
    r"""(?msx)                 # multiline, dotall, verbose
    ^ \s* <!--                 # opening comment, optional leading whitespace
    [\s\S]*?                  # comment body before the title line
    SLIDE \s+ \d+ : [^\n]*    # numbered slide title line
    [\s\S]*?                  # remainder of the comment body
    --> \s* $                  # closing comment and optional trailing whitespace
    """
)

DATA_SLIDE_PATTERN = re.compile(
    r"""(?mx)                  # multiline, verbose
    (?P<prefix>data-slide=")
    (?P<index>\d+)
    (?P<suffix>")
    """
)

VISIBLE_SLIDE_NUMBER_PATTERN = re.compile(
    r"""(?msx)                 # multiline, dotall, verbose
    <span \s+ class="slide-number">  # slide number element
    \s* \d+ \s* / \s* \d+ \s*      # current X / N text
    </span>
    """
)

COMMENT_SLIDE_NUMBER_PATTERN = re.compile(
    r"""(?mx)                  # multiline, verbose
    (?P<prefix>^[ \t]* SLIDE \s+)
    (?P<number>\d+)
    (?P<suffix> : [^\n]* $)
    """
)

TITLE_PATTERN = re.compile(
    r"""(?isx)                 # case-insensitive, dotall, verbose
    <h2 [^>]* > \s*            # heading start
    (?P<title>.*?)             # heading HTML
    \s* </h2>                  # heading end
    """
)

TAG_PATTERN = re.compile(
    r"""(?sx)                  # dotall, verbose
    < [^>]+ >                   # any HTML tag
    """
)


@dataclass(frozen=True)
class SlideBlock:
    html: str


@dataclass(frozen=True)
class Deck:
    prefix: str
    slides: list[SlideBlock]
    suffix: str


class DeckError(ValueError):
    pass


def split_lead(lead: str) -> tuple[str, str]:
    comment_start = lead.rfind("<!--")
    if comment_start == -1:
        return lead, ""

    while comment_start > 0 and lead[comment_start - 1].isspace():
        comment_start -= 1

    comment = lead[comment_start:]
    if not SLIDE_COMMENT_ONLY_PATTERN.fullmatch(comment):
        return lead, ""
    return lead[:comment_start], comment


def parse_deck(text: str) -> Deck:
    matches = list(SECTION_PATTERN.finditer(text))
    if not matches:
        raise DeckError("No slide sections found.")

    prefix = ""
    slides: list[SlideBlock] = []
    previous_end = 0
    for index, match in enumerate(matches):
        lead = text[previous_end : match.start()]
        head, comment = split_lead(lead)
        if index == 0:
            prefix = head
        elif head.strip():
            raise DeckError("Unexpected non-whitespace content between slides.")
        slides.append(SlideBlock(html=f"{comment}{match.group(0)}"))
        previous_end = match.end()

    suffix = text[previous_end:]
    return Deck(prefix=prefix, slides=slides, suffix=suffix)


def parse_single_slide(text: str) -> SlideBlock:
    deck = parse_deck(text)
    if len(deck.slides) != 1:
        raise DeckError("Snippet must contain exactly one slide section.")
    if f"{deck.prefix}{deck.suffix}".strip():
        raise DeckError("Snippet may only contain one slide block and whitespace.")
    return deck.slides[0]


def renumber_slide_block(block: SlideBlock, *, index: int, total: int) -> SlideBlock:
    html = DATA_SLIDE_PATTERN.sub(rf"\g<prefix>{index}\g<suffix>", block.html, count=1)
    html = VISIBLE_SLIDE_NUMBER_PATTERN.sub(
        f'<span class="slide-number">{index + 1} / {total}</span>',
        html,
        count=1,
    )
    html = COMMENT_SLIDE_NUMBER_PATTERN.sub(
        rf"\g<prefix>{index + 1}\g<suffix>",
        html,
        count=1,
    )
    return SlideBlock(html=html)


def rebuild_deck(deck: Deck) -> str:
    total = len(deck.slides)
    slides = [
        renumber_slide_block(slide, index=index, total=total).html
        for index, slide in enumerate(deck.slides)
    ]
    text = f"{deck.prefix}{''.join(slides)}{deck.suffix}"
    if TOTAL_SLIDES_PATTERN.search(text) is None:
        raise DeckError("Could not find --total-slides CSS variable.")
    return TOTAL_SLIDES_PATTERN.sub(rf"\g<prefix>{total}\g<suffix>", text, count=1)


def validate_position(*, position: int, total: int, label: str) -> None:
    if position < 1 or position > total:
        raise DeckError(f"{label} must be between 1 and {total}. Got {position}.")


def add_slide(text: str, snippet_text: str, *, after: int) -> str:
    deck = parse_deck(text)
    if after < 0 or after > len(deck.slides):
        raise DeckError(f"after must be between 0 and {len(deck.slides)}. Got {after}.")

    slides = list(deck.slides)
    slides.insert(after, parse_single_slide(snippet_text))
    return rebuild_deck(Deck(prefix=deck.prefix, slides=slides, suffix=deck.suffix))


def remove_slide(text: str, *, position: int) -> str:
    deck = parse_deck(text)
    validate_position(position=position, total=len(deck.slides), label="position")

    slides = list(deck.slides)
    del slides[position - 1]
    return rebuild_deck(Deck(prefix=deck.prefix, slides=slides, suffix=deck.suffix))


def move_slide(text: str, *, source: int, destination: int) -> str:
    deck = parse_deck(text)
    total = len(deck.slides)
    validate_position(position=source, total=total, label="source")
    validate_position(position=destination, total=total, label="destination")

    slides = list(deck.slides)
    slide = slides.pop(source - 1)
    slides.insert(destination - 1, slide)
    return rebuild_deck(Deck(prefix=deck.prefix, slides=slides, suffix=deck.suffix))


def extract_title(slide_html: str) -> str:
    match = TITLE_PATTERN.search(slide_html)
    if not match:
        return "(untitled slide)"
    return TAG_PATTERN.sub("", match.group("title")).strip() or "(untitled slide)"


@click.group()
def cli() -> None:
    """Manage HTML slide decks in place."""


@cli.command("add")
@click.argument(
    "deck_path", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
@click.argument(
    "snippet_path", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
@click.option(
    "--after",
    type=int,
    required=True,
    help="Insert after this 1-based slide number. Use 0 to prepend.",
)
def add_command(deck_path: Path, snippet_path: Path, after: int) -> None:
    """Insert a slide snippet into a deck."""
    updated = add_slide(deck_path.read_text(), snippet_path.read_text(), after=after)
    deck_path.write_text(updated)
    click.echo(
        f"Added '{extract_title(snippet_path.read_text())}' to {deck_path} after slide {after}."
    )


@cli.command("remove")
@click.argument(
    "deck_path", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
@click.argument("position", type=int)
def remove_command(deck_path: Path, position: int) -> None:
    """Remove a slide by its 1-based position."""
    deck_path.write_text(remove_slide(deck_path.read_text(), position=position))
    click.echo(f"Removed slide {position} from {deck_path}.")


@cli.command("move")
@click.argument(
    "deck_path", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
@click.argument("source", type=int)
@click.argument("destination", type=int)
def move_command(deck_path: Path, source: int, destination: int) -> None:
    """Move a slide from one 1-based position to another."""
    deck_path.write_text(
        move_slide(deck_path.read_text(), source=source, destination=destination)
    )
    click.echo(f"Moved slide {source} to {destination} in {deck_path}.")


def main() -> None:
    try:
        cli()
    except DeckError as error:
        raise click.ClickException(str(error)) from error


if __name__ == "__main__":
    main()
