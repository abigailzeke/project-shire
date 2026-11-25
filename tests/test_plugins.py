"""Finding plugins and reading plugin.yaml."""

from shire import plugins


def test_finds_built_in_plugins_and_yours(space):
    space.add("docker", "name: Docker\ncheck: port\nport: 2375\n", builtin_too=True)
    space.add("wallet", "name: Wallet\ncheck: website\nurl: http://localhost:5180\n")
    found = plugins.find()
    assert list(found) == ["docker", "wallet"]
    assert found["wallet"].problem is None
    assert found["wallet"].name == "Wallet"


def test_yours_goes_on_top_of_the_built_in_one(space):
    space.add("docker", "name: Docker\ncheck: script\nscript: collect.py\nevery: 30s\noptions: {a: 1, b: 2}\n",
              builtin_too=True)
    space.add("docker", "every: 5m\noptions: {b: 3}\n")
    docker = plugins.find()["docker"]
    assert docker.problem is None
    assert docker.every == 300
    assert docker.config["options"] == {"a": 1, "b": 3}
    assert docker.config["name"] == "Docker"
    assert docker.folders[0] == space.home / "plugins" / "docker"  # yours is looked in first


def test_defaults(space):
    space.add("p", "name: P\ncheck: port\nport: 80\n")
    p = plugins.find()["p"]
    assert (p.every, p.timeout, p.enabled) == (60, 10, True)


def test_a_missing_setting_is_said_plainly(space):
    space.add("wallet", "name: Wallet\ncheck: website\n")
    assert plugins.find()["wallet"].problem == "plugin.yaml: url is missing"


def test_a_typo_is_caught(space):
    space.add("wallet", "name: Wallet\ncheck: website\nurl: http://localhost\nevry: 1m\n")
    assert plugins.find()["wallet"].problem == "plugin.yaml: evry isn't something Shire knows"


def test_a_bad_duration_is_explained(space):
    space.add("wallet", "name: Wallet\ncheck: website\nurl: http://localhost\nevery: soon\n")
    assert "like 30s, 5m or 1h" in plugins.find()["wallet"].problem


def test_an_unknown_check_lists_the_real_ones(space):
    space.add("wallet", "name: Wallet\ncheck: webiste\n")
    assert "should be one of: website, program" in plugins.find()["wallet"].problem


def test_broken_yaml_is_a_problem_not_a_crash(space):
    space.add("wallet", "name: [Wallet\ncheck: website\n")
    assert "isn't valid YAML" in plugins.find()["wallet"].problem


def test_yamls_bare_on_is_caught(space):
    # YAML reads a bare `on` as true, so `on: false` would be silently lost.
    space.add("wallet", "name: Wallet\ncheck: port\nport: 80\non: false\n")
    assert "can't be the name of a setting" in plugins.find()["wallet"].problem


def test_a_badly_named_folder_is_a_problem(space):
    space.add("My Plugin", "name: Mine\ncheck: port\nport: 80\n")
    assert "small letters, numbers and dashes" in plugins.find()["My Plugin"].problem


def test_core_names_are_kept_for_the_plugins_that_come_with_shire(space):
    space.add("core-obsidian", "name: Obsidian\ncheck: folder\npath: null\n", builtin_too=True)
    space.add("core-obsidian", "path: ~/vault\n")      # changing a built-in one is fine
    space.add("core-obsidain", "path: ~/vault\n")      # a typo, or a name of your own, isn't
    found = plugins.find()
    assert found["core-obsidian"].problem is None and found["core-obsidian"].core
    assert "Shire has no plugin called core-obsidain" in found["core-obsidain"].problem
    assert not found["core-obsidain"].core


def test_a_folder_without_plugin_yaml_is_not_a_plugin(space):
    (space.home / "plugins" / "leftover").mkdir(parents=True)
    assert plugins.find() == {}


def test_seconds():
    assert [plugins.seconds(t, 7) for t in ("30s", "5m", "1h", "soon", None)] == [30, 300, 3600, 7, 7]
