"""Render the catalog + contracts as Markdown (CLI, skill references) and reStructuredText (Sphinx).

Both renderings walk the same sections in the same order, so the reference pages, the skill's
references and ``adare test info`` say the same thing:

summary · use for · where it runs · asserts / formats · supports / does not support · not for ·
parameters (with allowed values) · outcomes · limits · use cases · examples · related.
"""

import re
from pathlib import Path

from adare.backend.testfunction.catalog import CatalogEntry, runs_where, use_for
from adare.backend.testfunction.contract import Contract, Library, example_yaml

_CODE = re.compile(r'``(.+?)``')
DOCS_ROOT = Path(__file__).resolve().parents[4] / 'docsrc' / 'source'
# Collections documented in a guide page instead of one reference page per function.
GUIDE_PAGES = {'visual': '/guide/icon-library'}


def md_inline(text: str) -> str:
    """Docstring/contract markup (``code``) to Markdown (`code`)."""
    return _CODE.sub(lambda m: f'`{m.group(1)}`', text)


def _md_cell(text: str) -> str:
    return md_inline(text).replace('|', '\\|').replace('\n', ' ')


def prose(doc: str) -> str:
    """Docstring text before ``Args:``, without the ``Use for:`` paragraph (rendered on its own)."""
    paragraphs = doc.split('\nArgs:')[0].strip().split('\n\n')
    return '\n\n'.join(' '.join(p.split()) for p in paragraphs if p.strip() and not p.strip().startswith('Use for:'))


def _default(p) -> str:
    return '' if p.required else f'`{p.default!r}`'


def _feature_title(fid: str, library: Library) -> str:
    feature = library.features.get(fid)
    return feature.title if feature else fid


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def _md_block(title: str, lines: list[str]) -> list[str]:
    return [f'**{title}:**', *lines, ''] if lines else []


def _md_params(entry: CatalogEntry, c: Contract) -> list[str]:
    if not entry.params:
        return []
    out = ['| parameter | type | default | description |', '|---|---|---|---|']
    for p in entry.params:
        name = f'**{p.name}**' if p.required or p.default == '' else p.name
        doc = p.doc
        if p.name in c.choices:
            doc = f'{doc} Allowed: {", ".join(f"``{v}``" for v in c.choices[p.name])}.'.strip()
        type_text = f'`{p.type}`'.replace('|', '\\|') if p.type else ''
        out.append(f'| {name} | {type_text} | {_default(p)} | {_md_cell(doc)} |')
    return [*out, '']


def _md_examples(entry: CatalogEntry, c: Contract) -> list[str]:
    if not c.examples:
        return ['```yaml', entry.example_yaml().rstrip(), '```', '']
    out = ['**Examples:**', '']
    for example in c.examples:
        line = f'*{md_inline(example.title)}* → {example.expect.upper()}'
        if example.text:
            line += f'. {md_inline(example.text)}'
        out += [line, '', '```yaml', example_yaml(entry.dotnotation, example).rstrip(), '```', '']
    return out


def function_markdown(entry: CatalogEntry, library: Library, level: int = 3) -> str:
    c = entry.contract or Contract()
    out = ['#' * level + f' `{entry.dotnotation}`', '', md_inline(entry.summary), '']
    if prose(entry.doc):
        out += [md_inline(prose(entry.doc)), '']
    if use_for(entry.doc):
        out += [f'**Use for:** {md_inline(use_for(entry.doc))}', '']
    facts = [f'runs: {runs_where(entry.category, entry.name)}', f'os: {entry.os}']
    if entry.contract:
        facts[:0] = [f'asserts: {", ".join(c.asserts)}', f'formats: {", ".join(c.formats) or "-"}']
    out += [' · '.join(facts), '']
    if c.features:
        out += [f'**Supports:** {", ".join(f"{_feature_title(f, library)} (`{f}`)" for f in c.features)}', '']
    out += _md_block(
        'Does not support',
        [f'- {_feature_title(f, library)} (`{f}`): {md_inline(why)}' for f, why in c.unsupported.items()],
    )
    out += _md_block('Not for', [f'- {md_inline(r.text)} → `{r.use}`' for r in c.not_for])
    out += _md_params(entry, c)
    out += _md_block(
        'Outcomes',
        [f'- {o.upper()}: {md_inline(x)}' for o in ('passed', 'failed', 'error') for x in c.outcomes.get(o, ())],
    )
    out += _md_block('Limits', [f'- {md_inline(x)}' for x in c.limits])
    out += _md_block(
        'Use cases', [f'- {md_inline(u.title)}' + (f': {md_inline(u.text)}' if u.text else '') for u in c.use_cases]
    )
    out += _md_examples(entry, c)
    out += _md_block('Related', [f'- `{r.use}`: {md_inline(r.text)}' for r in c.related])
    return '\n'.join(out)


