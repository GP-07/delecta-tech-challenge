"""Pipeline steps of the menus app."""

from pathlib import Path

from apps.menus.categorization_services import categorize_run_items
from apps.menus.publish_services import publish_run as publish
from apps.pipeline.models import PipelineRun
from apps.pipeline.steps import StepOutcome


def categorize_menu_items(run: PipelineRun) -> StepOutcome:
    """Classifies the menu items of the venues this run crawled and linked to Google (accepted or confirmed)."""
    result = categorize_run_items(run)
    return StepOutcome(metrics=result.as_metrics(), output_dir=str(Path(result.output_file).parent))


def publish_run(run: PipelineRun) -> StepOutcome:
    """Makes everything the run staged visible at once (venues, links, taxonomy, menu items)."""
    return StepOutcome(metrics=publish(run))
