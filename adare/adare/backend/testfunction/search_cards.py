"""Search for agents: filters, \"not for -> use X\" redirects, honest \"no good match\", short cards.

Layer 1 of the progressive disclosure (``adare test search``, the agent tools): a few short
result cards with why each matched, what it supports and does not, and how to go deeper
(``adare test info``, ``adare test feature``). When no function covers the goal well the answer
says so and names the matching known gaps from ``library.yaml`` instead of offering a near miss.
"""

from dataclasses import dataclass, field

from adare.backend.testfunction.catalog import (
    CatalogEntry,
    Hit,
    _expand,
    _matches,
    _tokens,
    filter_pool,
    find,
    scored_search,
    use_for,
)
from adare.backend.testfunction.contract import Gap, Library, load_library
from adare.backend.testfunction.contract_render import md_inline

# A hit that matches less than this share of the query's words is a weak match.
_WEAK_COVERAGE = 0.5
# A not_for goal redirects to its target when (share of the query it covers) x (share of it the
# query covers) reaches _REDIRECT_FIT; the bonus grows with that fit.
_REDIRECT_BONUS = 6.0
_REDIRECT_FIT = 0.4
_FORMAT_BONUS = 3.0
# Format names that are also everyday words ("text in a file"): no format preference.
_GENERIC_FORMAT_WORDS = frozenset({'file', 'directory', 'text', 'system', 'screen', 'image'})
_STRONG_FIELDS = ('name', 'collection', 'summary', 'use_for', 'use_cases', 'facets')


@dataclass(frozen=True)
class SearchResult:
    hits: list[Hit]
    weak: bool
    gaps: list[Gap] = field(default_factory=list)
    redirects: dict[str, str] = field(default_factory=dict)  # target dotnotation -> "X is not for ..."


def facet_filter(
    entries: list[CatalogEntry],
    *,
    asserts: str | None = None,
    fmt: str | None = None,
    feature: str | None = None,
) -> list[CatalogEntry]:
    """Keep entries whose contract declares the facet (entries without a contract drop out)."""

    def keep(entry: CatalogEntry) -> bool:
        contract = entry.contract
        if contract is None:
            return not (asserts or fmt or feature)
        return (
            (not asserts or asserts in contract.asserts)
            and (not fmt or fmt in contract.formats)
            and (not feature or feature in contract.features)
        )

    return [e for e in entries if keep(e)]


def _coverage(query_tokens: list[str], text: str) -> float:
    words = set(_tokens(text))
    if not query_tokens:
        return 0.0
    hit = sum(1 for t in query_tokens if _matches(t, words) or (_expand(t) - {t}) & words)
    return hit / len(query_tokens)


def matching_gaps(query: str, library: Library) -> list[Gap]:
    """Known gaps one of whose keyword phrases occurs in the query (word by word, stems allowed)."""
    query_tokens = _tokens(query)
    found = []
    for gap in library.gaps:
        for keyword in gap.keywords:
            words = _tokens(keyword)
            if words and all(any(_matches(q, _expand(w)) or _matches(w, {q}) for q in query_tokens) for w in words):
                found.append(gap)
                break
    return found


