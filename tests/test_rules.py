from pedigree.rules import resolve_license, LICENSES, INHERITABLE


def test_other_plus_name_resolves():
    assert resolve_license("other", "llama3") == "llama3"
    assert resolve_license("other", "mystery") == "other"
    assert resolve_license(None) == "unknown"


def test_llama_carries_what_apache_does_not():
    inherited = LICENSES["llama3"] & INHERITABLE
    assert inherited
    assert not (inherited & LICENSES["apache-2.0"])