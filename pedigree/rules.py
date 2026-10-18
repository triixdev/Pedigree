"""Simplified license vocabulary. Not legal advice.

Each license maps to a small set of obligation tags in our own words.
Tags in INHERITABLE are the ones we expect to travel with derivatives.
If a child declares a license that lacks one of them we raise a review
flag and never a legal conclusion.
"""

INHERITABLE = {
    "noncommercial", "share_alike", "no_derivatives",
    "use_restrictions", "redistribution_notice", "derivative_naming",
    "copyleft", "network_copyleft",
}

_CUSTOM = {"use_restrictions", "redistribution_notice"}
_LLAMA = _CUSTOM | {"derivative_naming"}

LICENSES = {
    "mit": {"attribution"},
    "apache-2.0": {"attribution"},
    "bsd-2-clause": {"attribution"},
    "bsd-3-clause": {"attribution"},
    "cc0-1.0": set(),
    "cc-by-4.0": {"attribution"},
    "cc-by-sa-4.0": {"attribution", "share_alike"},
    "cc-by-nc-4.0": {"attribution", "noncommercial"},
    "cc-by-nc-sa-4.0": {"attribution", "noncommercial", "share_alike"},
    "cc-by-nc-nd-4.0": {"attribution", "noncommercial", "no_derivatives"},
    "gpl-3.0": {"attribution", "copyleft"},
    "agpl-3.0": {"attribution", "copyleft", "network_copyleft"},
    "openrail": _CUSTOM,
    "openrail++": _CUSTOM,
    "bigscience-openrail-m": _CUSTOM,
    "creativeml-openrail-m": _CUSTOM,
    "llama2": _LLAMA,
    "llama3": _LLAMA,
    "llama3.1": _LLAMA,
    "llama3.2": _LLAMA,
    "llama3.3": _LLAMA,
    "gemma": _CUSTOM,
}

# Checked against the license text. Everything else is unverified.
VERIFIED = {
    "llama3": "use per Acceptable Use Policy; notice and 'Built with Meta Llama 3'; "
              "derivative model names start with 'Llama 3'",
    "llama3.2": "text on meta-llama/Llama-3.2-1B-Instruct LICENSE.txt: copy of the agreement "
                "and a notice file and 'Built with Llama' on redistribution; Acceptable Use "
                "Policy incorporated by reference; naming clause for models made with it",
}

# Licenses whose obligations we cannot evaluate.
UNKNOWN = {"unknown", "other"}


def norm_license(value):
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if value is None:
        return "unknown"
    v = str(value).strip().lower()
    return v or "unknown"


def resolve_license(license_id, license_name=None):
    """Hub models often declare 'other' plus a license name. Map it if we know the name."""
    lic = norm_license(license_id)
    if lic == "other" and license_name:
        name = str(license_name).strip().lower()
        if name in LICENSES:
            return name
    return lic