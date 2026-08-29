from __future__ import annotations


from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def flatten_clauses(regulations: dict) -> list[dict]:
    out = []
    for jur in regulations["jurisdictions"]:
        for c in jur["clauses"]:
            row = dict(c)
            row["jurisdiction"] = jur["id"]
            row["jurisdiction_name"] = jur["name"]
            row["authority"] = c["obligation"].get("notify") or jur["authority"]
            row["form"] = c["obligation"]["form"]
            row["window_hours"] = c["obligation"]["window_hours"]
            row["clock_starts"] = c["obligation"]["clock_starts"]
            row["source_pdf"] = jur.get("source_pdf")
            row["site_types"] = c["trigger"]["site_types"]
            row["keywords"] = c["trigger"].get("keywords") or []
            out.append(row)
    return out


def clause_doc(c: dict) -> str:
    kws = " ".join(c.get("keywords") or [])
    return f"{c['heading']} {c['citation']} {c['text']} {kws}"


class Retriever:
    """Two collections, keyword + TF-IDF. No Chroma, no API. Fine at this scale."""

    def __init__(self, clauses: list[dict], incidents: list[dict]):
        self.clauses = clauses
        self.incidents = incidents
        self._clause_vec = TfidfVectorizer(stop_words="english")
        self._clause_mat = self._clause_vec.fit_transform([clause_doc(c) for c in clauses])
        inc_docs = [
            (i.get("raw_text") or "") + " " + " ".join(i.get("hazard_tags") or [])
            for i in incidents
        ]
        self._inc_vec = TfidfVectorizer(stop_words="english")
        self._inc_mat = self._inc_vec.fit_transform(inc_docs) if incidents else None

    def regulations(self, query: str, site_type: str | None = None, k: int = 6) -> list[dict]:
        q = self._clause_vec.transform([query])
        scores = cosine_similarity(q, self._clause_mat).ravel()
        ranked = sorted(enumerate(scores), key=lambda x: -x[1])
        hits = []
        for idx, score in ranked:
            c = dict(self.clauses[idx])
            if site_type and site_type not in (c.get("site_types") or []):
                # still allow ESI / EC which apply to both
                if site_type not in c.get("site_types", []):
                    continue
            c["score"] = float(score)
            hits.append(c)
            if len(hits) >= k:
                break
        if len(hits) < 3:
            hits = []
            for idx, score in ranked[:k]:
                c = dict(self.clauses[idx])
                c["score"] = float(score)
                hits.append(c)
        return hits

    def similar_incidents(self, query: str, exclude_id: str | None = None, k: int = 10) -> list[dict]:
        if self._inc_mat is None:
            return []
        q = self._inc_vec.transform([query])
        scores = cosine_similarity(q, self._inc_mat).ravel()
        out = []
        for idx in scores.argsort()[::-1]:
            row = dict(self.incidents[idx])
            if exclude_id and row.get("incident_id") == exclude_id:
                continue
            row["similarity"] = float(scores[idx])
            if row["similarity"] < 0.12:
                continue
            out.append(row)
            if len(out) >= k:
                break
        return out


def keyword_boost(incident_text: str, clauses: list[dict]) -> list[str]:
    text = incident_text.lower()
    scored = []
    for c in clauses:
        n = sum(1 for kw in c.get("keywords") or [] if kw.lower() in text)
        scored.append((n, c["clause_id"]))
    scored.sort(reverse=True)
    return [cid for n, cid in scored if n]


def merge_retrieval(tfidf_hits: list[dict], boosted_ids: list[str], clause_by_id: dict, k: int = 8) -> list[dict]:
    seen = set()
    out = []
    for cid in boosted_ids:
        if cid in clause_by_id and cid not in seen:
            out.append(clause_by_id[cid])
            seen.add(cid)
    for h in tfidf_hits:
        if h["clause_id"] not in seen:
            out.append(h)
            seen.add(h["clause_id"])
        if len(out) >= k:
            break
    return out
