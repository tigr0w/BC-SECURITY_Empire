from pathlib import Path

import pytest
import yaml

from empire.server.utils.listener_template_util import (
    convert_listener_options,
    load_listener_template_yaml,
)

SAMPLE = """\
id: sample
display_name: 'Sample[S]'
authors:
  - {name: Tester, handle: '@t', link: https://example.com}
description: |
  A sample listener.
comments: [hello]
software: ''
techniques: [T1071]
tactics: [TA0011]
options:
  - {name: Name, description: 'Name for the listener.', required: true, value: sample}
  - name: Mode
    description: Operating mode.
    required: false
    value: auto
    suggested_values: [auto, manual]
    strict: true
    depends_on:
      - {name: Name, values: [sample]}
  - {name: Secret, description: hidden, required: false, value: '', internal: true}
"""


@pytest.fixture
def sample_yaml(tmp_path: Path) -> Path:
    p = tmp_path / "sample.yaml"
    p.write_text(SAMPLE)
    return p


def test_convert_listener_options_capitalizes_and_defaults():
    raw = yaml.safe_load(SAMPLE)["options"]
    converted = convert_listener_options(raw)

    assert converted["Mode"]["Description"] == "Operating mode."
    assert converted["Mode"]["Required"] is False
    assert converted["Mode"]["Value"] == "auto"
    assert converted["Mode"]["SuggestedValues"] == ["auto", "manual"]
    assert converted["Mode"]["Strict"] is True
    assert converted["Mode"]["DependsOn"] == [{"name": "Name", "values": ["sample"]}]
    assert converted["Name"]["SuggestedValues"] == []
    assert converted["Name"]["Strict"] is False
    assert converted["Name"]["Internal"] is False
    assert converted["Name"]["DependsOn"] == []
    assert converted["Secret"]["Internal"] is True


def test_load_listener_template_yaml_builds_info_and_options(sample_yaml: Path):
    parsed = load_listener_template_yaml(sample_yaml)

    info = parsed["info"]
    assert info["Name"] == "Sample[S]"
    assert info["Authors"] == [
        {"Name": "Tester", "Handle": "@t", "Link": "https://example.com"}
    ]
    assert info["Description"].strip() == "A sample listener."
    assert info["Comments"] == ["hello"]
    assert info["Software"] == ""
    assert info["Techniques"] == ["T1071"]
    assert info["Tactics"] == ["TA0011"]

    assert parsed["id"] == "sample"
    assert parsed["options"]["Name"]["Value"] == "sample"


def test_missing_id_or_display_name_raises(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("display_name: X\noptions: []\n")
    with pytest.raises(KeyError):
        load_listener_template_yaml(bad)
