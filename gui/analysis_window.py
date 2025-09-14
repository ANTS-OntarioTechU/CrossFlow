# gui/analysis_window.py
import sys, os, logging
from datetime import datetime

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QDateTimeEdit, QComboBox, QMessageBox
)
from PyQt5.QtCore import QDateTime, Qt

from simulator import analysis, utils
from gui.chart_logic import generate_chart, METRIC_MAP, WEATHER_METRICS

logging.basicConfig(level=logging.DEBUG)

# Define analysis modes and their chart sub-options.
CHART_OPTIONS = {
    "single": [
        "Time Series",
        "Histogram",
        "Box Plot",
        "Peak Traffic by Time of Day",
        "Peak Traffic by Day of Week",
        "Holiday/Weekend Impact"
    ],
    "single_metric": [
        "Dual-Axis Time Series",
        "Scatter Plot (Traffic vs. Weather)",
        "Correlation Heatmap",
        "Peak Traffic & Weather Analysis"
    ],
    "multi": [
        "Bar Chart (Average Traffic)",
        "Box Plot Comparison",
        "Line Chart Overlay",
        "Peak Traffic Comparison"
    ],
    "multi_metric": [
        "Bar Chart (Correlation)",
        "Scatter Matrix",
        "Heatmap",
        "Combined Peak Analysis"
    ]
}

class GraphWindow(QMainWindow):
    """A window to display the Plotly graph."""
    def __init__(self, html_content):
        super().__init__()
        self.setWindowTitle("Analysis Graph")
        self.resize(900, 700)
        from PyQt5.QtWebEngineWidgets import QWebEngineView
        try:
            self.webView = QWebEngineView()
            self.webView.setHtml(html_content)
            self.setCentralWidget(self.webView)
        except Exception as e:
            logging.error(f"Error initializing web view: {e}")
            error_label = QLabel("Error displaying graph: " + str(e))
            self.setCentralWidget(error_label)

