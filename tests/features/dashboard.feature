Feature: Dashboard of the pipeline results
  As a business analyst
  I want to see the results of the last finished run
  So that I know how many restaurants were matched and what they offer

  Scenario: The dashboard shows the last finished run
    Given Just Eat serves the curated venues
    And a run that finished processing
    And I am logged in as a dashboard user
    When I open the dashboard summary
    Then I see 1 matched restaurant out of 1 crawled
    And I see 0 restaurants in review and 0 rejected
    And "salads" is among the top food categories

  Scenario: The dashboard is private
    Given Just Eat serves the curated venues
    And a run that finished processing
    When I open the dashboard summary
    Then access is denied
