# Pedigree

A fine-tuned model carries the license of the model it was made from. The fine-tune's own page on Hugging Face often says something different. Pedigree was built to catch that. It keeps models, datasets and licenses in a FalkorDB graph, follows a model up through its parents and points out where a parent's obligations seem to have gone missing.

Every flag shows the path it followed and links to the pages it came from, so a person can check it by hand in a minute. A flag only means someone should take a look. It is not a legal opinion.

It was made during Graph Hacks (WeMakeDevs and FalkorDB, October 15 to 18, 2026).

## Why a graph

Take a Llama 3.2 fine-tune that declares MIT. Llama 3.2 asks for a notice, a naming rule and an acceptable use policy and the MIT page mentions none of them. The gap only shows when the two pages are read side by side and real chains can run longer than two models. The author decided that made it a question about how things connect and the data went into a graph.

## What happens when a model is checked

Pedigree takes a model id like `org/name`. It reads the public metadata from the Hub (license, base model, declared datasets) and writes it into FalkorDB. Then it walks up the chain, between 1 and 6 levels, 4 by default. At each step it compares the declared license with what the parent's license requires.

Output looks like this. The model id is a placeholder because the real one belongs to someone else.

```
<fine-tune id> (depth 4): 1 to review, 0 warnings, 1 notes

[REVIEW] license_dropped
  path:   <fine-tune id> -> meta-llama/Llama-3.2-1B
  why:    declares mit, which does not carry derivative_naming, redistribution_notice,
          use_restrictions but its finetune parent is under llama3.2, which does.
  source: <fine-tune page>  <parent page>
```

Besides `license_dropped` there are warnings for unknown licenses and missing parents and a note when a model does not declare its training data.

## How FalkorDB fits in

The flag comes from walking the lineage in the graph and the path it walked is the explanation shown to the reader. Without the graph there would be nothing to show for a flag.

Checking a model again deletes its old parent links first. Model cards change and the graph should not keep a relationship the publisher has since removed.

Model ids come from the internet. So each one is matched against a strict `org/name` pattern before anything touches a query and depth is capped at 6.

## Running it

Python 3.12 and Docker are needed.

```
docker run -p 6379:6379 -it --rm falkordb/falkordb:latest

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

python -m pytest tests -q
python -m scripts.check <org/model-name>
```

Gated models need a Hugging Face token in the `HF_TOKEN` environment variable. A FalkorDB instance with a password reads it from `FALKORDB_PASSWORD`. Neither value is ever written to the repo.

## What was checked and what was not

Only the Llama 3 and Llama 3.2 rules were checked against the license text. Every other rule in `pedigree/rules.py` is marked unverified. So results for other licenses are leads and nothing more.

On October 18, 2026 the author read 60 of the most downloaded fine-tunes of Llama-3.2-1B. Six declared Apache-2.0 or MIT. The sample was picked by download count and is not random. So it says nothing about the Hub as a whole.

## Privacy

Pedigree reads public model metadata and asks for no personal data. Model ids belong to their authors. So the examples here and in the write-up avoid naming anyone.

## Track

Track 01, Agents That Act on Connected Data.

## Tests

`python -m pytest tests -q` passes with 30 tests at submission time.