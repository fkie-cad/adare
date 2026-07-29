"""
Export experiment files for submission to the shared Gitea repository.
"""
import logging
import re
from pathlib import Path

from adare.backend.project.directory import ProjectDirectory
from adare.services.recipe_contract import (
    SHA256_HEX_RE,
    RecipeContractError,
    check_recipe_publish_contract,
    normalized_iso_sha256,
    profile_platform,
)

log = logging.getLogger(__name__)

# Publish contract mirror (see server `giteaeventmanager/.../plugin.py`
# `check_file_validity` and webapi `_validate_url_format`): the same rules are
# enforced here, client-side, so a local path or a missing sha256 is caught
# BEFORE any Gitea branch/PR is created — never leak a local filesystem path.
#
# Case-INSENSITIVE here, and that is correct for the baked branch only: the
# download-time check lowercases the declared value before comparing
# (`backend/environment/commands.py`), so an uppercase `vm_sha256` verifies fine.
# The recipe branch is different — `verify_iso_hash` compares case-SENSITIVELY,
# so an uppercase `iso_sha256` would pass publish and then never build. That
# branch therefore goes through `services.recipe_contract`, which normalizes to
# lowercase and matches lowercase-only. The asymmetry is deliberate, not an
# oversight.
_SHA256_HEX_RE = re.compile(r'^[0-9a-f]{64}$', re.IGNORECASE)
_DISK_EXTENSIONS = ('.ova', '.qcow2', '.vmdk', '.vdi', '.img')
_VM_FORMATS = ('qcow2', 'ova', 'vmdk', 'vdi', 'img', 'raw')


class EnvironmentSubmissionError(ValueError):
    """An environment failed the client-side publish pre-flight.

    Raised before any Gitea branch/PR is created, so a non-publishable
    environment (local path, missing/invalid sha256, missing vm_format) never
    reaches the shared repo.
    """


class ExperimentSubmissionError(ValueError):
    """An experiment failed the client-side dependency pre-flight.

    Raised before any Gitea branch/PR is created, so an experiment whose
    test functions or environments the server cannot resolve never reaches the
    shared repo. Mirrors the server's ingest-time ``UNKNOWN_DEPENDENCY`` check
    (``giteaeventmanager/action/plugin.py``, ``ExperimentPlugin``).
    """


def _is_http_url(value: str) -> bool:
    from urllib.parse import urlparse
    return urlparse(value).scheme in ('http', 'https')


