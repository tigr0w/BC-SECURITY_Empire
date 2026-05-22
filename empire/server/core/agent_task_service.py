import base64
import json
import logging
import math
import threading
import time
import typing
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload, undefer

from empire.server.api.v2.agent.agent_task_dto import (
    AgentTaskOrderOptions,
    ModulePostRequest,
)
from empire.server.api.v2.shared_dto import OrderDirection
from empire.server.core.config.config_manager import empire_config
from empire.server.core.db import models
from empire.server.core.db.models import AgentTaskStatus
from empire.server.core.hooks import hooks

if typing.TYPE_CHECKING:
    from empire.server.common.empire import MainMenu

log = logging.getLogger(__name__)


class AgentTaskService:
    def __init__(self, main_menu: "MainMenu"):
        self.main_menu = main_menu

        self.module_service = main_menu.modulesv2
        self.listener_service = main_menu.listenersv2
        self.agent_socks_service = main_menu.agentsocksv2
        self.agent_service = main_menu.agentsv2
        self.download_service = main_menu.downloadsv2

        # { agent_id: [TemporaryTask] }
        self.temporary_tasks = defaultdict(list)

        # In-memory only -- not persisted to DB. Server restart silently abandons
        # in-progress chunked uploads (partial files remain on agent).
        # { session_id: { "upload_id": int, "file_location": str, "chunk_size": int,
        #                  "total_chunks": int, "next_index": int, "dest_path": str,
        #                  "started_at": float, "user_id": int | None } }
        self._pending_uploads: dict[str, dict] = {}
        self._pending_uploads_lock = threading.Lock()
        self._next_upload_id = 0

        self.last_task_lock = threading.Lock()

    @staticmethod
    def get_tasks(  # noqa: PLR0913 PLR0912
        db: Session,
        agents: list[str] | None = None,
        users: list[int] | None = None,
        tags: list[str] | None = None,
        limit: int = -1,
        offset: int = 0,
        include_full_input: bool = False,
        include_original_output: bool = False,
        include_output: bool = True,
        since: datetime | None = None,
        order_by: AgentTaskOrderOptions = AgentTaskOrderOptions.id,
        order_direction: OrderDirection = OrderDirection.desc,
        status: AgentTaskStatus | None = None,
        q: str | None = None,
    ):
        stmt = select(
            models.AgentTask, func.count(models.AgentTask.id).over().label("total")
        )

        if agents:
            stmt = stmt.where(models.AgentTask.agent_id.in_(agents))

        if users:
            user_filters = [models.AgentTask.user_id.in_(users)]
            if 0 in users:
                user_filters.append(models.AgentTask.user_id.is_(None))
            stmt = stmt.where(or_(*user_filters))

        if tags:
            tags_split = [tag.split(":", 1) for tag in tags]
            stmt = stmt.join(models.AgentTask.tags).where(
                and_(
                    models.Tag.name.in_([tag[0] for tag in tags_split]),
                    models.Tag.value.in_([tag[1] for tag in tags_split]),
                )
            )

        query_options = [
            joinedload(models.AgentTask.user),
            joinedload(models.AgentTask.agent).joinedload(models.Agent.host),
        ]
        if include_full_input:
            query_options.append(undefer(models.AgentTask.input_full))
        if include_original_output:
            query_options.append(undefer(models.AgentTask.original_output))
        if include_output:
            query_options.append(undefer(models.AgentTask.output))
        stmt = stmt.options(*query_options)

        if since:
            stmt = stmt.where(models.AgentTask.updated_at > since)

        if status:
            stmt = stmt.where(models.AgentTask.status == status)

        if q:
            stmt = stmt.where(
                or_(
                    models.AgentTask.input.like(f"%{q}%"),
                    models.AgentTask.output.like(f"%{q}%"),
                )
            )

        if order_by == AgentTaskOrderOptions.status:
            order_by_prop = models.AgentTask.status
        elif order_by == AgentTaskOrderOptions.updated_at:
            order_by_prop = models.AgentTask.updated_at
        elif order_by == AgentTaskOrderOptions.agent:
            order_by_prop = models.AgentTask.agent_id
        else:
            order_by_prop = models.AgentTask.id

        if order_direction == OrderDirection.asc:
            stmt = stmt.order_by(order_by_prop.asc())
        else:
            stmt = stmt.order_by(order_by_prop.desc())

        if limit > 0:
            stmt = stmt.limit(limit).offset(offset)

        results = db.execute(stmt).all()

        total = 0 if not results else results[0].total
        results = [x[0] for x in results]

        return results, total

    @staticmethod
    def get_task_for_agent(db: Session, agent_id: str, uid: int):
        return db.scalars(
            select(models.AgentTask).where(
                and_(models.AgentTask.agent_id == agent_id, models.AgentTask.id == uid)
            )
        ).first()

    def get_temporary_tasks_for_agent(self, agent_id: str, clear: bool = True):
        tasks = self.temporary_tasks[agent_id]

        if clear:
            self.temporary_tasks[agent_id] = []

        return tasks

    def create_task_shell(
        self,
        db: Session,
        agent: models.Agent,
        command: str,
        user: models.User | None = None,
    ):
        return self.add_task(db, agent, "TASK_SHELL", command, user=user)

    def create_task_chdir(
        self,
        db: Session,
        agent: models.Agent,
        path: str,
        user: models.User | None = None,
    ):
        return self.add_task(db, agent, "TASK_CHDIR", path, user=user)

    def create_task_upload(
        self,
        db: Session,
        agent: models.Agent,
        file_data: str,
        directory: str,
        user: models.User | None = None,
    ):
        data = f"{directory}|{file_data}"
        return self.add_task(db, agent, "TASK_UPLOAD", data, user=user)

    def create_task_upload_chunked(  # noqa: PLR0913
        self,
        db: Session,
        agent: models.Agent,
        file_location: str,
        file_size: int,
        path: str,
        user: models.User | None = None,
        chunk_size: int = 524288,
    ):
        """Create a chunked upload. Sends the first chunk immediately and
        queues remaining chunks to be dispatched one-at-a-time as the agent
        acknowledges each successful write."""
        total_chunks = math.ceil(file_size / chunk_size)

        try:
            with Path(file_location).open("rb") as f:
                chunk_0 = f.read(chunk_size)
        except OSError as e:
            log.error(
                "Failed to read first chunk from %s for agent %s: %s",
                file_location,
                agent.session_id,
                e,
            )
            return None, f"Failed to read upload file: {e}"
        chunk_0_b64 = base64.b64encode(chunk_0).decode("utf-8")
        data = f"0|{total_chunks}|{path}|{chunk_0_b64}"
        result = self.add_task(db, agent, "TASK_UPLOAD", data, user=user)

        if result[1] is not None:
            return result

        if total_chunks > 1:
            with self._pending_uploads_lock:
                if agent.session_id in self._pending_uploads:
                    existing = self._pending_uploads[agent.session_id]
                    log.warning(
                        "Overwriting existing chunked upload for agent %s (%d chunks remaining)",
                        agent.session_id,
                        existing["total_chunks"] - existing["next_index"],
                    )
                self._next_upload_id += 1
                self._pending_uploads[agent.session_id] = {
                    "upload_id": self._next_upload_id,
                    "file_location": file_location,
                    "chunk_size": chunk_size,
                    "total_chunks": total_chunks,
                    "next_index": 1,
                    "dest_path": path,
                    "started_at": time.time(),
                    "user_id": user.id if user else None,
                }
            log.info(
                "Chunked upload for %s: %d chunks (%d bytes, %d bytes/chunk)",
                path,
                total_chunks,
                file_size,
                chunk_size,
            )

        return result

    def cleanup_stale_uploads(self):
        """Remove any pending uploads that started over 30 minutes ago."""
        stale_timeout = 1800
        now = time.time()
        with self._pending_uploads_lock:
            stale = [
                sid
                for sid, p in self._pending_uploads.items()
                if now - p["started_at"] > stale_timeout
            ]
            for sid in stale:
                remaining = (
                    self._pending_uploads[sid]["total_chunks"]
                    - self._pending_uploads[sid]["next_index"]
                )
                log.warning(
                    "Cleaned up stale upload for agent %s, %d chunks abandoned",
                    sid,
                    remaining,
                )
                del self._pending_uploads[sid]

    def queue_next_upload_chunk(  # noqa: PLR0911
        self,
        db: Session,
        session_id: str,
    ):
        """Pop the next chunk for session_id and create a TASK_UPLOAD task.
        Discards all remaining chunks if the upload has been pending for over
        30 minutes or if the agent no longer exists."""
        self.cleanup_stale_uploads()

        with self._pending_uploads_lock:
            pending = self._pending_uploads.get(session_id)
            if not pending:
                log.debug(
                    "No pending upload for agent %s (server restart or already completed)",
                    session_id,
                )
                return

            upload_id = pending["upload_id"]
            index = pending["next_index"]
            total = pending["total_chunks"]
            if index >= total:
                del self._pending_uploads[session_id]
                return

            pending["next_index"] = index + 1
            is_last_chunk = (index + 1) >= total
            if is_last_chunk:
                del self._pending_uploads[session_id]

        offset = index * pending["chunk_size"]
        try:
            with Path(pending["file_location"]).open("rb") as f:
                f.seek(offset)
                raw_bytes = f.read(pending["chunk_size"])
        except OSError as e:
            log.error(
                "Failed to read chunk %d/%d from %s for agent %s: %s",
                index + 1,
                total,
                pending["file_location"],
                session_id,
                e,
            )
            self._cancel_upload_if_current(session_id, upload_id)
            return

        if not raw_bytes:
            log.error(
                "Empty chunk %d/%d read from %s for agent %s, file may have been truncated",
                index + 1,
                total,
                pending["file_location"],
                session_id,
            )
            self._cancel_upload_if_current(session_id, upload_id)
            return

        chunk_b64 = base64.b64encode(raw_bytes).decode("utf-8")
        data = f"{index}|{total}|{pending['dest_path']}|{chunk_b64}"

        agent = db.scalars(
            select(models.Agent).where(models.Agent.session_id == session_id)
        ).first()
        if not agent:
            log.warning(
                "Agent %s not found, discarding remaining upload chunks", session_id
            )
            self._cancel_upload_if_current(session_id, upload_id)
            return

        user = None
        if pending["user_id"]:
            user = db.scalars(
                select(models.User).where(models.User.id == pending["user_id"])
            ).first()

        try:
            result = self.add_task(db, agent, "TASK_UPLOAD", data, user=user)
        except Exception:
            log.exception(
                "Unexpected error queuing upload chunk %d/%d for agent %s",
                index + 1,
                total,
                session_id,
            )
            self._cancel_upload_if_current(session_id, upload_id)
            return

        if result[1] is not None:
            log.error(
                "Failed to queue upload chunk %d/%d for agent %s: %s",
                index + 1,
                total,
                session_id,
                result[1],
            )
            self._cancel_upload_if_current(session_id, upload_id)
            return

        log.info("Queued upload chunk %d/%d for agent %s", index + 1, total, session_id)

        if is_last_chunk:
            log.info(
                "Chunked upload to agent %s complete (%d chunks)", session_id, total
            )

    def cancel_pending_uploads(self, session_id: str):
        with self._pending_uploads_lock:
            pending = self._pending_uploads.pop(session_id, None)
        if pending:
            log.warning(
                "Cancelled chunked upload for agent %s, discarded %d remaining chunks",
                session_id,
                pending["total_chunks"] - pending["next_index"],
            )

    def _cancel_upload_if_current(self, session_id: str, upload_id: int):
        """Cancel the pending upload only if it still matches upload_id.
        Prevents error paths from accidentally cancelling a newer upload
        that was started for the same agent after the lock was released."""
        with self._pending_uploads_lock:
            current = self._pending_uploads.get(session_id)
            if current is not None and current["upload_id"] == upload_id:
                del self._pending_uploads[session_id]

    def create_task_download(
        self,
        db: Session,
        agent: models.Agent,
        path_to_file: str,
        user: models.User | None = None,
    ):
        return self.add_task(db, agent, "TASK_DOWNLOAD", path_to_file, user=user)

    def create_task_sysinfo(
        self, db: Session, agent: models.Agent, user: models.User | None = None
    ):
        return self.add_task(db, agent, "TASK_SYSINFO", user=user)

    def create_task_jobs(
        self, db: Session, agent: models.Agent, user: models.User | None = None
    ):
        return self.add_task(db, agent, "TASK_GETJOBS", user=user)

    def create_task_kill_job(
        self,
        db: Session,
        agent: models.Agent,
        job_id: str,
        user: models.User | None = None,
    ):
        return self.add_task(db, agent, "TASK_STOPJOB", job_id, user=user)

    def create_task_stop_job(
        self,
        db: Session,
        agent: models.Agent,
        job_id: str,
        user: models.User | None = None,
    ):
        return self.create_task_kill_job(db, agent, job_id, user=user)

    def create_task_exit(
        self, db: Session, agent: models.Agent, user: models.User | None = None
    ):
        resp, err = self.add_task(db, agent, "TASK_EXIT", user=user)
        agent.archived = True

        self.agent_socks_service.close_socks_client(agent)

        return resp, err

    def create_task_socks(
        self,
        db: Session,
        agent: models.Agent,
        socks_port,
        user: models.User | None = None,
    ):
        agent.socks = True
        agent.socks_port = socks_port
        resp, err = self.add_task(db, agent, "TASK_SOCKS", user=user)
        return resp, err

    def create_task_socks_data(self, agent_id: str, data: str):
        return self.add_temporary_task(agent_id, "TASK_SOCKS_DATA", data)

    def create_task_smb(
        self,
        db: Session,
        agent: models.Agent,
        pipe_name,
        user: models.User | None = None,
    ):
        resp, err = self.add_task(db, agent, "TASK_SMB_SERVER", pipe_name, user=user)
        return resp, err

    def create_task_update_sleep(
        self,
        db: Session,
        agent: models.Agent,
        delay: int,
        jitter: float,
        user: models.User | None = None,
    ):
        agent.delay = delay
        agent.jitter = jitter
        if agent.language == "powershell":
            return self.add_task(
                db,
                agent,
                "TASK_SHELL",
                f"Set-Delay {delay!s} {jitter!s}",
                user=user,
            )
        if agent.language in ["python", "ironpython"]:
            return self.add_task(
                db,
                agent,
                "TASK_PYTHON_CMD_WAIT",
                f"global agent; agent.delay={delay}; agent.jitter={jitter}; print('delay/jitter set to {delay}/{jitter}')",
                user=user,
            )
        if agent.language == "csharp":
            return self.add_task(
                db,
                agent,
                "TASK_SHELL",
                f"Set-Delay {delay!s} {jitter!s}",
                user=user,
            )

        return None, "Unsupported language."

    def create_task_update_kill_date(
        self,
        db: Session,
        agent: models.Agent,
        kill_date: str,
        user: models.User | None = None,
    ):
        # todo handle different languages
        agent.kill_date = kill_date
        return self.add_task(
            db, agent, "TASK_SHELL", f"Set-KillDate {kill_date}", user=user
        )

    def create_task_update_working_hours(
        self,
        db: Session,
        agent: models.Agent,
        working_hours: str,
        user: models.User | None = None,
    ):
        # todo handle different languages.
        agent.working_hours = working_hours
        return self.add_task(
            db,
            agent,
            "TASK_SHELL",
            f"Set-WorkingHours {working_hours}",
            user=user,
        )

    def create_task_module(
        self,
        db: Session,
        agent: models.Agent,
        module_req: ModulePostRequest,
        user: models.User | None = None,
    ):
        module_req.options["Agent"] = agent.session_id
        resp, err = self.module_service.execute_module(
            db,
            agent,
            module_req.module_id,
            module_req.options,
            module_req.ignore_language_version_check,
            module_req.ignore_admin_check,
            modified_input=module_req.modified_input,
            background_override=module_req.background_override,
        )

        if err:
            return None, err

        return self.add_task(
            db,
            agent,
            task_name=resp.command,
            task_input=resp.data,
            module_name=module_req.module_id,
            module_options=module_req.options,
            user=user,
            files=resp.files,
        )

    def create_task_directory_list(
        self,
        db: Session,
        agent: models.Agent,
        path: str,
        user: models.User | None = None,
    ):
        return self.add_task(db, agent, "TASK_DIR_LIST", path, user=user)

    class TemporaryTask(BaseModel):
        """
        Fields should match the Task db model, so that we can use the same
        functions to retrieve tasks.
        """

        id: int = 0  # We don't need an ID for these, but it is used in agents.py:1206, so we just initialize it to 0
        agent_id: str
        task_name: str
        input_full: str
        module_name: str | None = None
        module_options: dict | None = None

    def add_temporary_task(
        self,
        agent_id: str,
        task_name,
        task_input="",
        module_name: str | None = None,
        module_options: dict | None = None,
    ) -> tuple[TemporaryTask | None, str | None]:
        """
        Add a temporary task for the agent to execute. These tasks are not saved in the database,
        since they don't provide any value to end users and can be very write-heavy.
        """
        task = self.TemporaryTask(
            agent_id=agent_id,
            task_name=task_name,
            input_full=task_input,
            module_name=module_name,
            module_options=module_options,
        )
        self.temporary_tasks[agent_id].append(task)

        return task, None

    def add_task(  # noqa: PLR0913
        self,
        db: Session,
        agent: models.Agent,
        task_name,
        task_input="",
        module_name: str | None = None,
        module_options: dict | None = None,
        user: models.User | None = None,
        files: list[Path] | None = None,
    ) -> tuple[models.AgentTask | None, str | None]:
        """
        Task an agent. Adapted from agents.py
        """
        files = files or []
        if agent.archived:
            return None, f"[!] Agent {agent.session_id} is archived."

        message = f"Tasked {agent.session_id} to run {task_name}"
        log.info(message)
        self.agent_service.save_agent_log(agent.session_id, message)

        pk = db.scalar(
            select(func.max(models.AgentTask.id)).where(
                models.AgentTask.agent_id == agent.session_id
            )
        )

        if pk is None:
            pk = 0
        pk = (pk + 1) % 65536

        if task_name in ["TASK_CSHARP_CMD_JOB", "TASK_CSHARP_CMD_WAIT"]:
            compiled_path, arguments = task_input.split("|")
            arguments = arguments.lstrip(",").strip()

            if module_name.startswith("bof_"):
                decoded_arguments = base64.b64decode(arguments).decode("UTF-8")
                data_dict = json.loads(decoded_arguments)
                base64_data = data_dict.get("base64_bof_data", "")
                truncated_base64_data = (
                    base64_data[:15] + "..."
                    if len(base64_data) > 10  # noqa: PLR2004
                    else base64_data
                )
                data_dict["base64_bof_data"] = truncated_base64_data
                short_task_input = f"{module_name} {json.dumps(data_dict)}"

            else:
                filename = compiled_path.rsplit("/", 1)[-1].split(".")[0].split("_")[0]
                short_task_input = f"{filename} " + base64.b64decode(
                    arguments.encode("UTF-8")
                ).decode("UTF-8")

            task = models.AgentTask(
                id=pk,
                agent_id=agent.session_id,
                input=short_task_input[:150],
                input_full=task_input,
                user_id=user.id if user else None,
                module_name=module_name,
                module_options=module_options,
                task_name=task_name,
                status=AgentTaskStatus.queued,
            )
        else:
            task = models.AgentTask(
                id=pk,
                agent_id=agent.session_id,
                input=task_input[:100],
                input_full=task_input,
                user_id=user.id if user else None,
                module_name=module_name,
                module_options=module_options,
                task_name=task_name,
                status=AgentTaskStatus.queued,
            )
        db.add(task)
        db.flush()

        for path in files:
            task.downloads.append(
                self.download_service.create_download(
                    db, user, path, tags=["task:input"]
                )
            )
        db.flush()

        last_task_config = empire_config.debug.last_task
        if last_task_config.enabled:
            with self.last_task_lock:
                location = Path(last_task_config.file)
                location.parent.mkdir(parents=True, exist_ok=True)
                location.write_text(task_input)

        db.expunge(task)
        hooks.run_hooks(hooks.AFTER_TASKING_HOOK, None, task)
        db.add(task)

        message = f"Agent {agent.session_id} tasked with task ID {pk}"
        log.info(message)

        return task, None

    @staticmethod
    def delete_task(db: Session, task: models.AgentTask):
        db.delete(task)
