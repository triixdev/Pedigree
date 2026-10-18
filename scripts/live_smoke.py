"""Run this on your own machine with internet access. It shows what the Hub really returns
for a few models so you can see whether Pedigree reads the lineage correctly.

    python -m scripts.live_smoke org/model-one org/model-two

For each model it prints the license and the parents and the datasets it found.
If a model that is clearly derived shows no parents then the Hub metadata has a gap.
That is a real finding and Pedigree should surface it and never hide it.
"""
import json
import sys

from pedigree import hf

ids = sys.argv[1:] or ["gpt2"]
for model_id in ids:
    print("=" * 60)
    try:
        rec = hf.fetch_model(model_id)
    except Exception as err:
        print(model_id, "-> ERROR", type(err).__name__, err)
        continue
    if rec is None:
        print(model_id, "-> not found, private or gated (set HF_TOKEN for gated models)")
        continue
    print(json.dumps(rec, indent=2, default=str))
    for data_id in rec["datasets"][:2]:
        print("dataset", data_id, "->", hf.fetch_dataset(data_id))