def _preflight_environment(env_file: Path) -> None:
    """Enforce the URL-only + required-sha256 publish contract on ``env_file``.

    Raises:
        EnvironmentSubmissionError: If the environment is not publishable.
    """
    from adare.types.environment import parse_environment_file

    metadata = parse_environment_file(env_file)
    if metadata is None:
        raise EnvironmentSubmissionError(f'Could not parse environment file: {env_file}')

    # Recipe source: the disk is built on load. The ISO must be either a published
    # http(s) URL, or — for a Windows profile only, where the installer cannot
    # lawfully be rehosted — a consumer-supplied `iso_name`. `iso_sha256` is
    # required either way. This is gate 1, and it is AUTHORITATIVE for publishing:
    # the server's ingest check cannot resolve profile -> platform (it has no OS
    # catalog), so this is the only place the full contract is enforced before a
    # Gitea branch/PR exists.
    if metadata.is_recipe_environment:
        declared_platform = metadata.os.platform if metadata.os is not None else None
        try:
            check_recipe_publish_contract(metadata.recipe, declared_platform)
        except RecipeContractError as e:
            # Fold the solutions into the message: EnvironmentSubmissionError has no
            # structured field for them, and "host the ISO" / "run env recipe-byo"
            # is the part the publisher actually acts on.
            detail = str(e)
            if e.possible_solutions:
                detail += '\n' + '\n'.join(f'  - {hint}' for hint in e.possible_solutions)
            raise EnvironmentSubmissionError(detail) from e
        return

    # Legacy vagrantbox (owner/box) is verified by the server against Vagrant
    # Cloud; nothing local to leak here.
    if metadata.is_vagrant_environment:
        return

    # Baked VM source: must be a published http(s) URL with a required sha256.
    vm = metadata.vm or ''
    if not _is_http_url(vm):
        raise EnvironmentSubmissionError(
            f"'vm' must be an http(s) URL to publish a baked environment (got a local path: {vm!r}). "
            "Host the disk image and reference its URL, e.g. via "
            "'adare environment publish-prepare'."
        )
    if not metadata.vm_sha256 or not _SHA256_HEX_RE.match(metadata.vm_sha256):
        raise EnvironmentSubmissionError(
            "'vm_sha256' is required and must be 64 hex characters to publish a baked VM URL."
        )
    if metadata.vm_format is not None and metadata.vm_format not in _VM_FORMATS:
        raise EnvironmentSubmissionError(
            "'vm_format' must be one of: " + ", ".join(_VM_FORMATS)
        )
    from urllib.parse import urlparse
    has_ext = urlparse(vm).path.lower().endswith(_DISK_EXTENSIONS)
    if not has_ext and not metadata.vm_format:
        raise EnvironmentSubmissionError(
            "'vm_format' is required when the VM URL has no recognized disk extension "
            "(one of: " + ", ".join(_VM_FORMATS) + ")."
        )

    # Optional install-profile provenance (informational only -- never blocks a
    # publish, never used to rebuild the disk; see EnvironmentMetadata.source_profile).
    if metadata.source_iso_sha256:
        digest = normalized_iso_sha256(metadata.source_iso_sha256)
        if not SHA256_HEX_RE.match(digest):
            raise EnvironmentSubmissionError(
                f"'source_iso_sha256' must be 64 hex characters (got {metadata.source_iso_sha256!r})."
            )
    if metadata.source_profile and profile_platform(metadata.source_profile) is None:
        log.warning(
            "'source_profile' %r is not a known OS profile on this host; publishing "
            "anyway -- this field is informational and not validated as authoritative "
            "(a host-local custom profile in ~/.adare/os-profiles/ may simply not "
            "resolve here).",
            metadata.source_profile,
        )
    if not metadata.source_profile and not metadata.source_iso_sha256:
        declared_platform = metadata.os.platform if metadata.os is not None else None
        if declared_platform != 'windows':
            print(
                "Note: no source install-profile/ISO hash attached -- consider "
                "'adare environment publish-prepare --source-profile ... "
                "--source-iso-sha256 ...' for provenance."
            )


# --- Experiment dependency pre-flight -------------------------------------------
#
# The server resolves an experiment's dependencies at INGEST time, long after the
# CLI has already opened a Gitea PR (`giteaeventmanager/action/plugin.py`,
# `ExperimentPlugin.__db_get_abstract_test` / `__db_create_experiment`):
#
#   TestFunction.objects.filter(name=test.type).first()   -> UNKNOWN_DEPENDENCY
#   Environment.objects.filter(name=env)                  -> UNKNOWN_DEPENDENCY
#
# `test.type` is the playbook's `function:` string VERBATIM, and the environment
# name is the metadata entry verbatim. Both are exact-match lookups. So the check
# below deliberately models the SERVER's lookup, not the client's resolution rule
# (`adarelib.testset.testfunction.get_testclass_from_testfunction`, which splits
# `<set>.<name>` and treats an unprefixed name as `standard.<name>`). A pre-flight
# written against the client's rule would pass names the server then rejects.
_PUBLIC_CATALOG_PAGE_LIMIT = 500
_PUBLIC_CATALOG_MAX_PAGES = 20
# Catalog responses are cached briefly so that submitting several experiments in a
# row does not re-fetch (and trip the server's rate limiter). Short enough that a
# dependency PR merged mid-session is picked up on the next attempt.
_PUBLIC_CATALOG_CACHE_SECONDS = 60
_public_catalog_cache: dict[str, tuple[float, list[dict]]] = {}


def _load_yaml_ignoring_custom_tags(yaml_file: Path) -> dict:
    """Parse ``yaml_file``, keeping unknown ``!tag`` values as opaque scalars.

    Playbooks carry custom tags (``!re``, ``!timestamp``, ...) that plain
    ``yaml.safe_load`` refuses to construct. The pre-flight only needs the plain
    strings under ``tests[].function`` and ``environments``, so every unrecognized
    tag is collapsed to its raw node value rather than requiring this module to
    track the full tag vocabulary.

    Raises:
        yaml.YAMLError: If the document is not well-formed YAML.
    """
    import yaml

    class _TolerantLoader(yaml.SafeLoader):
        pass

    def _keep_raw(loader, tag_suffix, node):
        if isinstance(node, yaml.ScalarNode):
            return node.value
        if isinstance(node, yaml.SequenceNode):
            return loader.construct_sequence(node)
        return loader.construct_mapping(node)

    _TolerantLoader.add_multi_constructor('', _keep_raw)

    parsed = yaml.load(yaml_file.read_text(encoding='utf-8'), Loader=_TolerantLoader)
    return parsed if isinstance(parsed, dict) else {}


