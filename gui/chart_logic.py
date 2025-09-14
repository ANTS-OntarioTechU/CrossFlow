# gui/chart_logic.py
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from simulator import analysis
import logging

logging.basicConfig(level=logging.DEBUG)

# Mapping of friendly weather metric names to actual column names.
METRIC_MAP = {
    "Temperature": "temp",
    "Visibility": "visibility",
    "Dew Point": "dew_point",
    "Humidity": "humidity",
    "Wind Speed": "wind_speed",
    "Weather": "weather_main_encoded",
    "Weekend/Holiday": "is_weekend-holiday"
}

# List of friendly weather metric names.
WEATHER_METRICS = list(METRIC_MAP.keys())

def get_df(inter_name, start_dt, end_dt):
    """Helper function to load and filter data for a given intersection."""
    try:
        df = analysis.load_intersection_data(inter_name)
        return analysis.get_data_in_timeframe(df, start_dt, end_dt)
    except Exception as e:
        logging.error(f"Error loading data for {inter_name}: {e}")
        raise

def generate_chart(analysis_results, mode, chart_type, variant, start_dt, end_dt, weather_metric):
    """
    Generates and returns an HTML string (via Plotly's to_html) for the chart.
    
    Parameters:
      - analysis_results: list of analysis dicts.
      - mode: one of "single", "single_metric", "multi", "multi_metric".
      - chart_type: selected chart type (friendly name).
      - variant: "Lane-specific" or "Total Traffic".
      - start_dt, end_dt: datetime objects.
      - weather_metric: actual column name (if applicable).
      
    For charts that have a datetime x-axis, a range slider is added.
    """
    try:
        if mode in ["single", "single_metric"]:
            inter_name = analysis_results[0]["local_intersection_name"]
            df = get_df(inter_name, start_dt, end_dt)
            if df.empty:
                fig = go.Figure()
                fig.add_annotation(text="No data in selected timeframe", x=0.5, y=0.5, showarrow=False)
                return fig.to_html(full_html=True, include_plotlyjs='cdn')
            traffic_cols = [col for col in df.columns if col.startswith("traffic_")]
            if variant == "Total Traffic":
                df["Total Traffic"] = df[traffic_cols].sum(axis=1)
            if mode == "single":
                # Non-metric mode.
                if chart_type == "Time Series":
                    fig = go.Figure()
                    if variant == "Lane-specific":
                        for col in traffic_cols:
                            fig.add_trace(go.Scatter(x=df["datetime_bin"], y=df[col], mode='lines', name=col))
                    else:
                        fig.add_trace(go.Scatter(x=df["datetime_bin"], y=df["Total Traffic"], mode='lines', name="Total Traffic"))
                    fig.update_layout(title=f"Time Series for {inter_name}",
                                      xaxis_title="Time", yaxis_title="Vehicle Count")
                elif chart_type == "Histogram":
                    fig = go.Figure()
                    if variant == "Lane-specific":
                        for col in traffic_cols:
                            fig.add_trace(go.Histogram(x=df[col].dropna(), name=col, opacity=0.6))
                    else:
                        fig.add_trace(go.Histogram(x=df["Total Traffic"].dropna(), name="Total Traffic", opacity=0.6))
                    fig.update_layout(title=f"Histogram for {inter_name}",
                                      xaxis_title="Vehicle Count", barmode='overlay')
                elif chart_type == "Box Plot":
                    fig = go.Figure()
                    if variant == "Lane-specific":
                        for col in traffic_cols:
                            fig.add_trace(go.Box(y=df[col].dropna(), name=col))
                    else:
                        fig.add_trace(go.Box(y=df["Total Traffic"].dropna(), name="Total Traffic"))
                    fig.update_layout(title=f"Box Plot for {inter_name}", yaxis_title="Vehicle Count")
                elif chart_type == "Peak Traffic by Time of Day":
                    df["Hour"] = pd.to_datetime(df["datetime_bin"]).dt.hour
                    fig = go.Figure()
                    if variant == "Lane-specific":
                        for col in traffic_cols:
                            peak = df.groupby("Hour")[col].mean().reset_index()
                            fig.add_trace(go.Scatter(x=peak["Hour"], y=peak[col], mode='lines+markers', name=col))
                    else:
                        peak = df.groupby("Hour")["Total Traffic"].mean().reset_index()
                        fig.add_trace(go.Scatter(x=peak["Hour"], y=peak["Total Traffic"], mode='lines+markers', name="Total Traffic"))
                    fig.update_layout(title=f"Peak Traffic by Hour for {inter_name}",
                                      xaxis_title="Hour", yaxis_title="Average Traffic")
                elif chart_type == "Peak Traffic by Day of Week":
                    df["DayOfWeek"] = pd.to_datetime(df["datetime_bin"]).dt.dayofweek
                    fig = go.Figure()
                    if variant == "Lane-specific":
                        for col in traffic_cols:
                            peak = df.groupby("DayOfWeek")[col].mean().reset_index()
                            fig.add_trace(go.Scatter(x=peak["DayOfWeek"], y=peak[col], mode='lines+markers', name=col))
                    else:
                        peak = df.groupby("DayOfWeek")["Total Traffic"].mean().reset_index()
                        fig.add_trace(go.Scatter(x=peak["DayOfWeek"], y=peak["Total Traffic"], mode='lines+markers', name="Total Traffic"))
                    fig.update_layout(title=f"Peak Traffic by Day of Week for {inter_name}",
                                      xaxis_title="Day of Week (0=Monday)", yaxis_title="Average Traffic")
                elif chart_type == "Holiday/Weekend Impact":
                    if "is_weekend-holiday" not in df.columns:
                        fig = go.Figure()
                        fig.add_annotation(text="Weekend/Holiday indicator missing", x=0.5, y=0.5, showarrow=False)
                    else:
                        fig = go.Figure()
                        if variant == "Lane-specific":
                            for col in traffic_cols:
                                avg = df.groupby("is_weekend-holiday")[col].mean().reset_index()
                                fig.add_trace(go.Scatter(x=avg["is_weekend-holiday"], y=avg[col], mode='lines+markers', name=col))
                        else:
                            avg = df.groupby("is_weekend-holiday")["Total Traffic"].mean().reset_index()
                            fig.add_trace(go.Scatter(x=avg["is_weekend-holiday"], y=avg["Total Traffic"], mode='lines+markers', name="Total Traffic"))
                        fig.update_layout(title=f"Holiday/Weekend Impact for {inter_name}",
                                          xaxis_title="Weekend/Holiday Indicator", yaxis_title="Average Traffic")
                else:
                    fig = go.Figure()
                    fig.add_annotation(text="Chart type not recognized", x=0.5, y=0.5, showarrow=False)
                # For time-series charts, add a date range slider.
                if chart_type in ["Time Series"]:
                    fig.update_layout(xaxis=dict(rangeslider=dict(visible=True), type="date"))
                return fig.to_html(full_html=True, include_plotlyjs='cdn')
        
        elif mode == "single_metric":
            inter_name = analysis_results[0]["local_intersection_name"]
            df = get_df(inter_name, start_dt, end_dt)
            if df.empty:
                fig = go.Figure()
                fig.add_annotation(text="No data in selected timeframe", x=0.5, y=0.5, showarrow=False)
                return fig.to_html(full_html=True, include_plotlyjs='cdn')
            traffic_cols = [col for col in df.columns if col.startswith("traffic_")]
            if variant == "Total Traffic":
                df["Total Traffic"] = df[traffic_cols].sum(axis=1)
            if chart_type == "Dual-Axis Time Series":
                fig = go.Figure()
                if variant == "Lane-specific":
                    for col in traffic_cols:
                        fig.add_trace(go.Scatter(x=df["datetime_bin"], y=df[col], mode='lines', name=col))
                else:
                    fig.add_trace(go.Scatter(x=df["datetime_bin"], y=df["Total Traffic"], mode='lines', name="Total Traffic"))
                if weather_metric in df.columns:
                    fig.add_trace(go.Scatter(x=df["datetime_bin"], y=df[weather_metric], mode='lines', name=weather_metric, yaxis="y2"))
                    fig.update_layout(yaxis2=dict(title=weather_metric, overlaying="y", side="right"))
                fig.update_layout(title=f"Traffic and {weather_metric} for {inter_name}",
                                  xaxis_title="Time", yaxis_title="Traffic")
                if "datetime_bin" in df.columns:
                    fig.update_layout(xaxis=dict(rangeslider=dict(visible=True), type="date"))
                return fig.to_html(full_html=True, include_plotlyjs='cdn')
            elif chart_type == "Scatter Plot (Traffic vs. Weather)":
                fig = go.Figure()
                if variant == "Lane-specific":
                    total_traffic = df[traffic_cols].sum(axis=1)
                else:
                    total_traffic = df["Total Traffic"]
                if weather_metric in df.columns:
                    fig.add_trace(go.Scatter(x=total_traffic, y=df[weather_metric], mode='markers', name="Traffic vs. Weather"))
                    fig.update_layout(title=f"Traffic vs. {weather_metric} for {inter_name}",
                                      xaxis_title="Traffic", yaxis_title=weather_metric)
                else:
                    fig.add_annotation(text=f"{weather_metric} data missing", x=0.5, y=0.5, showarrow=False)
                return fig.to_html(full_html=True, include_plotlyjs='cdn')
            elif chart_type == "Correlation Heatmap":
                if weather_metric in df.columns:
                    cols = traffic_cols + [weather_metric] if variant == "Lane-specific" else ["Total Traffic", weather_metric]
                    data = df[cols].dropna()
                    corr = data.corr()
                    fig = go.Figure(data=go.Heatmap(z=corr.values, x=corr.columns, y=corr.index, colorscale='Viridis'))
                    fig.update_layout(title=f"Correlation Heatmap for {inter_name}")
                    return fig.to_html(full_html=True, include_plotlyjs='cdn')
                else:
                    fig = go.Figure()
                    fig.add_annotation(text=f"{weather_metric} data missing", x=0.5, y=0.5, showarrow=False)
                    return fig.to_html(full_html=True, include_plotlyjs='cdn')
            elif chart_type == "Peak Traffic & Weather Analysis":
                df["Hour"] = pd.to_datetime(df["datetime_bin"]).dt.hour
                fig = go.Figure()
                if variant == "Lane-specific":
                    for col in traffic_cols:
                        peak = df.groupby("Hour")[col].mean().reset_index()
                        fig.add_trace(go.Scatter(x=peak["Hour"], y=peak[col], mode='lines+markers', name=col))
                else:
                    peak = df.groupby("Hour")["Total Traffic"].mean().reset_index()
                    fig.add_trace(go.Scatter(x=peak["Hour"], y=peak["Total Traffic"], mode='lines+markers', name="Total Traffic"))
                if weather_metric in df.columns:
                    fig.add_trace(go.Scatter(x=df["datetime_bin"], y=df[weather_metric], mode='lines', name=weather_metric, yaxis="y2"))
                    fig.update_layout(yaxis2=dict(title=weather_metric, overlaying="y", side="right"))
                fig.update_layout(title=f"Peak Traffic & {weather_metric} for {inter_name}",
                                  xaxis_title="Hour", yaxis_title="Average Traffic")
                return fig.to_html(full_html=True, include_plotlyjs='cdn')
            else:
                fig = go.Figure()
                fig.add_annotation(text="Chart type not recognized", x=0.5, y=0.5, showarrow=False)
                return fig.to_html(full_html=True, include_plotlyjs='cdn')
        elif mode == "multi":
            if chart_type == "Bar Chart (Average Traffic)":
                if variant == "Lane-specific":
                    data = {}
                    for res in analysis_results:
                        inter = res["local_intersection_name"]
                        df = get_df(inter, start_dt, end_dt)
                        traffic_cols = [col for col in df.columns if col.startswith("traffic_")]
                        avgs = df[traffic_cols].mean().to_dict()
                        data[inter] = avgs
                    fig = go.Figure()
                    if data:
                        lanes = list(next(iter(data.values())).keys())
                        width = 0.8 / len(data)
                        x = list(range(len(lanes)))
                        for i, (inter, avgs) in enumerate(data.items()):
                            fig.add_trace(go.Bar(x=[xi + i * width for xi in x], y=[avgs[lane] for lane in lanes],
                                                   name=inter, width=width))
                        fig.update_layout(title="Lane-specific Average Traffic per Intersection",
                                          xaxis_title="Lane", yaxis_title="Average Traffic",
                                          barmode='group',
                                          xaxis=dict(tickmode='array',
                                                     tickvals=[xi + width*(len(data)-1)/2 for xi in x],
                                                     ticktext=lanes))
                    else:
                        fig = go.Figure()
                        fig.add_annotation(text="No data available", x=0.5, y=0.5, showarrow=False)
                    return fig.to_html(full_html=True, include_plotlyjs='cdn')
                else:
                    intersections = []
                    totals = []
                    for res in analysis_results:
                        inter = res["local_intersection_name"]
                        df = get_df(inter, start_dt, end_dt)
                        traffic_cols = [col for col in df.columns if col.startswith("traffic_")]
                        total_avg = df[traffic_cols].sum(axis=1).mean()
                        intersections.append(inter)
                        totals.append(total_avg)
                    fig = go.Figure(go.Bar(x=intersections, y=totals, marker_color='blue'))
                    fig.update_layout(title="Average Total Traffic per Intersection",
                                      xaxis_title="Intersection", yaxis_title="Average Traffic")
                    return fig.to_html(full_html=True, include_plotlyjs='cdn')
            elif chart_type == "Box Plot Comparison":
                data = {}
                for res in analysis_results:
                    inter = res["local_intersection_name"]
                    df = get_df(inter, start_dt, end_dt)
                    traffic_cols = [col for col in df.columns if col.startswith("traffic_")]
                    if variant == "Lane-specific":
                        data[inter] = [df[col].dropna() for col in traffic_cols]
                    else:
                        df["Total Traffic"] = df[traffic_cols].sum(axis=1)
                        data[inter] = df["Total Traffic"].dropna()
                fig = go.Figure()
                if data:
                    labels = list(data.keys())
                    if variant == "Lane-specific":
                        for inter in labels:
                            combined = pd.concat(data[inter])
                            fig.add_trace(go.Box(y=combined, name=inter))
                        fig.update_layout(title="Combined Lane Traffic Distribution per Intersection", yaxis_title="Traffic")
                    else:
                        for inter in labels:
                            fig.add_trace(go.Box(y=data[inter], name=inter))
                        fig.update_layout(title="Total Traffic Distribution per Intersection", yaxis_title="Traffic")
                    return fig.to_html(full_html=True, include_plotlyjs='cdn')
                else:
                    fig = go.Figure()
                    fig.add_annotation(text="No data available for box plot", x=0.5, y=0.5, showarrow=False)
                    return fig.to_html(full_html=True, include_plotlyjs='cdn')
            elif chart_type == "Line Chart Overlay":
                fig = go.Figure()
                for res in analysis_results:
                    inter = res["local_intersection_name"]
                    df = get_df(inter, start_dt, end_dt)
                    traffic_cols = [col for col in df.columns if col.startswith("traffic_")]
                    if variant == "Lane-specific":
                        for col in traffic_cols:
                            fig.add_trace(go.Scatter(x=df["datetime_bin"], y=df[col], mode='lines', name=f"{inter}:{col}"))
                    else:
                        df["Total Traffic"] = df[traffic_cols].sum(axis=1)
                        fig.add_trace(go.Scatter(x=df["datetime_bin"], y=df["Total Traffic"], mode='lines', name=inter))
                fig.update_layout(title="Traffic Time Series Overlay", xaxis_title="Time", yaxis_title="Traffic")
                return fig.to_html(full_html=True, include_plotlyjs='cdn')
            elif chart_type == "Peak Traffic Comparison":
                fig = go.Figure()
                for res in analysis_results:
                    inter = res["local_intersection_name"]
                    df = get_df(inter, start_dt, end_dt)
                    df["Hour"] = pd.to_datetime(df["datetime_bin"]).dt.hour
                    traffic_cols = [col for col in df.columns if col.startswith("traffic_")]
                    if variant == "Lane-specific":
                        for col in traffic_cols:
                            peak = df.groupby("Hour")[col].mean().reset_index()
                            fig.add_trace(go.Scatter(x=peak["Hour"], y=peak[col], mode='lines+markers', name=f"{inter}:{col}"))
                    else:
                        df["Total Traffic"] = df[traffic_cols].sum(axis=1)
                        peak = df.groupby("Hour")["Total Traffic"].mean().reset_index()
                        fig.add_trace(go.Scatter(x=peak["Hour"], y=peak["Total Traffic"], mode='lines+markers', name=inter))
                fig.update_layout(title="Peak Traffic Comparison by Hour", xaxis_title="Hour", yaxis_title="Average Traffic")
                return fig.to_html(full_html=True, include_plotlyjs='cdn')
            else:
                fig = go.Figure()
                fig.add_annotation(text="Chart type not recognized", x=0.5, y=0.5, showarrow=False)
                return fig.to_html(full_html=True, include_plotlyjs='cdn')
        elif mode == "multi_metric":
            if chart_type == "Bar Chart (Correlation)":
                intersections = [res["local_intersection_name"] for res in analysis_results]
                correlations = []
                for res in analysis_results:
                    corr = res.get("weather_traffic_correlation")
                    correlations.append(corr if corr is not None else 0)
                fig = go.Figure(go.Bar(x=intersections, y=correlations, marker_color='green'))
                fig.update_layout(title="Correlation (Traffic vs. Selected Weather) per Intersection",
                                  xaxis_title="Intersection", yaxis_title="Correlation Coefficient")
                return fig.to_html(full_html=True, include_plotlyjs='cdn')
            elif chart_type == "Scatter Matrix":
                all_data = []
                for res in analysis_results:
                    inter = res["local_intersection_name"]
                    df = get_df(inter, start_dt, end_dt)
                    traffic_cols = [col for col in df.columns if col.startswith("traffic_")]
                    if weather_metric in df.columns and not df.empty:
                        if variant == "Lane-specific":
                            total = df[traffic_cols]
                        else:
                            total = df[traffic_cols].sum(axis=1)
                        combined = pd.DataFrame({
                            "Traffic": total if isinstance(total, pd.Series) else total.sum(axis=1),
                            "Weather": df[weather_metric]
                        })
                        combined["Intersection"] = inter
                        all_data.append(combined)
                if all_data:
                    combined_data = pd.concat(all_data)
                    fig = px.scatter_matrix(combined_data, dimensions=["Traffic", "Weather"], color="Intersection",
                                            title="Scatter Matrix (Traffic vs. Selected Weather)")
                    return fig.to_html(full_html=True, include_plotlyjs='cdn')
                else:
                    fig = go.Figure()
                    fig.add_annotation(text="No combined data for scatter matrix", x=0.5, y=0.5, showarrow=False)
                    return fig.to_html(full_html=True, include_plotlyjs='cdn')
            elif chart_type == "Heatmap":
                intersections = [res["local_intersection_name"] for res in analysis_results]
                correlations = []
                for res in analysis_results:
                    corr = res.get("weather_traffic_correlation")
                    correlations.append(corr if corr is not None else 0)
                fig = go.Figure(go.Heatmap(z=[correlations], x=intersections, colorscale='coolwarm'))
                fig.update_layout(title="Correlation Heatmap (Traffic vs. Selected Weather)")
                return fig.to_html(full_html=True, include_plotlyjs='cdn')
            elif chart_type == "Combined Peak Analysis":
                fig = go.Figure()
                for res in analysis_results:
                    inter = res["local_intersection_name"]
                    df = get_df(inter, start_dt, end_dt)
                    df["Hour"] = pd.to_datetime(df["datetime_bin"]).dt.hour
                    traffic_cols = [col for col in df.columns if col.startswith("traffic_")]
                    if variant == "Lane-specific":
                        for col in traffic_cols:
                            peak = df.groupby("Hour")[col].mean().reset_index()
                            fig.add_trace(go.Scatter(x=peak["Hour"], y=peak[col], mode='lines+markers', name=f"{inter}:{col}"))
                    else:
                        df["Total Traffic"] = df[traffic_cols].sum(axis=1)
                        peak = df.groupby("Hour")["Total Traffic"].mean().reset_index()
                        fig.add_trace(go.Scatter(x=peak["Hour"], y=peak["Total Traffic"], mode='lines+markers', name=inter))
                fig.update_layout(title="Combined Peak Traffic & Weather Analysis", xaxis_title="Hour", yaxis_title="Average Traffic")
                return fig.to_html(full_html=True, include_plotlyjs='cdn')
            else:
                fig = go.Figure()
                fig.add_annotation(text="Chart type not recognized", x=0.5, y=0.5, showarrow=False)
                return fig.to_html(full_html=True, include_plotlyjs='cdn')
        else:
            fig = go.Figure()
            fig.add_annotation(text="Analysis mode not recognized", x=0.5, y=0.5, showarrow=False)
            return fig.to_html(full_html=True, include_plotlyjs='cdn')
    except Exception as e:
        logging.error(f"Error generating Plotly figure: {e}")
        fig = go.Figure()
        fig.add_annotation(text=f"Error generating figure: {e}", x=0.5, y=0.5, showarrow=False)
        return fig.to_html(full_html=True, include_plotlyjs='cdn')
