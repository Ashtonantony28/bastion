from bastion import fixtures
from bastion.paths import FIXTURE_RAW


def test_generator_is_deterministic():
    assert fixtures.generate() == fixtures.generate()


def test_committed_fixtures_match_generator():
    assert fixtures.check(FIXTURE_RAW) == []
