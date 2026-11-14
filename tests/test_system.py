import os
import sys
from pathlib import Path

import pytest

from discogs_alert.util import system as da_system


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_new_files_and_directories_are_private_to_the_owner(tmp_path: Path):
    os.umask(0o022)
    da_system.restrict_new_files_to_owner()
    (tmp_path / "dir").mkdir()
    (tmp_path / "file").write_text("x")
    assert (tmp_path / "dir").stat().st_mode & 0o777 == 0o700
    assert (tmp_path / "file").stat().st_mode & 0o777 == 0o600
