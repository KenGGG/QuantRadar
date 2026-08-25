import io
import zipfile

import pytest


def test_safe_zip_rejects_path_traversal(tmp_path) -> None:
    from quantradar.research.parser.mineru import extract_mineru_zip

    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("../escape.md", "bad")

    with pytest.raises(ValueError, match="unsafe"):
        extract_mineru_zip(payload.getvalue(), tmp_path / "out")