def _first_sentence(text: str, limit: int = 220) -> str:
    """The first sentence ("e.g. x" does not end one), cut at ``limit`` characters."""
    text = ' '.join(text.split())
    match = re.match(r'(.+?\.)(?=\s+[A-Z]|$)', text)
    sentence = match.group(1) if match else text
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rsplit(' ', 1)[0] + ' …'


def index_markdown(entries: list[CatalogEntry], library: Library) -> str:
    """Layer 1 on disk: one line per function, to pick candidates before reading details."""
    out = [
        '# Testfunction index',
        '',
        '<!-- Generated by `adare test catalog --markdown-dir`; do not edit by hand. -->',
        '',
        'One line per testfunction: `name` [asserts · formats] use for. Prefer `adare test search "<goal>"`;',
        'read `catalog/<collection>.md` (or `adare test info <name>`) for parameters, outcomes, limits and',
        'examples, and `features.md` (or `adare test feature <id>`) for shared syntax.',
        '',
        '**Assertion kinds:** ' + ', '.join(f'`{k}` {v}' for k, v in library.asserts.items()),
        '',
    ]
    collection = None
    for entry in entries:
        if entry.collection != collection:
            collection = entry.collection
            info = entry.collection_info
            title = info.title if info and info.title else collection
            out += ['', f'## {title} (`catalog/{collection}.md`)', '']
        c = entry.contract
        facets = f' [{", ".join(c.asserts)} · {", ".join(c.formats)}]' if c else ''
        intent = use_for(entry.doc) or entry.summary
        out.append(f'- `{entry.dotnotation}`{facets} {md_inline(_first_sentence(intent))}')
    out.append('')
    return '\n'.join(out)


def collection_markdown(collection: str, entries: list[CatalogEntry], library: Library) -> str:
    own = [e for e in entries if e.collection == collection]
    info = own[0].collection_info if own else None
    title = info.title if info and info.title else collection
    out = [f'# {title} (`{collection}.*`)', '', '<!-- Generated; do not edit by hand. -->', '']
    if info and info.summary:
        out += [md_inline(info.summary), '']
    for entry in own:
        out.append(function_markdown(entry, library, level=2))
    return '\n'.join(out)


def features_markdown(entries: list[CatalogEntry], library: Library) -> str:
    out = ['# Shared features and known gaps', '', '<!-- Generated; do not edit by hand. -->', '']
    for fid, feature in library.features.items():
        out += [f'## {feature.title} (`{fid}`)', '', md_inline(feature.summary), '']
        if feature.syntax:
            out += ['```', feature.syntax, '```', '']
        supported = [e.dotnotation for e in entries if e.contract and fid in e.contract.features]
        refused = [e.dotnotation for e in entries if e.contract and fid in e.contract.unsupported]
        if supported:
            out += [f'Supported by: {", ".join(f"`{d}`" for d in supported)}', '']
        if refused:
            out += [f'Not supported by: {", ".join(f"`{d}`" for d in refused)}', '']
    out += ['## Known gaps (no bundled testfunction does this)', '']
    for gap in library.gaps:
        out.append(f'- **{md_inline(gap.summary)}** Instead: {md_inline(gap.instead)}')
    out.append('')
    return '\n'.join(out)


