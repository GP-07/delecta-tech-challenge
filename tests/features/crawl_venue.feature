Feature: Crawl Just Eat venues
  As a data engineer
  I want to crawl the venues listed in just_eat_urls.json
  So that their details and full menus are stored like just_eat_venues.json and can be queried

  Scenario: Crawl the listed venues into the output file
    Given Just Eat serves the venue "tiflis-restaurant-barcelona"
    And the URL list contains "https://www.just-eat.es/restaurants-tiflis-restaurant-barcelona/menu"
    When I run the crawler
    Then the command succeeds
    And the output contains venue "63038" exactly as in just_eat_venue_example.json
    And the database contains no venues

  Scenario: A missing venue does not stop the run
    Given Just Eat serves the venue "tiflis-restaurant-barcelona"
    And Just Eat does not know the venue "closed-restaurant"
    And the URL list contains "https://www.just-eat.es/restaurants-tiflis-restaurant-barcelona/menu" and "https://www.just-eat.es/restaurants-closed-restaurant/menu"
    When I run the crawler
    Then the command reports failures
    And the output contains venue "63038" exactly as in just_eat_venue_example.json
    And the failures file lists "https://www.just-eat.es/restaurants-closed-restaurant/menu"

  Scenario: A stalled run is cancelled and marked as failed
    Given Just Eat never answers for the venue "stalled"
    And runs time out after 0.2 seconds
    And the URL list contains "https://www.just-eat.es/restaurants-stalled/menu"
    When I run the crawler
    Then the command reports a timeout
    And no output file is created
