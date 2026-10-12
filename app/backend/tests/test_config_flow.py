import yaml

from backend.core.config_manager import ConfigManager


def test_import_export(tmp_path):
    # Use a temporary file so the test never touches the developer's config.yaml.
    cm = ConfigManager(tmp_path / "config.yaml")

    test_value = "TEST_API_KEY_12345"
    cm.update_section("translation", {"openai_api_key": test_value})
    current_config = cm.get_config()
    assert current_config["translation"]["openai_api_key"] == test_value

    # Export to a YAML string, then change the value.
    yaml_content = yaml.dump(current_config, allow_unicode=True, sort_keys=False)
    cm.update_section("translation", {"openai_api_key": "RESET_VALUE"})
    assert cm.get_config()["translation"]["openai_api_key"] == "RESET_VALUE"

    # Import section by section, as the import API does.
    for section, data in yaml.safe_load(yaml_content).items():
        if isinstance(data, dict):
            cm.update_section(section, data)

    assert cm.get_config()["translation"]["openai_api_key"] == test_value
    assert ConfigManager(tmp_path / "config.yaml").get_config()["translation"]["openai_api_key"] == test_value
