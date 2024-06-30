from empire.server.common import helpers


def test_dynamic_powershell():
    expected_len = 96863
    with open(
        "empire/server/data/module_source/situational_awareness/network/powerview.ps1",
    ) as file:
        script = file.read()
    new_script = helpers.generate_dynamic_powershell_script(
        script, "Find-LocalAdminAccess"
    )
    assert len(new_script) == expected_len
