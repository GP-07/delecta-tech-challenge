import pytest

from tests.pipeline import handlers

EXTRACT = ("extract", "tests.pipeline.handlers.extract")
MATCH = ("match", "tests.pipeline.handlers.match")
BROKEN = ("broken", "tests.pipeline.handlers.broken")


@pytest.fixture(autouse=True)
def two_step_pipeline(settings):
    """A pipeline of fake steps; tests that need another one set settings.PIPELINE_STEPS themselves."""
    settings.PIPELINE_STEPS = [EXTRACT, MATCH]
    handlers.calls.clear()
    yield handlers.calls
