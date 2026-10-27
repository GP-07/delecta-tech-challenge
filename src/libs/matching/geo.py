"""Distances between places and a grid to find the places near a point without comparing against all of them.

Distance (haversine)
    The Earth is taken as a sphere of radius EARTH_RADIUS_M. The great-circle distance between two points is

        haversine_term = sin²(Δlatitude / 2) + cos(latitude_1) · cos(latitude_2) · sin²(Δlongitude / 2)
        distance       = 2 · R · asin(√haversine_term)

    (angles in radians). The cosines shrink the longitude difference away from the equator: in Barcelona a degree
    of longitude is ~83 km, a degree of latitude ~111 km. At the distances that matter here (metres to a few hundred
    metres) the error of the spherical model is well under a metre.

Grid
    Comparing each of the ~2,700 Just Eat venues with each of the ~22,000 Google places would be ~59 million
    distances. Instead, places are put in square cells of GRID_CELL_DEGREES (~555 m x ~420 m in Barcelona), keyed by
    (floor(latitude / size), floor(longitude / size)). A circle of radius up to one cell around a point always fits
    in the 3 x 3 cells around the point's own cell, so a search only measures the places of those 9 cells.
"""

import math
from collections import defaultdict
from collections.abc import Iterable, Iterator

from libs.matching.constants import EARTH_RADIUS_M, GRID_CELL_DEGREES, GRID_NEIGHBOUR_OFFSETS, MIN_METRES_PER_DEGREE
from libs.matching.domain import Place

GridCell = tuple[int, int]


def distance_m(origin: Place, destination: Place) -> float:
    """Great-circle (haversine) distance in metres."""
    origin_latitude, origin_longitude, destination_latitude, destination_longitude = map(
        math.radians, (origin.latitude, origin.longitude, destination.latitude, destination.longitude))
    haversine_term = (math.sin((destination_latitude - origin_latitude) / 2) ** 2
                      + math.cos(origin_latitude) * math.cos(destination_latitude)
                      * math.sin((destination_longitude - origin_longitude) / 2) ** 2)
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(haversine_term))


def grid_cell(place: Place) -> GridCell:
    """The (row, column) of the grid cell the place falls in."""
    return math.floor(place.latitude / GRID_CELL_DEGREES), math.floor(place.longitude / GRID_CELL_DEGREES)


class GridIndex:
    """Places bucketed in a latitude/longitude grid, so a search only looks at the 9 cells around a point."""

    def __init__(self, places: Iterable[Place]) -> None:
        self._places_by_cell: dict[GridCell, list[Place]] = defaultdict(list)
        for place in places:
            self._places_by_cell[grid_cell(place)].append(place)

    def near(self, origin: Place, radius_m: float) -> Iterator[tuple[Place, float]]:
        """Every place within `radius_m` of `origin`, with its distance in metres (in no particular order)."""
        if radius_m > GRID_CELL_DEGREES * MIN_METRES_PER_DEGREE:  # a neighbouring cell would no longer cover it
            raise ValueError(f"radius {radius_m} m too large for the grid")
        origin_row, origin_column = grid_cell(origin)
        for row_offset in GRID_NEIGHBOUR_OFFSETS:
            for column_offset in GRID_NEIGHBOUR_OFFSETS:
                for place in self._places_by_cell.get((origin_row + row_offset, origin_column + column_offset), ()):
                    distance = distance_m(origin, place)
                    if distance <= radius_m:
                        yield place, distance
