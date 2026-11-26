"""Cards shown on the home page = the Hive test catalog. Card clicks are tracked per test id/title."""

from .catalog import CATALOG, public_card

CARDS = [public_card(c) for c in CATALOG]
CARDS_BY_ID = {c["id"]: c for c in CARDS}
