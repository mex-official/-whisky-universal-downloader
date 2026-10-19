from pathlib import Path
import tempfile

import pytest

import downloader


class FakeYDL:
    """Simulate yt-dlp without making network requests."""

    def __init__(self, opts, content=b"test media"):
        self.opts = opts
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=True):
        output = Path(
            self.opts["outtmpl"]
            .replace("%(id)s", "sample")
            .replace("%(ext)s", "mp4")
        )
        output.write_bytes(self.content)
        return {
            "id": "sample",
            "ext": "mp4",
            "filepath": str(output),
        }

    def prepare_filename(self, info):
        return self.opts["outtmpl"].replace(
            "%(id)s", info["id"]
        ).replace("%(ext)s", info["ext"])


def test_download_success_returns_file_and_temp_directory(monkeypatch):
    monkeypatch.setattr(downloader, "is_valid_url", lambda url: True)
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", FakeYDL)

    temp, path = downloader.download_media("https://example.com/video")

    try:
        assert path.is_file()
        assert path.read_bytes() == b"test media"
        assert path.resolve().is_relative_to(Path(temp.name).resolve())
    finally:
        temp.cleanup()


def test_invalid_url_is_rejected_before_temp_directory(monkeypatch):
    monkeypatch.setattr(downloader, "is_valid_url", lambda url: False)

    def should_not_create_temp(*args, **kwargs):
        pytest.fail("Temporary directory must not be created for invalid URL")

    monkeypatch.setattr(
        downloader.tempfile, "TemporaryDirectory", should_not_create_temp
    )

    with pytest.raises(downloader.DownloadError, match="URL rejected"):
        downloader.download_media("https://example.com/video")


def test_yt_dlp_failure_cleans_temporary_directory(monkeypatch):
    monkeypatch.setattr(downloader, "is_valid_url", lambda url: True)
    real_factory = tempfile.TemporaryDirectory
    created = []

    def tracked_temp(*args, **kwargs):
        item = real_factory(*args, **kwargs)
        created.append(item)
        return item

    class FailingYDL(FakeYDL):
        def extract_info(self, url, download=True):
            raise RuntimeError("simulated download failure")

    monkeypatch.setattr(
        downloader.tempfile, "TemporaryDirectory", tracked_temp
    )
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", FailingYDL)

    with pytest.raises(RuntimeError, match="simulated download failure"):
        downloader.download_media("https://example.com/video")

    assert len(created) == 1
    assert not Path(created[0].name).exists()


def test_size_filter_rejects_known_oversized_media(monkeypatch):
    monkeypatch.setattr(downloader, "MAX_BYTES", 100)

    assert downloader._size_filter({"filesize": 101}) is not None
    assert downloader._size_filter({"filesize": 100}) is None


def test_size_filter_checks_approximate_size():
    assert downloader._size_filter({"filesize_approx": downloader.MAX_BYTES + 1})


@pytest.mark.parametrize(
    "status",
    [
        {"downloaded_bytes": downloader.MAX_BYTES + 1},
        {"total_bytes": downloader.MAX_BYTES + 1},
        {"total_bytes_estimate": downloader.MAX_BYTES + 1},
    ],
)
def test_progress_hook_rejects_oversized_download(status):
    with pytest.raises(downloader.DownloadError, match="exceeds"):
        downloader._enforce_download_limit(status)


def test_progress_hook_allows_download_within_limit():
    downloader._enforce_download_limit(
        {"downloaded_bytes": downloader.MAX_BYTES}
    )


def test_merged_output_path_is_preferred(tmp_path):
    merged = tmp_path / "sample.mkv"
    merged.write_bytes(b"merged media")

    class YDL:
        def prepare_filename(self, info):
            return str(tmp_path / "sample.mp4")

    result = downloader._find_output(
        {"filepath": str(merged)}, YDL(), tmp_path.resolve()
    )

    assert result == merged.resolve()


def test_ambiguous_output_is_rejected(tmp_path):
    (tmp_path / "first.mp4").write_bytes(b"first")
    (tmp_path / "second.mp4").write_bytes(b"second")

    class YDL:
        def prepare_filename(self, info):
            return str(tmp_path / "missing.mp4")

    with pytest.raises(downloader.DownloadError, match="single downloaded file"):
        downloader._find_output({}, YDL(), tmp_path.resolve())


def test_final_file_size_is_checked(monkeypatch):
    monkeypatch.setattr(downloader, "is_valid_url", lambda url: True)

    class OversizedYDL(FakeYDL):
        def extract_info(self, url, download=True):
            return super().extract_info(url, download)

    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", OversizedYDL)
    monkeypatch.setattr(downloader, "MAX_BYTES", 5)

    with pytest.raises(downloader.DownloadError, match="exceeds"):
        downloader.download_media("https://example.com/video")


@pytest.mark.parametrize(
    "bad_size",
    [True, -1, float("nan"), float("inf"), float("-inf"), "123"],
)
@pytest.mark.parametrize("field", ["filesize", "filesize_approx"])
def test_size_metadata_rejects_invalid_values(field, bad_size):
    assert downloader._size_filter({field: bad_size}) is not None


@pytest.mark.parametrize(
    ("field", "bad_size"),
    [
        ("downloaded_bytes", True),
        ("downloaded_bytes", -1),
        ("downloaded_bytes", float("nan")),
        ("downloaded_bytes", float("inf")),
        ("total_bytes", "123"),
        ("total_bytes_estimate", -1),
    ],
)
def test_progress_hook_rejects_invalid_size_metadata(field, bad_size):
    with pytest.raises(downloader.DownloadError, match="Invalid download size"):
        downloader._enforce_download_limit({field: bad_size})


def test_progress_hook_rejects_non_dict_metadata():
    with pytest.raises(downloader.DownloadError, match="Invalid download progress"):
        downloader._enforce_download_limit(None)


def test_size_metadata_accepts_exact_limit():
    assert downloader._size_filter({"filesize": downloader.MAX_BYTES}) is None


def test_size_metadata_rejects_oversized_exact_integer():
    assert downloader._size_filter(
        {"filesize": downloader.MAX_BYTES + 1}
    ) == "File exceeds Telegram upload limit"
