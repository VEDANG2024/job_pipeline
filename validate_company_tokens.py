"""
validate_company_tokens.py — one-off audit of config.yaml's pinned
Greenhouse/Lever company tokens.

There's no discovery API for either board — a token is only found by
checking a company's actual careers page, so pinned lists silently rot as
companies migrate ATS or rename their board. Today's run showed ~90 of
~130 pinned tokens 404ing. Rather than guess replacement tokens (which
would mean inventing URLs I can't verify), this just tells you which
ones are alive right now so you can prune/replace with confidence.

Usage:
    python validate_company_tokens.py
"""
import sys
import time

import requests
import yaml

GH_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
LEVER_URL = "https://api.lever.co/v0/postings/{token}"


def check(url: str, token: str) -> tuple:
    try:
        r = requests.get(url.format(token=token), timeout=10)
        return token, r.status_code == 200, r.status_code
    except Exception as e:
        return token, False, str(e)


def main():
    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)

    for source_name, url_tmpl in (("greenhouse", GH_URL), ("lever", LEVER_URL)):
        tokens = cfg["companies"].get(source_name, [])
        alive, dead = [], []
        for token in tokens:
            _, ok, detail = check(url_tmpl, token)
            (alive if ok else dead).append(token)
            time.sleep(0.2)  # be polite to the public API
        print(f"\n=== {source_name}: {len(alive)}/{len(tokens)} alive ===")
        print("ALIVE:", ", ".join(alive) if alive else "(none)")
        print("DEAD: ", ", ".join(dead) if dead else "(none)")


if __name__ == "__main__":
    sys.exit(main())