def search_goal(
    entries: list[CatalogEntry],
    query: str,
    *,
    collection: str | None = None,
    category: str | None = None,
    os: str | None = None,
    asserts: str | None = None,
    fmt: str | None = None,
    feature: str | None = None,
    limit: int = 5,
    library: Library | None = None,
) -> SearchResult:
    library = library or load_library()
    pool = facet_filter(
        filter_pool(entries, collection=collection, category=category, os=os), asserts=asserts, fmt=fmt, feature=feature
    )
    hits = scored_search(pool, query)
    query_tokens = _tokens(query)
    # A format named in the query ("... in sqlite") prefers the functions that read it, even
    # those the ranking cut off as incidental.
    named_formats = {t for t in query_tokens if t in library.formats and t not in _GENERIC_FORMAT_WORDS}
    if named_formats:
        readers = [e for e in pool if e.contract and named_formats & set(e.contract.formats)]
        known = {h.entry.dotnotation for h in hits}
        hits += [h for h in scored_search(readers, query) if h.entry.dotnotation not in known]

    # A function that says "not for <this goal>, use Y" lifts Y and sinks itself.
    redirects: dict[str, str] = {}
    boost: dict[str, float] = {}
    for hit in hits:
        if named_formats and hit.entry.contract:
            reads = named_formats & set(hit.entry.contract.formats)
            # a function that cannot read the named format is no answer, however well it matches
            bonus = _FORMAT_BONUS if reads else -2 * _FORMAT_BONUS
            boost[hit.entry.dotnotation] = boost.get(hit.entry.dotnotation, 0.0) + bonus
        for redirect in hit.entry.contract.not_for if hit.entry.contract else ():
            # both ways: the goal says most of the query, and the query says most of the goal
            fit = _coverage(query_tokens, redirect.text) * _coverage(_tokens(redirect.text), ' '.join(query_tokens))
            if fit < _REDIRECT_FIT:
                continue
            target = find(pool, redirect.use)
            if target is None:
                continue
            boost[target.dotnotation] = boost.get(target.dotnotation, 0.0) + _REDIRECT_BONUS * fit
            boost[hit.entry.dotnotation] = boost.get(hit.entry.dotnotation, 0.0) - _REDIRECT_BONUS * fit / 2
            redirects.setdefault(target.dotnotation, f'{hit.entry.dotnotation} is not for "{redirect.text}"')
    if boost:
        by_name = {h.entry.dotnotation: h for h in hits}
        for dotnotation in boost:
            if dotnotation not in by_name:
                entry = find(pool, dotnotation)
                if entry is not None:
                    by_name[dotnotation] = Hit(entry, 0.0, {}, tuple(query_tokens))
        hits = sorted(
            (Hit(h.entry, h.score + boost.get(d, 0.0), h.matched, h.missed) for d, h in by_name.items()),
            key=lambda h: (-h.score, h.entry.dotnotation),
        )

    hits = hits[:limit]
    best = hits[0] if hits else None
    # Words found only in parameter docs or prose are incidental; intent lives in the strong fields.
    strong = [t for t, f in best.matched.items() if f in _STRONG_FIELDS] if best else []
    weak = best is None or (bool(query_tokens) and len(strong) / len(query_tokens) < _WEAK_COVERAGE)
    if best is not None and best.entry.dotnotation in redirects:
        weak = False
    gaps = matching_gaps(query, library)
    if gaps and len(strong) < len(query_tokens):
        weak = True  # a known gap names the goal and the best hit does not cover all of it
    return SearchResult(hits=hits, weak=weak, gaps=gaps, redirects=redirects)


def card(hit: Hit, redirects: dict[str, str] | None = None) -> dict:
    """The short form an agent reads first: enough to choose, with pointers to go deeper."""
    entry = hit.entry
    contract = entry.contract
    data: dict = {
        'testfunction': entry.dotnotation,
        'summary': entry.summary,
    }
    if use_for(entry.doc):
        data['use_for'] = md_inline(use_for(entry.doc))
    why = sorted({field for field in hit.matched.values() if field})
    if why:
        data['matched'] = f'{", ".join(hit.matched)} (in {", ".join(why)})'
    if redirects and entry.dotnotation in redirects:
        data['redirected'] = redirects[entry.dotnotation]
    if entry.contract_note:
        data['note'] = entry.contract_note
    if contract:
        data['asserts'] = list(contract.asserts)
        data['formats'] = list(contract.formats)
        data['supports'] = list(contract.features)
        if contract.unsupported:
            data['does_not_support'] = {k: md_inline(v) for k, v in contract.unsupported.items()}
        if contract.not_for:
            data['not_for'] = [f'{md_inline(r.text)} -> {r.use}' for r in contract.not_for]
    data['required'] = [p.name for p in entry.params if p.required or p.default == '']
    data['os'] = entry.os
    data['example'] = entry.example()
    data['next'] = f'adare test info {entry.dotnotation}'
    return data


def result_dict(result: SearchResult, query: str) -> dict:
    data: dict = {
        'query': query,
        'match': 'weak' if result.weak else 'good',
        'results': [card(h, result.redirects) for h in result.hits],
    }
    if result.gaps:
        data['known_gaps'] = [{'gap': md_inline(g.summary), 'instead': md_inline(g.instead)} for g in result.gaps]
    if result.weak:
        data['advice'] = (
            'No testfunction clearly covers this goal. Check the known gaps, narrow with '
            '--asserts/--reads/--feature, or write a collection (adare-testfunction skill, section 1).'
        )
    return data
