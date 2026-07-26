"""Assemble a full investigation object from the demo fixtures.

Reuses the real taxonomy, bias analyzer and risk engine so the demo output is
the same shape and passes through the same scoring logic as a live run.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.demo.dataset import ARTICLES, GRAPH_EDGES, GRAPH_NODES, SUBJECTS
from app.risk import bias
from app.risk.engine import evaluate, recommendation
from app.risk.taxonomy import RISK_TAXONOMY, categories_for
from app.risk.term_matcher import match_terms


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def _node(label: str, center: str) -> dict:
    meta = GRAPH_NODES[label]
    ntype = "entity" if label == center else meta["type"]
    return {"id": _slug(label), "label": label, "type": ntype,
            "detail": meta.get("detail"), "center": label == center}


def _edge(e: dict) -> dict:
    return {"source": _slug(e["source"]), "target": _slug(e["target"]),
            "label": e["rel"], "relationship": e["rel"], "confidence": e["confidence"],
            "description": e["description"], "kind": "connection"}


def _full_graph() -> dict[str, Any]:
    return {
        "nodes": [{"id": _slug(l), "label": l, "type": m["type"], "detail": m.get("detail")}
                  for l, m in GRAPH_NODES.items()],
        "edges": [_edge(e) for e in GRAPH_EDGES],
    }


def _connection_subgraph(center: str, hops: int = 2, limit: int = 16) -> dict[str, Any]:
    """Breadth-first neighbourhood around the subject, capped for readability."""
    adj: dict[str, list[str]] = defaultdict(list)
    for e in GRAPH_EDGES:
        adj[e["source"]].append(e["target"])
        adj[e["target"]].append(e["source"])

    seen = {center}
    frontier = [center]
    for _ in range(hops):
        nxt = []
        for node in frontier:
            for nb in adj[node]:
                if nb not in seen and len(seen) < limit:
                    seen.add(nb)
                    nxt.append(nb)
        frontier = nxt

    nodes = [_node(label, center) for label in seen]
    edges = [_edge(e) for e in GRAPH_EDGES
             if e["source"] in seen and e["target"] in seen]
    return {"nodes": nodes, "edges": edges}


def list_subjects() -> list[dict]:
    return [
        {
            "id": sid,
            "name": s["name"],
            "entity_type": s["entity_type"],
            "country": s["country"],
            "tagline": s["tagline"],
            "article_count": sum(1 for a in ARTICLES if a["subject"] == sid),
        }
        for sid, s in SUBJECTS.items()
    ]


def _enrich_articles(sid: str) -> list[dict]:
    out: list[dict] = []
    for i, art in enumerate(a for a in ARTICLES if a["subject"] == sid):
        text = f"{art['title']} {art['body']}"
        categories = categories_for(text)
        # Cosine-matched controlled risk terms (for the word cloud + tags).
        risk_terms = list(match_terms(text))
        # If the taxonomy lexicon missed it but cosine found risk terms, derive
        # the category from the strongest matched term so every article is tagged.
        if not categories and risk_terms:
            key = risk_terms[0]["category"]
            spec = RISK_TAXONOMY[key]
            categories = [{
                "key": key, "label": spec["label"], "color": spec["color"],
                "severity": round(risk_terms[0]["score"], 2),
                "matched_terms": [t["term"] for t in risk_terms[:3]],
            }]
        # An article that matched no risk category or term genuinely carries no
        # signal - default to 0.0, not a mystery "moderate" score. Every
        # template-generated adverse article always hits at least one category
        # (the risk term is baked into its text), so this only changes the
        # score for genuinely clean fixtures.
        severity = max((c["severity"] for c in categories), default=0.0)
        out.append(
            {
                "id": f"M{i + 1}",
                "title": art["title"],
                "source": art["source"],
                "date": art["date"],
                "url": None,
                "language": "en",
                "sentiment": art.get("sentiment", "negative"),
                "severity": round(severity, 2),
                "confidence": 0.9,
                "categories": categories,
                "category_keys": [c["key"] for c in categories],
                "risk_terms": risk_terms,
                "matched_terms": [t["term"] for t in risk_terms[:6]],
                "body": art["body"],
                "bias": bias.analyze(art["body"]),
            }
        )
    out.sort(key=lambda a: (a["severity"], a["date"]), reverse=True)
    return out


def _transactions(records: list[dict], issuer: str) -> dict[str, Any]:
    if not records:
        return {
            "available": False, "records": [], "summary": {},
            "note": ("No Form 4 insider transactions found. Non-US entities have "
                     "no Section 16 filing obligation."),
        }
    recs = []
    for r in records:
        value = round(r["shares"] * r["price_per_share"], 2)
        recs.append({**r, "security": "Common Stock", "value": value,
                     "filing_url": None})
    recs.sort(key=lambda t: t["date"], reverse=True)
    acquired = [t for t in recs if t["direction"] == "acquired"]
    disposed = [t for t in recs if t["direction"] == "disposed"]
    return {
        "available": True, "records": recs, "note": None,
        "summary": {
            "count": len(recs),
            "insiders": len({t["insider"] for t in recs}),
            "acquired_count": len(acquired), "disposed_count": len(disposed),
            "acquired_value": round(sum(t["value"] for t in acquired), 2),
            "disposed_value": round(sum(t["value"] for t in disposed), 2),
            "total_value": round(sum(t["value"] for t in recs), 2),
            "earliest": min(t["date"] for t in recs),
            "latest": max(t["date"] for t in recs),
            "issuer": issuer,
        },
    }


def _graphs(meta: dict, ownership: list, transactions: dict) -> dict[str, Any]:
    name = meta["name"]

    res_nodes = [{"id": "query", "label": name, "type": "query",
                  "detail": "Search subject"}]
    res_edges = []
    selected = {"name": name, "source": "SEC" if meta["cik"] else "GLEIF",
                "confidence": meta["identity_confidence"],
                "breakdown": {"name": 1.0, "embedding": 0.62, "address": 1.0}}
    candidates = [selected] + [
        {"name": a["name"], "source": a["source"], "confidence": a["confidence"],
         "breakdown": a["confidence_breakdown"]} for a in meta["alternatives"]
    ]
    for i, c in enumerate(candidates):
        nid = f"cand{i}"
        top = max(c["breakdown"].items(), key=lambda kv: kv[1])[0] if c["breakdown"] else "name"
        res_nodes.append({"id": nid, "label": c["name"],
                          "type": "selected" if i == 0 else ("match" if c["confidence"] >= 0.72 else "rejected"),
                          "source": c["source"], "confidence": c["confidence"],
                          "breakdown": c["breakdown"],
                          "detail": f"{c['source']} candidate, confidence {c['confidence']:.2f}"})
        res_edges.append({"source": "query", "target": nid, "weight": c["confidence"],
                          "label": f"{c['confidence']:.2f} ({top})"})

    net_nodes = [{"id": "entity", "label": name, "type": "entity",
                  "detail": f"{meta['status']} - confidence {meta['identity_confidence']:.2f}"}]
    net_edges = []
    for i, o in enumerate(ownership):
        nid = f"p{i}"
        is_parent = o["relationship_type"] in ("direct_parent", "ultimate_parent")
        net_nodes.append({"id": nid, "label": o["name"],
                          "type": "parent" if is_parent else "person",
                          "source": o.get("source"), "confidence": o.get("confidence"),
                          "detail": o.get("role")})
        rel = o.get("role") or o["relationship_type"]
        net_edges.append({"source": nid, "target": "entity", "weight": o.get("confidence", 0.5),
                          "label": rel, "relationship": rel,
                          "description": f"{o['name']} is linked to {name} as {rel}.",
                          "kind": "ownership" if is_parent else "officer"})

    txn_nodes, txn_edges = [], []
    if transactions["available"]:
        txn_nodes.append({"id": "issuer", "label": name, "type": "entity", "detail": "Issuer"})
        per: dict[str, dict] = {}
        for t in transactions["records"]:
            b = per.setdefault(t["insider"], {"acquired": 0.0, "disposed": 0.0,
                                              "count": 0, "shares": 0.0})
            b["count"] += 1
            b["shares"] += t["shares"]
            b[t["direction"]] += t["value"]
        for i, (insider, tot) in enumerate(sorted(per.items(), key=lambda kv: kv[1]["count"], reverse=True)):
            nid = f"i{i}"
            txn_nodes.append({"id": nid, "label": insider, "type": "person",
                              "detail": f"{tot['count']} filed transaction(s)"})
            net_v = tot["acquired"] - tot["disposed"]
            txn_edges.append({"source": nid, "target": "issuer",
                              "weight": min(1.0, tot["count"] / 6), "count": tot["count"],
                              "shares": round(tot["shares"], 2),
                              "acquired_value": round(tot["acquired"], 2),
                              "disposed_value": round(tot["disposed"], 2),
                              "direction": "acquired" if net_v >= 0 else "disposed",
                              "label": f"{tot['count']} txn", "kind": "transaction"})

    return {
        "resolution": {"nodes": res_nodes, "edges": res_edges},
        "network": {"nodes": net_nodes, "edges": net_edges},
        "transactions": {"nodes": txn_nodes, "edges": txn_edges},
    }


def _evidence(articles: list, litigation: dict, ownership: list, meta: dict) -> list[dict]:
    ev = []

    def add(source, description, url=None):
        ev.append({"id": f"E{len(ev) + 1}", "source": source, "url": url,
                   "description": description})

    add(meta["source_label"], f"Registry identity for '{meta['name']}' "
        f"({meta['country']}); resolution confidence {meta['identity_confidence']:.2f}")
    add("OFAC", f"Sanctions screening against {meta['sanctions_list_size']} SDN "
        f"names: no match")
    for c in litigation["cases"][:4]:
        add("CourtListener", f"{c['case']} ({c['court']}, filed {c['date']})", c.get("url"))
    for a in articles[:10]:
        add(a["source"], f"{a['title']} [{a['bias']['label']}]", a["url"])
    return ev


def _graph_block(meta: dict, ownership: list, transactions: dict) -> dict[str, Any]:
    """Resolution + transaction graphs always; the rich cross-entity connection
    network only for the hand-authored subjects that live in the demo graph.
    Generated entities fall back to their ownership-derived network."""
    block = _graphs(meta, ownership, transactions)
    if meta["name"] in GRAPH_NODES:
        block["network"] = _connection_subgraph(meta["name"])
        block["network_full"] = _full_graph()
    return block


def build_investigation(sid: str) -> dict[str, Any]:
    meta = SUBJECTS[sid]
    meta = {**meta, "source_label": "SEC" if meta["cik"] else "GLEIF"}

    articles = _enrich_articles(sid)
    from app.pipeline import _summarize_media  # local import avoids any cycle
    media_summary = _summarize_media(articles)

    sanctions = {
        "match": False, "confidence": 0.98, "matched_entity": None,
        "closest_entry": None, "source": "OFAC",
        "list_size": meta["sanctions_list_size"],
    }
    litigation = {"available": True, "cases": meta["litigation"], "note": None}
    ownership = [
        {**o, "source": o.get("source", meta["source_label"]),
         "evidence_url": None}
        for o in meta["ownership"]
    ]
    transactions = _transactions(meta["transactions"], meta["name"])

    verdict = "verified" if meta["status"] == "verified" else meta["status"]
    risk, _ = evaluate(
        sanctions=sanctions, litigation=litigation, adverse_media=articles,
        identity_confidence=meta["identity_confidence"], identity_verdict=verdict,
        ownership=ownership,
        sources_consulted={k: True for k in ("ofac", "sec", "gleif", "gdelt", "courtlistener")},
    )

    supplier = {
        "name": meta["name"], "verified": meta["status"] == "verified",
        "status": meta["status"], "identity_confidence": meta["identity_confidence"],
        "entity_type": meta["entity_type"], "country": meta["country"],
        "website": meta["website"], "lei": meta["lei"], "cik": meta["cik"],
        "registration_number": meta["registration"], "aliases": meta["aliases"],
        "primary_source": meta["source_label"],
    }

    top_cat = media_summary["categories"][0]["label"] if media_summary["categories"] else "adverse media"
    rec = recommendation(risk)
    summary = (
        f"{meta['name']} resolved with identity confidence "
        f"{meta['identity_confidence']:.2f} ({meta['status']}). No OFAC match "
        f"against {meta['sanctions_list_size']} SDN names. "
        f"{len(litigation['cases'])} litigation record(s) and {len(articles)} "
        f"adverse-media article(s) across {len(media_summary['categories'])} risk "
        f"categories, led by {top_cat}. Of those articles, "
        f"{media_summary['bias']['polarized']} read as polarized and "
        f"{media_summary['bias']['factual']} as factual. Composite risk "
        f"{risk['score']}/100 ({risk['level']})."
    )

    agent_summary = {
        "generated_by": "demo dataset (deterministic)",
        "summary": summary,
        "identity_assessment": f"Resolved to '{meta['name']}' at "
        f"{meta['identity_confidence']:.2f} confidence.",
        "ownership_assessment": "; ".join(f"{o['name']} ({o['role']})" for o in ownership[:4]) or "None.",
        "sanctions_assessment": f"No OFAC SDN match ({meta['sanctions_list_size']} names screened).",
        "litigation_assessment": f"{len(litigation['cases'])} docket(s), including {litigation['cases'][0]['case']}." if litigation["cases"] else "None.",
        "adverse_media_assessment": f"{len(articles)} article(s); "
        f"{media_summary['bias']['polarized']} polarized, "
        f"{media_summary['bias']['factual']} factual. Discount the polarized share.",
        "recommendation": rec,
        "rule_based_recommendation": rec,
    }

    return {
        "investigation_id": None,
        "demo": True,
        "query": {
            "name": meta["name"], "entity_type": meta["entity_type"],
            "country": meta["country"], "website": meta["website"],
            "address": None, "city": None, "date_of_birth": None,
            "registration_number": meta["registration"], "aliases": meta["aliases"],
        },
        "supplier": supplier,
        "entity_resolution": {
            "embedding_backend": "hashed",
            "candidates_considered": 1 + len(meta["alternatives"]),
            "match_threshold": 0.72,
            "selected": {
                "source": meta["source_label"], "name": meta["name"],
                "confidence": meta["identity_confidence"],
                "confidence_breakdown": {"name": 1.0, "embedding": 0.62, "address": 1.0},
                "weights_used": {"name": 0.53, "embedding": 0.27, "address": 0.2},
                "explanation": f"{meta['source_label']} record '{meta['name']}' "
                "scored on: name 1.00, embedding 0.62, address 1.00",
            },
            "alternatives": [
                {"source": a["source"], "name": a["name"], "confidence": a["confidence"],
                 "confidence_breakdown": a["confidence_breakdown"],
                 "explanation": f"{a['source']} candidate '{a['name']}'"}
                for a in meta["alternatives"]
            ],
        },
        "ownership": ownership,
        "sanctions": sanctions,
        "adverse_media": articles,
        "media_summary": media_summary,
        "litigation": litigation,
        "transactions": transactions,
        "graph": _graph_block(meta, ownership, transactions),
        "risk": risk,
        "evidence": _evidence(articles, litigation, ownership, meta),
        "agent_summary": agent_summary,
        "sources_consulted": {k: True for k in ("ofac", "sec", "gleif", "gdelt", "courtlistener")},
        "optional_sources": {
            "opencorporates": {"source": "OpenCorporates", "mocked": True,
                               "reason": "demo", "registry_records": []},
            "virustotal": {"source": "VirusTotal", "mocked": True, "reason": "demo",
                           "domain": meta["website"], "verdict": "not_evaluated"},
        },
        "duration_seconds": 0.2,
    }
