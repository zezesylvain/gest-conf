import pytest

from htaccess_merge import merge

BLOCK = "# BEGIN GEST-CONF\nRewriteEngine On\n# END GEST-CONF\n"
PASSENGER = (
    "# DO NOT REMOVE. CLOUDLINUX PASSENGER CONFIGURATION BEGIN\n"
    'PassengerAppRoot "/home/compte/gestconf-app"\n'
    'PassengerBaseURI "/api"\n'
    "# DO NOT REMOVE. CLOUDLINUX PASSENGER CONFIGURATION END\n"
)


def test_adds_block_to_empty_file():
    assert merge("", BLOCK) == BLOCK


def test_keeps_passenger_block_and_appends_ours():
    result = merge(PASSENGER, BLOCK)
    assert result.startswith(PASSENGER)
    assert result.endswith(BLOCK)


def test_replaces_previous_version_only():
    previous = PASSENGER + "\n# BEGIN GEST-CONF\nancienne règle\n# END GEST-CONF\n# fin\n"
    result = merge(previous, BLOCK)
    assert "ancienne règle" not in result
    assert result == PASSENGER + "\n" + BLOCK + "# fin\n"


def test_is_idempotent():
    once = merge(PASSENGER, BLOCK)
    assert merge(once, BLOCK) == once


def test_refuses_unbalanced_markers():
    with pytest.raises(ValueError, match="incohérents"):
        merge("# BEGIN GEST-CONF\nsans fin\n", BLOCK)


def test_refuses_block_without_markers():
    with pytest.raises(ValueError, match="marqueurs"):
        merge("", "RewriteEngine On\n")
