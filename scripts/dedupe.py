#!/usr/bin/env python3
"""
Deduplicate the anti-AD list against AdGuard's official filters.

anti-AD (https://anti-ad.net/adguard.txt) is essentially a domain blocklist:
every blocking rule is an unmodified `||domain^` (no modifiers, no cosmetic
rules). We therefore only have to decide, for each blocked domain, whether an
enabled AdGuard official filter already blocks that domain *unconditionally*
(no `$`-modifier restriction) and is not overridden by a whole-domain
`@@`-exception in those same filters. If so, the anti-AD rule is redundant.

Conservative on purpose:
  * rules with modifiers (`$third-party`, `$domain=`, ...) are never treated
    as coverage - a modifier may narrow the scope,
  * exception rules with modifiers are ignored too,
  * a parent-domain cover (`||example.com^` covers `sub.example.com`) is only
    applied when no whole-domain `@@`-exception targets the domain or any of
    its parents,
  * every non-`||domain^` line of anti-AD (its `@@` allow rules etc.) is kept
    verbatim, so dedup can never lose behavior anti-AD explicitly adds.

Usage:
    python scripts/dedupe.py [--lists-dir lists] [--output antiad-deduped.txt]
                             [--no-parent]

Expected files inside --lists-dir:
    anti-ad.txt            <- https://anti-ad.net/adguard.txt
    adguard_2.txt          <- https://filters.adtidy.org/android/filters/2_optimized.txt
    adguard_3.txt          <- ... /3_optimized.txt
    adguard_11.txt         <- ... /11_optimized.txt
    adguard_19.txt         <- ... /19_optimized.txt
    adguard_20.txt         <- ... /20_optimized.txt
    adguard_21.txt         <- ... /21_optimized.txt
    adguard_224.txt        <- ... /224_optimized.txt
"""

import argparse
import datetime
import os
import re
import sys

# AdGuard official filters this list is deduplicated against.
# Keep exactly these enabled in the AdGuard app, or the generated list may
# drop rules that would no longer be covered.
ADGUARD_FILTERS = [
    (2, "AdGuard Base"),
    (3, "AdGuard Tracking Protection"),
    (11, "AdGuard Mobile Ads"),
    (19, "AdGuard Popups"),
    (20, "AdGuard Mobile App Banners"),
    (21, "AdGuard Other Annoyances"),
    (224, "AdGuard Chinese"),
]

# Whole-domain rule shapes we consider as *full* coverage / exception.
# e.g. `||example.com^` / `||example.com` block the domain and all subdomains.
RE_BLOCK = re.compile(r"^\|\|([a-z0-9.\-]+)\^$")
RE_BLOCK_BARE = re.compile(r"^\|\|([a-z0-9.\-]+)$")
RE_ALLOW = re.compile(r"^@@\|\|([a-z0-9.\-]+)\^$")
RE_ALLOW_BARE = re.compile(r"^@@\|\|([a-z0-9.\-]+)$")


