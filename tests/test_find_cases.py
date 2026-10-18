from scripts.find_cases import classify

LLAMA = {"use_restrictions", "redistribution_notice", "derivative_naming"}


def test_permissive_child_of_llama_is_a_gap():
    verdict, missing = classify(LLAMA, "apache-2.0", None)
    assert verdict == "gap" and missing == ["derivative_naming", "redistribution_notice", "use_restrictions"]


def test_same_family_license_is_ok():
    assert classify(LLAMA, "llama3.2", None) == ("ok", [])
    assert classify(LLAMA, "other", "llama3") == ("ok", [])


def test_unknown_and_undeclared_are_never_called_ok():
    assert classify(LLAMA, "other", None) == ("unknown", [])
    assert classify(LLAMA, None, None) == ("undeclared", [])


def test_parent_with_nothing_inheritable_gives_no_gap():
    assert classify(set(), "mit", None) == ("ok", [])