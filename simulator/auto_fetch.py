import os
import math
import requests
import subprocess
from datetime import datetime

def download_osm_data(coordinates, radius_km=5, osm_output=None):
    """
    Download OSM data for an area covering all given coordinates with a buffer.
    
    Args:
        coordinates: List of (lat, lon) tuples.
        radius_km: Buffer distance in kilometers.
        osm_output: Output file path for the OSM file; if None, a filename is generated with a timestamp.
    
    Returns:
        Path to the downloaded OSM file.
    """
    if not coordinates:
        raise ValueError("No coordinates provided for OSM data download.")
    
    # Compute bounding box
    min_lat = min(lat for lat, _ in coordinates)
    max_lat = max(lat for lat, _ in coordinates)
    min_lon = min(lon for _, lon in coordinates)
    max_lon = max(lon for _, lon in coordinates)
    
    # Buffer: approximately 1 degree latitude ~ 111 km
    lat_offset = radius_km / 111.0  
    avg_lat = (min_lat + max_lat) / 2.0
    lon_offset = radius_km / (111.0 * math.cos(math.radians(avg_lat)))
    
    min_lat -= lat_offset
    max_lat += lat_offset
    min_lon -= lon_offset
    max_lon += lon_offset
    
    overpass_url = "https://overpass-api.de/api/interpreter"
    overpass_query = f"""
    [out:xml];
    (
      way["highway"]({min_lat},{min_lon},{max_lat},{max_lon});
      relation["highway"]({min_lat},{min_lon},{max_lat},{max_lon});
    );
    (._;>;);
    out body;
    """
    
    response = requests.post(overpass_url, data=overpass_query)
    response.raise_for_status()
    
    if osm_output is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        osm_output = os.path.join("data", f"map_area_{timestamp}.osm")
    os.makedirs(os.path.dirname(osm_output), exist_ok=True)
    
    with open(osm_output, "w", encoding="utf-8") as f:
        f.write(response.text)
    
    return osm_output

def convert_to_sumo_network(osm_file, net_output=None):
    """
    Convert an OSM file to a SUMO network using netconvert.
    
    Args:
        osm_file: Path to the OSM file.
        net_output: Output path for the SUMO network file; if None, a filename is generated with a timestamp.
    
    Returns:
        Path to the generated SUMO network file.
    """
    if net_output is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        net_output = os.path.join("data", f"auto_fetched_network_{timestamp}.net.xml")
    os.makedirs(os.path.dirname(net_output), exist_ok=True)
    
    subprocess.run([
        "netconvert",
        "--osm-files", osm_file,
        "--output", net_output,
        "--geometry.remove",
        "--roundabouts.guess",
        "--ramps.guess",
        "--junctions.join",
        "--tls.guess-signals",
        "--tls.discard-simple",
        "--tls.join"
    ], check=True)
    
    return net_output

def fetch_map_for_intersections(coordinates, data_folder="data", radius_km=2):
    """
    High-level function to fetch OSM data for the given coordinates and convert it to a SUMO network.
    
    Args:
        coordinates: List of (lat, lon) tuples.
        data_folder: Folder to save the downloaded files.
        radius_km: Buffer radius in kilometers.
    
    Returns:
        Path to the generated SUMO network file.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    osm_output = os.path.join(data_folder, f"map_area_{timestamp}.osm")
    net_output = os.path.join(data_folder, f"auto_fetched_network_{timestamp}.net.xml")
    
    downloaded_osm = download_osm_data(coordinates, radius_km=radius_km, osm_output=osm_output)
    sumo_net = convert_to_sumo_network(downloaded_osm, net_output=net_output)
    return sumo_net

def fetch_csv_data(data_folder="data"):
    """
    Fetch the CSV data from the CKAN API for traffic volumes.
    
    Returns:
        Path to the saved CSV file.
    """
    base_url = "https://ckan0.cf.opendata.inter.prod-toronto.ca"
    package_url = base_url + "/api/3/action/package_show"
    params = {"id": "traffic-volumes-at-intersections-for-all-modes"}
    
    package = requests.get(package_url, params=params).json()
    
    for resource in package["result"]["resources"]:
        if resource["name"] == "tmc_raw_data_2020_2029":
            if resource["datastore_active"]:
                dump_url = base_url + "/datastore/dump/" + resource["id"]
                csv_data = requests.get(dump_url).text
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"tmc_raw_data_2020_2029_{timestamp}.csv"
                file_path = os.path.join(data_folder, filename)
                os.makedirs(data_folder, exist_ok=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(csv_data)
                return file_path
            else:
                raise RuntimeError("Resource is not datastore_active. Please download manually.")
    raise RuntimeError("Resource 'tmc_raw_data_2020_2029' not found in the package.")
