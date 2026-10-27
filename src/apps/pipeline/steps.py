"""The steps of the pipeline, in order (settings.PIPELINE_STEPS: [(name, "dotted.path.to.handler"), ...]).

A handler receives the run and does the work of its step. It returns a StepOutcome on success and raises any
exception on failure; the pipeline records either one and decides what comes next.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from django.conf import settings
from django.utils.module_loading import import_string

from apps.pipeline.models import PipelineRun, Status


@dataclass(frozen=True)
class StepOutcome:
    metrics: dict = field(default_factory=dict)  # small JSON-serialisable summary, shown in the admin
    output_dir: str = ""  # where the step left its files, if any


StepHandler = Callable[[PipelineRun], StepOutcome]


class StepNotDoneError(Exception):
    """A step needs the output of an earlier step of its own run, and that step has not succeeded."""


def require_succeeded(run: PipelineRun, *names: str) -> None:
    """A step only works on what earlier steps of the same run produced, and only once they succeeded."""
    done = set(run.steps.filter(name__in=names, status=Status.SUCCEEDED).values_list("name", flat=True))
    missing = [name for name in names if name not in done]
    if missing:
        raise StepNotDoneError(f"run {run.pk}: step {', '.join(missing)} of this run has not succeeded")


def step_names() -> list[str]:
    return [name for name, _ in settings.PIPELINE_STEPS]


def get_handler(name: str) -> StepHandler:
    return import_string(dict(settings.PIPELINE_STEPS)[name])
