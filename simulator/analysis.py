# simulator/analysis.py
import os
import csv
import logging
from datetime import datetime
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.DEBUG)

def load_intersection_data(local_intersection_name, csv_folder="input"):
    """Load CSV data for an intersection as a pandas DataFrame.
       CSV file is expected to be named <local_intersection_name>.csv in csv_folder.
    """
    csv_file = os.path.join(csv_folder, f"{local_intersection_name}.csv")
    logging.debug(f"Loading data from {csv_file}")
    try:
        df = pd.read_csv(csv_file)
        # Convert datetime_bin column to datetime objects.
        if "datetime_bin" in df.columns:
            df["datetime_bin"] = pd.to_datetime(df["datetime_bin"], format="%Y-%m-%d %H:%M:%S", errors='coerce')
        return df
    except Exception as e:
        logging.error(f"Error loading CSV for {local_intersection_name}: {e}")
        raise

def compute_traffic_metrics(df):
    """Compute traffic metrics from DataFrame.
       Traffic columns are those starting with 'traffic_'.
       Returns a dict with average per lane and overall average.
    """
    traffic_cols = [col for col in df.columns if col.startswith("traffic_")]
    if not traffic_cols:
        raise ValueError("No traffic columns found in data.")
    metrics = {}
    for col in traffic_cols:
        metrics[col] = df[col].mean()
    metrics["total_traffic_avg"] = df[traffic_cols].sum(axis=1).mean()
    return metrics

def compute_weather_traffic_correlation(df, weather_metric="humidity"):
    """Compute Pearson correlation between total traffic and a given weather metric.
    """
    traffic_cols = [col for col in df.columns if col.startswith("traffic_")]
    if weather_metric not in df.columns:
        raise ValueError(f"Weather metric '{weather_metric}' not found in data.")
    total_traffic = df[traffic_cols].sum(axis=1)
    correlation = total_traffic.corr(df[weather_metric])
    return correlation

def get_data_in_timeframe(df, start_dt, end_dt):
    """Filter the DataFrame for rows where datetime_bin is between start_dt (inclusive) and end_dt (exclusive)."""
    if "datetime_bin" not in df.columns:
        raise ValueError("datetime_bin column missing in data.")
    filtered = df[(df["datetime_bin"] >= start_dt) & (df["datetime_bin"] < end_dt)]
    return filtered

def analyze_intersection(local_intersection_name, start_dt, end_dt, csv_folder="input", weather_metric="humidity"):
    """Load data for a given intersection, filter it by time, and compute metrics.
       Returns a dict with:
         - local_intersection_name
         - traffic_metrics (averages for each lane and overall)
         - weather_traffic_correlation (correlation coefficient between total traffic and the weather metric)
         - missing_data (True if no data exists in the timeframe)
    """
    logging.debug(f"Analyzing intersection: {local_intersection_name} for timeframe {start_dt} to {end_dt}")
    df = load_intersection_data(local_intersection_name, csv_folder)
    filtered = get_data_in_timeframe(df, start_dt, end_dt)
    missing_data = filtered.empty
    metrics = {}
    correlation = None
    if not missing_data:
        metrics = compute_traffic_metrics(filtered)
        try:
            correlation = compute_weather_traffic_correlation(filtered, weather_metric)
        except Exception as e:
            logging.error(f"Error computing correlation for {local_intersection_name}: {e}")
            correlation = None
    else:
        logging.warning(f"Data missing for {local_intersection_name} in the selected timeframe.")
    return {
        "local_intersection_name": local_intersection_name,
        "traffic_metrics": metrics,
        "weather_traffic_correlation": correlation,
        "missing_data": missing_data
    }
