"""Reads public model and dataset metadata from the Hugging Face Hub.

Read only. The token is optional and comes from the HF_TOKEN environment
variable. The Hub records a derived model's parents in two places: the
model card (base_model) and generated tags. We read both and keep the
relation type (finetune, adapter, merge or quantized) when we find one.
"""
import os

from huggingface_hub import HfApi
from huggingface_hub.errors import HfHubHTTPError, RepositoryNotFoundError

from .graph import check_id

_RELATIONS = {"finetune", "adapter", "merge", "quantized"}


def _api():
    return HfApi(token=os.environ.get("HF_TOKEN") or None)


def _as_list(value):
    if value is None:
        return []
    return [value] if isinstance(value, str) else list(value)


def _is_missing(err):
    # not found and private and gated repos are facts about the model so we record them
    if isinstance(err, RepositoryNotFoundError):
        return True
    status = getattr(getattr(err, "response", None), "status_code", None)
    return isinstance(err, HfHubHTTPError) and status in (401, 403, 404)


def _valid(ids):
    good, skipped = [], []
    for i in ids:
        try:
            good.append(check_id(i))
        except ValueError:
            skipped.append(str(i))
    return good, skipped


def fetch_model(model_id):
    try:
        info = _api().model_info(model_id, timeout=15)
    except Exception as err:
        if _is_missing(err):
            return None
        raise  # a network problem must not be reported as a missing model
    card = info.card_data.to_dict() if getattr(info, "card_data", None) else {}
    relations = {}
    yaml_relation = card.get("base_model_relation")
    for base in _as_list(card.get("base_model")):
        relations[base] = yaml_relation if yaml_relation in _RELATIONS else None
    datasets = _as_list(card.get("datasets"))
    for tag in info.tags or []:
        parts = tag.split(":", 2)
        if parts[0] == "base_model" and len(parts) == 3 and parts[1] in _RELATIONS:
            relations[parts[2]] = parts[1]
        elif parts[0] == "dataset" and len(parts) == 2 and parts[1] not in datasets:
            datasets.append(parts[1])
    base_ids, skipped_bases = _valid(relations)
    dataset_ids, skipped_data = _valid(datasets)
    return {
        "id": model_id,
        "license": card.get("license"),
        "license_name": card.get("license_name"),
        "bases": [{"id": b, "relation": relations[b]} for b in base_ids],
        "datasets": dataset_ids,
        "skipped": skipped_bases + skipped_data,
        "last_modified": info.last_modified,
    }


def fetch_dataset(dataset_id):
    try:
        info = _api().dataset_info(dataset_id, timeout=15)
    except Exception as err:
        if _is_missing(err):
            return None
        raise
    card = info.card_data.to_dict() if getattr(info, "card_data", None) else {}
    return {"id": dataset_id, "license": card.get("license"), "license_name": card.get("license_name")}