def _playbook_test_function_names(playbook_file: Path) -> list[str]:
    """Return the `function:` values of a playbook's `tests:` block, in order.

    Mirrors the server's `testsetfile.parser.parse_playbook_tests`: only flat
    `function` entries exist in the playbook schema, and values are taken as
    authored (unresolved ``{{ }}`` tokens included).
    """
    parsed = _load_yaml_ignoring_custom_tags(playbook_file)
    functions = []
    for entry in parsed.get('tests') or []:
        if isinstance(entry, dict) and entry.get('function'):
            functions.append(str(entry['function']))
    return functions


def _metadata_environment_names(metadata_file: Path) -> list[str]:
    """Return the environment names declared in an experiment's metadata.yml."""
    parsed = _load_yaml_ignoring_custom_tags(metadata_file)
    return [str(env) for env in (parsed.get('environments') or [])]


def _fetch_public_catalog(endpoint: str) -> list[dict]:
    """GET every page of a catalog list endpoint under ``API_URL``, authenticated.

    The endpoints (``testfunction/``, ``environment/``) are themselves
    ``AllowAny``, but this pre-flight runs on every experiment submission and an
    anonymous GET is subject to the anon throttle -- shared with every other
    unauthenticated caller of the API. ``adare web submit`` already requires a
    login (``_create_pr`` raises ``NotLoggedInError`` otherwise), so there is no
    reason to hit the anon path here: authenticate with the same Django token
    used for the rest of the submit flow, which the ``user`` throttle governs
    instead.

    Raises:
        NotLoggedInError: If the CLI has no active session.
        requests.RequestException: On any transport/HTTP failure.
        ValueError: If a response body is not the expected paginated JSON.
    """
    import time

    import requests

    import adare.config.server as config_server
    from adare.webappaccess.login import WebappLogin

    cached = _public_catalog_cache.get(endpoint)
    if cached and (time.monotonic() - cached[0]) < _PUBLIC_CATALOG_CACHE_SECONDS:
        return cached[1]

    headers = WebappLogin().get_django_authenticated_request_header()
    url = f'{config_server.API_URL}{endpoint}?limit={_PUBLIC_CATALOG_PAGE_LIMIT}'
    results: list[dict] = []
    for _ in range(_PUBLIC_CATALOG_MAX_PAGES):
        response = requests.get(url, headers=headers, timeout=config_server.TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get('results'), list):
            raise ValueError(f'unexpected response shape from {endpoint}')
        results.extend(item for item in payload['results'] if isinstance(item, dict))
        url = payload.get('next')
        if not url:
            break

    _public_catalog_cache[endpoint] = (time.monotonic(), results)
    return results


def _server_testfunction_index() -> tuple[set[str], dict[str, set[str]], set[str]]:
    """Read the server's published test-function catalog.

    Returns:
        ``(registered, bare_to_sets, published_sets)`` where ``registered`` holds
        every ``TestFunction.name`` exactly as the server stores it (that is what
        ingest matches against), ``bare_to_sets`` maps a registered name to the
        set(s) that own it, and ``published_sets`` holds the testfunctionset names.
    """
    registered: set[str] = set()
    bare_to_sets: dict[str, set[str]] = {}
    published_sets: set[str] = set()

    for tfset in _fetch_public_catalog('testfunction/'):
        set_name = tfset.get('name')
        if not set_name:
            continue
        published_sets.add(set_name)
        for testfunction in tfset.get('testfunctions') or []:
            if not isinstance(testfunction, dict):
                continue
            tf_name = testfunction.get('name')
            if not tf_name:
                continue
            registered.add(tf_name)
            bare_to_sets.setdefault(tf_name, set()).add(set_name)

    return registered, bare_to_sets, published_sets


def _server_environment_names() -> set[str]:
    """Read the names of the server's published environments."""
    return {
        env['name'] for env in _fetch_public_catalog('environment/')
        if env.get('name')
    }


