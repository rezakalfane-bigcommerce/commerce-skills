#!/usr/bin/env python3
"""BigCommerce Store Translations GraphQL helper.

Examples:
  python translations_api.py inventory PRODUCTS --locale fr --channel 1891823
  python translations_api.py upload plan.json
  python translations_api.py verify PRODUCTS --locale fr --channel 1891823

The upload plan is JSON containing either one object or a list of objects:
  {"resourceType":"PRODUCTS", "locale":"fr", "channel":1891823,
   "entities":[{"resourceId":"bc/store/product/123",
                 "fields":[{"fieldName":"name","value":"Nom"}]}]}
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from bc_api import _creds, redact

QUERY = """
query($resourceType: TranslationResourceType!, $channelId: ID!, $localeId: ID!, $after: String) {
  store { translations(filters: {resourceType: $resourceType, channelId: $channelId, localeId: $localeId}, first: 50, after: $after) {
    edges { cursor node { resourceId fields { fieldName original translation } } }
    pageInfo { hasNextPage endCursor }
  } }
}
"""
MUTATION = """
mutation($input: UpdateTranslationsInput!) { translation { updateTranslations(input: $input) {
  __typename errors { __typename ... on Error { message } }
} } }
"""


def gql(store_hash, token, document, variables):
    request = urllib.request.Request(
        f"https://api.bigcommerce.com/stores/{store_hash}/graphql",
        data=json.dumps({"query": document, "variables": variables}).encode(),
        headers={"X-Auth-Token": token, "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError) as error:
        raise RuntimeError(redact(str(error))) from error
    if body.get("errors"):
        raise RuntimeError(redact(json.dumps(body["errors"])))
    return body.get("data", {})


def context(args):
    store_hash, token = _creds(args.env)
    channel = args.channel or __import__("os").environ.get("BIGCOMMERCE_CHANNEL_ID") or __import__("os").environ.get("BC_CHANNEL_ID")
    if not store_hash or not token or not channel:
        raise SystemExit("Missing credentials or channel ID (use --channel or BIGCOMMERCE_CHANNEL_ID).")
    return store_hash, token, f"bc/store/channel/{channel}"


def read_all(store_hash, token, resource_type, channel_id, locale):
    nodes, after = [], None
    while True:
        data = gql(store_hash, token, QUERY, {"resourceType": resource_type, "channelId": channel_id, "localeId": f"bc/store/locale/{locale}", "after": after})
        connection = data["store"]["translations"]
        nodes.extend(edge["node"] for edge in connection["edges"])
        if not connection["pageInfo"]["hasNextPage"]:
            return nodes
        after = connection["pageInfo"]["endCursor"]


def upload(store_hash, token, plan):
    plans = plan if isinstance(plan, list) else [plan]
    for item in plans:
        resource_type, locale, channel = item["resourceType"], item["locale"], item["channel"]
        entities = item["entities"]
        for start in range(0, len(entities), 50):
            batch = entities[start:start + 50]
            data = gql(store_hash, token, MUTATION, {"input": {"resourceType": resource_type, "channelId": f"bc/store/channel/{channel}", "localeId": f"bc/store/locale/{locale}", "entities": batch}})
            errors = data["translation"]["updateTranslations"]["errors"]
            if errors:
                raise RuntimeError(redact(json.dumps(errors)))
            print(f"Uploaded {resource_type} {locale}: {start + 1}-{start + len(batch)}")


def main():
    parser = argparse.ArgumentParser(description="Read, write, and verify BigCommerce Store Translations.")
    parser.add_argument("--env", help="Named credential environment passed to bc_api.py")
    parser.add_argument("--channel", help="Numeric storefront channel ID")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("inventory", "verify"):
        p = sub.add_parser(name)
        p.add_argument("resource_type")
        p.add_argument("--locale", required=True)
    p = sub.add_parser("upload")
    p.add_argument("plan", type=Path)
    args = parser.parse_args()
    store_hash, token, channel_id = context(args)
    if args.command in ("inventory", "verify"):
        nodes = read_all(store_hash, token, args.resource_type, channel_id, args.locale)
        if args.command == "inventory":
            print(json.dumps(nodes, indent=2, ensure_ascii=False))
        else:
            fields = [field for node in nodes for field in node["fields"]]
            missing = [field for field in fields if not field.get("translation")]
            print(f"{args.resource_type} {args.locale}: {len(nodes)} resources, {len(fields)} fields, {len(missing)} missing translations")
            if missing:
                raise SystemExit(1)
    else:
        upload(store_hash, token, json.loads(args.plan.read_text()))


if __name__ == "__main__":
    main()
