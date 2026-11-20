"""Short author lines for the viewer. Full names stay in the metadata."""


def surname(name):
    """Family name from "Given Family" or "Family, Given"."""
    name = " ".join(str(name).split())
    if "," in name:
        return name.split(",", 1)[0].strip()
    return name.rsplit(" ", 1)[-1]


def byline(surnames):
    """List form: "Viana et al.", "Gan and Ng" or "Gan"."""
    if len(surnames) > 2:
        return f"{surnames[0]} et al."
    return " and ".join(surnames)


def heading(surnames, limit=6):
    """Heading form: up to `limit` family names, then "et al."."""
    shown = ", ".join(surnames[:limit])
    return f"{shown} et al." if len(surnames) > limit else shown