class AnalysisWindow(QMainWindow):
    def __init__(self, input_json_file="input/input.json"):
        super().__init__()
        self.setWindowTitle("Data Analysis")
        self.resize(900, 700)
        self.input_json_file = input_json_file
        self.intersections = []  # Loaded automatically.
        self.initUI()
        self.autoLoadData()

    def initUI(self):
        central = QWidget()
        mainLayout = QVBoxLayout()

        # Timeframe selection.
        timeLayout = QHBoxLayout()
        self.startTimeEdit = QDateTimeEdit()
        self.startTimeEdit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.endTimeEdit = QDateTimeEdit()
        self.endTimeEdit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        timeLayout.addWidget(QLabel("Analysis Start Time:"))
        timeLayout.addWidget(self.startTimeEdit)
        timeLayout.addWidget(QLabel("Analysis End Time:"))
        timeLayout.addWidget(self.endTimeEdit)
        mainLayout.addLayout(timeLayout)

        # Analysis Mode selection.
        modeLayout = QHBoxLayout()
        modeLayout.addWidget(QLabel("Select Analysis Mode:"))
        self.modeCombo = QComboBox()
        self.modeCombo.addItem("Single Intersection", "single")
        self.modeCombo.addItem("Single Intersection with Metric", "single_metric")
        self.modeCombo.addItem("Multi Intersection", "multi")
        self.modeCombo.addItem("Multi Intersection with Metric", "multi_metric")
        self.modeCombo.currentIndexChanged.connect(self.updateChartOptions)
        modeLayout.addWidget(self.modeCombo)
        mainLayout.addLayout(modeLayout)

        # Chart Type selection.
        chartLayout = QHBoxLayout()
        chartLayout.addWidget(QLabel("Select Chart Type:"))
        self.chartTypeCombo = QComboBox()
        chartLayout.addWidget(self.chartTypeCombo)
        mainLayout.addLayout(chartLayout)

        # Graph Variant selection.
        variantLayout = QHBoxLayout()
        variantLayout.addWidget(QLabel("Select Graph Variant:"))
        self.variantCombo = QComboBox()
        self.variantCombo.addItems(["Lane-specific", "Total Traffic"])
        variantLayout.addWidget(self.variantCombo)
        mainLayout.addLayout(variantLayout)

        # Weather Metric selection (only for metric modes).
        weatherLayout = QHBoxLayout()
        weatherLayout.addWidget(QLabel("Select Weather Metric:"))
        self.weatherMetricCombo = QComboBox()
        self.weatherMetricCombo.addItems(WEATHER_METRICS)
        weatherLayout.addWidget(self.weatherMetricCombo)
        mainLayout.addLayout(weatherLayout)
        self.weatherMetricCombo.setEnabled(False)
        self.weatherMetricCombo.setToolTip("Not applicable for this mode")

        # Intersection selection list.
        self.intersectionList = QListWidget()
        mainLayout.addWidget(QLabel("Select Intersection(s) for Analysis:"))
        mainLayout.addWidget(self.intersectionList)

        # Analysis refresh button.
        btnRefresh = QPushButton("Refresh Analysis")
        btnRefresh.clicked.connect(self.refreshAnalysis)
        mainLayout.addWidget(btnRefresh)

        # Missing data note label.
        self.noteLabel = QLabel("")
        self.noteLabel.setWordWrap(True)
        mainLayout.addWidget(self.noteLabel)

        central.setLayout(mainLayout)
        self.setCentralWidget(central)
        self.setStyleSheet("""
            QWidget { background-color: #2e2e2e; color: #ffffff; font-family: "Segoe UI", sans-serif; font-size: 10pt; }
            QLineEdit, QDateTimeEdit, QComboBox { background-color: #3e3e3e; border: 1px solid #5e5e5e; padding: 4px; border-radius: 4px; color: #ffffff; }
            QPushButton { background-color: #007ACC; border: none; padding: 8px; border-radius: 4px; }
            QPushButton:hover { background-color: #005999; }
            QLabel { color: #ffffff; }
        """)
        self.updateChartOptions()

    def autoLoadData(self):
        try:
            self.intersections = utils.load_input_json(self.input_json_file)
            self.intersectionList.clear()
            for inter in self.intersections:
                if "local_intersection_name" in inter and inter["local_intersection_name"]:
                    item = QListWidgetItem(inter["local_intersection_name"])
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Unchecked)
                    self.intersectionList.addItem(item)
            overall_min, overall_max = utils.get_overall_time_range(self.input_json_file)
            self.startTimeEdit.setDateTime(QDateTime(overall_min))
            self.endTimeEdit.setDateTime(QDateTime(overall_max))
        except Exception as e:
            logging.error(f"Error auto-loading data: {e}")

    def updateChartOptions(self):
        mode = self.modeCombo.currentData()
        self.chartTypeCombo.clear()
        if mode in CHART_OPTIONS:
            self.chartTypeCombo.addItems(CHART_OPTIONS[mode])
        else:
            self.chartTypeCombo.addItem("Default")
        if mode in ["single_metric", "multi_metric"]:
            self.weatherMetricCombo.setEnabled(True)
            self.weatherMetricCombo.setToolTip("")
        else:
            self.weatherMetricCombo.setEnabled(False)
            self.weatherMetricCombo.setCurrentIndex(-1)
            self.weatherMetricCombo.setToolTip("Not applicable for this mode")

    def refreshAnalysis(self):
        selected = []
        for index in range(self.intersectionList.count()):
            item = self.intersectionList.item(index)
            if item.checkState() == Qt.Checked:
                selected.append(item.text())
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select at least one intersection for analysis.")
            return

        start_dt = self.startTimeEdit.dateTime().toPyDateTime()
        end_dt = self.endTimeEdit.dateTime().toPyDateTime()
        if start_dt >= end_dt:
            QMessageBox.critical(self, "Error", "Start time must be before end time.")
            return

        analysis_mode = self.modeCombo.currentData()
        chart_type = self.chartTypeCombo.currentText()
        variant = self.variantCombo.currentText()
        weather_metric = None
        if analysis_mode in ["single_metric", "multi_metric"]:
            weather_metric = METRIC_MAP[self.weatherMetricCombo.currentText()]
        logging.debug(f"Refreshing analysis: mode={analysis_mode}, chart={chart_type}, variant={variant}, weather_metric={weather_metric}, selected={selected}")
        analysis_results = []
        missing_notes = []

        if analysis_mode in ["single", "single_metric"] and len(selected) != 1:
            QMessageBox.critical(self, "Error", "Please select exactly one intersection for single intersection analysis.")
            return

        for inter in selected:
            try:
                if analysis_mode in ["single_metric", "multi_metric"]:
                    result = analysis.analyze_intersection(inter, start_dt, end_dt, weather_metric=weather_metric)
                else:
                    result = analysis.analyze_intersection(inter, start_dt, end_dt)
                analysis_results.append(result)
                if result["missing_data"]:
                    missing_notes.append(f"Intersection '{inter}' has missing data for the selected timeframe.")
            except Exception as e:
                missing_notes.append(f"Error processing {inter}: {e}")
                logging.error(f"Error analyzing {inter}: {e}")

        self.noteLabel.setText("Notes:\n" + "\n".join(missing_notes) if missing_notes else "")
        try:
            html_str = generate_chart(analysis_results, analysis_mode, chart_type, variant, start_dt, end_dt, weather_metric)
        except Exception as e:
            logging.error(f"Error generating Plotly figure: {e}")
            html_str = "<h1>Error generating graph</h1><p>" + str(e) + "</p>"
        self.openGraphWindow(html_str)

    def openGraphWindow(self, html_content):
        import tempfile
        from PyQt5.QtCore import QUrl
        from PyQt5.QtWebEngineWidgets import QWebEngineView

        # Write HTML content to a temporary file.
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=".html")
        temp.write(html_content.encode("utf-8"))
        temp.close()

        self.graphWindow = QMainWindow()
        self.graphWindow.setWindowTitle("Analysis Graph")
        self.graphWindow.resize(900, 700)
        webView = QWebEngineView()
        # Load the temporary file via URL.
        webView.load(QUrl.fromLocalFile(temp.name))
        layout = QVBoxLayout()
        layout.addWidget(webView)
        central = QWidget()
        central.setLayout(layout)
        self.graphWindow.setCentralWidget(central)
        self.graphWindow.show()

if __name__ == "__main__":
    from PyQt5.QtCore import QCoreApplication, Qt
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = AnalysisWindow()
    window.show()
    sys.exit(app.exec_())