def read_lines(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.readlines()


def load_adguard_filter(path):
    """Return (blocks, exceptions) domain sets for one AdGuard filter.

    blocks      domains blocked unconditionally (whole domain, no modifiers)
    exceptions  domains allowed unconditionally (`@@||domain^`, no modifiers)
    """
    blocks = set()
    exceptions = set()
    for raw in read_lines(path):
        line = raw.strip()
        if not line or line.startswith(("!", "#", "$")):
            continue
        if line.startswith("@@"):
            m = RE_ALLOW.match(line) or RE_ALLOW_BARE.match(line)
            if m:
                exceptions.add(m.group(1).lower())
        elif line.startswith("||"):
            m = RE_BLOCK.match(line) or RE_BLOCK_BARE.match(line)
            if m:
                blocks.add(m.group(1).lower())
        # anything else (modifiers, regex, cosmetic, ...) -> not treated as coverage
    return blocks, exceptions


def is_blocked_by_adguard(domain, blocks, exceptions, use_parent):
    """True if AdGuard already blocks `domain` unconditionally."""
    parts = domain.split(".")
    # An `@@`-exception on the domain or any parent whitelists it -> not covered.
    for i in range(len(parts)):
        if ".".join(parts[i:]) in exceptions:
            return False
    # Covered by a block on the domain itself, or (optionally) any parent.
    if domain in blocks:
        return True
    if use_parent:
        for i in range(1, len(parts)):
            if ".".join(parts[i:]) in blocks:
                return True
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lists-dir", default="lists", help="directory with downloaded filter files")
    parser.add_argument("--output", default="antiad-deduped.txt", help="output list path")
    parser.add_argument("--no-parent", action="store_true",
                        help="do not treat a parent-domain rule as covering subdomains")
    args = parser.parse_args()

    antiad_path = os.path.join(args.lists_dir, "anti-ad.txt")
    if not os.path.isfile(antiad_path):
        sys.exit(f"missing {antiad_path}")

    # --- parse AdGuard filters ------------------------------------------------
    all_blocks = set()
    all_exceptions = set()
    for fid, fname in ADGUARD_FILTERS:
        path = os.path.join(args.lists_dir, f"adguard_{fid}.txt")
        if not os.path.isfile(path):
            sys.exit(f"missing {path} (is the workflow up to date?)")
        blocks, exceptions = load_adguard_filter(path)
        all_blocks |= blocks
        all_exceptions |= exceptions
        print(f"  [{fid:>3}] {fname:<34} blocks={len(blocks):>7} exceptions={len(exceptions):>5}")

    use_parent = not args.no_parent
    print(f"coverage: {len(all_blocks)} domains, {len(all_exceptions)} whole-domain exceptions, "
          f"parent-domain cover={'on' if use_parent else 'off'}")

    # --- parse anti-AD ---------------------------------------------------------
    preserved = []   # non-`||domain^` lines kept verbatim (incl. @@ allow rules)
    block_rules = []  # (domain, original_line) candidates for removal
    for raw in read_lines(antiad_path):
        line = raw.strip()
        if not line or line.startswith("!"):
            continue  # anti-AD header/comments -> replaced by our own header
        m = RE_BLOCK.match(line)
        if m:
            block_rules.append((m.group(1).lower(), raw.rstrip("\n")))
        else:
            preserved.append(raw.rstrip("\n"))

    print(f"anti-AD: {len(block_rules)} `||domain^` blocking rules, "
          f"{len(preserved)} other lines kept verbatim")

    # --- remove redundant blocking rules --------------------------------------
    kept = []
    removed = 0
    seen = set()
    for domain, original in block_rules:
        if domain in seen:  # duplicate inside anti-AD itself
            removed += 1
            continue
        seen.add(domain)
        if is_blocked_by_adguard(domain, all_blocks, all_exceptions, use_parent):
            removed += 1
        else:
            kept.append(original)

    # --- write output ----------------------------------------------------------
    now = datetime.datetime.now(datetime.timezone.utc)
    total = len(preserved) + len(kept)
    lines = [
        "! Title: anti-AD (deduplicated for AdGuard)",
        "! Description: anti-AD with rules already covered by AdGuard official filters removed.",
        f"! Version: {now:%Y%m%d%H%M%S}",
        f"! TimeUpdated: {now:%Y-%m-%dT%H:%M:%S+00:00}",
        "! Expires: 1 day (update frequency)",
        "! Homepage: https://github.com/Alizesa/AdGuard-Rules",
        f"! Total lines: {total}",
        "",
        "! Source: https://anti-ad.net/adguard.txt",
        "! Deduplicated against AdGuard official filters - keep these enabled in the AdGuard app:",
    ] + [f"!   {fid}: {fname}" for fid, fname in ADGUARD_FILTERS] + [
        "",
        *preserved,
        "",
        *kept,
    ]
    with open(args.output, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\nkept {len(kept)} blocking + {len(preserved)} other lines = {total} total")
    print(f"removed {removed} redundant rules (out of {len(block_rules)}) = "
          f"{removed / len(block_rules) * 100:.1f}% of blocking rules")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
