"""Example setup helper. Change these relative paths to suit your own project."""

import sys

from shacl_py.cli import main
from shacl_py.paper_review import ReviewLayout

layout = ReviewLayout(
    collection="research/papers",
    notes="README.md",
    notebooks="notebooks",
    raw="data/raw",
    outputs="data/output",
    shared=(("Shared code", "src"), ("Catalogue", "research/catalogue")),
)

if __name__ == "__main__":
    raise SystemExit(
        main(
            ["setup", "--template", "paper-review", *sys.argv[1:]], review_layout=layout
        )
    )
