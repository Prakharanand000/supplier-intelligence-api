"""End-to-end demo against live sources.

    python -m scripts.demo            # all three demo companies
    python -m scripts.demo "Siemens AG" --country Germany

Demo 1 (clean)              expects: verified, no sanctions, low risk
Demo 2 (risk positive)      expects: litigation and/or negative media found
Demo 3 (entity resolution)  expects: several similar entities, one selected,
                                     with the confidence breakdown explaining why
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import close_db, init_db  # noqa: E402
from app.http_client import close_client  # noqa: E402
from app.pipeline import investigate  # noqa: E402
from app.sources import ofac  # noqa: E402

DEMOS = [
    {
        # Deliberately not a US public company: every large US registrant is
        # party to federal litigation, so "clean" has to be tested on an entity
        # that genuinely has none.
        "label": "Demo 1 - clean supplier",
        "name": "Kesko Oyj",
        "country": "Finland",
        "website": "https://www.kesko.fi",
    },
    {
        "label": "Demo 2 - risk positive",
        "name": "Wells Fargo & Company",
        "country": "United States",
        "website": None,
    },
    {
        "label": "Demo 3 - entity resolution challenge",
        "name": "ABC Manufacturing",
        "country": "United States",
        "website": None,
    },
]

RULE = "=" * 78


def summarize(result: dict) -> None:
    s, r, er = result["supplier"], result["risk"], result["entity_resolution"]

    print(f"  resolved       : {s['name']}  [{s['status']}"
          f" conf={s['identity_confidence']:.2f}, source={s['primary_source']}]")
    if er["selected"]:
        breakdown = ", ".join(
            f"{k}={v:.2f}" for k, v in er["selected"]["confidence_breakdown"].items()
        )
        print(f"  why            : {breakdown}")
    print(f"  candidates     : {er['candidates_considered']} considered, "
          f"{len(er['alternatives'])} alternatives rejected")
    for alt in er["alternatives"][:3]:
        print(f"                   - {alt['name'][:52]:<52} "
              f"{alt['source']:<7} {alt['confidence']:.2f}")

    sanctions = result["sanctions"]
    if sanctions.get("match"):
        entity = sanctions["matched_entity"]
        print(f"  sanctions      : MATCH {entity['name']} "
              f"(program {entity['program']}, sim {sanctions['confidence']:.2f})")
    else:
        print(f"  sanctions      : no match "
              f"({sanctions.get('list_size', 0)} SDN names screened)")

    cases = result["litigation"].get("cases") or []
    print(f"  litigation     : {len(cases)} docket(s)"
          + (f" - {cases[0]['case'][:60]}" if cases else
             f" ({result['litigation'].get('note') or 'none found'})"))
    media = result["adverse_media"]
    print(f"  adverse media  : {len(media)} article(s)"
          + (f" - {media[0]['title'][:60]}" if media else ""))
    print(f"  ownership      : {len(result['ownership'])} related part(ies)")
    print(f"  evidence       : {len(result['evidence'])} citable items")
    print(f"  RISK           : {r['score']}/100 ({r['level']})")
    for contribution in r["contributions"]:
        print(f"                   +{contribution['points']:>3} "
              f"{contribution['category']} ({contribution['source']})")
    print(f"  recommendation : {result['agent_summary']['recommendation']}")
    print(f"  report by      : {result['agent_summary'].get('generated_by')}")
    print(f"  duration       : {result['duration_seconds']}s")


async def run(targets: list[dict], dump: Path | None) -> int:
    await init_db()
    print("Loading OFAC SDN list (first run downloads a few MB)...")
    count = await ofac.ingest()
    print(f"OFAC ready: {count} names indexed\n")

    failures = 0
    outputs = []
    try:
        for target in targets:
            print(RULE)
            print(target.get("label", target["name"]))
            print(RULE)
            try:
                result = await investigate(
                    name=target["name"],
                    country=target.get("country"),
                    website=target.get("website"),
                )
                summarize(result)
                outputs.append(result)
                if result["duration_seconds"] > 60:
                    print("  ! exceeded the 60s target")
                    failures += 1
            except Exception as exc:  # noqa: BLE001
                print(f"  FAILED: {exc}")
                failures += 1
            print()
    finally:
        await close_client()
        await close_db()

    if dump and outputs:
        dump.write_text(json.dumps(outputs, indent=2, default=str), encoding="utf-8")
        print(f"Full JSON written to {dump}")

    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Supplier Intelligence demo")
    parser.add_argument("name", nargs="?", help="Company to investigate")
    parser.add_argument("--country")
    parser.add_argument("--website")
    parser.add_argument("--json", type=Path, help="Write full results to this file")
    args = parser.parse_args()

    targets = (
        [{"label": f"Ad-hoc - {args.name}", "name": args.name,
          "country": args.country, "website": args.website}]
        if args.name
        else DEMOS
    )

    failures = asyncio.run(run(targets, args.json))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
