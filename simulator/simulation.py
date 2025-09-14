import os
import csv
import json
import xml.etree.ElementTree as ET
from datetime import datetime
import sumolib
from . import database, edge_mapping, utils

def time_overlaps(intervals, sim_start, sim_end):
    """
    Returns True if the simulation window [sim_start, sim_end]
    overlaps with any interval in the intervals list.
    Each interval is a dict with "start" and "end" as strings.
    """
    for interval in intervals:
        try:
            interval_start = datetime.strptime(interval["start"], "%Y-%m-%d %H:%M:%S")
            interval_end = datetime.strptime(interval["end"], "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        if sim_start < interval_end and sim_end > interval_start:
            return True
    return False

def generate_flows_for_intersection(mapping, rows, intersection_id, simulation_start_dt, simulation_end_dt):
    flows = []
    incoming_mapping = {"n": "north", "s": "south", "e": "east", "w": "west"}
    outgoing_mapping = {
        "r": {"n": "west", "e": "north", "s": "east", "w": "south"},
        "t": {"n": "south", "e": "west", "s": "north", "w": "east"},
        "l": {"n": "east", "e": "south", "s": "west", "w": "north"}
    }
    ignore_keys = {
        "_id", "count_id", "count_date", "location_name", "longitude", "latitude", 
        "centreline_type", "centreline_id", "px", "start_time", "end_time"
    }
    
    for row in rows:
        try:
            row_start = datetime.fromisoformat(row["start_time"])
            row_end = datetime.fromisoformat(row["end_time"])
        except Exception:
            continue
        if row_start < simulation_start_dt or row_start >= simulation_end_dt:
            continue
        base_time = int((row_start - simulation_start_dt).total_seconds())
        duration = int((row_end - row_start).total_seconds())
        for key, value in row.items():
            if key in ignore_keys:
                continue
            parts = key.split("_")
            if len(parts) == 3:
                prefix, vehicle_str, movement = parts
            elif len(parts) == 4:
                prefix, appr, vehicle_str, movement = parts
                if appr.lower() != "appr":
                    continue
            else:
                continue
            if vehicle_str == "cars":
                vehicle = "car"
            elif vehicle_str in ("truck", "bus"):
                vehicle = vehicle_str
            else:
                continue
            try:
                count = int(value)
            except Exception:
                continue
            if count <= 0:
                continue
            from_dir = incoming_mapping.get(prefix.lower())
            to_dir = outgoing_mapping.get(movement.lower(), {}).get(prefix.lower())
            if not from_dir or not to_dir:
                continue
            if not mapping["incoming"].get(from_dir) or not mapping["outgoing"].get(to_dir):
                raise ValueError(
                    f"Incomplete edge mapping for key '{key}': "
                    f"missing incoming '{from_dir}' or outgoing '{to_dir}'."
                )
            from_edge = mapping["incoming"][from_dir][0]
            to_edge = mapping["outgoing"][to_dir][0]
            flow_id = f"{intersection_id}_{key}_{base_time}"
            flow_elem = ET.Element("flow", {
                "id": flow_id,
                "begin": str(base_time),
                "end": str(base_time + duration),
                "number": str(count),
                "from": from_edge,
                "to": to_edge,
                "type": vehicle
            })
            flows.append(flow_elem)
    return flows

def simulate_simulation(input_json_file, map_file, data_csv_file,
                       simulation_start_dt, simulation_end_dt,
                       output_folder, vehicle_params=None):
    """
    Generates the SUMO routes file and simulation details.
    
    :param input_json_file: Path to the intersections JSON file.
    :param map_file: Path to the SUMO network (map) file.
    :param data_csv_file: Path to the CSV file containing intersection data.
    :param simulation_start_dt: Simulation start datetime.
    :param simulation_end_dt: Simulation end datetime.
    :param output_folder: Folder in which to save the generated files.
    :param vehicle_params: Optional dictionary for vehicle parameters. For example:
           {
               "car": {
                   "carFollowModel": "Krauss",
                   "accel": "1.0",
                   "decel": "4.5",
                   "sigma": "0.5",
                   "length": "5",
                   "maxSpeed": "25"
               },
               "truck": {
                   ...
               },
               "bus": {
                   ...
               }
           }
           If not provided, default values are used.
    :return: Tuple (route_file, warnings)
    """
    from . import database  # ensure we import database inside function if needed

    # Load intersections from JSON
    try:
        intersections = utils.load_input_json(input_json_file)
    except Exception as e:
        raise RuntimeError(f"Error loading JSON: {e}")
    
    # Load SUMO network
    try:
        net = sumolib.net.readNet(map_file)
    except Exception as e:
        raise RuntimeError(f"Error reading map file '{map_file}': {e}")
    
    # Load processed DB
    processed_db = database.load_processed_db()

    # Use default parameters if none provided
    if vehicle_params is None:
        vehicle_params = {
            "car": {
                "carFollowModel": "Krauss", "accel": "1.0", "decel": "4.5",
                "sigma": "0.5", "length": "5",  "maxSpeed": "25"
            },
            "truck": {
                "carFollowModel": "Krauss", "accel": "0.8", "decel": "4.0",
                "sigma": "0.5", "length": "12", "maxSpeed": "20"
            },
            "bus": {
                "carFollowModel": "Krauss", "accel": "0.7", "decel": "4.0",
                "sigma": "0.5", "length": "12", "maxSpeed": "20"
            }
        }
    
    # Create the root element for routes
    routes_root = ET.Element("routes")
    # Create vehicle type definitions using vehicle_params
    for vtype, params in vehicle_params.items():
        ET.SubElement(routes_root, "vType", id=vtype, **params)
    
    incomplete_data = []
    simulation_details = []
    
    # Group CSV rows by centreline_id
    data_rows_by_id = {}
    try:
        with open(data_csv_file, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            if "centreline_id" not in reader.fieldnames:
                raise ValueError(f"CSV file '{data_csv_file}' is missing 'centreline_id' column.")
            if "start_time" not in reader.fieldnames:
                raise ValueError(f"CSV file '{data_csv_file}' is missing 'start_time' column.")
            for row in reader:
                key = str(row.get("centreline_id", "")).strip()
                if not key:
                    continue
                data_rows_by_id.setdefault(key, []).append(row)
    except Exception as e:
        raise RuntimeError(f"Error processing CSV file '{data_csv_file}': {e}")
    
    # Process each intersection from JSON
    for inter in intersections:
        location_name = inter.get("location_name", f"Intersection {inter.get('centreline_id')}")
        if "centreline_id" not in inter or not inter["centreline_id"]:
            incomplete_data.append(f"Intersection '{location_name}' skipped: Missing centreline_id.")
            continue
        unique_id = str(inter["centreline_id"]).strip()
        junction_id = None
        input_coords = None
        
        if "intersection_id" in inter and inter["intersection_id"]:
            junction_id = inter["intersection_id"]
        elif unique_id in data_rows_by_id and len(data_rows_by_id[unique_id]) > 0:
            try:
                first_row = data_rows_by_id[unique_id][0]
                target_lon = float(first_row["longitude"])
                target_lat = float(first_row["latitude"])
                input_coords = {"longitude": target_lon, "latitude": target_lat}
                try:
                    junction_id = edge_mapping.find_intersection(net, target_lon, target_lat)
                except Exception as ex:
                    incomplete_data.append(
                        f"Intersection '{location_name}' (ID: {unique_id}) skipped: "
                        f"Error in finding junction: {ex}"
                    )
                    continue
                if not junction_id:
                    incomplete_data.append(
                        f"Intersection '{location_name}' (ID: {unique_id}) skipped: Not located on map."
                    )
                    continue
            except Exception as e:
                incomplete_data.append(
                    f"Intersection '{location_name}' (ID: {unique_id}) skipped: Coordinates error: {e}"
                )
                continue
        else:
            incomplete_data.append(
                f"Intersection '{location_name}' (ID: {unique_id}) skipped: No CSV data available."
            )
            continue
        
        # Compute availability intervals
        intervals = []
        for row in data_rows_by_id.get(unique_id, []):
            try:
                st = datetime.fromisoformat(row["start_time"])
                et = datetime.fromisoformat(row["end_time"])
                intervals.append((st, et))
            except Exception:
                continue
        if not intervals:
            incomplete_data.append(
                f"Intersection '{location_name}' (ID: {unique_id}) skipped: No valid time data in CSV."
            )
            continue
        intervals.sort(key=lambda x: x[0])
        merged_intervals = []
        for st, et in intervals:
            if not merged_intervals:
                merged_intervals.append((st, et))
            else:
                last_st, last_et = merged_intervals[-1]
                if st <= last_et:
                    merged_intervals[-1] = (last_st, max(last_et, et))
                else:
                    merged_intervals.append((st, et))
        availability_intervals = [
            {
                "start": st.strftime("%Y-%m-%d %H:%M:%S"),
                "end": et.strftime("%Y-%m-%d %H:%M:%S")
            }
            for st, et in merged_intervals
        ]
        
        # Check overlap with simulation window
        if availability_intervals and not time_overlaps(
            availability_intervals, simulation_start_dt, simulation_end_dt
        ):
            incomplete_data.append(
                f"Intersection '{location_name}' (ID: {unique_id}) skipped: "
                f"Data not available for selected time window."
            )
            continue
        
        # Check or compute mapping
        if junction_id in processed_db:
            record = processed_db[junction_id]
            mapping = record.get("edge_mapping")
        else:
            if "mapped_edges" in inter and inter["mapped_edges"]:
                mapping = inter["mapped_edges"]
            else:
                try:
                    mapping = edge_mapping.map_junction_edges(net, junction_id)
                except Exception as e:
                    incomplete_data.append(
                        f"Intersection '{location_name}' (ID: {junction_id}) "
                        f"skipped: Mapping error: {e}"
                    )
                    continue
            try:
                junction_node = net.getNode(junction_id)
            except Exception as e:
                incomplete_data.append(
                    f"Intersection '{location_name}' (ID: {junction_id}) "
                    f"skipped: Node error: {e}"
                )
                continue
            record = {
                "intersection_id": junction_id,
                "centreline_id": unique_id,
                "location_name": location_name,
                "input_coordinates": input_coords,
                "network_coordinates": {
                    "x": junction_node.getCoord()[0],
                    "y": junction_node.getCoord()[1]
                },
                "data_availability": availability_intervals,
                "edge_mapping": mapping
            }
            database.update_processed_db(junction_id, record)
        
        intersection_rows = data_rows_by_id.get(unique_id, [])
        try:
            flows = generate_flows_for_intersection(
                mapping, intersection_rows, junction_id,
                simulation_start_dt, simulation_end_dt
            )
            if not flows:
                incomplete_data.append(
                    f"Intersection '{location_name}' (ID: {junction_id}) has no flows "
                    f"for the selected time window."
                )
                continue
            monitored_incoming = set()
            monitored_outgoing = set()
            incoming_directions = {}
            outgoing_directions = {}
            for flow in flows:
                incoming_edge = flow.get("from")
                outgoing_edge = flow.get("to")
                monitored_incoming.add(incoming_edge)
                monitored_outgoing.add(outgoing_edge)
                for direction, edges in mapping.get("incoming", {}).items():
                    if incoming_edge in edges:
                        incoming_directions[incoming_edge] = direction
                for direction, edges in mapping.get("outgoing", {}).items():
                    if outgoing_edge in edges:
                        outgoing_directions[outgoing_edge] = direction
                routes_root.append(flow)
            simulation_details.append({
                "intersection_id": junction_id,
                "centreline_id": unique_id,
                "location_name": location_name,
                "data_availability": availability_intervals,
                "simulation_start": simulation_start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "simulation_end": simulation_end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "monitored_incoming_edges": list(monitored_incoming),
                "monitored_outgoing_edges": list(monitored_outgoing),
                "incoming_edge_directions": incoming_directions,
                "outgoing_edge_directions": outgoing_directions
            })
        except Exception as e:
            incomplete_data.append(
                f"Intersection '{location_name}' (ID: {junction_id}) CSV processing error: {e}"
            )
            continue

    if len(routes_root.findall("flow")) > 0:
        route_file = os.path.join(output_folder, "routes.rou.xml")
        tree = ET.ElementTree(routes_root)
        tree.write(route_file, encoding="utf-8", xml_declaration=True)
        details_file = os.path.join(output_folder, "simulation_details.json")
        with open(details_file, "w") as f:
            json.dump(simulation_details, f, indent=4)
        return route_file, incomplete_data
    else:
        details_file = os.path.join(output_folder, "simulation_details.json")
        with open(details_file, "w") as f:
            json.dump({"warnings": incomplete_data}, f, indent=4)
        return None, incomplete_data

def generate_sumo_config(output_folder, map_file, route_file, sim_start, sim_end):
    """
    Generates the SUMO configuration file.
    """
    config = ET.Element("configuration")
    inp = ET.SubElement(config, "input")
    ET.SubElement(inp, "net-file", value=os.path.abspath(map_file))
    ET.SubElement(inp, "route-files", value=os.path.abspath(route_file))
    time_elem = ET.SubElement(config, "time")
    begin_sec = 0
    end_sec = int((sim_end - sim_start).total_seconds())
    ET.SubElement(time_elem, "begin", value=str(begin_sec))
    ET.SubElement(time_elem, "end", value=str(end_sec))
    config_file = os.path.join(output_folder, "simulation.sumocfg")
    tree = ET.ElementTree(config)
    tree.write(config_file, encoding="utf-8", xml_declaration=True)
    return config_file
