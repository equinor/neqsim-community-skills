from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from field_layout_import import FieldLayoutImporter


def main() -> None:
    importer = FieldLayoutImporter()

    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                "properties": {"name": "Host", "water_depth_m": 120.0, "kind": "host"},
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [8000.0, 1500.0]},
                "properties": {"name": "W1", "water_depth_m": 340.0, "kind": "well"},
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [6000.0, 1200.0]},
                "properties": {"name": "M1", "kind": "drilling-centre"},
            },
        ],
    }

    result = importer.from_geojson(geojson)
    print("Field layout import result")
    print(f"node_count={result.node_count}")
    for node in result.nodes:
        print(f"  {node.name}: ({node.x}, {node.y}) depth={node.water_depth_m} kind={node.kind}")
    print(f"issues={result.issues}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()
