from pathlib import Path
import hashlib

from backend_business.services.file_service import FileService


def test_file_service_preserves_unicode_folder_structure_and_metadata(tmp_path):
    service = FileService(str(tmp_path / "uploads"))

    saved = service.save_uploaded_file(
        user_id="u1",
        original_filename="照片 01.jpg",
        content=b"fake-image-content",
        content_type="image/jpeg",
        folder="旅行/上海",
        import_time="1710000000000",
        capture_time="1700000000000",
    )

    assert saved["folder"] == "旅行/上海"
    assert saved["relativePath"].startswith("旅行/上海/")
    assert saved["importTime"] == 1710000000000
    assert saved["captureTime"] == 1700000000000
    assert saved["checksum"] == hashlib.sha256(b"fake-image-content").hexdigest()

    folders = service.list_user_folders("u1")
    assert folders[0]["name"] == "旅行"
    assert folders[0]["fileCount"] == 1

    folder_files = service.list_folder_files("u1", "旅行")
    assert len(folder_files) == 1
    assert folder_files[0]["originalFilename"] == "照片 01.jpg"
    assert folder_files[0]["relativePath"] == saved["relativePath"]
    assert folder_files[0]["captureTime"] == 1700000000000
    assert folder_files[0]["checksum"] == saved["checksum"]

    listed_files = service.list_uploaded_files("u1")
    assert listed_files[0]["relativePath"] == saved["relativePath"]

    all_files = service.list_all_users_files()
    assert all_files["u1"][0]["userId"] == "u1"
    assert all_files["u1"][0]["relativePath"] == saved["relativePath"]

    tree = service.list_all_users_file_tree()
    assert tree[0]["userId"] == "u1"
    assert tree[0]["folders"][0]["path"] == "旅行/上海"
    assert tree[0]["folders"][0]["files"][0]["importTime"] == 1710000000000

    resolved_path, mime_type, normalized_path = service.resolve_user_file_by_relative_path(
        "u1", saved["relativePath"]
    )
    assert normalized_path == saved["relativePath"]
    assert resolved_path.endswith(saved["filename"])
    assert mime_type == "image/jpeg"

    nested_path, _, nested_name = service.resolve_accessible_file("u1", saved["filename"])
    assert nested_path.endswith(saved["filename"])
    assert nested_name == saved["filename"]


def test_delete_user_file_by_relative_path_removes_file_and_metadata(tmp_path):
    service = FileService(str(tmp_path / "uploads"))

    saved = service.save_uploaded_file(
        user_id="u1",
        original_filename="demo.png",
        content=b"demo",
        content_type="image/png",
        folder="相册A",
    )
    file_path, _, _ = service.resolve_user_file_by_relative_path("u1", saved["relativePath"])
    metadata_path = service._metadata_path(file_path)

    service.delete_user_file_by_relative_path("u1", saved["relativePath"])

    assert not tmp_path.joinpath("uploads", "u1", saved["relativePath"]).exists()
    assert not Path(metadata_path).exists()
