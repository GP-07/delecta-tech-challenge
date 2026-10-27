Feature: Pipeline runs controlled from the database
  As a data engineer
  I want to register a run and let the daily dispatcher process it through the queue
  So that every run, its steps, their results and their errors can be followed in the database

  Scenario: A waiting run is processed step by step
    Given Just Eat serves the curated venues
    And a run waiting to be processed
    When the daily dispatcher runs
    Then the run has succeeded with the steps "crawl_just_eat, load_google_venues, match_venues, categorize_menu_items, publish_run"
    And the step "crawl_just_eat" reports 1 venue crawled and 1 failed
    And the database contains Just Eat venue "63038"
    And the Just Eat venue "63038" is linked to the Google place "ChIJqTJI7ESjpBIR7jRF8cSRyDI"
    And the menu item "Ensalada Georgiana" of venue "63038" is in the category "salads" of the family "food"
    And the run folder contains the categorized menu items

  Scenario: A run that fails halfway leaves the last published run untouched
    Given Just Eat serves the curated venues
    And a run that already finished
    And the food categories file of new runs is broken
    And a run waiting to be processed
    When the daily dispatcher runs
    Then the run has failed with "categorize_menu_items: TaxonomyFileError: food categories file not found"
    And the published venues, links and menu items are those of the finished run
    And the failed run's staged data is kept for diagnosis

  Scenario: A failing step fails the run with its error message
    Given Just Eat serves the curated venues
    And runs time out after 0 seconds
    And a run waiting to be processed
    When the daily dispatcher runs
    Then the run has failed with "crawl_just_eat: CrawlTimeoutError: crawl run exceeded 0.0s"
    And the database contains no venues
    And the steps "load_google_venues, match_venues, categorize_menu_items, publish_run" never ran

  Scenario: A failed run is reprocessed as a new run
    Given a failed run
    When I retry it
    Then a new run is waiting to be processed
