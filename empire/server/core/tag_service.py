import hashlib
import logging
import typing

from sqlalchemy import delete, func, or_, select, union_all
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from empire.server.api.v2.shared_dto import OrderDirection
from empire.server.api.v2.tag.tag_dto import TagOrderOptions, TagSourceFilter
from empire.server.core.db import models
from empire.server.core.db.models import get_database_config
from empire.server.core.hooks import hooks

if typing.TYPE_CHECKING:
    from empire.server.common.empire import MainMenu

_DB_DIALECT, _ = get_database_config()


log = logging.getLogger(__name__)


def color_from_name(name: str) -> str:
    """Deterministic default hex color for a tag name.

    Stable across processes and DB backends so the same tag name always gets
    the same default color. Stored on creation and editable afterward.
    """
    digest = hashlib.md5(name.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"#{digest[:6]}"


Taggable = (
    models.Listener
    | models.Agent
    | models.AgentTask
    | models.PluginTask
    | models.Credential
    | models.Download
)


def tag_name_filter(tags_relationship, names: list[str]):
    """EXISTS-subquery tag-name filter.

    Use `.any()` rather than `.join()`: a join multiplies rows when an entity
    carries 2+ of the filtered tags, duplicating records (and, for queries with
    a `count(...).over()` window column, inflating the total).
    """
    return tags_relationship.any(models.Tag.name.in_(names))


# One place pairing each source filter with its association table, so get_all's
# `sources=` handling is a single comprehension instead of six near-identical
# branches (which would have to be kept in sync by hand).
_SOURCE_TABLES = {
    TagSourceFilter.agent_task: models.agent_task_tag_assc,
    TagSourceFilter.plugin_task: models.plugin_task_tag_assc,
    TagSourceFilter.agent: models.agent_tag_assc,
    TagSourceFilter.listener: models.listener_tag_assc,
    TagSourceFilter.download: models.download_tag_assc,
    TagSourceFilter.credential: models.credential_tag_assc,
}


class TagService:
    def __init__(self, main_menu: "MainMenu"):
        self.main_menu = main_menu

    def get_by_id(self, db: Session, tag_id: int):
        return db.scalars(select(models.Tag).where(models.Tag.id == tag_id)).first()

    def get_by_name(self, db: Session, name: str):
        return db.scalars(select(models.Tag).where(models.Tag.name == name)).first()

    def get_all(  # noqa: PLR0913
        self,
        db: Session,
        tag_types: list[TagSourceFilter] | None,
        q: str | None = None,
        limit: int = -1,
        offset: int = 0,
        order_by: TagOrderOptions = TagOrderOptions.updated_at,
        order_direction: OrderDirection = OrderDirection.desc,
    ):
        stmt = select(models.Tag, func.count(models.Tag.id).over().label("total"))

        tag_types = tag_types or []
        sub = [
            select(assc.c.tag_id.label("tag_id"))
            for src, assc in _SOURCE_TABLES.items()
            if src in tag_types
        ]

        subquery = None
        if sub:
            # `.union()` (plain UNION, not UNION ALL) dedupes across 2+ branches,
            # but a single branch skips that union entirely and can carry
            # duplicate tag_ids when one tag is attached to 2+ entities of that
            # type — `.distinct()` it explicitly so the single-source case can't
            # inflate the join/total the same way the multi-source case does not.
            subquery = sub[0].union(*sub[1:]) if len(sub) > 1 else sub[0].distinct()
            subquery = subquery.subquery()

        if subquery is not None:
            stmt = stmt.join(subquery, subquery.c.tag_id == models.Tag.id)

        if q:
            stmt = stmt.where(
                or_(
                    models.Tag.name.like(f"%{q}%"),
                )
            )

        if order_by == TagOrderOptions.name:
            order_by_prop = func.lower(models.Tag.name)
        elif order_by == TagOrderOptions.created_at:
            order_by_prop = models.Tag.created_at
        else:
            order_by_prop = models.Tag.updated_at

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

    def get_or_create_tag(self, db: Session, name: str) -> tuple[models.Tag, bool]:
        """Return the existing tag by name, or create it. Returns (tag, created).

        Concurrency-safe: Empire is multi-operator and `tags.name` is UNIQUE, so a
        plain check-then-insert races to a fatal IntegrityError. Use the repo's
        dialect-aware upsert idiom (see agent_service.py), then a LOCKING read-back
        — a no-op ON DUPLICATE KEY UPDATE creates no transaction-visible version, so
        a plain SELECT can return None under MySQL REPEATABLE READ.

        ACCEPTED LIMITATION (MariaDB): the `.with_for_update()` read-back can, on
        MariaDB InnoDB REPEATABLE READ, raise error 1020 "Record has changed since
        last read" when a rival committed this same name mid-race — surfacing as an
        unhandled 500 in the by-name attach path (the automatic ``task:input``
        download tag). It does not occur on Oracle MySQL (locking reads see the
        latest committed row). Left as a documented limitation: it is a rare race,
        creates no bad data, and a proper fix is a cross-dialect recovery redesign.

        Note: tag-name uniqueness is case-insensitive on MySQL (table collation)
        and case-sensitive on SQLite (default BINARY collation, not set explicitly)
        — `Foo`/`foo` are one tag on MySQL, two on SQLite.

        Caveat: in the rare concurrent-create race the losing caller also returns
        ``created=True`` (the upsert gives no per-caller winner/loser signal), so
        ``AFTER_TAG_CREATED_HOOK`` can fire more than once for the same tag.
        Consumers needing at-most-once semantics must tolerate that.
        """
        tag = self.get_by_name(db, name)
        if tag is not None:
            return tag, False

        values = {
            "name": name,
            "color": color_from_name(name),
            "description": None,
        }
        if _DB_DIALECT == "mysql":
            stmt = (
                mysql_insert(models.Tag)
                .values(**values)
                .on_duplicate_key_update(name=name)
            )
        else:
            stmt = sqlite_insert(models.Tag).values(**values).on_conflict_do_nothing()
        try:
            with db.begin_nested():
                db.execute(stmt)
        except IntegrityError:
            pass

        tag = db.scalars(
            select(models.Tag).where(models.Tag.name == name).with_for_update()
        ).first()
        if tag is None:
            # The upsert neither inserted nor found a conflicting row — the insert
            # failed for an unexpected reason (not the duplicate-name race). Don't
            # return None and let a caller append it to a relationship.
            log.error(
                "Failed to create or fetch tag %r: upsert ran but the read-back "
                "returned no row",
                name,
            )
            raise RuntimeError(f"Failed to create or fetch tag {name!r}")
        return tag, True

    def attach_tag(
        self,
        db: Session,
        taggable: Taggable,
        *,
        name: str | None = None,
        tag_id: int | None = None,
    ) -> tuple[models.Tag | None, bool]:
        """Attach a tag to an entity. Returns (tag, created).

        `tag_id` attaches an existing tag (returns (None, False) on unknown id so
        the API can 404). `name` attaches by name, creating the tag on miss — used
        by internal callers (e.g. the automatic ``task:input`` download tag); the
        public API attaches by ``tag_id`` only.
        """
        if tag_id is not None:
            tag = self.get_by_id(db, tag_id)
            if tag is None:
                return None, False
            created = False
        else:
            tag, created = self.get_or_create_tag(db, name)

        newly_attached = tag not in taggable.tags
        try:
            # Savepoint so a flush conflict (the association's composite-unique
            # uq_<entity>_tag) doesn't poison the outer transaction — mirrors
            # create_tag/update_tag's _flush_or_conflict. The append MUST happen
            # INSIDE the savepoint: entering begin_nested() autoflushes pending
            # state, so appending before it would flush the association INSERT
            # (and hit the unique conflict) OUTSIDE the savepoint's protection,
            # poisoning the outer transaction so the recovery below crashes with
            # an unhandled error (a 500) instead of running on a healthy txn.
            # (Whether that recovery then resolves to a 200 vs a 404 depends on
            # whether the locking reload observes the rival's committed row — see
            # the note in the except block; on MariaDB REPEATABLE READ it may not.)
            with db.begin_nested():
                if newly_attached:
                    taggable.tags.append(tag)
                db.flush()
        except IntegrityError:
            # The flush hit a unique/FK violation. Try to distinguish an idempotent
            # re-attach (the rival committed the same (entity, tag) row) from a real
            # failure (e.g. the tag was concurrently deleted, so the association FK
            # failed) by reloading the collection with a locking read.
            #
            # ACCEPTED LIMITATION (MariaDB): this reload is NOT reliable there. On
            # MariaDB InnoDB REPEATABLE READ, SQLAlchemy's `with_for_update` refresh
            # does not apply FOR UPDATE to the m2m collection reload, so it returns
            # this transaction's stale (pre-rival) snapshot and misses the rival's
            # now-committed row — so a genuine concurrent double-attach falls into
            # the `return None, False` branch below and the API answers a misleading
            # 404 instead of the documented idempotent 200. (A true FOR UPDATE read
            # would instead raise MariaDB error 1020 "Record has changed since last
            # read".) Oracle MySQL's InnoDB reads latest-committed on a locking read,
            # so it resolves to the intended 200 there. This is a rare race with no
            # data corruption (the association exists exactly once regardless), so
            # it is left as a documented limitation rather than a recovery redesign.
            db.refresh(taggable, attribute_names=["tags"], with_for_update=True)
            if tag not in taggable.tags:
                # Either a real failure (tag concurrently deleted) or, on MariaDB,
                # the stale-read false negative described above. Not an idempotent
                # no-op as far as we can tell here.
                return None, False
            # Otherwise another operator attached this same tag first and the
            # composite-unique rejected our duplicate: idempotent no-op (200).
            newly_attached = False

        if created:
            # Pure registry-creation signal; the entity association is delivered
            # by AFTER_TAG_ATTACHED_HOOK, which always fires below in this path
            # (a brand-new tag is necessarily a new attach).
            hooks.run_hooks(hooks.AFTER_TAG_CREATED_HOOK, db, tag)
        # Fire the "entity was tagged" signal only on an actual attach, not on an
        # idempotent re-attach of an already-applied tag.
        if newly_attached:
            hooks.run_hooks(hooks.AFTER_TAG_ATTACHED_HOOK, db, tag, taggable)
        return tag, created

    def detach_tag(self, db: Session, taggable: Taggable, tag_id: int) -> None:
        """Remove the tag from this entity. The tag row persists in the registry."""
        taggable.tags = [tag for tag in taggable.tags if tag.id != tag_id]
        db.flush()

    @staticmethod
    def _flush_or_conflict(db: Session, conflict_name: str) -> None:
        """Flush inside a savepoint, converting a unique-name IntegrityError into a
        ValueError (which the API maps to 409). The savepoint rolls back the failed
        insert/update so the session stays usable; the race occurs when another
        operator takes the same name between the pre-check and this flush."""
        try:
            with db.begin_nested():
                db.flush()
        except IntegrityError as e:
            raise ValueError(f"A tag named '{conflict_name}' already exists.") from e

    def create_tag(
        self,
        db: Session,
        name: str,
        color: str | None = None,
        description: str | None = None,
    ) -> models.Tag:
        if self.get_by_name(db, name):
            raise ValueError(f"A tag named '{name}' already exists.")
        tag = models.Tag(
            name=name, color=color or color_from_name(name), description=description
        )
        db.add(tag)
        self._flush_or_conflict(db, name)
        hooks.run_hooks(hooks.AFTER_TAG_CREATED_HOOK, db, tag)
        return tag

    def update_tag(
        self,
        db: Session,
        tag: models.Tag,
        name: str | None = None,
        color: str | None = None,
        description: str | None = None,
    ) -> models.Tag:
        changed = False
        if name is not None and name != tag.name:
            clash = db.scalars(
                select(models.Tag).where(
                    models.Tag.name == name, models.Tag.id != tag.id
                )
            ).first()
            if clash:
                raise ValueError(f"A tag named '{name}' already exists.")
            tag.name = name
            changed = True
        if color is not None and color != tag.color:
            tag.color = color
            changed = True
        if description is not None and description != tag.description:
            tag.description = description
            changed = True
        # Use the requested name when present, else the tag's current name.
        self._flush_or_conflict(db, name or tag.name)
        # Fire only on an actual change, not a no-op PUT — mirrors attach_tag's
        # newly_attached gating on AFTER_TAG_ATTACHED_HOOK.
        if changed:
            hooks.run_hooks(hooks.AFTER_TAG_UPDATED_HOOK, db, tag)
        return tag

    def delete_tag(self, db: Session, tag: models.Tag) -> None:
        # Remove associations first so no taggable keeps a dangling reference,
        # then delete the registry row — both inside a savepoint. A Core
        # `delete()` executes eagerly at `db.execute()`, not at a later flush,
        # so the guard must wrap the executes themselves (e.g. a concurrent
        # attach_tag landing mid-delete and tripping the FK on the final
        # delete) for the savepoint to roll back cleanly instead of poisoning
        # the outer transaction.
        try:
            with db.begin_nested():
                for assc in models.all_tag_assc_tables:
                    db.execute(delete(assc).where(assc.c.tag_id == tag.id))
                db.execute(delete(models.Tag).where(models.Tag.id == tag.id))
        except IntegrityError as e:
            raise ValueError(
                f"Cannot delete tag {tag.id}: it was attached to another "
                "entity concurrently."
            ) from e

    def usage_counts(self, db: Session, tag_ids: list[int]) -> dict[int, int]:
        """Association count per tag id across all assoc tables. Tags with no
        usage are omitted; callers default missing ids to 0."""
        if not tag_ids:
            return {}
        sels = [
            select(assc.c.tag_id.label("tag_id")).where(assc.c.tag_id.in_(tag_ids))
            for assc in models.all_tag_assc_tables
        ]
        sub = union_all(*sels).subquery()
        rows = db.execute(
            select(sub.c.tag_id, func.count().label("n")).group_by(sub.c.tag_id)
        ).all()
        return dict(rows)
