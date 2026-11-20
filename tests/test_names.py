from shacl_py.names import byline, heading, surname


def test_surname():
    assert surname("Matheus P Viana") == "Viana"
    assert surname("Rory M Donovan-Maiye") == "Donovan-Maiye"
    assert surname("Viana, Matheus P") == "Viana"
    assert surname("Shavindra") == "Shavindra"


def test_byline():
    assert byline([]) == ""
    assert byline(["Gan"]) == "Gan"
    assert byline(["Gan", "Ng"]) == "Gan and Ng"
    assert byline(["Viana", "Chen", "Vasan"]) == "Viana et al."


def test_heading():
    six = ["Borrelli", "Pirone", "Miccio", "Memmolo", "Ferraro", "Bianco"]
    assert heading(six) == ", ".join(six)
    assert heading(six + ["Extra"]) == ", ".join(six) + " et al."
    assert heading(six, limit=2) == "Borrelli, Pirone et al."
