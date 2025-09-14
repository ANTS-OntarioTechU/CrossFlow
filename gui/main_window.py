import sys, os, subprocess, csv
from datetime import datetime, timedelta
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QMessageBox,
    QDateTimeEdit, QComboBox, QSlider, QCheckBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialog, QGroupBox
)
from PyQt5.QtCore import QDateTime, Qt, QThread, QObject, pyqtSignal
from simulator import simulation, utils
from simulator import edge_mapping
from simulator.auto_fetch import fetch_map_for_intersections, fetch_csv_data
from config import DEFAULT_JSON, DEFAULT_MAP, DEFAULT_DATA_CSV

# ------------------ ConfigureParametersDialog ------------------
class ConfigureParametersDialog(QDialog):
    def __init__(self, current_params, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Vehicle Parameters")
        self.setModal(True)
        self.resize(500, 400)
        self.current_params = {}
        for vehicle, params in current_params.items():
            if "carFollowModel" not in params:
                params["carFollowModel"] = "Krauss"
            self.current_params[vehicle] = params.copy()
        self.initUI()
    
    def initUI(self):
        mainLayout = QVBoxLayout(self)
        self.widgets = {}
        for vehicle, params in self.current_params.items():
            groupBox = QGroupBox(vehicle.capitalize(), self)
            form = QFormLayout(groupBox)
            comboModel = QComboBox()
            comboModel.addItems(["Krauss", "KraussPS", "KraussOrig", "Wiedemann", "SmartDriver"])
            if "carFollowModel" in params:
                index = comboModel.findText(params["carFollowModel"])
                if index >= 0:
                    comboModel.setCurrentIndex(index)
            form.addRow(QLabel("Model:"), comboModel)
            self.widgets.setdefault(vehicle, {})["carFollowModel"] = comboModel
            for param in ["accel", "decel", "sigma", "length", "maxSpeed"]:
                line = QLineEdit(str(params.get(param, "")))
                form.addRow(QLabel(param.capitalize() + ":"), line)
                self.widgets[vehicle][param] = line
            mainLayout.addWidget(groupBox)
        btnLayout = QHBoxLayout()
        btnSave = QPushButton("Save")
        btnSave.clicked.connect(self.accept)
        btnCancel = QPushButton("Cancel")
        btnCancel.clicked.connect(self.reject)
        btnLayout.addWidget(btnSave)
        btnLayout.addWidget(btnCancel)
        mainLayout.addLayout(btnLayout)
    
    def getParameters(self):
        new_params = {}
        for vehicle, wd in self.widgets.items():
            new_params[vehicle] = {}
            for key, widget in wd.items():
                if key == "carFollowModel":
                    new_params[vehicle][key] = widget.currentText().strip()
                else:
                    new_params[vehicle][key] = widget.text().strip()
        return new_params

# ------------------ LoadingDialog and AutoFetch Workers ------------------
class LoadingDialog(QDialog):
    def __init__(self, parent=None):
        super(LoadingDialog, self).__init__(parent)
        self.setWindowTitle("Loading")
        self.setModal(True)
        self.setFixedSize(300, 100)
        layout = QVBoxLayout(self)
        self.label = QLabel(
            "It can take some time depending on the size of the network map.\n"
            "This window will close when the download is complete.\n"
            "It will be saved to 'data' directory."
        )
        self.label.setWordWrap(True)
        layout.addWidget(self.label, alignment=Qt.AlignCenter)

class AutoFetchWorker(QObject):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    
    def __init__(self, coordinates, parent=None):
        super().__init__(parent)
        self.coordinates = coordinates
    
    def run(self):
        try:
            net_file = fetch_map_for_intersections(self.coordinates, data_folder="data", radius_km=5)
            self.finished.emit(net_file)
        except Exception as e:
            self.error.emit(str(e))

class AutoFetchDataWorker(QObject):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    
    def run(self):
        try:
            csv_file = fetch_csv_data(data_folder="data")
            self.finished.emit(csv_file)
        except Exception as e:
            self.error.emit(str(e))

# ------------------ MainWindow ------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CrossFlow")
        self.resize(700, 1000)  # Change main window size here
        self.overall_min = None  
        self.overall_max = None  
        self.sim_duration = timedelta(minutes=15)
        self._simulation_running = False
        self.vehicle_params = {
            "car":   {"carFollowModel": "Krauss", "accel": "1.0", "decel": "4.5", "sigma": "0.5", "length": "5",  "maxSpeed": "25"},
            "truck": {"carFollowModel": "Krauss", "accel": "0.8", "decel": "4.0", "sigma": "0.5", "length": "12", "maxSpeed": "20"},
            "bus":   {"carFollowModel": "Krauss", "accel": "0.7", "decel": "4.0", "sigma": "0.5", "length": "12", "maxSpeed": "20"}
        }
        self.initUI()

    def initUI(self):
        central = QWidget()
        self.setCentralWidget(central)
        mainLayout = QVBoxLayout()
        formLayout = QFormLayout()

        # Input JSON file
        self.jsonLine = QLineEdit(DEFAULT_JSON)
        btnJson = QPushButton("Browse")
        btnJson.clicked.connect(self.browseJSON)
        hboxJson = QHBoxLayout()
        hboxJson.addWidget(self.jsonLine)
        hboxJson.addWidget(btnJson)
        formLayout.addRow(QLabel("Input Intersection List:"), hboxJson)


        # Input CSV file with Auto Fetch button
        self.csvLine = QLineEdit(DEFAULT_DATA_CSV)
        btnCSV = QPushButton("Browse")
        btnCSV.clicked.connect(self.browseCSV)
        btnAutoFetchData = QPushButton("Auto Fetch")
        btnAutoFetchData.setToolTip("Automatically fetch the CSV data from CKAN.")
        btnAutoFetchData.clicked.connect(self.autoFetchData)
        hboxCSV = QHBoxLayout()
        hboxCSV.addWidget(self.csvLine)
        hboxCSV.addWidget(btnCSV)
        hboxCSV.addWidget(btnAutoFetchData)
        formLayout.addRow(QLabel("Input Data File:"), hboxCSV)


        # Input Map file with Auto Fetch button
        self.mapLine = QLineEdit(DEFAULT_MAP)
        btnMap = QPushButton("Browse")
        btnMap.clicked.connect(self.browseMap)
        btnAutoFetch = QPushButton("Auto Fetch")
        btnAutoFetch.setToolTip("Automatically fetch the map from OSM based on the coordinates from the CSV using centreline_id.")
        btnAutoFetch.clicked.connect(self.autoFetchMap)
        hboxMap = QHBoxLayout()
        hboxMap.addWidget(self.mapLine)
        hboxMap.addWidget(btnMap)
        hboxMap.addWidget(btnAutoFetch)
        formLayout.addRow(QLabel("Input Map File:"), hboxMap)


        # Time Range Selection – overall time range (read-only)
        self.startTimeEdit = QDateTimeEdit()
        self.startTimeEdit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.startTimeEdit.setReadOnly(True)
        self.startTimeEdit.setEnabled(True)
        self.endTimeEdit = QDateTimeEdit()
        self.endTimeEdit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.endTimeEdit.setReadOnly(True)
        self.endTimeEdit.setEnabled(True)
        formLayout.addRow(QLabel("Simulation Start Time:"), self.startTimeEdit)
        formLayout.addRow(QLabel("Simulation End Time:"), self.endTimeEdit)

        # Custom Simulation Window checkbox
        self.customSimCheck = QCheckBox("Custom Simulation Window")
        self.customSimCheck.toggled.connect(self.customSimToggled)
        formLayout.addRow(self.customSimCheck)

        # Simulation Duration and Slider
        self.durationCombo = QComboBox()
        self.durationCombo.addItem("15 minutes", 15)
        self.durationCombo.addItem("30 minutes", 30)
        self.durationCombo.addItem("45 minutes", 45)
        self.durationCombo.addItem("60 minutes", 60)
        self.durationCombo.currentIndexChanged.connect(self.updateSliderRange)
        self.startSlider = QSlider(Qt.Horizontal)
        self.startSlider.setEnabled(True)
        self.startSlider.valueChanged.connect(self.updateTimeEdits)
        hboxDuration = QHBoxLayout()
        hboxDuration.addWidget(self.durationCombo)
        hboxDuration.addWidget(self.startSlider)
        formLayout.addRow(QLabel("Simulation Window:"), hboxDuration)

        # Button to load overall time range and update detailed table
        btnLoadRange = QPushButton("Load Time Range")
        btnLoadRange.clicked.connect(self.loadTimeRange)
        formLayout.addRow(btnLoadRange)

        mainLayout.addLayout(formLayout)
        
        # Detailed Time Range Table
        self.detailTable = QTableWidget()
        self.detailTable.setColumnCount(3)
        self.detailTable.setHorizontalHeaderLabels(["Centreline ID", "Start Time", "End Time"])
        self.detailTable.horizontalHeader().setStyleSheet("""
            QHeaderView::section {
                background-color: #3e3e3e;
                color: #ffffff;
            }
        """)
        self.detailTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        mainLayout.addWidget(QLabel("Data Availability:"))
        mainLayout.addWidget(self.detailTable)

        # Button row: Configure Parameters, Save Simulation, Run Simulation.
        hboxButtons = QHBoxLayout()
        self.btnConfig = QPushButton("Configure Parameters")
        self.btnConfig.clicked.connect(self.configureParameters)
        self.btnSave = QPushButton("Save Simulation")
        self.btnSave.clicked.connect(self.saveSimulation)
        self.btnRun = QPushButton("Run Simulation")
        self.btnRun.clicked.connect(self.runSimulation)
        hboxButtons.addWidget(self.btnConfig)
        hboxButtons.addWidget(self.btnSave)
        hboxButtons.addWidget(self.btnRun)
        mainLayout.addLayout(hboxButtons)

        central.setLayout(mainLayout)
        self.setStyleSheet("""
            QWidget { background-color: #2e2e2e; color: #ffffff; font-family: "Segoe UI", sans-serif; font-size: 10pt; }
            QLineEdit, QDateTimeEdit, QComboBox, QTableWidget {
                background-color: #3e3e3e; border: 1px solid #5e5e5e;
                padding: 4px; border-radius: 4px; color: #ffffff;
            }
            QPushButton { background-color: #007ACC; border: none; padding: 8px; border-radius: 4px; }
            QPushButton:hover { background-color: #005999; }
            QLabel { color: #ffffff; }
            QSlider::groove:horizontal { height: 8px; background: #5e5e5e; border-radius: 4px; }
            QSlider::handle:horizontal { background: #007ACC; border: none; width: 16px; margin: -4px 0; border-radius: 8px; }
        """)

    # ------------------ HELPER METHODS FOR NON-MODAL MESSAGES ------------------
    def show_info(self, title, text):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.setModal(False)
        msg.show()

    def show_error(self, title, text):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.setModal(False)
        msg.show()

    # ------------------ BROWSE BUTTONS ------------------
    def browseJSON(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Select Input JSON File", "input", "JSON Files (*.json)")
        if fname:
            self.jsonLine.setText(fname)

    def browseMap(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Select Input Map File", "input", "XML Files (*.xml)")
        if fname:
            self.mapLine.setText(fname)

    def browseCSV(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Select Input CSV File", "input", "CSV Files (*.csv)")
        if fname:
            self.csvLine.setText(fname)

    # ------------------ AUTO FETCH MAP ------------------
    def autoFetchMap(self):
        json_file = self.jsonLine.text().strip()
        if not json_file or not os.path.exists(json_file):
            self.show_error("Error", "Please select a valid JSON file first.")
            return

        csv_file = self.csvLine.text().strip()
        if not csv_file or not os.path.exists(csv_file):
            self.show_error("Error", "Please select a valid CSV file first.")
            return

        # 1) Load centreline_ids from the JSON:
        try:
            with open(json_file, "r", encoding="utf-8") as jf:
                import json
                intersections = json.load(jf)
        except Exception as e:
            self.show_error("Error", f"Failed to read JSON: {e}")
            return

        # Build a set of centreline_id’s (as strings) present in the JSON
        json_ids = set()
        for inter in intersections:
            cid = inter.get("centreline_id")
            if cid is not None:
                # Normalize to string, since CSV values are read as strings
                json_ids.add(str(cid).strip())

        if not json_ids:
            self.show_error("Error", "No centreline_id found in the JSON.")
            return

        # 2) Read the CSV and collect coords only for those IDs in json_ids
        coords = {}
        try:
            with open(csv_file, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    raw_cid = row.get("centreline_id")
                    if raw_cid is None:
                        continue
                    cid_str = str(raw_cid).strip()
                    # Only keep rows whose centreline_id is in the JSON set
                    if cid_str not in json_ids:
                        continue

                    try:
                        lat = float(row["latitude"])
                        lon = float(row["longitude"])
                    except Exception:
                        continue

                    # We only need one (lat, lon) per centreline_id
                    if cid_str not in coords:
                        coords[cid_str] = (lat, lon)
        except Exception as e:
            self.show_error("Error", f"Failed to read CSV: {e}")
            return

        if not coords:
            self.show_error("Error", "No matching coordinates found in CSV for JSON intersections.")
            return

        # Build a list of (lat, lon) tuples for the auto‐fetch worker
        coord_list = list(coords.values())

        # 3) Spawn the LoadingDialog + worker thread as before
        loading = LoadingDialog(self)
        loading.show()
        QApplication.processEvents()

        self.thread = QThread()
        self.worker = AutoFetchWorker(coord_list)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.onAutoFetchFinished)
        self.worker.error.connect(self.onAutoFetchError)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.loadingDialog = loading
        self.thread.start()


    def onAutoFetchFinished(self, net_file):
        self.mapLine.setText(os.path.abspath(net_file))
        self.show_info("Auto Fetch Complete", f"Map fetched and saved to:\n{net_file}")
        if self.loadingDialog:
            self.loadingDialog.close()
            self.loadingDialog = None

    def onAutoFetchError(self, error_str):
        self.show_error("Error", f"Auto-fetch failed: {error_str}")
        if self.loadingDialog:
            self.loadingDialog.close()
            self.loadingDialog = None

    # ------------------ AUTO FETCH CSV DATA ------------------
    def autoFetchData(self):
        # Use a loading dialog for CSV auto-fetch.
        loading = LoadingDialog(self)
        loading.label.setText(
            "Fetching CSV data...\nIt can take some time depending on the size of the dataset.\n"
            "This window will close when the CSV is downloaded.\nIt will be saved to 'data' directory."
        )
        loading.show()
        QApplication.processEvents()

        self.csvThread = QThread()
        self.csvWorker = AutoFetchDataWorker()
        self.csvWorker.moveToThread(self.csvThread)
        self.csvThread.started.connect(self.csvWorker.run)
        self.csvWorker.finished.connect(self.onAutoFetchDataFinished)
        self.csvWorker.error.connect(self.onAutoFetchDataError)
        self.csvWorker.finished.connect(self.csvThread.quit)
        self.csvWorker.finished.connect(self.csvWorker.deleteLater)
        self.csvThread.finished.connect(self.csvThread.deleteLater)
        self.loadingDialogData = loading
        self.csvThread.start()

    def onAutoFetchDataFinished(self, csv_file_path):
        self.csvLine.setText(os.path.abspath(csv_file_path))
        self.show_info("Auto Fetch CSV Complete", f"CSV data fetched and saved to:\n{csv_file_path}")
        if self.loadingDialogData:
            self.loadingDialogData.close()
            self.loadingDialogData = None

    def onAutoFetchDataError(self, error_str):
        self.show_error("Error", f"CSV auto-fetch failed: {error_str}")
        if self.loadingDialogData:
            self.loadingDialogData.close()
            self.loadingDialogData = None

    # ------------------ LOAD TIME RANGE ------------------
    def loadTimeRange(self):
        try:
            json_file = self.jsonLine.text().strip()
            if not json_file or not os.path.exists(json_file):
                self.show_error("Error", "Please select a valid JSON file.")
                return
            csv_file = self.csvLine.text().strip()
            if not csv_file or not os.path.exists(csv_file):
                self.show_error("Error", "Please select a valid CSV file.")
                return
            overall_min, overall_max = utils.get_overall_time_range(json_file, csv_file)
            self.overall_min = overall_min
            self.overall_max = overall_max
            self.startTimeEdit.setDateTime(QDateTime(overall_min))
            self.endTimeEdit.setDateTime(QDateTime(overall_max))
            self.startSlider.setEnabled(not self.customSimCheck.isChecked())
            self.durationCombo.setEnabled(not self.customSimCheck.isChecked())
            self.updateSliderRange()
            self.updateTimeEdits()
            detailed = utils.get_data_availability_by_intersection(json_file, csv_file)
            self.updateDetailTable(detailed)
        except Exception as e:
            self.show_error("Error", str(e))

    def updateDetailTable(self, data):
        rows = []
        for centreline, intervals in data.items():
            for interval in intervals:
                rows.append((centreline, interval["start"], interval["end"]))
        self.detailTable.setRowCount(len(rows))
        for i, (cid, st, et) in enumerate(rows):
            self.detailTable.setItem(i, 0, QTableWidgetItem(cid))
            self.detailTable.setItem(i, 1, QTableWidgetItem(st))
            self.detailTable.setItem(i, 2, QTableWidgetItem(et))

    # ------------------ SLIDER / TIME EDITS ------------------
    def updateSliderRange(self):
        if not self.overall_min or not self.overall_max:
            return
        minutes = self.durationCombo.currentData()
        self.sim_duration = timedelta(minutes=minutes)
        total_seconds = int((self.overall_max - self.overall_min - self.sim_duration).total_seconds())
        if total_seconds < 0:
            total_seconds = 0
        self.startSlider.setMinimum(0)
        self.startSlider.setMaximum(total_seconds)
        self.startSlider.setValue(0)
        self.updateTimeEdits()

    def updateTimeEdits(self):
        if not self.customSimCheck.isChecked() and self.overall_min:
            offset = timedelta(seconds=self.startSlider.value())
            sim_start = self.overall_min + offset
            sim_end = sim_start + self.sim_duration
            self.startTimeEdit.setDateTime(QDateTime(sim_start))
            self.endTimeEdit.setDateTime(QDateTime(sim_end))

    def customSimToggled(self, checked):
        if checked:
            # Disable slider/duration widgets:
            self.startSlider.setEnabled(False)
            self.durationCombo.setEnabled(False)
            # Make the date/time edits editable so the drop-down opens
            self.startTimeEdit.setReadOnly(False)
            self.endTimeEdit.setReadOnly(False)
        else:
            # Re-enable slider/duration and return to auto-mode:
            self.startSlider.setEnabled(True)
            self.durationCombo.setEnabled(True)
            # Put the date/time edits back into read-only mode
            self.startTimeEdit.setReadOnly(True)
            self.endTimeEdit.setReadOnly(True)
            # Recompute the slider range + values
            self.updateSliderRange()
            self.updateTimeEdits()

    # ------------------ CONFIGURE PARAMETERS ------------------
    def configureParameters(self):
        dlg = ConfigureParametersDialog(self.vehicle_params, self)
        if dlg.exec_():
            self.vehicle_params = dlg.getParameters()
            self.show_info("Parameters Saved", "Vehicle parameters have been updated.")

    # ------------------ SAVE / RUN SIMULATION ------------------
    def saveSimulationFiles(self):
        try:
            json_file = self.jsonLine.text().strip()
            map_file = self.mapLine.text().strip()
            csv_file = self.csvLine.text().strip()
            sim_start = self.startTimeEdit.dateTime().toPyDateTime()
            sim_end = self.endTimeEdit.dateTime().toPyDateTime()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            sim_folder = f"sumo_sim_{timestamp}"
            os.makedirs(sim_folder, exist_ok=True)
            route_file, incomplete = simulation.simulate_simulation(
                json_file, map_file, csv_file, sim_start, sim_end, sim_folder,
                vehicle_params=self.vehicle_params
            )
        except Exception as e:
            raise RuntimeError(f"Error generating routes: {e}")
        if route_file is None:
            details_file = os.path.join(sim_folder, "simulation_details.json")
            with open(details_file, "w") as f:
                import json
                json.dump({"warnings": incomplete}, f, indent=4)
            return sim_folder, None, incomplete
        try:
            config_file = simulation.generate_sumo_config(sim_folder, map_file, route_file, sim_start, sim_end)
        except Exception as e:
            raise RuntimeError(f"Error generating SUMO config: {e}")
        return sim_folder, config_file, incomplete

    def saveSimulation(self):
        if self._simulation_running:
            return
        self._simulation_running = True
        try:
            sim_folder, config_file, incomplete = self.saveSimulationFiles()
            if config_file is None:
                msg = "Simulation not created due to the following issues:\n" + "\n".join(incomplete)
                self.show_info("Simulation Not Saved", msg)
            else:
                msg = f"Files saved in folder '{sim_folder}'.\nConfig: {config_file}"
                if incomplete:
                    msg += "\n\nWarnings:\n" + "\n".join(incomplete)
                self.show_info("Simulation Saved", msg)
        except Exception as e:
            self.show_error("Error", str(e))
        finally:
            self._simulation_running = False

    def runSimulation(self):
        if self._simulation_running:
            return
        self._simulation_running = True
        try:
            sim_folder, config_file, incomplete = self.saveSimulationFiles()
            if config_file is None:
                msg = "Simulation not run due to the following issues:\n" + "\n".join(incomplete)
                self.show_info("Simulation Not Run", msg)
                return
            if incomplete:
                self.show_info("Incomplete Data", "Warning: Some intersections have incomplete data:\n" + "\n".join(incomplete))

            import shutil
            print("Launching SUMO-GUI from:", shutil.which("sumo-gui"))
            subprocess.Popen(["sumo-gui", "-c", config_file])
            self.show_info("Simulation Running", f"Simulation running using config '{config_file}'.")
        except Exception as e:
            self.show_error("Error", str(e))
        finally:
            self._simulation_running = False

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
