import fnmatch
import logging
import os
import subprocess
import tempfile
from pathlib import Path

import python_obfuscator
from python_obfuscator.techniques import one_liner
from sqlalchemy.orm import Session

from empire.server.core.config import empire_config
from empire.server.core.db import models
from empire.server.core.db.base import SessionLocal
from empire.server.utils import data_util

log = logging.getLogger(__name__)


class ObfuscationService(object):
    def __init__(self, main_menu):
        self.main_menu = main_menu

    @staticmethod
    def get_all_keywords(db: Session):
        return db.query(models.Keyword).all()

    @staticmethod
    def get_keyword_by_id(db: Session, uid: int):
        return db.query(models.Keyword).filter(models.Keyword.id == uid).first()

    @staticmethod
    def get_by_keyword(db: Session, keyword: str):
        return (
            db.query(models.Keyword).filter(models.Keyword.keyword == keyword).first()
        )

    @staticmethod
    def delete_keyword(db: Session, keyword: models.Keyword):
        db.delete(keyword)

    def create_keyword(self, db: Session, keyword_req):
        if self.get_by_keyword(db, keyword_req.keyword):
            return None, f"Keyword with name {keyword_req.keyword} already exists."

        db_keyword = models.Keyword(
            keyword=keyword_req.keyword, replacement=keyword_req.replacement
        )

        db.add(db_keyword)
        db.flush()

        return db_keyword, None

    def update_keyword(self, db: Session, db_keyword: models.Keyword, keyword_req):
        if keyword_req.keyword != db_keyword.keyword:
            if not self.get_by_keyword(db, keyword_req.keyword):
                db_keyword.keyword = keyword_req.keyword
            else:
                return None, f"Keyword with name {keyword_req.keyword} already exists."

        db_keyword.replacement = keyword_req.replacement

        db.flush()

        return db_keyword, None

    def get_all_obfuscation_configs(self, db: Session):
        return db.query(models.ObfuscationConfig).all()

    @staticmethod
    def get_obfuscation_config(db: Session, language: str):
        return (
            db.query(models.ObfuscationConfig)
            .filter(models.ObfuscationConfig.language == language)
            .first()
        )

    @staticmethod
    def update_obfuscation_config(
        db: Session, db_obf_config: models.ObfuscationConfig, obf_config_req
    ):
        db_obf_config.module = obf_config_req.module
        db_obf_config.command = obf_config_req.command
        db_obf_config.enabled = obf_config_req.enabled

        return db_obf_config, None

    def preobfuscate_modules(
        self, db: Session, db_obf_config: models.ObfuscationConfig, reobfuscate=False
    ):
        """
        Preobfuscate PowerShell module_source files
        """
        if not data_util.is_powershell_installed():
            err = "PowerShell is not installed and is required to use obfuscation, please install it first."
            log.error(err)
            return err

        files = self._get_module_source_files(db_obf_config.language)

        for file in files:
            file = os.getcwd() + "/" + file
            if reobfuscate or not self._is_obfuscated(file):
                message = f"Obfuscating {os.path.basename(file)}..."
                log.info(message)
            else:
                log.warning(
                    f"{os.path.basename(file)} was already obfuscated. Not reobfuscating."
                )
            self.obfuscate_module(file, db_obf_config.command, reobfuscate)

    # this is still written in a way that its only used for PowerShell
    # to make it work for other languages, we probably want to just pass in the db_obf_config
    # and delegate to language specific functions
    def obfuscate_module(
        self, module_source, obfuscation_command="", force_reobfuscation=False
    ):
        if self._is_obfuscated(module_source) and not force_reobfuscation:
            return

        try:
            with open(module_source, "r") as f:
                module_code = f.read()
        except Exception:
            log.error(f"Could not read module source path at: {module_source}")
            return ""

        # Get the random function name generated at install and patch the stager with the proper function name
        module_code = self.obfuscate_keywords(module_code)

        # obfuscate and write to obfuscated source path
        obfuscated_code = self.obfuscate(module_code, obfuscation_command)

        obfuscated_source = module_source.replace(
            empire_config.directories.module_source,
            empire_config.directories.obfuscated_module_source,
        )

        try:
            Path(obfuscated_source).parent.mkdir(parents=True, exist_ok=True)
            with open(obfuscated_source, "w") as f:
                f.write(obfuscated_code)
        except Exception:
            log.error(
                f"Could not write obfuscated module source path at: {obfuscated_source}"
            )
            return ""

    def obfuscate(self, ps_script, obfuscation_command):
        """
        Obfuscate PowerShell scripts using Invoke-Obfuscation
        """
        if not data_util.is_powershell_installed():
            log.error(
                "PowerShell is not installed and is required to use obfuscation, please install it first."
            )
            return ""

        # run keyword obfuscation before obfuscation
        ps_script = self.obfuscate_keywords(ps_script)

        # When obfuscating large scripts, command line length is too long. Need to save to temp file
        with tempfile.NamedTemporaryFile(
            "r+"
        ) as toObfuscateFile, tempfile.NamedTemporaryFile("r+") as obfuscatedFile:
            toObfuscateFile.write(ps_script)

            # Obfuscate using Invoke-Obfuscation w/ PowerShell
            install_path = self.main_menu.installPath
            toObfuscateFile.seek(0)
            subprocess.call(
                f'{data_util.get_powershell_name()} -C \'$ErrorActionPreference = "SilentlyContinue";Import-Module {install_path}/data/Invoke-Obfuscation/Invoke-Obfuscation.psd1;Invoke-Obfuscation -ScriptPath {toObfuscateFile.name} -Command "{self._convert_obfuscation_command(obfuscation_command)}" -Quiet | Out-File -Encoding ASCII {obfuscatedFile.name}\'',
                shell=True,
            )

            # Obfuscation writes a newline character to the end of the file, ignoring that character
            obfuscatedFile.seek(0)
            ps_script = obfuscatedFile.read()[0:-1]

        return ps_script

    def remove_preobfuscated_modules(self, language: str):
        """
        Remove preobfuscated PowerShell module_source files
        """
        files = self._get_obfuscated_module_source_files(language)
        for file in files:
            try:
                os.remove(file)
            except Exception:
                pass

    def obfuscate_keywords(self, data):
        with SessionLocal.begin() as db:
            keywords = db.query(models.Keyword).all()

            for keyword in keywords:
                data = data.replace(keyword.keyword, keyword.replacement)

            return data

    def _get_module_source_files(self, language: str):
        """
        Get the filepaths of PowerShell module_source files located
        in the data/module_source directory.
        """
        paths = []
        # This logic will need to be updated later. Right now we're only doing powershell.
        pattern = "*.ps1"
        for root, dirs, files in os.walk(empire_config.directories.module_source):
            for filename in fnmatch.filter(files, pattern):
                paths.append(os.path.join(root, filename))

        return paths

    def _get_obfuscated_module_source_files(self, language: str):
        """
        Get the filepaths of PowerShell module_source files located
        in the data/module_source directory.
        """
        paths = []
        # This logic will need to be updated later. Right now we're only doing powershell.
        pattern = "*.ps1"
        for root, dirs, files in os.walk(
            empire_config.directories.obfuscated_module_source
        ):
            for filename in fnmatch.filter(files, pattern):
                paths.append(os.path.join(root, filename))

        return paths

    def _is_obfuscated(self, module_source):
        obfuscated_source = module_source.replace(
            empire_config.directories.module_source,
            empire_config.directories.obfuscated_module_source,
        )
        return os.path.isfile(obfuscated_source)

    def _convert_obfuscation_command(self, obfuscate_command):
        return (
            "".join(obfuscate_command.split()).replace(",", ",home,").replace("\\", ",")
        )

    def python_obfuscate(self, module_source):
        """
        Obfuscate Python scripts using python-obfuscator
        """
        obfuscator = python_obfuscator.obfuscator()
        obfuscated_code = obfuscator.obfuscate(module_source, [one_liner])

        return obfuscated_code
