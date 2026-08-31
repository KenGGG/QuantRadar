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


def test_parse_pdf_returns_markdown_from_completed_response(tmp_path, monkeypatch) -> None:
    from quantradar.research.parser.mineru import MineruClient

    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4\nbody")

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"status": "completed", "version": "3.4.4", "results": {"report": {"md_content": "# parsed"}}}

    class FakeClient:
        def __init__(self, **_kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            pass

        def post(self, url, *, files, data):
            assert url == "http://mineru.test/file_parse"
            assert files["files"][0] == "report.pdf"
            assert data == {"backend": "pipeline", "return_md": "true", "response_format_zip": "false"}
            return FakeResponse()

    monkeypatch.setattr("quantradar.research.parser.mineru.httpx.Client", FakeClient)

    assert MineruClient("http://mineru.test").parse_pdf(pdf) == ("# parsed", "3.4.4")
