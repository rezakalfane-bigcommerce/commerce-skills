import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude/skills/commerce-admin/scripts"))
from bc_api import request  # noqa: E402

TREE_IDS = [1, 2]
BATCH_SIZE = 10


def load_rows():
    with open("categories.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def url_path_for(slug: str) -> str:
    return f"/{slug}/"


def batched(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def create_level(tree_id, rows, local_to_bc):
    """rows: list of our local-id category dicts, all at the same tree depth,
    whose parent's BC id is already known in local_to_bc."""
    payload = []
    for r in rows:
        parent_local = int(r["parent_id"])
        parent_bc = 0 if parent_local == 0 else local_to_bc[parent_local]
        payload.append({
            "name": r["name"][:50],
            "tree_id": tree_id,
            "parent_id": parent_bc,
            "sort_order": int(r["sort_order"]),
            "url": {"path": url_path_for(r["slug"]), "is_customized": True},
        })

    created_ids = []
    for chunk, chunk_rows in zip(batched(payload, BATCH_SIZE), batched(rows, BATCH_SIZE)):
        status, resp = request("POST", "/v3/catalog/trees/categories", body=chunk)
        if status >= 300:
            print(f"  ERROR tree {tree_id}: {resp}")
            raise SystemExit(1)
        data = resp.get("data", [])
        meta = resp.get("meta", {})
        if meta.get("failed"):
            print(f"  WARNING tree {tree_id}: {meta['failed']} failed in this chunk")
            print(f"  response: {resp}")
        for local_row, created in zip(chunk_rows, data):
            local_to_bc[int(local_row["id"])] = created["category_id"]
            created_ids.append(created["category_id"])
    return created_ids


def main():
    rows = load_rows()
    by_level = {1: [], 2: [], 3: []}
    for r in rows:
        by_level[int(r["level"])].append(r)

    for tree_id in TREE_IDS:
        print(f"=== Tree {tree_id} ===")
        local_to_bc = {}
        for level in (1, 2, 3):
            level_rows = by_level[level]
            print(f"Creating level {level}: {len(level_rows)} categories")
            create_level(tree_id, level_rows, local_to_bc)
        print(f"Tree {tree_id}: created {len(local_to_bc)} categories total")

        # Persist the id map for this tree so we can verify / reuse later.
        with open(f"bc_category_ids_tree{tree_id}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["local_id", "bc_category_id"])
            for k, v in sorted(local_to_bc.items()):
                w.writerow([k, v])


if __name__ == "__main__":
    main()
