import uuid

import pytest
from starlette import status

from empire.server.core.db.models import PluginTaskStatus
from empire.server.core.tag_service import TagService

PLUGIN_ID = "basic_reporting"


def _create_tag(client, admin_auth_header, name, **extra):
    """Create a registry tag and return its JSON (incl. id)."""
    resp = client.post(
        "/api/v2/tags",
        headers=admin_auth_header,
        json={"name": name, **extra},
    )
    assert resp.status_code == status.HTTP_201_CREATED
    return resp.json()


def _attach(client, admin_auth_header, path, taggable_id, tag_id):
    """Attach an existing tag (by id) to an entity."""
    return client.post(
        f"{path}/{taggable_id}/tags",
        headers=admin_auth_header,
        json={"tag_id": tag_id},
    )


def _test_attach_tag(client, admin_auth_header, path, taggable_id):
    # Unique tag name per invocation: the DB is session-scoped, so tags created in
    # one test persist across tests in the same run.
    name = f"needs_review_{uuid.uuid4().hex[:8]}"
    tag = _create_tag(client, admin_auth_header, name)
    tag_id = tag["id"]
    assert tag["color"].startswith("#")
    assert tag["description"] is None

    # Attach the existing tag by id -> 200; the entity now lists exactly it.
    resp = _attach(client, admin_auth_header, path, taggable_id, tag_id)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["id"] == tag_id

    resp = client.get(f"{path}/{taggable_id}", headers=admin_auth_header)
    assert resp.status_code == status.HTTP_200_OK
    tags = resp.json()["tags"]
    assert len(tags) == 1
    assert tags[0]["id"] == tag_id

    # Re-attaching the same tag -> 200, idempotent (still a single association).
    resp = _attach(client, admin_auth_header, path, taggable_id, tag_id)
    assert resp.status_code == status.HTTP_200_OK
    resp = client.get(f"{path}/{taggable_id}", headers=admin_auth_header)
    assert len(resp.json()["tags"]) == 1

    # Attaching an unknown tag_id -> 404.
    resp = _attach(client, admin_auth_header, path, taggable_id, 999999)
    assert resp.status_code == status.HTTP_404_NOT_FOUND

    # Missing tag_id -> 422.
    resp = client.post(f"{path}/{taggable_id}/tags", headers=admin_auth_header, json={})
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # Detach -> 204; entity has no tags but the tag persists in the registry.
    resp = client.delete(
        f"{path}/{taggable_id}/tags/{tag_id}", headers=admin_auth_header
    )
    assert resp.status_code == status.HTTP_204_NO_CONTENT

    resp = client.get(f"{path}/{taggable_id}", headers=admin_auth_header)
    assert resp.json()["tags"] == []

    resp = client.get("/api/v2/tags?order_by=name", headers=admin_auth_header)
    assert any(t["id"] == tag_id for t in resp.json()["records"])


def test_listener_attach_tag(client, admin_auth_header, listener):
    _test_attach_tag(client, admin_auth_header, "/api/v2/listeners", listener["id"])


def test_agent_attach_tag(client, admin_auth_header, agent):
    _test_attach_tag(client, admin_auth_header, "/api/v2/agents", agent)


def test_agent_task_attach_tag(client, admin_auth_header, agent_task):
    _test_attach_tag(
        client,
        admin_auth_header,
        f"/api/v2/agents/{agent_task['agent_id']}/tasks",
        agent_task["id"],
    )


def test_plugin_task_attach_tag(client, admin_auth_header, plugin_task):
    _test_attach_tag(
        client, admin_auth_header, "/api/v2/plugins/basic_reporting/tasks", plugin_task
    )


def test_credential_attach_tag(client, admin_auth_header, credential):
    _test_attach_tag(client, admin_auth_header, "/api/v2/credentials", credential)


def test_download_attach_tag(client, admin_auth_header, download):
    _test_attach_tag(client, admin_auth_header, "/api/v2/downloads", download)