def _owning_set(function_name: str) -> str:
    """The testfunctionset a playbook `function:` value belongs to.

    Matches `adarelib`'s rule: an unprefixed name lives in `standard`.
    """
    return function_name.split('.', 1)[0] if '.' in function_name else 'standard'


def _qualified_name(function_name: str) -> str:
    """``function_name`` in the ``<set>.<name>`` form the server now registers.

    The server qualifies every ``TestFunction.name`` on ingest (adare-server
    migration ``0018_qualify_testfunction_names``), including bare decorator
    names living in ``standard``. Comparing a playbook's bare ``function:``
    value against that catalog verbatim would false-positive every unprefixed
    standard function as missing -- this mirrors the same ``adarelib`` rule
    ``_owning_set`` already applies, so a name that resolves locally resolves
    here too.
    """
    return function_name if '.' in function_name else f'{_owning_set(function_name)}.{function_name}'


def _describe_missing_testfunction(function_name: str, bare_to_sets: dict[str, set[str]],
                                   published_sets: set[str]) -> str:
    """One actionable line explaining why the server cannot resolve ``function_name``."""
    owner = _owning_set(function_name)
    bare = function_name.split('.', 1)[1] if '.' in function_name else function_name

    if bare in bare_to_sets and owner in bare_to_sets[bare]:
        # The server is expected to register every function as `<set>.<name>`
        # (adare-server migration 0018_qualify_testfunction_names). A set still
        # carrying an unprefixed registration for this function means IT has not
        # been re-ingested since that migration -- resubmitting this experiment
        # will not help, since the mismatch is in the set's own registration.
        return (f"  - {function_name}: the set '{owner}' is published but still registers this "
                f"function as '{bare}' (without the set prefix), so the server's exact-name "
                f"lookup for the qualified '{owner}.{bare}' misses it. Re-submit the "
                f"testfunctionset so it is re-ingested under the qualified name: "
                f"adare web submit testfunction {owner} -p <project>.")

    if owner not in published_sets:
        return (f"  - {function_name}: testfunctionset '{owner}' is not published on the "
                f"server. Submit it first: adare web submit testfunction {owner} "
                f"-p <project>, then have that PR merged.")

    return (f"  - {function_name}: testfunctionset '{owner}' is published but registers no "
            f"function matching this name. Check the @testfunction(name=...) value in "
            f"{owner}/{owner}.py and resubmit the set.")


def _preflight_experiment(experiment_name: str, playbook_file: Path, metadata_file: Path) -> None:
    """Verify the server can resolve every dependency this experiment declares.

    Runs before any Gitea branch/PR exists. If the shared server cannot be reached
    the check is skipped with a warning -- an offline host must not be blocked from
    submitting, and the server stays authoritative either way.

    Raises:
        ExperimentSubmissionError: If a referenced test function or environment is
            not resolvable server-side, i.e. ingest would fail with
            ``UNKNOWN_DEPENDENCY``.
    """
    import requests
    import yaml

    try:
        declared_functions = _playbook_test_function_names(playbook_file)
        declared_environments = _metadata_environment_names(metadata_file)
    except yaml.YAMLError as e:
        log.warning(
            'Could not parse %r to pre-flight its dependencies (%s); submitting '
            'anyway -- the server will still reject an unresolvable dependency at '
            'ingest time.', experiment_name, e,
        )
        return

    try:
        registered, bare_to_sets, published_sets = _server_testfunction_index()
        published_environments = _server_environment_names()
    except (requests.RequestException, ValueError) as e:
        log.warning(
            'Could not read the server catalog to pre-flight %r dependencies (%s); '
            'submitting anyway -- the server will still reject an unresolvable '
            'dependency at ingest time.', experiment_name, e,
        )
        return

    problems: list[str] = []

    # Compare the QUALIFIED form: the server registers every function as
    # `<set>.<name>` (see _qualified_name), so a bare playbook name must be
    # normalized the same way before the set-difference, or every unprefixed
    # `standard` function would false-positive as missing.
    missing_functions = [
        function for function in dict.fromkeys(declared_functions)
        if _qualified_name(function) not in registered
    ]
    if missing_functions:
        problems.append(
            f"Test functions the server cannot resolve for experiment '{experiment_name}':"
        )
        problems.extend(
            _describe_missing_testfunction(function, bare_to_sets, published_sets)
            for function in missing_functions
        )

    missing_environments = [
        env for env in dict.fromkeys(declared_environments)
        if env not in published_environments
    ]
    if missing_environments:
        problems.append(
            f"Environments not published on the server for experiment '{experiment_name}':"
        )
        problems.extend(
            f"  - {env}: submit and merge it first: adare web submit environment {env} "
            f"-p <project>" for env in missing_environments
        )

    if problems:
        raise ExperimentSubmissionError(
            '\n'.join(problems)
            + '\nThe server resolves these at ingest and would reject the pull request '
              'with UNKNOWN_DEPENDENCY, so no PR was created.'
        )


