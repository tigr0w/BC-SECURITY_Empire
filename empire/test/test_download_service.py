def test__increment_filename(tmp_path):
    from empire.server.core.download_service import DownloadService

    path = tmp_path / "test.txt"

    filename, location = DownloadService._increment_filename("test.txt", path)

    assert filename == "test.txt"
    assert location == path

    path.write_text("test")

    filename, location = DownloadService._increment_filename("test.txt", path)

    assert filename == "test(1).txt"
    assert location == tmp_path / "test(1).txt"

    location.write_text("test")

    filename, location = DownloadService._increment_filename("test.txt", path)

    assert filename == "test(2).txt"
    assert location == tmp_path / "test(2).txt"
