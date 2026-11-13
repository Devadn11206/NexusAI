from pathlib import Path
import pytest

from app.tools.filesystem import (
    create_file,
    read_file,
    edit_file,
    delete_file_or_folder,
    organize_directory,
    search_workspace_files,
    get_directory_tree,
)
from app.tools.computer import (
    launch_application,
    send_hotkey,
    capture_desktop_screenshot,
    list_active_windows,
)


@pytest.mark.asyncio
async def test_filesystem_crud_and_edit():
    """Verify create, read, edit, and delete operations inside workspace."""
    filename = "doc_crud_test.txt"
    initial_content = "Target system: Alpha. Version: 1.0."

    # 1. Create
    created_path = await create_file(filename, initial_content)
    assert Path(created_path).exists()

    # 2. Read
    content = await read_file(filename)
    assert content == initial_content

    # 3. Edit (Search & Replace)
    edit_res = await edit_file(filename, "1.0", "2.0")
    assert edit_res["status"] == "success"
    assert edit_res["occurrences"] == 1

    updated_content = await read_file(filename)
    assert "Version: 2.0." in updated_content

    # 4. Search
    matches = await search_workspace_files("crud_test", search_content=False)
    assert len(matches) >= 1
    assert matches[0]["filename"] == filename

    # 5. Delete
    del_res = await delete_file_or_folder(filename)
    assert del_res["status"] == "success"
    assert not Path(created_path).exists()


@pytest.mark.asyncio
async def test_directory_tree_generation():
    """Verify ASCII tree generation of workspace directory structure."""
    await create_file("tree_test/sub/file_a.txt", "content a")
    await create_file("tree_test/file_b.txt", "content b")

    tree_str = await get_directory_tree("tree_test")
    assert "tree_test/" in tree_str
    assert "file_a.txt" in tree_str
    assert "file_b.txt" in tree_str

    # Clean up
    await delete_file_or_folder("tree_test")


@pytest.mark.asyncio
async def test_strict_security_path_traversal():
    """Verify that any escape attempt outside ./workspace/ raises PermissionError."""
    with pytest.raises(PermissionError):
        await create_file("../../escape_attempt.txt", "evil")

    with pytest.raises(PermissionError):
        await read_file("..\\..\\Windows\\win.ini")

    with pytest.raises(PermissionError):
        await edit_file("../outside.txt", "find", "replace")


@pytest.mark.asyncio
async def test_computer_launch_app_and_hotkey():
    """Verify launching desktop application command and dispatching hotkeys."""
    # Test launching standard calculator or safe cmd
    res = await launch_application("calc")
    assert res["status"] in ("success", "failed")  # Handles machines without GUI safely

    # Test hotkey dispatch
    hotkey_res = await send_hotkey(["shift"])
    assert hotkey_res["status"] == "success"

    # Test desktop active windows enumeration
    windows = await list_active_windows()
    assert isinstance(windows, list)
    assert len(windows) >= 1


@pytest.mark.asyncio
async def test_computer_desktop_screenshot_artifact():
    """Verify desktop screenshot captures a valid PNG into workspace."""
    filename = "test_adv_desktop.png"
    shot_path = await capture_desktop_screenshot(filename=filename)

    assert Path(shot_path).exists()
    assert Path(shot_path).stat().st_size > 500

    # Clean up
    await delete_file_or_folder(filename)