def export_experiment_for_submission(project_path: Path, experiment_name: str,
                                     check_dependencies: bool = True) -> dict[str, bytes]:
    """
    Collect experiment files for Gitea submission.

    Args:
        project_path: Project root.
        experiment_name: Experiment to export.
        check_dependencies: Run the server dependency pre-flight (see
            :func:`_preflight_experiment`). Pass ``False`` to bypass it when the
            server's published catalog is known to understate what ingest can
            resolve.

    Returns dict mapping repo-relative filepaths to file content bytes.
    """
    experiment_dir = ProjectDirectory(project_path).experiments / experiment_name
    if not experiment_dir.is_dir():
        raise FileNotFoundError(f'Experiment directory not found: {experiment_dir}')

    files = {}

    playbook_file = experiment_dir / 'playbook.yml'
    if not playbook_file.is_file():
        raise FileNotFoundError(f'playbook.yml not found in {experiment_dir}')
    files[f'experiments/{experiment_name}/playbook.yml'] = playbook_file.read_bytes()

    metadata_file = experiment_dir / 'metadata.yml'
    if not metadata_file.is_file():
        raise FileNotFoundError(f'metadata.yml not found in {experiment_dir}')
    files[f'experiments/{experiment_name}/metadata.yml'] = metadata_file.read_bytes()

    # Pre-flight the dependency contract BEFORE returning any bytes to the submit
    # service (which would otherwise open a PR the server can only ever reject).
    if check_dependencies:
        _preflight_experiment(experiment_name, playbook_file, metadata_file)

    img_dir = experiment_dir / 'img'
    if img_dir.is_dir():
        image_count = 0
        for entry in img_dir.iterdir():
            if entry.is_file():
                files[f'experiments/{experiment_name}/img/{entry.name}'] = entry.read_bytes()
                image_count += 1
        log.info(f'Collected {image_count} image(s) from {img_dir}')

    return files


def export_testfunction_for_submission(project_path: Path, testfunction_name: str) -> dict[str, bytes]:
    """
    Collect testfunction files for Gitea submission.

    Returns dict mapping repo-relative filepaths to file content bytes.
    """
    tf_dir = ProjectDirectory(project_path).testfunctions / testfunction_name
    if not tf_dir.is_dir():
        raise FileNotFoundError(f'Testfunction directory not found: {tf_dir}')

    files = {}

    py_file = tf_dir / f'{testfunction_name}.py'
    if not py_file.is_file():
        raise FileNotFoundError(f'{testfunction_name}.py not found in {tf_dir}')
    files[f'testfunctions/{testfunction_name}/{testfunction_name}.py'] = py_file.read_bytes()

    req_file = tf_dir / 'requirements.txt'
    if not req_file.is_file():
        raise FileNotFoundError(f'requirements.txt not found in {tf_dir}')
    files[f'testfunctions/{testfunction_name}/requirements.txt'] = req_file.read_bytes()

    return files


def export_environment_for_submission(project_path: Path, environment_name: str) -> dict[str, bytes]:
    """
    Collect environment file for Gitea submission.

    Returns dict mapping repo-relative filepaths to file content bytes.
    """
    # Local import mirrors the codebase's lazy-import pattern and avoids any
    # backend<->webappaccess import cycle.
    from adare.backend.environment.database import get_environment_path_by_project_and_name

    env_file = get_environment_path_by_project_and_name(project_path, environment_name)
    if not env_file.is_file():
        raise FileNotFoundError(f'Environment file not found: {env_file}')

    # Pre-flight the publish contract BEFORE returning any bytes to the submit
    # service (which would otherwise create a Gitea branch/PR for a
    # non-publishable environment). This is the client-side no-path-leak guard.
    _preflight_environment(env_file)

    return {f'environments/{environment_name}.yml': env_file.read_bytes()}
