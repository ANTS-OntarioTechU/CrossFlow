import sys
import csv
import json
import re
from datetime import datetime
import matplotlib.pyplot as plt
import traci

SUMO_CONFIG_FILE = "sumo_sim_20250326_202651/simulation.sumocfg"
SIM_DETAILS_FILE = "sumo_sim_20250326_202651/simulation_details.json"
DATA_CSV_FILE    = "input/TMC_data.csv"

# Regex to extract turning keys from vehicle IDs like:
#    "cluster_..._w_appr_bus_t_0" -> "w_appr_bus_t"
FLOW_KEY_PATTERN = re.compile(r'(?:n|s|e|w)_appr_[a-zA-Z]+(?:_[rlt])?')

def extract_turning_key(vehicle_id: str) -> str:
    """
    Attempt to find a turning key (e.g. 'n_appr_cars_r', 'w_appr_bus_t')
    in the vehicle/flow ID. Returns None if no match is found.
    """
    match = FLOW_KEY_PATTERN.search(vehicle_id)
    if match:
        return match.group(0)
    return None

def run_simulation_collect_vehicle_keys(sumo_config_file, sim_details):
    """
    Runs SUMO with the given config, collects vehicle IDs from the
    monitored edges, and extracts turning keys from each vehicle ID.
    
    Returns a dictionary:
        {
          intersection_id: {
              turning_key_str: set_of_vehicle_ids,
              ...
          },
          ...
        }
    """
    # Prepare data structure
    intersection_vehicle_data = {
        detail["intersection_id"]: {} for detail in sim_details
    }
    
    traci.start(["sumo", "-c", sumo_config_file])
    
    while traci.simulation.getMinExpectedNumber() > 0:
        traci.simulationStep()
        
        for detail in sim_details:
            inter_id = detail["intersection_id"]
            edges = detail.get("monitored_incoming_edges", []) + detail.get("monitored_outgoing_edges", [])
            
            for edge in edges:
                try:
                    vehicle_ids = traci.edge.getLastStepVehicleIDs(edge)
                except Exception:
                    # If edge doesn't exist or some other error occurs
                    continue
                
                for vid in vehicle_ids:
                    tkey = extract_turning_key(vid)
                    if not tkey:
                        continue
                    if tkey not in intersection_vehicle_data[inter_id]:
                        intersection_vehicle_data[inter_id][tkey] = set()
                    intersection_vehicle_data[inter_id][tkey].add(vid)
    
    traci.close()
    return intersection_vehicle_data

def aggregate_csv_counts_by_intersection(data_csv_file, sim_details):
    """
    Reads the CSV file and aggregates vehicle counts per intersection
    and per turning movement key (cars, trucks, etc.).
    Skips peds/bike columns entirely.
    """
    # Map centreline_id -> intersection_id
    centreline_map = {}
    for detail in sim_details:
        cid_json = str(detail["centreline_id"])
        centreline_map[cid_json] = detail["intersection_id"]

    # Build simulation time windows (optional, if you need to check times)
    sim_windows = {}
    for detail in sim_details:
        inter_id = detail["intersection_id"]
        try:
            sim_start = datetime.strptime(detail["simulation_start"], "%Y-%m-%d %H:%M:%S")
            sim_end   = datetime.strptime(detail["simulation_end"],   "%Y-%m-%d %H:%M:%S")
        except (KeyError, ValueError):
            sim_start, sim_end = None, None
        sim_windows[inter_id] = (sim_start, sim_end)

    csv_counts = {}

    with open(data_csv_file, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            # Match centreline_id in CSV to intersection_id from JSON
            row_cid = row.get("centreline_id", "").strip()
            if row_cid not in centreline_map:
                continue

            inter_id = centreline_map[row_cid]
            sim_start, sim_end = sim_windows.get(inter_id, (None, None))

            # Optional check: only include rows that fall within a known time window
            if sim_start and sim_end:
                try:
                    row_time = datetime.strptime(row["start_time"], "%Y-%m-%dT%H:%M:%S")
                except (KeyError, ValueError):
                    continue
                if row_time < sim_start or row_time >= sim_end:
                    continue

            # Initialize dictionary if needed
            if inter_id not in csv_counts:
                csv_counts[inter_id] = {}

            # Loop over each column in the row
            for key, val in row.items():
                # Skip metadata columns
                if key in (
                    "_id", "count_id", "count_date", "location_name", "longitude",
                    "latitude", "centreline_type", "centreline_id", "px",
                    "start_time", "end_time"
                ):
                    continue

                # Skip all peds / bike columns
                if "peds" in key or "bike" in key:
                    continue

                # Otherwise, treat this as a valid turning-movement count
                try:
                    count_val = int(val)
                except ValueError:
                    count_val = 0

                csv_counts[inter_id][key] = csv_counts[inter_id].get(key, 0) + count_val

    return csv_counts

def validate_simulation():
    # Read the simulation details
    with open(SIM_DETAILS_FILE, "r") as f:
        sim_details = json.load(f)
    
    # Collect the actual vehicles (by turning key) from simulation
    sim_vehicle_data = run_simulation_collect_vehicle_keys(SUMO_CONFIG_FILE, sim_details)
    
    # Collect CSV data aggregated by intersection & turning key
    csv_counts = aggregate_csv_counts_by_intersection(DATA_CSV_FILE, sim_details)
    
    # Compare
    report = []
    for detail in sim_details:
        inter_id = detail["intersection_id"]
        
        # from simulation
        sim_breakdown = {}
        for tkey, vehicle_ids in sim_vehicle_data.get(inter_id, {}).items():
            sim_breakdown[tkey] = len(vehicle_ids)
        
        # from CSV
        csv_breakdown = csv_counts.get(inter_id, {})
        
        all_keys = set(sim_breakdown.keys()) | set(csv_breakdown.keys())
        
        comparison = {}
        for k in all_keys:
            sim_val = sim_breakdown.get(k, 0)
            csv_val = csv_breakdown.get(k, 0)
            comparison[k] = {
                "simulation": sim_val,
                "csv": csv_val,
                "difference": sim_val - csv_val
            }
        
        report.append({
            "intersection_id": inter_id,
            "centreline_id": detail["centreline_id"],
            "comparison": comparison
        })
    
    return report

def plot_comparison_chart(report):
    """
    Plots a simple bar chart comparing simulation vs CSV for each intersection.
    """
    for item in report:
        inter_id = item["intersection_id"]
        comp     = item["comparison"]
        
        keys = sorted(comp.keys())
        sim_vals = [comp[k]["simulation"] for k in keys]
        csv_vals = [comp[k]["csv"] for k in keys]
        
        x = range(len(keys))
        width = 0.35
        
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.bar([xi - width/2 for xi in x], sim_vals, width, label="Simulation")
        ax.bar([xi + width/2 for xi in x], csv_vals, width, label="CSV Data")
        
        ax.set_title(f"Intersection ID: {inter_id}")
        ax.set_xlabel("Turning Movement Data")
        ax.set_ylabel("Count")
        ax.set_xticks(list(x))
        ax.set_xticklabels(keys, rotation=45, ha="right")
        
        ax.legend()
        plt.tight_layout()
        plt.show()

if __name__ == "__main__":
    report = validate_simulation()
    
    print("Validation Report:")
    for row in report:
        print(f"Intersection: {row['intersection_id']} (centreline_id={row['centreline_id']})")
        for k, vals in row["comparison"].items():
            print(f"  {k} => simulation={vals['simulation']} csv={vals['csv']} diff={vals['difference']}")
    
    plot_comparison_chart(report)
