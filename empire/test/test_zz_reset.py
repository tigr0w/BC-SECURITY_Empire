import shutil
import sys
from importlib import reload
from pathlib import Path

import pytest

from empire.test.conftest import CLIENT_CONFIG_LOC


# These tests are run last since they reset the server and can cause other tests to fail
@pytest.fixture(scope="module", autouse=True)
def wrap_reset(server_config_dict):
    """
    This wraps the reset tests by backing up the db and restoring it.
    """
    # Move the db to a temp location
    if server_config_dict.get("database", {}).get("type") == "sqlite":
        db_loc = server_config_dict["database"]["location"]
        db_loc_backup = db_loc + ".backup"
        db_loc_path = Path(db_loc)
        db_loc_backup_path = Path(db_loc_backup)

        shutil.copyfile(db_loc, db_loc_backup)

        yield

        # Restore the db
        db_loc_backup_path.rename(db_loc_path)
    else:
        yield


@pytest.mark.slow
@pytest.mark.timeout(30)
def test_reset_server(monkeypatch, tmp_path, default_argv, server_config_dict):
    """
    Test for
     1. Deletes the sqlite db. Don't need to test mysql atm.
     2. Deletes the downloads dir contents
     3. Deletes the csharp generated files
     4. Deletes the obfuscated modules
     5. Deletes / Copies invoke obfuscation
    """
    monkeypatch.setattr("builtins.input", lambda _: "y")
    sys.argv = default_argv.copy() + ["--reset"]

    # Setup
    # Write to the downloads directory
    downloads_dir = server_config_dict["directories"]["downloads"]
    download_files = [
        ("file1.txt", "TEST"),
        ("file2.txt", "TESTTEST"),
        ("file3.txt", "TESTTESTTEST"),
        ("nested/file5.txt", "TEST"),
        ("nested/again/file6.txt", "TEST"),
        (".keep", ""),
    ]

    for f in download_files:
        write_to_file(downloads_dir + f[0], f[1])

    # check they wrote properly
    for f in download_files:
        assert Path(downloads_dir + f[0]).exists()

    # Change the csharp and Invoke-Obfuscation dir so we don't delete real files.
    csharp_dir = tmp_path / "empire/server/data/csharp"
    invoke_obfs_dir = tmp_path / "powershell/Modules/Invoke-Obfuscation"

    # Write files to csharp_dir
    csharp_files = [
        ("file1.cs", "TEST"),
        ("file2.cs", "TESTTEST"),
        ("file3.cs", "TESTTESTTEST"),
    ]
    for f in csharp_files:
        write_to_file(csharp_dir / "bin" / f[0], f[1])
        write_to_file(csharp_dir / "obj" / f[0], f[1])
        write_to_file(csharp_dir / "Data/Tasks/CSharp/Compiled/net35" / f[0], f[1])
        write_to_file(csharp_dir / "Data/Tasks/CSharp/Compiled/net40" / f[0], f[1])
        write_to_file(
            csharp_dir / "Data/Tasks/CSharp/Compiled/netcoreapp3.0" / f[0],
            f[1],
        )

    for f in csharp_files:
        assert Path(csharp_dir / "bin" / f[0]).exists()
        assert Path(csharp_dir / "obj" / f[0]).exists()
        assert Path(csharp_dir / "Data/Tasks/CSharp/Compiled/net35" / f[0]).exists()
        assert Path(csharp_dir / "Data/Tasks/CSharp/Compiled/net40" / f[0]).exists()
        assert Path(
            csharp_dir / "Data/Tasks/CSharp/Compiled/netcoreapp3.0" / f[0]
        ).exists()

    import empire.arguments

    reload(empire.arguments)
    from empire.arguments import args
    from empire.server import server

    if server_config_dict.get("database", {}).get("type") == "sqlite":
        assert Path(server_config_dict["database"]["location"]).exists()

    server.CSHARP_DIR_BASE = csharp_dir
    server.INVOKE_OBFS_DST_DIR_BASE = invoke_obfs_dir

    with pytest.raises(SystemExit):
        server.run(args)

    for f in download_files:
        if f[0] != ".keep":
            assert not Path(downloads_dir + f[0]).exists()
        else:
            assert Path(downloads_dir + f[0]).exists()

    for f in csharp_files:
        assert not Path(csharp_dir / "bin" / f[0]).exists()
        assert not Path(csharp_dir / "obj" / f[0]).exists()
        assert not Path(csharp_dir / "Data/Tasks/CSharp/Compiled/net35" / f[0]).exists()
        assert not Path(csharp_dir / "Data/Tasks/CSharp/Compiled/net40" / f[0]).exists()
        assert not Path(
            csharp_dir / "Data/Tasks/CSharp/Compiled/netcoreapp3.0" / f[0]
        ).exists()

    assert Path(invoke_obfs_dir / "Invoke-Obfuscation.ps1").exists()

    if server_config_dict.get("database", {}).get("type") == "sqlite":
        assert not Path(server_config_dict["database"]["location"]).exists()

    sys.argv = default_argv


# TODO: At the moment, this is the only client test we have.
#  It probably makes sense to split the tests into server and client directories, but
#  I'm hesitant to do that just yet because it could cause some merge pain with 5.x
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_reset_client(monkeypatch, tmp_path, default_argv, client_config_dict):
    monkeypatch.setattr("builtins.input", lambda _: "y")
    sys.argv = ["", "client", "--config", CLIENT_CONFIG_LOC, "--reset"]

    download_files = [
        ("file1.txt", "TEST"),
        ("file2.txt", "TESTTEST"),
        ("file3.txt", "TESTTESTTEST"),
        (".keep", ""),
    ]
    for f in download_files:
        write_to_file(client_config_dict["directories"]["downloads"] + f[0], f[1])

    for f in download_files:
        assert Path(client_config_dict["directories"]["downloads"] + f[0]).exists()

    stager_files = [
        ("file1.ps1", "TEST"),
        ("file2.ps1", "TESTTEST"),
        ("file3.ps1", "TESTTESTTEST"),
        (".keep", ""),
    ]
    for f in stager_files:
        write_to_file(
            client_config_dict["directories"]["generated-stagers"] + f[0], f[1]
        )

    for f in stager_files:
        assert Path(
            client_config_dict["directories"]["generated-stagers"] + f[0]
        ).exists()

    import empire.arguments
    import empire.client.client as client

    reload(empire.arguments)
    from empire.arguments import args

    with pytest.raises(SystemExit):
        client.start(args)

    for f in download_files:
        if f[0] != ".keep":
            assert not Path(
                client_config_dict["directories"]["downloads"] + f[0]
            ).exists()
        else:
            assert Path(client_config_dict["directories"]["downloads"] + f[0]).exists()

    for f in stager_files:
        if f[0] != ".keep":
            assert not Path(
                client_config_dict["directories"]["generated-stagers"] + f[0]
            ).exists()
        else:
            assert Path(
                client_config_dict["directories"]["generated-stagers"] + f[0]
            ).exists()

    sys.argv = default_argv


def write_to_file(file_path, content):
    dr = Path(file_path).parent
    Path(dr).mkdir(parents=True, exist_ok=True)

    with open(file_path, "w") as f:
        f.write(content)
