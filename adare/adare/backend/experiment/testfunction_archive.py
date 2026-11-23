"""Build the zip archive of testfunction files that is uploaded to the guest."""

import io
import logging
import zipfile
from collections.abc import Iterable
from pathlib import Path

from adare.exceptions import TestfunctionUploadError

log = logging.getLogger(__name__)


def build_testfunctions_zip(testfunctions_path: Path, specific_files: Iterable[Path] | None = None) -> bytes:
    """Zip testfunction files, with archive names relative to ``testfunctions_path``.

    Paths are compared after ``Path.resolve()`` so a symlinked or differently spelled
    testfunctions directory (e.g. ADARE_HOME reached through a symlink, while the
    testfunction database holds the real paths) still matches.

    Args:
        testfunctions_path: Directory that contains the testfunctions.
        specific_files: Files to upload. ``None`` (or empty) uploads the whole directory.

    Raises:
        TestfunctionUploadError: If a requested file is missing or is not inside
            ``testfunctions_path``. Nothing partial is ever returned: the guest would
            only report the missing functions as "not found".
    """
    root = testfunctions_path.resolve()
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        if specific_files:
            problems = []
            to_write: list[tuple[Path, Path]] = []
            for file_path in sorted(specific_files):
                resolved = file_path.resolve()
                if not resolved.is_file():
                    problems.append(f"{file_path}: file does not exist")
                    continue
                try:
                    to_write.append((resolved, resolved.relative_to(root)))
                except ValueError:
                    problems.append(f"{file_path}: outside the testfunctions directory {root}")
            if problems:
                raise TestfunctionUploadError(
                    log,
                    "Cannot upload testfunctions to the guest; required file(s) unusable:\n  " + "\n  ".join(problems),
                    possible_solutions=[
                        "Reload the testfunctions: adare test load <path>",
                        "Check that the testfunction paths in the database lie inside the ADARE state directory",
                    ],
                )
            for resolved, arcname in to_write:
                zip_file.write(resolved, arcname)
        else:
            for file_path in root.rglob('*'):
                if file_path.is_file():
                    zip_file.write(file_path, file_path.relative_to(root))
    return zip_buffer.getvalue()
