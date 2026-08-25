from pathlib import Path


def test_download_writes_atomically_and_hashes_pdf(tmp_path: Path) -> None:
    from quantradar.research.download.pdf import PdfDownloader

    downloader = PdfDownloader(tmp_path, fetch=lambda _: b"%PDF-1.4\nbody", page_counter=lambda _: 3)
    artifact = downloader.download("A" * 32, {"fileUrl": "https://example.test/a.pdf", "filePages": 3})

    assert artifact.status == "SUCCESS"
    assert artifact.path.exists()
    assert artifact.sha256
    assert artifact.pages == 3
    assert not list(tmp_path.rglob("*.part"))


def test_non_pdf_is_unsupported_not_failed(tmp_path: Path) -> None:
    from quantradar.research.download.pdf import PdfDownloader

    artifact = PdfDownloader(tmp_path).download("A" * 32, None)

    assert artifact.status == "UNSUPPORTED"
    assert artifact.error_code == "UNSUPPORTED_CONTENT"
