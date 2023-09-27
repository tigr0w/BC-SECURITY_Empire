import logging
import os
import random
import string

from prompt_toolkit.completion import Completion

from empire.client.src.EmpireCliState import state
from empire.client.src.menus.Menu import Menu
from empire.client.src.utils import date_util, print_util, table_util
from empire.client.src.utils.autocomplete_util import (
    complete_path,
    current_files,
    filtered_search_list,
    position_util,
)
from empire.client.src.utils.cli_util import command, register_cli_commands
from empire.client.src.utils.data_util import get_data_from_file

log = logging.getLogger(__name__)


@register_cli_commands
class AdminMenu(Menu):
    def __init__(self):
        super().__init__(display_name="admin", selected="")

    def autocomplete(self):
        return self._cmd_registry + super().autocomplete()

    def get_completions(self, document, complete_event, cmd_line, word_before_cursor):
        if cmd_line[0] in [
            "malleable_profile",
            "delete_malleable_profile",
        ] and position_util(cmd_line, 2, word_before_cursor):
            for profile in filtered_search_list(
                word_before_cursor, state.profiles.keys()
            ):
                yield Completion(profile, start_position=-len(word_before_cursor))
        elif cmd_line[0] == "load_malleable_profile" and position_util(
            cmd_line, 2, word_before_cursor
        ):
            for profile in filtered_search_list(
                word_before_cursor, complete_path(".profile")
            ):
                yield Completion(profile, start_position=-len(word_before_cursor))
        elif cmd_line[0] == "download" and position_util(
            cmd_line, 2, word_before_cursor
        ):
            for files in filtered_search_list(
                word_before_cursor, state.server_files.keys()
            ):
                yield Completion(files, start_position=-len(word_before_cursor))
        elif cmd_line[0] in ["upload"] and position_util(
            cmd_line, 2, word_before_cursor
        ):
            if len(cmd_line) > 1 and cmd_line[1] == "-p":
                file = state.search_files()
                if file:
                    yield Completion(file, start_position=-len(word_before_cursor))
            else:
                for files in filtered_search_list(
                    word_before_cursor, current_files(state.directory["downloads"])
                ):
                    yield Completion(
                        files,
                        display=files.split("/")[-1],
                        start_position=-len(word_before_cursor),
                    )

        yield from super().get_completions(
            document, complete_event, cmd_line, word_before_cursor
        )

    def on_enter(self):
        state.get_files()
        self.user_id = state.get_user_me()["id"]
        return True

    @command
    def user_list(self) -> None:
        """
        Display all Empire user accounts

        Usage: user_list
        """
        users_list = []

        for user in state.get_users()["records"]:
            users_list.append(
                [
                    str(user["id"]),
                    user["username"],
                    str(user["is_admin"]),
                    str(user["enabled"]),
                    date_util.humanize_datetime(user["updated_at"]),
                ]
            )

        users_list.insert(0, ["ID", "Username", "Admin", "Enabled", "Last Logon Time"])

        table_util.print_table(users_list, "Users")

    @command
    def create_user(
        self, username: str, password: str, confirm_password: str, admin: str
    ) -> None:
        """
        Create user account for Empire

        Usage: create_user <username> <password> <confirm_password> <admin>
        """
        if admin == "True":
            admin = True
        else:
            admin = False

        options = {
            "username": username,
            "password": password,
            "confirm_password": confirm_password,
            "is_admin": admin,
        }
        response = state.create_user(options)

        # Return results and error message
        if "id" in response.keys():
            log.info(f"Added user: {username}")
        elif "detail" in response.keys():
            log.error(["detail"])

    @command
    def disable_user(self, user_id: str):
        """
        Disable user account for Empire

        Usage: disable_user <user_id>
        """
        user = state.get_user(user_id)
        user["enabled"] = False
        response = state.edit_user(user_id, user)

        # Return results and error message
        if "id" in response.keys():
            log.info(f"Disabled user: {user['username']}")
        elif "detail" in response.keys():
            log.error(response["detail"])

    @command
    def enable_user(self, user_id: str):
        """
        Enable user account for Empire

        Usage: enable_user <user_id>
        """
        user = state.get_user(user_id)
        user["enabled"] = True
        response = state.edit_user(user_id, user)

        # Return results and error message
        if "id" in response.keys():
            log.info(f"Enabled user: {user['username']}")
        elif "detail" in response.keys():
            log.error(["detail"])

    @command
    def malleable_profile(self, profile_name: str):
        """
        View malleable c2 profile

        Usage: malleable_profile <profile_name>
        """
        if profile_name in state.profiles.keys():
            record_list = []
            for key, value in state.profiles[profile_name].items():
                record_list.append([print_util.color(key, "blue"), value])
            table_util.print_table(
                record_list, "Malleable Profile", colored_header=False, borders=False
            )

    @command
    def load_malleable_profile(
        self, profile_directory: str, profile_category: str = ""
    ):
        """
        Load malleable c2 profile to the database

        Usage: load_malleable_profile <profile_directory> [profile_category]
        """
        with open(profile_directory) as stream:
            profile_data = stream.read()

        post_body = {
            "categeory": profile_category,
            "data": profile_data,
            "name": os.path.basename(profile_directory),
        }

        response = state.add_malleable_profile(post_body)

        if "id" in response.keys():
            log.info(f"Added {post_body['name']} to database")
            state.get_malleable_profile()
        elif "detail" in response.keys():
            log.error(response["detail"])

    @command
    def delete_malleable_profile(
        self,
        profile_name: str,
    ):
        """
        Delete malleable c2 profile from the database

        Usage: delete_malleable_profile <profile_name>
        """
        profile_id = state.get_malleable_profile()[profile_name]["id"]
        response = state.delete_malleable_profile(profile_id)

        if "id" in response.keys():
            log.info(f"Deleted {profile_name} from database")
            state.get_malleable_profile()
        elif "detail" in response.keys():
            log.error(response["detail"])

    @command
    def upload(self, file_directory: str):
        """
        Upload a file to the server from /empire/client/downloads. Use '-p' for a file selection dialog.

        Usage: upload <file_directory>
        """
        filename = file_directory.split("/")[-1]
        data = get_data_from_file(file_directory)

        if data:
            response = state.upload_file(filename, data)

            if "id" in response.keys():
                log.info(f"Uploaded {filename} to server")
            elif "detail" in response.keys():
                log.error(["detail"])
        else:
            log.error("Invalid file path")

    @command
    def download(self, filename: str):
        """
        Download a file from the server to /empire/client/downloads

        Usage: download <filename>
        """
        file_id = state.server_files[filename]["id"]
        response = state.download_file(file_id)

        if "location" in response.keys():
            link = response["location"]
            filename = response["filename"]

            log.info(f"Downloading { filename } from server")
            data = state.download_stager(link)

            with open(f"{state.directory['downloads']}{ filename }", "wb+") as f:
                f.write(data)
            log.info(f"Downloaded {filename} from server")

        elif "detail" in response.keys():
            log.error(response["detail"])

    @command
    def preobfuscate(self, reobfuscate: str = None):
        """
        Preobfuscate modules on the server.
        If reobfuscate is false, will not obfuscate modules that have already been obfuscated.
        Usage: preobfuscate [<reobfuscate>]
        """
        if not reobfuscate:
            log.info("Preobfuscating modules without replacement.")
        else:
            log.info("Preobfuscating modules with replacement")
        response = state.preobfuscate(language="powershell", reobfuscate=reobfuscate)

        # Return results and error message
        if response.status_code == 202:
            log.info("Preobfuscating modules...")
        elif "detail" in response.keys():
            log.error(response["detail"])

    @command
    def keyword_obfuscation(self, keyword: str, replacement: str = None):
        """
        Add keywords to be obfuscated from commands. Empire will generate a random word
        if no replacement word is provided.

        Usage: keyword_obfuscation <keyword> [<replacement>]
        """
        if not replacement:
            log.info(f"Generating random string for keyword {keyword}")
            replacement = random.choice(string.ascii_uppercase) + "".join(
                random.choices(string.ascii_uppercase + string.digits, k=4)
            )
        else:
            log.info(f"Replacing keyword {keyword} with {replacement}")

        options = {"keyword": keyword, "replacement": replacement}
        response = state.keyword_obfuscation(options)

        if "id" in response:
            log.info(f"Keyword obfuscation set to replace {keyword} with {replacement}")
        elif "detail" in response:
            log.error(response["detail"])


admin_menu = AdminMenu()
