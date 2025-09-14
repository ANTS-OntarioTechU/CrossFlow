import os
import csv
import json
from datetime import datetime

def load_input_json(filename):
    try:
        with open(filename, "r") as f:
            data = json.load(f)
        if isinstance(data, dict):
            if "intersections" in data:
                intersections = data["intersections"]
                if not isinstance(intersections, list):
                    raise ValueError("'intersections' must be a list.")
                return intersections
            else:
                return [data]
        elif isinstance(data, list):
            return data
        else:
            raise ValueError("Input JSON must be an object or list of intersections.")
    except Exception as e:
        raise RuntimeError(f"Error loading input JSON file '{filename}': {e}")

def get_overall_time_range(json_file, data_csv_file):
    intersections = load_input_json(json_file)
    valid_ids = {str(inter["centreline_id"]).strip() for inter in intersections if "centreline_id" in inter and inter["centreline_id"]}
    overall_min = None
    overall_max = None
    with open(data_csv_file, newline="") as f:
        reader = csv.DictReader(f)
        if "start_time" not in reader.fieldnames:
            raise ValueError(f"CSV file '{data_csv_file}' is missing 'start_time' column.")
        if "centreline_id" not in reader.fieldnames:
            raise ValueError(f"CSV file '{data_csv_file}' is missing 'centreline_id' column.")
        for row in reader:
            key = str(row.get("centreline_id", "")).strip()
            if key not in valid_ids:
                continue
            try:
                dt = datetime.fromisoformat(row["start_time"])
            except Exception:
                continue
            if overall_min is None or dt < overall_min:
                overall_min = dt
            if overall_max is None or dt > overall_max:
                overall_max = dt
    if overall_min is None or overall_max is None:
        raise ValueError("Could not determine overall time range from traffic data.")
    return overall_min, overall_max

def get_data_availability_by_intersection(json_file, data_csv_file):
    import csv
    from datetime import datetime
    intersections = load_input_json(json_file)
    valid_ids = {str(inter["centreline_id"]).strip() for inter in intersections if "centreline_id" in inter and inter["centreline_id"]}
    availability = {vid: [] for vid in valid_ids}
    with open(data_csv_file, newline="") as f:
        reader = csv.DictReader(f)
        if "start_time" not in reader.fieldnames or "centreline_id" not in reader.fieldnames:
            raise ValueError("CSV file is missing required columns.")
        for row in reader:
            key = str(row.get("centreline_id", "")).strip()
            if key not in valid_ids:
                continue
            try:
                st = datetime.fromisoformat(row["start_time"])
                et = datetime.fromisoformat(row["end_time"])
            except Exception:
                continue
            availability[key].append((st, et))
    result = {}
    for vid, intervals in availability.items():
        if not intervals:
            continue
        intervals.sort(key=lambda x: x[0])
        merged = []
        for interval in intervals:
            if not merged:
                merged.append(interval)
            else:
                last = merged[-1]
                if interval[0] <= last[1]:
                    merged[-1] = (last[0], max(last[1], interval[1]))
                else:
                    merged.append(interval)
        result[vid] = [{"start": i[0].strftime("%Y-%m-%d %H:%M:%S"), "end": i[1].strftime("%Y-%m-%d %H:%M:%S")} for i in merged]
    return result