def feature_markdown(fid: str, entries: list[CatalogEntry], library: Library) -> str:
    feature = library.features[fid]
    out = [f'# {feature.title} (`{fid}`)', '', md_inline(feature.summary), '']
    if feature.syntax:
        out += ['```', feature.syntax, '```', '']
    if feature.example:
        out += ['```yaml', feature.example, '```', '']
    supported = [e.dotnotation for e in entries if e.contract and fid in e.contract.features]
    out += [f'Supported by: {", ".join(f"`{d}`" for d in supported) or "-"}', '']
    for e in entries:
        if e.contract and fid in e.contract.unsupported:
            out.append(f'- Not `{e.dotnotation}`: {md_inline(e.contract.unsupported[fid])}')
    if feature.doc:
        out += ['', f'Full description: docs page `{feature.doc}`']
    out.append('')
    return '\n'.join(out)


def markdown_files(entries: list[CatalogEntry], library: Library) -> dict[str, str]:
    """Relative path -> content of the skill's generated references."""
    files = {'catalog/index.md': index_markdown(entries, library), 'features.md': features_markdown(entries, library)}
    for collection in sorted({e.collection for e in entries}):
        files[f'catalog/{collection}.md'] = collection_markdown(collection, entries, library)
    return files


# ---------------------------------------------------------------------------
# reStructuredText (Sphinx directive bodies)
# ---------------------------------------------------------------------------


def _rst_inline(text: str) -> str:
    return ' '.join(text.split())


def doc_link(dotnotation: str, docs_root: Path = DOCS_ROOT) -> str:
    """``:doc:`` link to a function's page when it has one, else the dotnotation as code."""
    collection, _, name = dotnotation.partition('.')
    if collection in GUIDE_PAGES:
        return f':doc:`{dotnotation} <{GUIDE_PAGES[collection]}>`'
    page = docs_root / 'reference' / 'testfunctions' / collection / f'{name}.rst'
    if page.is_file():
        return f':doc:`{dotnotation} </reference/testfunctions/{collection}/{name}>`'
    return f'``{dotnotation}``'


def feature_ref(fid: str, library: Library) -> str:
    return f':ref:`{_feature_title(fid, library)} <tf-feature-{fid}>`' if fid in library.features else f'``{fid}``'


def _rst_section(title: str, char: str = '-') -> list[str]:
    return [title, char * len(title), '']


def _indent(text: str, n: int = 3) -> list[str]:
    return [(' ' * n + line) if line else '' for line in text.splitlines()]


def _rst_block(title: str, lines: list[str]) -> list[str]:
    return [*_rst_section(title), *lines, ''] if lines else []


def _rst_params(entry: CatalogEntry, c: Contract) -> list[str]:
    if not entry.params:
        return []
    out = ['.. list-table::', '   :widths: 20 15 15 50', '   :header-rows: 1', '']
    out += ['   * - Parameter', '     - Type', '     - Default', '     - Description']
    for p in entry.params:
        doc = _rst_inline(p.doc) or '-'
        if p.name in c.choices:
            doc += ' Allowed: ' + ', '.join(f'``{v}``' for v in c.choices[p.name]) + '.'
        out += [
            f'   * - ``{p.name}``',
            f'     - ``{p.type}``' if p.type else '     - ',
            '     - **required**' if p.required or p.default == '' else f'     - ``{p.default!r}``',
            f'     - {doc}',
        ]
    return out


def _rst_outcomes(c: Contract) -> list[str]:
    out = []
    for outcome in ('passed', 'failed', 'error'):
        conditions = c.outcomes.get(outcome, ())
        if conditions:
            out += [f'**{outcome.capitalize()}**', '', *[f'* {_rst_inline(x)}' for x in conditions], '']
    return out


