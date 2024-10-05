import logging
import subprocess
from pathlib import Path

import jinja2

from empire.server.common.helpers import random_string
from empire.server.core.exceptions import ModuleExecutionException

log = logging.getLogger(__name__)


class GoCompiler:
    def __init__(self, install_path):
        self.install_path = install_path
        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(
                str(Path(self.install_path) / "data/agent/gopire")
            ),
            autoescape=True,
        )

    def compile_task(self, source_code, task_name, goos="linux", goarch="amd64"):
        random_suffix = random_string(5)
        source_path = self.compiler / f"{task_name}_{random_suffix}.go"
        with open(source_path, "w") as source_file:
            source_file.write(source_code)

        # Prepare the Go build command
        output_filename = f"{task_name}_{random_suffix}.bin"
        args = [
            "go",
            "build",
            "-o",
            str(self.compiler / output_filename),
            str(source_path),
        ]

        env = {"GOOS": goos, "GOARCH": goarch}

        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            cwd=self.compiler,
            env={**env, **subprocess.os.environ},
        )

        if result.returncode != 0:
            raise ModuleExecutionException(
                f"Go build execution failed with error: {result.stderr.strip()}"
            )

        return str(self.compiler / output_filename)

    def generate_main_go(self, template_path, output_path, template_vars):
        """
        Generate the main.go file using the Jinja2 template engine.

        :param template_path: Path to the template file (e.g., main.template.go).
        :param output_path: Path to the output main.go file.
        :param template_vars: Dictionary of variables to replace in the template.
        """
        template = self.jinja_env.get_template(template_path)
        rendered_content = template.render(template_vars)

        with open(output_path, "w") as output_file:
            output_file.write(rendered_content)

    def compile_stager(self, template_vars, task_name, goos="windows", goarch="amd64"):
        random_suffix = random_string(5)
        source_file = Path(self.install_path) / "data/agent/gopire/"
        output_file = (
            Path(self.install_path)
            / f"data/agent/gopire/{task_name}_{random_suffix}.exe"
        )

        template_path = "main.template"
        output_path = source_file / "main.go"

        self.generate_main_go(template_path, output_path, template_vars)

        env = {"GOOS": goos, "GOARCH": goarch}

        result = subprocess.run(
            ["go", "build", "-o", str(output_file)],
            env={**env, **subprocess.os.environ},
            capture_output=True,
            text=True,
            cwd=source_file,
            check=False,
        )

        if result.returncode != 0:
            raise ModuleExecutionException(f"Go build failed: {result.stderr.strip()}")

        return str(output_file)
