"""Audit every product's live BC option-value labels against the corrected
product_option_values.csv (post word-order/blacklist fixes) and PUT-correct
any label whose token set matches but whose word order/spelling is stale
from before the fix - without touching the label's stable ID, so existing
variant references stay intact."""
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude/skills/commerce-admin/scripts"))
from bc_api import request  # noqa: E402


def load_csv(name):
    with open(name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def norm_tokens(s):
    return frozenset(re.findall(r"[a-z0-9]+", s.lower()))


product_ids = {r["family_id"]: r["bc_product_id"] for r in load_csv("bc_product_ids.csv")}
option_values = load_csv("product_option_values.csv")

correct_by_family_option = {}
for r in option_values:
    correct_by_family_option.setdefault((r["family_id"], r["option_name"]), set()).add(r["value_label"])

fixed, checked = 0, 0
for fid, pid in product_ids.items():
    status, resp = request("GET", f"/v3/catalog/products/{pid}/options")
    if status >= 300:
        print(f"FAILED to fetch options for product {pid}: {resp}")
        continue
    for opt in resp.get("data", []):
        correct_labels = correct_by_family_option.get((fid, opt["display_name"]))
        if not correct_labels:
            continue
        correct_by_tokens = {norm_tokens(lbl): lbl for lbl in correct_labels}
        for v in opt.get("option_values", []):
            checked += 1
            live_label = v["label"]
            if live_label in correct_labels:
                continue  # already correct
            toks = norm_tokens(live_label)
            correct_label = correct_by_tokens.get(toks)
            if correct_label is None:
                # Not just reordered - some merges lost a word entirely (e.g.
                # stale "Dark" where the correct value is "Dark Blonde").
                # Only apply when exactly one correct label is a superset of
                # the stale tokens, so we don't guess between ambiguous
                # candidates.
                supersets = [lbl for t, lbl in correct_by_tokens.items() if toks and toks.issubset(t)]
                if len(supersets) == 1:
                    correct_label = supersets[0]
            if correct_label and correct_label != live_label:
                pstatus, presp = request(
                    "PUT", f"/v3/catalog/products/{pid}/options/{opt['id']}/values/{v['id']}",
                    body={"label": correct_label},
                )
                if pstatus >= 300:
                    print(f"  FAILED to fix product {pid} option {opt['id']} value {v['id']}: {presp}")
                else:
                    fixed += 1
                    print(f"  Fixed product {pid} '{opt['display_name']}': {live_label!r} -> {correct_label!r}")

print(f"\nChecked {checked} option values, fixed {fixed} stale labels")
