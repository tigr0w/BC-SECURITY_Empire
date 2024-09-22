import base64
import logging
import subprocess
from pathlib import Path

from empire.server.core.exceptions import ModuleExecutionException

log = logging.getLogger(__name__)


class DotnetCompiler:
    def __init__(self, install_path):
        self.install_path = install_path
        self.compiler = Path(install_path) / "Empire-Compiler/EmpireCompiler/"

    def compile_task(self, compiler_yaml, task_name, dotnet="net35", confuse=False):
        args = [
            "./EmpireCompiler",
            "--task",
            task_name,
            "--yaml",
            base64.b64encode(compiler_yaml.encode("UTF-8")).decode("UTF-8"),
        ]

        if confuse:
            args.extend(["--confuse"])

        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            cwd=self.compiler,
        )

        if result.returncode != 0:
            raise ModuleExecutionException(
                f"EmpireCompiler execution failed with error: {result.stderr.strip()}"
            )

        output = result.stdout.strip()

        if "Final Task Name:" not in output:
            log.error(result.stdout)
            raise ModuleExecutionException("Module compile failed")

        file_name = output.split("Final Task Name:")[1].strip()
        return f"{self.install_path}/Empire-Compiler/EmpireCompiler/Data/Tasks/CSharp/Compiled/{dotnet}/{file_name}.compiled"

    def compile_stager(self, compiler_yaml, task_name, confuse=False):
        args = [
            "./EmpireCompiler",
            "--task",
            task_name,
            "--yaml",
            base64.b64encode(compiler_yaml.encode("UTF-8")).decode("UTF-8"),
        ]

        if confuse:
            args.extend(["--confuse"])

        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            cwd=self.compiler,
        )

        if result.returncode != 0:
            raise ModuleExecutionException(
                f"EmpireCompiler execution failed with error: {result.stderr.strip()}"
            )

        output = result.stdout.strip()

        if "Final Task Name:" not in output:
            log.error(result.stdout)
            raise ModuleExecutionException("Stager compile failed")

        return output.split("Final Task Name:")[1].strip()