def _rst_examples(entry: CatalogEntry, c: Contract) -> list[str]:
    if not c.examples:
        return ['.. code-block:: yaml', '', *_indent(entry.example_yaml().rstrip()), '']
    out = []
    for example in c.examples:
        text = f'. {_rst_inline(example.text)}' if example.text else ''
        out += [f'*{_rst_inline(example.title)}* → **{example.expect.upper()}**{text}', '']
        out += ['.. code-block:: yaml', '', *_indent(example_yaml(entry.dotnotation, example).rstrip()), '']
    return out


def function_rst(entry: CatalogEntry, library: Library, docs_root: Path = DOCS_ROOT) -> str:
    c = entry.contract or Contract()
    out = [f'**{_rst_inline(entry.summary[:1].upper() + entry.summary[1:])}.**', '']
    if prose(entry.doc):
        out += [prose(entry.doc), '']
    if use_for(entry.doc):
        out += [f'**Use for:** {_rst_inline(use_for(entry.doc))}', '']
    out += [f':Runs: {runs_where(entry.category, entry.name)}', f':OS: {entry.os}']
    if entry.contract:
        out += [f':Asserts: {", ".join(c.asserts)}', f':Formats: {", ".join(c.formats) or "-"}']
    if c.features:
        out.append(f':Supports: {", ".join(feature_ref(f, library) for f in c.features)}')
    out.append('')
    out += _rst_block(
        'What it does not do',
        [f'* No {feature_ref(fid, library)}: {_rst_inline(why)}' for fid, why in c.unsupported.items()]
        + [f'* Not for {_rst_inline(r.text)}: use {doc_link(r.use, docs_root)}.' for r in c.not_for],
    )
    out += _rst_block('Parameters', _rst_params(entry, c))
    if c.outcomes:
        out += [*_rst_section('Outcomes'), *_rst_outcomes(c)]
    out += _rst_block('Limits', [f'* {_rst_inline(x)}' for x in c.limits])
    cases = []
    for u in c.use_cases:
        cases += [f'**{_rst_inline(u.title)}**', *([f'   {_rst_inline(u.text)}'] if u.text else []), '']
    out += _rst_block('Common Use Cases', cases)
    out += [*_rst_section('Examples'), *_rst_examples(entry, c)]
    out += _rst_block('See Also', [f'* {doc_link(r.use, docs_root)}: {_rst_inline(r.text)}' for r in c.related])
    return '\n'.join(out)


def features_rst(entries: list[CatalogEntry], library: Library, docs_root: Path = DOCS_ROOT) -> str:
    out: list[str] = []
    for fid, feature in library.features.items():
        out += [f'.. _tf-feature-{fid}:', '']
        out += _rst_section(f'{feature.title}')
        out += [_rst_inline(feature.summary), '']
        if feature.syntax:
            out += ['.. code-block:: text', '', *_indent(feature.syntax), '']
        supported = [doc_link(e.dotnotation, docs_root) for e in entries if e.contract and fid in e.contract.features]
        if supported:
            out += [f'**Supported by:** {", ".join(supported)}', '']
        for e in entries:
            if e.contract and fid in e.contract.unsupported:
                out.append(f'* Not {doc_link(e.dotnotation, docs_root)}: {_rst_inline(e.contract.unsupported[fid])}')
        if any(e.contract and fid in e.contract.unsupported for e in entries):
            out.append('')
        if feature.doc:
            out += [f'More: :doc:`{feature.doc}`', '']
    out += ['.. _tf-known-gaps:', '']
    out += _rst_section('Known gaps')
    out += ['Goals no bundled testfunction covers; ``adare test search`` names them when a query hits one.', '']
    for gap in library.gaps:
        out += [f'* **{_rst_inline(gap.summary)}** {_rst_inline(gap.instead)}']
    out.append('')
    return '\n'.join(out)


def collection_rst(collection: str, entries: list[CatalogEntry]) -> str:
    own = [e for e in entries if e.collection == collection]
    info = own[0].collection_info if own else None
    return _rst_inline(info.summary) + '\n' if info and info.summary else ''
