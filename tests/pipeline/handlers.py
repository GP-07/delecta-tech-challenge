"""Step handlers for the pipeline tests: they record their calls instead of doing real work."""

from apps.pipeline.steps import StepOutcome

calls: list[tuple[str, int]] = []


def extract(run):
    calls.append(("extract", run.pk))
    return StepOutcome(metrics={"venues": 3}, output_dir="/data/extract")


def match(run):
    calls.append(("match", run.pk))
    return StepOutcome(metrics={"matched": 2})


def broken(run):
    calls.append(("broken", run.pk))
    raise ValueError("Just Eat answered 503")
