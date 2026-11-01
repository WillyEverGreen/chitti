"""Tests for student configuration manager and setup wizard."""

import json
import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from classroom.config import (
    StudentConfig,
    load_config,
    save_config,
    get_default_config_path,
    slugify,
)
import classroom_setup


def test_default_config_values():
    cfg = StudentConfig()
    assert cfg.student_name == ""
    assert cfg.roll_number == ""
    assert cfg.department == ""
    assert cfg.institution == ""
    assert cfg.output_dir == "output"
    assert cfg.credentials_path == "credentials.json"
    assert cfg.token_path == "token.json"
    assert cfg.chrome_debug_port == 9444
    assert not cfg.is_configured()


def test_custom_config_values():
    cfg = StudentConfig(
        student_name="Jane Doe",
        roll_number="CS2026-001",
        department="Computer Science & Engineering",
        institution="Apex Institute of Technology",
        output_dir="custom_output",
        credentials_path="my_creds.json",
        token_path="my_token.json",
        chrome_debug_port=9222,
    )
    assert cfg.student_name == "Jane Doe"
    assert cfg.roll_number == "CS2026-001"
    assert cfg.department == "Computer Science & Engineering"
    assert cfg.institution == "Apex Institute of Technology"
    assert cfg.output_dir == "custom_output"
    assert cfg.credentials_path == "my_creds.json"
    assert cfg.token_path == "my_token.json"
    assert cfg.chrome_debug_port == 9222
    assert cfg.is_configured()


def test_config_serialization_roundtrip(tmp_path):
    cfg_file = tmp_path / "sub" / "student_config.json"
    cfg = StudentConfig(
        student_name="Alice Smith",
        roll_number="CS-42",
        department="Data Science",
        institution="Tech University",
        output_dir=str(tmp_path / "out"),
    )
    saved_path = save_config(cfg, cfg_file)
    assert saved_path == cfg_file
    assert cfg_file.exists()

    loaded = load_config(cfg_file)
    assert loaded.student_name == "Alice Smith"
    assert loaded.roll_number == "CS-42"
    assert loaded.department == "Data Science"
    assert loaded.institution == "Tech University"
    assert loaded.output_dir == str(tmp_path / "out")
    assert loaded.credentials_path == "credentials.json"
    assert loaded.token_path == "token.json"
    assert loaded.chrome_debug_port == 9444


def test_to_dict_and_from_dict():
    cfg = StudentConfig(
        student_name="Bob Jones",
        roll_number="EE-101",
    )
    d = cfg.to_dict()
    assert d["student_name"] == "Bob Jones"
    assert d["roll_number"] == "EE-101"
    assert d["chrome_debug_port"] == 9444

    reconstructed = StudentConfig.from_dict(d)
    assert reconstructed == cfg


def test_from_dict_ignores_extra_keys():
    data = {
        "student_name": "Charlie",
        "roll_number": "12345",
        "department": "Physics",
        "institution": "State College",
        "unknown_extra_field": "some_value",
    }
    cfg = StudentConfig.from_dict(data)
    assert cfg.student_name == "Charlie"
    assert cfg.roll_number == "12345"


def test_load_config_file_not_found(tmp_path):
    missing_file = tmp_path / "does_not_exist.json"
    with pytest.raises(FileNotFoundError):
        load_config(missing_file)


def test_load_config_corrupted_json(tmp_path):
    bad_file = tmp_path / "broken.json"
    bad_file.write_text("{ this is not valid json }", encoding="utf-8")
    with pytest.raises((ValueError, json.JSONDecodeError)):
        load_config(bad_file)


def test_default_config_path(monkeypatch, tmp_path):
    # Test env var override
    custom_path = str(tmp_path / "custom_student_config.json")
    monkeypatch.setenv("CLASSROOM_CONFIG", custom_path)
    assert get_default_config_path() == Path(custom_path)

    # Test default when env var unset
    monkeypatch.delenv("CLASSROOM_CONFIG", raising=False)
    default_path = get_default_config_path()
    assert default_path.name == "student_config.json"


def test_slugify():
    assert slugify("Computer Networks") == "computer_networks"
    assert slugify("Assignment #1: TCP/IP & UDP (Fall 2026)?") == "assignment_1_tcp_ip_udp_fall_2026"
    assert slugify("Lab 03: File I/O <Advanced> *Strict*") == "lab_03_file_i_o_advanced_strict"
    assert slugify("   Spaces   Everywhere   ") == "spaces_everywhere"
    assert slugify("Special---Dashes___Underscores") == "special_dashes_underscores"
    assert slugify("") == ""
    assert slugify("100% Guaranteed!") == "100_guaranteed"


def test_slugify_preserve_case_option():
    assert slugify("Operating Systems - Lab 1", lowercase=False) == "Operating_Systems_Lab_1"


def test_setup_wizard_non_interactive(tmp_path, capsys):
    target_config = tmp_path / "student_config.json"
    ret = classroom_setup.run_setup([
        "--non-interactive",
        "--name", "Ada Lovelace",
        "--roll", "CS-1815",
        "--dept", "Computing",
        "--institution", "London College",
        "--output-dir", str(tmp_path / "out"),
        "--config-path", str(target_config),
    ])
    assert ret == 0
    assert target_config.exists()
    loaded = load_config(target_config)
    assert loaded.student_name == "Ada Lovelace"
    assert loaded.roll_number == "CS-1815"
    assert loaded.department == "Computing"
    assert loaded.institution == "London College"
    captured = capsys.readouterr()
    assert "Configuration saved to" in captured.out


def test_setup_wizard_interactive_mock(tmp_path, monkeypatch, capsys):
    target_config = tmp_path / "interactive_config.json"
    inputs = iter([
        "Grace Hopper",          # Name
        "CS-1906",              # Roll
        "Systems Architecture", # Dept
        "Yale University",      # Institution
        "",                     # Output dir (accept default)
        "",                     # Credentials path (accept default)
    ])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    ret = classroom_setup.run_setup([
        "--config-path", str(target_config),
    ])
    assert ret == 0
    assert target_config.exists()
    loaded = load_config(target_config)
    assert loaded.student_name == "Grace Hopper"
    assert loaded.roll_number == "CS-1906"
    assert loaded.department == "Systems Architecture"
    assert loaded.institution == "Yale University"
    assert loaded.output_dir == "output"


def test_setup_wizard_credentials_warning(tmp_path, capsys):
    target_config = tmp_path / "student_config.json"
    fake_creds = tmp_path / "nonexistent_creds.json"
    ret = classroom_setup.run_setup([
        "--non-interactive",
        "--name", "Alan Turing",
        "--roll", "CS-1912",
        "--credentials", str(fake_creds),
        "--config-path", str(target_config),
    ])
    assert ret == 0
    captured = capsys.readouterr()
    assert "credentials" in captured.out.lower() or "credentials" in captured.err.lower()
