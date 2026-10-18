"""Look for real fine-tunes whose declared license lacks obligations their parent's license carries.

    python -m scripts.find_cases meta-llama/Llama-3.2-1B 60

This only finds candidates. Run scripts.check on one and then read both
license pages yourself before you claim anything about it.
"""
import sys

from pedigree import hf
from pedigree.rules import INHERITABLE, LICENSES, resolve_license


def classify(carried, license_id, license_name):
    """Compare one child's declared license with what the parent's license carries."""
    if license_id is None:
        return "undeclared", []
    lic = resolve_license(license_id, license_name)
    if lic not in LICENSES:
        return "unknown", []
    missing = sorted(carried - LICENSES[lic])
    return ("gap", missing) if missing else ("ok", [])


def main():
    parent_id = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    parent = hf.fetch_model(parent_id)
    if parent is None:
        sys.exit(f"{parent_id} could not be read. Gated models may need HF_TOKEN.")
    parent_license = resolve_license(parent["license"], parent["license_name"])
    if parent_license not in LICENSES:
        sys.exit(f"{parent_id} declares `{parent_license}` and we have no rule for it.")
    carried = LICENSES[parent_license] & INHERITABLE
    print(f"parent {parent_id} declares `{parent_license}` which carries: {sorted(carried)}")
    api = hf._api()
    ids = [m.id for m in api.list_models(filter=f"base_model:finetune:{parent_id}", sort="downloads", limit=limit)]
    if not ids:
        sys.exit("The Hub returned no fine-tunes for that filter. Check the Model tree on the parent's page.")
    print(f"found {len(ids)} fine-tunes, reading each one...\n")
    tally = {"ok": 0, "gap": 0, "unknown": 0, "undeclared": 0}
    gaps = []
    for model_id in ids:
        try:
            rec = hf.fetch_model(model_id)
        except Exception as err:
            print("skipped", model_id, type(err).__name__)
            continue
        if rec is None:
            continue
        verdict, missing = classify(carried, rec["license"], rec["license_name"])
        tally[verdict] += 1
        if verdict == "gap":
            gaps.append((model_id, resolve_license(rec["license"], rec["license_name"]), missing))
    print("summary:", tally)
    print("\ncandidates (declared license lacks obligations the parent's license carries):")
    for model_id, lic, missing in gaps[:15]:
        print(f"  {model_id}  declares {lic}  missing {missing}")
        print(f"    https://huggingface.co/{model_id}")
    print("\nThese are candidates only. Read both license pages before you claim anything.")


if __name__ == "__main__":
    main()