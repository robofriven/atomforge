from atomforge import AtomSpaceAPI
from atomforge.csv_import import import_links_csv


space = AtomSpaceAPI.create()

report = import_links_csv(space, "intersection_graph.csv")
print(f"Loaded {report.nodes_created} nodes")
print(f"Loaded {report.ligatures_created} ligatures")

# A and B are known to converge in the test graph.
a = space.find_by_label("A")[0]
b = space.find_by_label("B")[0]

print(f"\nA = {a}")
print(f"B = {b}")

intersections = space.intersection(
    [a, b],
    max_depth=6,
)

print("\nIntersections:")

for intersection in intersections:
    atom = space.get(intersection.atom_id)

    print(f"{atom.label} ({intersection.atom_id}) depths={intersection.depths}")
