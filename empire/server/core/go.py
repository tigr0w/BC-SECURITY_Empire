import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import jinja2

from empire.server.common.helpers import random_string
from empire.server.core.exceptions import ModuleExecutionException

log = logging.getLogger(__name__)


class GoCompiler:
    def __init__(self, install_path: Path):
        self.install_path = install_path
        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(
                str(self.install_path / "data/agent/gopire")
            ),
            autoescape=True,
        )

    def compile_task(self, source_code, task_name, goos="linux", goarch="amd64"):
        random_suffix = random_string(5)
        source_path = self.compiler / f"{task_name}_{random_suffix}.go"
        with source_path.open("w") as source_file:
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
        :return: The rendered string (also written to ``output_path``).
        """
        template = self.jinja_env.get_template(template_path)
        rendered_content = template.render(template_vars)

        with Path(output_path).open("w") as output_file:
            output_file.write(rendered_content)

        return rendered_content

    def compile_stager(self, template_vars, task_name, goos="windows", goarch="amd64"):
        env = {"GOOS": goos, "GOARCH": goarch}
        random_task_name = f"{task_name}_{random_string(6)}.exe"
        template_path = "main.template"
        gopire_src = self.install_path / "data/agent/gopire"
        final_path = Path(tempfile.gettempdir()) / random_task_name

        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = Path(tmpdir) / "gopire"
            shutil.copytree(gopire_src, build_dir)

            self.generate_main_go(
                template_path, str(build_dir / "main.go"), template_vars
            )

            build_output = build_dir / random_task_name
            result = subprocess.run(
                ["go", "build", "-o", str(build_output), "."],
                env={**env, **os.environ},
                capture_output=True,
                text=True,
                cwd=build_dir,
                check=False,
            )

            if result.returncode != 0:
                preservation_note = ""
                try:
                    preserved_fd, preserved_name = tempfile.mkstemp(
                        prefix="gopire-failed-main-", suffix=".go"
                    )
                    os.close(preserved_fd)
                    shutil.copy2(build_dir / "main.go", preserved_name)
                    preservation_note = (
                        f" (rendered main.go preserved at {preserved_name})"
                    )
                except OSError as preserve_err:
                    log.warning(
                        "Could not preserve failed main.go for debugging: %s",
                        preserve_err,
                        exc_info=True,
                    )
                    preservation_note = (
                        " (failed to preserve rendered main.go; see logs)"
                    )
                raise ModuleExecutionException(
                    f"Go build failed: {result.stderr.strip()}{preservation_note}"
                )

            shutil.move(str(build_output), str(final_path))

        return str(final_path)
