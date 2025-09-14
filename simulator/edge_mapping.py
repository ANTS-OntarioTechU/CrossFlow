import math
import sumolib

def is_edge_for_cars(edge):
    etype = edge.getType()
    return etype and "highway" in etype and "footway" not in etype

def compute_bearing(x1, y1, x2, y2):
    angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
    return angle + 360 if angle < 0 else angle

def classify_direction(angle):
    if angle >= 315 or angle < 45:
        return 'east'
    elif angle < 135:
        return 'north'
    elif angle < 225:
        return 'west'
    else:
        return 'south'

def map_junction_edges(net, junction_id):
    try:
        junction = net.getNode(junction_id)
    except Exception as e:
        raise ValueError(f"Junction '{junction_id}' not found in network: {e}")
    
    mapping = {"incoming": {}, "outgoing": {}}
    
    for edge in junction.getIncoming():
        if not is_edge_for_cars(edge):
            continue
        from_node = edge.getFromNode()
        # REVERSED: calculate FROM junction TO edge start
        angle = compute_bearing(junction.getCoord()[0], junction.getCoord()[1],
                                from_node.getCoord()[0], from_node.getCoord()[1])
        direction = classify_direction(angle)
        mapping["incoming"].setdefault(direction, []).append(edge.getID())
    
    for edge in junction.getOutgoing():
        if not is_edge_for_cars(edge):
            continue
        to_node = edge.getToNode()
        angle = compute_bearing(junction.getCoord()[0], junction.getCoord()[1],
                                to_node.getCoord()[0], to_node.getCoord()[1])
        direction = classify_direction(angle)
        mapping["outgoing"].setdefault(direction, []).append(edge.getID())
    
    # DEBUG CODE
    print(f"\n=== DEBUG: Junction {junction_id} at {junction.getCoord()} ===")
    print("INCOMING EDGES:")
    for direction, edges in mapping["incoming"].items():
        for edge_id in edges:
            edge = net.getEdge(edge_id)
            from_node = edge.getFromNode()
            angle = compute_bearing(from_node.getCoord()[0], from_node.getCoord()[1],
                                    junction.getCoord()[0], junction.getCoord()[1])
            print(f"  {direction}: {edge_id} (angle: {angle:.1f}°)")
            print(f"    From: {from_node.getCoord()} -> To: {junction.getCoord()}")
    
    print("OUTGOING EDGES:")
    for direction, edges in mapping["outgoing"].items():
        for edge_id in edges:
            edge = net.getEdge(edge_id)
            to_node = edge.getToNode()
            angle = compute_bearing(junction.getCoord()[0], junction.getCoord()[1],
                                    to_node.getCoord()[0], to_node.getCoord()[1])
            print(f"  {direction}: {edge_id} (angle: {angle:.1f}°)")
            print(f"    From: {junction.getCoord()} -> To: {to_node.getCoord()}")
    
    return mapping

def find_intersection(net, target_lon, target_lat, tolerance=10.0):
    target_x, target_y = net.convertLonLat2XY(target_lon, target_lat)
    closest_node = None
    min_distance = float('inf')
    for node in net.getNodes():
        node_x, node_y = node.getCoord()
        distance = math.hypot(node_x - target_x, node_y - target_y)
        if distance < min_distance:
            min_distance = distance
            closest_node = node
    if closest_node is None:
        raise ValueError("No nodes found in the network.")
    if min_distance > tolerance:
        prompt = (f"Warning: Closest node (ID: {closest_node.getID()}) is {min_distance:.2f}m away "
                  f"(tolerance {tolerance}m). Proceed? (y/n): ")
        if input(prompt).strip().lower() != 'y':
            raise ValueError("User declined to proceed with out-of-tolerance intersection.")
    return closest_node.getID()