def test_tag_shared_across_entities(client, admin_auth_header, listener, agent):
    """One tag attached to two entities is the SAME shared row."""
    tag = _create_tag(client, admin_auth_header, f"shared_{uuid.uuid4().hex[:8]}")
    r1 = _attach(
        client, admin_auth_header, "/api/v2/listeners", listener["id"], tag["id"]
    )
    assert r1.status_code == status.HTTP_200_OK
    r2 = _attach(client, admin_auth_header, "/api/v2/agents", agent, tag["id"])
    assert r2.status_code == status.HTTP_200_OK
    assert r1.json()["id"] == r2.json()["id"] == tag["id"]
    assert r1.json()["color"] == r2.json()["color"]

    client.delete(
        f"/api/v2/listeners/{listener['id']}/tags/{tag['id']}",
        headers=admin_auth_header,
    )
    client.delete(f"/api/v2/agents/{agent}/tags/{tag['id']}", headers=admin_auth_header)


def test_attach_validation(client, admin_auth_header, agent):
    # Missing tag_id -> 422.
    resp = client.post(
        f"/api/v2/agents/{agent}/tags", headers=admin_auth_header, json={}
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # Non-integer tag_id -> 422.
    resp = client.post(
        f"/api/v2/agents/{agent}/tags",
        headers=admin_auth_header,
        json={"tag_id": "notanint"},
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_get_credentials_tag_filter(client, admin_auth_header, credential):
    """The credentials list honors the exact-name tag filter."""
    tag_name = f"cred_tag_{uuid.uuid4().hex[:8]}"
    tag = _create_tag(client, admin_auth_header, tag_name)
    resp = _attach(
        client, admin_auth_header, "/api/v2/credentials", credential, tag["id"]
    )
    assert resp.status_code == status.HTTP_200_OK

    resp = client.get(f"/api/v2/credentials?tags={tag_name}", headers=admin_auth_header)
    assert resp.status_code == status.HTTP_200_OK
    records = resp.json()["records"]
    assert len(records) == 1
    assert records[0]["id"] == credential
    assert records[0]["tags"][0]["name"] == tag_name


@pytest.fixture
def create_agent_tasks_with_tags(client, admin_auth_header, agent):
    agent_id = agent
    # Unique tag names per run: tags persist in the session-scoped DB, so static
    # names would collide (409) on a second run.
    run = uuid.uuid4().hex[:8]
    tag_names = [f"flt_{run}_{i}" for i in range(3)]
    tag_ids = [_create_tag(client, admin_auth_header, n)["id"] for n in tag_names]
    agent_tasks = []
    for i in range(3):
        resp = client.post(
            f"/api/v2/agents/{agent_id}/tasks/shell",
            headers=admin_auth_header,
            json={"command": f"whoami_{i}"},
        )
        assert resp.status_code == status.HTTP_201_CREATED
        agent_tasks.append(resp.json())

    for i, agent_task in enumerate(agent_tasks):
        resp = _attach(
            client,
            admin_auth_header,
            f"/api/v2/agents/{agent_id}/tasks",
            agent_task["id"],
            tag_ids[i],
        )
        assert resp.status_code == status.HTTP_200_OK
    return tag_names


def test_get_agent_tasks_tag_filter(
    client, admin_auth_header, agent, create_agent_tasks_with_tags
):
    tag_names = create_agent_tasks_with_tags
    resp = client.get(
        f"/api/v2/agents/{agent}/tasks?tags={tag_names[0]}", headers=admin_auth_header
    )
    assert resp.status_code == status.HTTP_200_OK
    assert len(resp.json()["records"]) == 1
    assert resp.json()["records"][0]["input"] == "whoami_0"
    assert resp.json()["records"][0]["tags"][0]["name"] == tag_names[0]

    resp = client.get(
        f"/api/v2/agents/{agent}/tasks?tags={tag_names[0]}&tags={tag_names[1]}",
        headers=admin_auth_header,
    )
    assert resp.status_code == status.HTTP_200_OK
    records = resp.json()["records"]
    assert len(records) == 2  # noqa: PLR2004
    # OR-union: exactly the two tasks carrying either tag (not just any two).
    assert {r["input"] for r in records} == {"whoami_0", "whoami_1"}


def test_tag_filter_no_duplicate_for_entity_with_multiple_filtered_tags(
    client, admin_auth_header, agent
):
    """A single task carrying 2+ of the filtered tags must appear exactly once
    (and not inflate `total`). A join-based filter would multiply rows; the filter
    uses an EXISTS subquery to avoid that."""
    run = uuid.uuid4().hex[:8]
    names = [f"dup_{run}_{i}" for i in range(2)]
    tag_ids = [_create_tag(client, admin_auth_header, n)["id"] for n in names]
    resp = client.post(
        f"/api/v2/agents/{agent}/tasks/shell",
        headers=admin_auth_header,
        json={"command": "whoami_dup"},
    )
    assert resp.status_code == status.HTTP_201_CREATED
    task_id = resp.json()["id"]
    for tag_id in tag_ids:
        resp = _attach(
            client, admin_auth_header, f"/api/v2/agents/{agent}/tasks", task_id, tag_id
        )
        assert resp.status_code == status.HTTP_200_OK

    resp = client.get(
        f"/api/v2/agents/{agent}/tasks?tags={names[0]}&tags={names[1]}",
        headers=admin_auth_header,
    )
    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    matching = [r for r in body["records"] if r["id"] == task_id]
    assert len(matching) == 1, f"task duplicated by multi-tag filter: {body['records']}"
    # The names are unique to this run, so exactly one task matches — `total` (the
    # count(...).over() window) must not be inflated by the multi-tag join either.
    assert body["total"] == 1, f"total inflated by multi-tag filter: {body}"


def test_get_all_agents_tasks_tag_filter(client, admin_auth_header, agent):
    """The cross-agent GET /api/v2/agents/tasks honors the exact-name tag filter."""
    tag_name = f"allagents_{uuid.uuid4().hex[:8]}"
    tag_id = _create_tag(client, admin_auth_header, tag_name)["id"]
    resp = client.post(
        f"/api/v2/agents/{agent}/tasks/shell",
        headers=admin_auth_header,
        json={"command": "whoami"},
    )
    assert resp.status_code == status.HTTP_201_CREATED
    task_id = resp.json()["id"]
    resp = _attach(
        client, admin_auth_header, f"/api/v2/agents/{agent}/tasks", task_id, tag_id
    )
    assert resp.status_code == status.HTTP_200_OK

    resp = client.get(
        f"/api/v2/agents/tasks?tags={tag_name}", headers=admin_auth_header
    )
    assert resp.status_code == status.HTTP_200_OK
    records = resp.json()["records"]
    assert len(records) == 1
    assert records[0]["id"] == task_id
    assert records[0]["tags"][0]["name"] == tag_name


def test_registry_sources_filter_no_duplicate_for_tag_on_multiple_entities(
    client, admin_auth_header, agent
):
    """A single tag attached to 2+ entities of the SAME source type must appear
    exactly once in the registry listing (and not inflate `total`) when filtering
    by that one source. `get_all`'s `sources=` filter only de-dupes via the
    `.union()` path when 2+ source types are combined; a single source type used
    to skip that and join against a non-distinct subquery."""
    run = uuid.uuid4().hex[:8]
    name = f"shared_{run}"
    tag_id = _create_tag(client, admin_auth_header, name)["id"]

    task_ids = []
    for i in range(2):
        resp = client.post(
            f"/api/v2/agents/{agent}/tasks/shell",
            headers=admin_auth_header,
            json={"command": f"whoami_shared_{i}"},
        )
        assert resp.status_code == status.HTTP_201_CREATED
        task_id = resp.json()["id"]
        task_ids.append(task_id)
        resp = _attach(
            client, admin_auth_header, f"/api/v2/agents/{agent}/tasks", task_id, tag_id
        )
        assert resp.status_code == status.HTTP_200_OK

    resp = client.get("/api/v2/tags?sources=agent_task", headers=admin_auth_header)
    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    matching = [r for r in body["records"] if r["id"] == tag_id]
    assert len(matching) == 1, f"tag duplicated by single-source filter: {body}"
    # No id should repeat regardless of how many other tags exist from other
    # tests sharing this session-scoped DB.
    ids = [r["id"] for r in body["records"]]
    assert len(ids) == len(set(ids)), f"duplicate tag id in records: {body}"
    assert body["total"] == len(body["records"]), f"total inflated: {body}"


@pytest.fixture
def create_downloads_with_tags(models, session_local, client, admin_auth_header):
    downloads = []
    for i in range(3):
        download = models.Download(
            location=f"lblpath/{i}", filename=f"lblfile_{i}", size=1
        )
        with session_local.begin() as db:
            db.add(download)
            db.flush()
            downloads.append({"id": download.id})

    tag_names = [f"dl_{uuid.uuid4().hex[:8]}_{i}" for i in range(3)]
    for i, download in enumerate(downloads):
        tag_id = _create_tag(client, admin_auth_header, tag_names[i])["id"]
        resp = _attach(
            client, admin_auth_header, "/api/v2/downloads", download["id"], tag_id
        )
        assert resp.status_code == status.HTTP_200_OK
    return downloads, tag_names


def test_get_downloads_tag_filter(
    client, admin_auth_header, create_downloads_with_tags
):
    _downloads, tag_names = create_downloads_with_tags
    resp = client.get(
        f"/api/v2/downloads?tags={tag_names[0]}", headers=admin_auth_header
    )
    assert resp.status_code == status.HTTP_200_OK
    assert len(resp.json()["records"]) == 1
    assert resp.json()["records"][0]["location"] == "lblpath/0"
    assert resp.json()["records"][0]["tags"][0]["name"] == tag_names[0]


def test_plugin_task_tag_filter(models, session_local, client, admin_auth_header):
    tag_names = [f"pl_{uuid.uuid4().hex[:8]}_{i}" for i in range(3)]
    plugin_tasks = []
    for i in range(3):
        plugin_task = models.PluginTask(
            plugin_id=PLUGIN_ID,
            input=f"lbl input {i}",
            input_full=f"lbl input {i}",
            user_id=None,
            status=PluginTaskStatus.completed,
        )
        with session_local.begin() as db:
            db.add(plugin_task)
            db.flush()
            plugin_tasks.append({"id": plugin_task.id})

    for i, plugin_task in enumerate(plugin_tasks):
        tag_id = _create_tag(client, admin_auth_header, tag_names[i])["id"]
        resp = _attach(
            client,
            admin_auth_header,
            f"/api/v2/plugins/{PLUGIN_ID}/tasks",
            plugin_task["id"],
            tag_id,
        )
        assert resp.status_code == status.HTTP_200_OK

    resp = client.get(
        f"/api/v2/plugins/{PLUGIN_ID}/tasks?tags={tag_names[0]}",
        headers=admin_auth_header,
    )
    assert resp.status_code == status.HTTP_200_OK
    assert len(resp.json()["records"]) == 1
    assert resp.json()["records"][0]["input"] == "lbl input 0"


def test_registry_crud(client, admin_auth_header):
    # Create.
    resp = client.post(
        "/api/v2/tags",
        headers=admin_auth_header,
        json={"name": "crud_tag", "description": "a tag", "color": "#112233"},
    )
    assert resp.status_code == status.HTTP_201_CREATED
    tag = resp.json()
    assert tag["color"] == "#112233"
    assert tag["description"] == "a tag"
    tid = tag["id"]

    # Duplicate create -> 409.
    resp = client.post(
        "/api/v2/tags", headers=admin_auth_header, json={"name": "crud_tag"}
    )
    assert resp.status_code == status.HTTP_409_CONFLICT

    # Get one.
    resp = client.get(f"/api/v2/tags/{tid}", headers=admin_auth_header)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["name"] == "crud_tag"

    # Update (rename + recolor).
    resp = client.put(
        f"/api/v2/tags/{tid}",
        headers=admin_auth_header,
        json={"name": "crud_tag_2", "color": "#445566"},
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["name"] == "crud_tag_2"
    assert resp.json()["color"] == "#445566"

    # Partial update: PUT without `name` recolors only (name left unchanged), per
    # TagUpdateRequest's documented partial-update semantics.
    resp = client.put(
        f"/api/v2/tags/{tid}", headers=admin_auth_header, json={"color": "#778899"}
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["name"] == "crud_tag_2"
    assert resp.json()["color"] == "#778899"

    # Rename collision -> 409.
    client.post("/api/v2/tags", headers=admin_auth_header, json={"name": "other_tag"})
    resp = client.put(
        f"/api/v2/tags/{tid}", headers=admin_auth_header, json={"name": "other_tag"}
    )
    assert resp.status_code == status.HTTP_409_CONFLICT

    # Delete.
    resp = client.delete(f"/api/v2/tags/{tid}", headers=admin_auth_header)
    assert resp.status_code == status.HTTP_204_NO_CONTENT
    resp = client.get(f"/api/v2/tags/{tid}", headers=admin_auth_header)
    assert resp.status_code == status.HTTP_404_NOT_FOUND


def test_list_usage_count(client, admin_auth_header, listener, agent):
    name = f"counted_{uuid.uuid4().hex[:8]}"
    tag_id = _create_tag(client, admin_auth_header, name)["id"]
    _attach(client, admin_auth_header, "/api/v2/listeners", listener["id"], tag_id)
    _attach(client, admin_auth_header, "/api/v2/agents", agent, tag_id)
    resp = client.get("/api/v2/tags?order_by=name", headers=admin_auth_header)
    assert resp.status_code == status.HTTP_200_OK
    counted = next(t for t in resp.json()["records"] if t["name"] == name)
    assert counted["usage_count"] == 2  # noqa: PLR2004

    # Detach from the session-scoped listener/agent so this leaked association
    # can't break a later test's exact tag-count assertion on the same entities.
    client.delete(
        f"/api/v2/listeners/{listener['id']}/tags/{tag_id}", headers=admin_auth_header
    )
    client.delete(f"/api/v2/agents/{agent}/tags/{tag_id}", headers=admin_auth_header)


def test_delete_tag_detaches_everywhere(client, admin_auth_header, agent):
    tag_id = _create_tag(
        client, admin_auth_header, f"to_delete_{uuid.uuid4().hex[:8]}"
    )["id"]
    resp = _attach(client, admin_auth_header, "/api/v2/agents", agent, tag_id)
    assert resp.status_code == status.HTTP_200_OK
    resp = client.delete(f"/api/v2/tags/{tag_id}", headers=admin_auth_header)
    assert resp.status_code == status.HTTP_204_NO_CONTENT
    resp = client.get(f"/api/v2/agents/{agent}", headers=admin_auth_header)
    assert all(t["id"] != tag_id for t in resp.json()["tags"])


@pytest.mark.parametrize(
    "color",
    ["notacolor", "#12345", "#1234567"],  # non-hex, 5-digit, 7-digit (invalid lengths)
)
def test_registry_create_rejects_bad_color(client, admin_auth_header, color):
    """POST /api/v2/tags rejects non-CSS hex colors with 422 (valid: 3/4/6/8 digits)."""
    resp = client.post(
        "/api/v2/tags",
        headers=admin_auth_header,
        json={"name": f"badcolor_{uuid.uuid4().hex[:8]}", "color": color},
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_registry_create_rejects_empty_name(client, admin_auth_header):
    resp = client.post("/api/v2/tags", headers=admin_auth_header, json={"name": ""})
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_get_or_create_tag_is_idempotent(client, admin_auth_header, session_local):
    """get_or_create_tag (the internal concurrency-safe upsert used by the download
    auto-tag) creates once then returns the same row — and the created tag is real
    (visible in the registry with a derived color)."""
    svc = TagService(None)
    name = f"goc_{uuid.uuid4().hex[:8]}"
    with session_local.begin() as db:
        tag1, created1 = svc.get_or_create_tag(db, name)
        tag1_id, tag1_color = tag1.id, tag1.color
        assert created1 is True
        assert tag1.name == name
        assert tag1_color.startswith("#")

        tag2, created2 = svc.get_or_create_tag(db, name)
        assert created2 is False
        assert tag2.id == tag1_id

    resp = client.get("/api/v2/tags?order_by=name", headers=admin_auth_header)
    assert resp.status_code == status.HTTP_200_OK
    assert any(
        t["id"] == tag1_id and t["color"] == tag1_color for t in resp.json()["records"]
    )
