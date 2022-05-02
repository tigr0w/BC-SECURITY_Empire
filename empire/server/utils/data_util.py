import logging
import subprocess

from empire.server.database import models
from empire.server.database.base import SessionLocal

log = logging.getLogger(__name__)


def get_config(fields):
    """
    Helper to pull common database config information outside of the
    normal menu execution.

    Fields should be comma separated.
        i.e. 'version,install_path'
    """
    with SessionLocal.begin() as db:
        results = []
        config = db.query(models.Config).first()

        for field in fields.split(","):
            results.append(config[field.strip()])

        return results


def get_listener_options(listener_name):
    """
    Returns the options for a specified listenername from the database outside
    of the normal menu execution.
    """
    try:
        with SessionLocal() as db:
            listener_options = (
                db.query(models.Listener.options)
                .filter(models.Listener.name == listener_name)
                .first()
            )
        return listener_options

    except Exception:
        return None


def is_powershell_installed():
    return get_powershell_name() != ""


def get_powershell_name():
    try:
        powershell_location = subprocess.check_output("which powershell", shell=True)
    except subprocess.CalledProcessError as e:
        try:
            powershell_location = subprocess.check_output("which pwsh", shell=True)
        except subprocess.CalledProcessError as e:
            return ""
        return "pwsh"
    return "powershell"


def convert_obfuscation_command(obfuscate_command):
    return "".join(obfuscate_command.split()).replace(",", ",home,").replace("\\", ",")


def ps_convert_to_oneliner(psscript):
    """
    Converts a PowerShell script to a one-liner.
    """
    psscript = psscript.replace('"kernel32"', '`"kernel32`"')
    psscript = psscript.replace('"Kernel32.dll"', '`"Kernel32.dll`"')
    psscript = psscript.replace('"RtlMoveMemory"', '`"RtlMoveMemory`"')
    psscript = psscript.replace('"amsi.dll"', '`"amsi.dll`"')
    psscript = psscript.replace('"Amsi"', '`"Amsi`"')
    psscript = psscript.replace('"Scan"', '`"Scan`"')
    psscript = psscript.replace('"Buffer"', '`"Buffer`"')
    psscript = psscript.replace('@"', '"')
    psscript = psscript.replace('"@', '"')
    psscript = psscript.replace("\n", "")
    psscript = psscript.replace("    ", "")

    return psscript
