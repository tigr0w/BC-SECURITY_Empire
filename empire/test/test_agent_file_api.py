import pytest
from sqlalchemy.orm import Session

from empire.server.database import models


@pytest.fixture(scope="module", autouse=True)
def agent(db):
    from empire.server.server import main

    agent = db.query(models.Agent).filter(models.Agent.session_id == 'TEST123').first()
    if not agent:
        agent = models.Agent(name='TEST123',
                             session_id='TEST123',
                             delay=1,
                             jitter=0.1,
                             external_ip='1.1.1.1',
                             session_key='qwerty',
                             nonce='nonce',
                             profile='profile',
                             kill_date='killDate',
                             working_hours='workingHours',
                             lost_limit=60,
                             listener='http',
                             language='powershell',
                             language_version='5',
                             high_integrity=True,
                             archived=False
                             )
        db.add(agent)
        db.flush()
        db.commit()

    main.agents.agents['TEST123'] = {'sessionKey': agent.session_key, 'functions': agent.functions}

    yield agent

    db.delete(agent)
    db.commit()


@pytest.fixture(scope="module", autouse=True)
def agent_no_files(db):
    from empire.server.server import main

    agent = db.query(models.Agent).filter(models.Agent.session_id == 'EMPTY').first()
    if not agent:
        agent = models.Agent(name='EMPTY',
                             session_id='EMPTY',
                             delay=1,
                             jitter=0.1,
                             external_ip='1.1.1.1',
                             session_key='qwerty',
                             nonce='nonce',
                             profile='profile',
                             kill_date='killDate',
                             working_hours='workingHours',
                             lost_limit=60,
                             listener='http',
                             language='powershell',
                             language_version='5',
                             high_integrity=True,
                             archived=False
                             )
        db.add(agent)
        db.flush()
        db.commit()

    main.agents.agents['EMPTY'] = {'sessionKey': agent.session_key, 'functions': agent.functions}

    yield agent

    db.delete(agent)
    db.commit()


@pytest.fixture(scope="module", autouse=True)
def files(db: Session, agent):
    root_file = models.AgentFile(session_id=agent.session_id, name="/", path="/", is_file=False, parent_id=None)

    db.add(root_file)
    db.flush()

    file_1 = models.AgentFile(session_id=agent.session_id, name="C:\\", path="/C:\\", is_file=False, parent_id=root_file.id)
    file_2 = models.AgentFile(session_id=agent.session_id, name="D:\\", path="/D:\\", is_file=False, parent_id=root_file.id)
    db.add(file_1)
    db.add(file_2)
    db.flush()

    file_3 = models.AgentFile(session_id=agent.session_id, name="photo.png", path="/C:\\photo.png", is_file=True, parent_id=file_1.id)
    file_4 = models.AgentFile(session_id=agent.session_id, name="Documents", path="/C:\\Documents", is_file=False, parent_id=file_1.id)
    db.add(file_3)
    db.add(file_4)
    db.flush()
    db.commit()

    yield [root_file, file_1, file_2, file_3, file_4]

    db.delete(root_file)
    db.delete(file_1)
    db.delete(file_2)
    db.delete(file_3)
    db.delete(file_4)
    db.commit()


def test_get_root_agent_not_found(client, admin_auth_header):
    response = client.get('/api/v2beta/agents/abc/files/root', headers=admin_auth_header)
    assert response.status_code == 404
    assert response.json()['detail'] == 'Agent not found for id abc'


def test_get_root_not_found(client, admin_auth_header, agent_no_files):
    response = client.get(f'/api/v2beta/agents/{agent_no_files.session_id}/files/root', headers=admin_auth_header)
    assert response.status_code == 404
    assert response.json()['detail'] == f'File not found for agent {agent_no_files.session_id} and file path "/"'


def test_get_root(client, admin_auth_header, agent):
    response = client.get(f'/api/v2beta/agents/{agent.session_id}/files/root', headers=admin_auth_header)
    assert response.status_code == 200
    assert response.json()['name'] == '/'
    assert response.json()['path'] == '/'
    assert response.json()['is_file'] is False
    assert response.json()['parent_id'] is None
    assert len(response.json()['children']) == 2


def test_get_file_agent_not_found(client, admin_auth_header):
    response = client.get('/api/v2beta/agents/abc/files/root', headers=admin_auth_header)
    assert response.status_code == 404
    assert response.json()['detail'] == 'Agent not found for id abc'


def test_get_file_not_found(client, admin_auth_header, agent):
    response = client.get(f'/api/v2beta/agents/{agent.session_id}/files/9999', headers=admin_auth_header)
    assert response.status_code == 404
    assert response.json()['detail'] == 'File not found for agent TEST123 and file id 9999'


def test_get_file_with_children(client, admin_auth_header, agent, files):
    response = client.get(f'/api/v2beta/agents/{agent.session_id}/files/{files[1].id}', headers=admin_auth_header)
    assert response.status_code == 200
    assert response.json()['name'] == 'C:\\'
    assert response.json()['path'] == '/C:\\'
    assert response.json()['is_file'] is False
    assert response.json()['parent_id'] == 1
    assert len(response.json()['children']) == 2


def test_get_file_no_children(client, admin_auth_header, agent, files):
    response = client.get(f'/api/v2beta/agents/{agent.session_id}/files/{files[3].id}', headers=admin_auth_header)
    assert response.status_code == 200
    assert response.json()['name'] == 'photo.png'
    assert response.json()['path'] == '/C:\\photo.png'
    assert response.json()['is_file'] is True
    assert response.json()['parent_id'] == 2
    assert len(response.json()['children']) == 0

