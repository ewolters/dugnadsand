"""Bake a county map into a static SVG.

RUN ONCE, BY HAND, AND COMMIT THE RESULT. Nothing here runs at request time
and nothing the browser loads comes from anywhere but this server: a tile
provider would receive the IP address of every visitor who looks at the
chapter map, which is a worse trade than a slightly plainer map.

Source: the US Census Bureau's TIGERweb service. Census cartographic products
are works of the United States government and carry no copyright.

    python3 deploy/build_county_map.py sc.json nc.json \
        > site_app/templates/site_app/_counties.svg

Takes one GeoJSON per state and draws them as one map, because a chapter's
area is not obliged to respect a state line -- Upstate SC and Western North
Carolina are one chapter.

IDS CARRY THE STATE, and must. Beaufort, Cherokee, Lee and Union are county
names in BOTH Carolinas, and Cherokee and Union are both inside this very
chapter: an id of "c-cherokee" would have shaded a county 250 miles away.

It lands in templates rather than static because it is INCLUDED, not linked:
an <img> cannot be styled per-path, and the whole point is shading the
counties a chapter covers.

The geometry is simplified hard on purpose. This is a diagram of where
chapters are, not a survey: an outline nobody could navigate by is the right
amount of detail, and it keeps the asset small enough to inline.
"""

import json
import re
import sys

WIDTH = 900          # SVG user units; the viewBox scales it anywhere
PADDING = 8
TOLERANCE = 0.004    # degrees; roughly 400m, invisible at this size


# FIPS state code -> postal abbreviation. Only the states we draw.
STATES = {"37": "nc", "45": "sc"}


def slug(state, name):
    """("45", "Greenville County") -> "sc-greenville".

    The state prefix is not decoration. Four county names occur in both
    Carolinas, two of them inside this chapter.
    """
    name = re.sub(r"\s+County$", "", name, flags=re.I)
    stem = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{STATES.get(state, state)}-{stem}"


def rings(geometry):
    """Every ring in a Polygon or MultiPolygon, outer and inner alike."""
    if geometry["type"] == "Polygon":
        return list(geometry["coordinates"])
    out = []
    for polygon in geometry["coordinates"]:
        out.extend(polygon)
    return out


def simplify(points, tolerance):
    """Douglas-Peucker. Keeps the shape, drops the surveying."""
    if len(points) < 3:
        return points

    def perpendicular(p, a, b):
        (px, py), (ax, ay), (bx, by) = p, a, b
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
        t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        return ((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2) ** 0.5

    worst, index = 0.0, 0
    for i in range(1, len(points) - 1):
        d = perpendicular(points[i], points[0], points[-1])
        if d > worst:
            worst, index = d, i

    if worst <= tolerance:
        return [points[0], points[-1]]
    return (simplify(points[:index + 1], tolerance)[:-1]
            + simplify(points[index:], tolerance))


def main(paths):
    features = []
    for path in paths:
        features.extend(json.load(open(path))["features"])

    lons = [x for f in features for r in rings(f["geometry"]) for x, _ in r]
    lats = [y for f in features for r in rings(f["geometry"]) for _, y in r]
    west, east = min(lons), max(lons)
    south, north = min(lats), max(lats)

    # Equirectangular, with longitude squeezed by cos(mid-latitude) so the
    # state is not stretched sideways. Adequate for one state; anything more
    # would be pretending this is cartography.
    import math
    squeeze = math.cos(math.radians((south + north) / 2))
    span_x = (east - west) * squeeze
    span_y = north - south
    scale = (WIDTH - 2 * PADDING) / span_x
    height = round(span_y * scale + 2 * PADDING)

    def project(lon, lat):
        x = PADDING + (lon - west) * squeeze * scale
        y = PADDING + (north - lat) * scale
        return round(x, 1), round(y, 1)

    paths = []
    for feature in sorted(features, key=lambda f: (f["properties"]["STATE"],
                                                   f["properties"]["NAME"])):
        name = feature["properties"]["NAME"]
        state = feature["properties"]["STATE"]
        d = []
        for ring in rings(feature["geometry"]):
            ring = simplify([tuple(p[:2]) for p in ring], TOLERANCE)
            if len(ring) < 3:
                continue
            pts = [project(lon, lat) for lon, lat in ring]
            d.append("M" + "L".join(f"{x} {y}" for x, y in pts) + "Z")
        if d:
            paths.append(
                f'<path id="c-{slug(state, name)}" class="county" '
                f'data-name="{re.sub(r" County$", "", name)}, '
                f'{STATES.get(state, state).upper()}" d="{"".join(d)}"/>')

    print(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height}" '
          f'role="img" aria-label="Counties of the Carolinas">')
    print("<g>")
    print("\n".join(paths))
    print("</g>")
    print("</svg>")


if __name__ == "__main__":
    sys.setrecursionlimit(30000)
    main(sys.argv[1:])
