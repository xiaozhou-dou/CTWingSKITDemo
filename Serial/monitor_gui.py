import sys
import serial
import serial.tools.list_ports
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QGridLayout, QLabel, QPushButton,
                             QComboBox, QTextEdit, QGroupBox, QFrame, QRadioButton,
                             QButtonGroup, QSplitter, QSlider)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont, QTextCursor


class STM32MonitorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.serial_port = serial.Serial()
        self.rx_buffer = bytearray()
        self.initUI()

        self.timer = QTimer()
        self.timer.timeout.connect(self.read_serial)
        self.timer.start(20)

    def initUI(self):
        self.setWindowTitle('STM32 Industrial Terminal [Cyber Edition]')
        self.resize(1000, 750)
        self.apply_cyber_theme()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # ====== 1. 顶部：串口配置区 ======
        port_frame = QFrame()
        port_frame.setProperty("class", "panel")
        port_layout = QHBoxLayout(port_frame)

        self.combo_ports = QComboBox()
        self.combo_ports.setMinimumWidth(200)
        self.refresh_ports()

        self.btn_refresh = QPushButton("⟳ SCAN PORTS")
        self.btn_refresh.clicked.connect(self.refresh_ports)

        self.btn_connect = QPushButton("▶ CONNECT")
        self.btn_connect.setProperty("class", "btn_connect")
        self.btn_connect.clicked.connect(self.toggle_connection)

        lbl_link = QLabel("<b>LINK INTERFACE:</b>")
        lbl_link.setStyleSheet("color: #a5b4fc; font-size: 11pt;")

        port_layout.addWidget(lbl_link)
        port_layout.addWidget(self.combo_ports)
        port_layout.addWidget(self.btn_refresh)
        port_layout.addWidget(self.btn_connect)
        port_layout.addStretch()
        main_layout.addWidget(port_frame)

        # ====== 2. 中部：数据与控制大屏区 ======
        dashboard_layout = QGridLayout()
        dashboard_layout.setSpacing(10)

        # [传感器大屏]
        sensor_group = QGroupBox("CORE SENSORS (HTS221)")
        sensor_grid = QGridLayout()
        sensor_grid.setContentsMargins(20, 20, 20, 20)
        sensor_grid.setHorizontalSpacing(15)

        lbl_t_tag = QLabel("TEMP")
        lbl_t_tag.setFont(QFont("Consolas", 16, QFont.Bold))
        lbl_t_tag.setStyleSheet("color: #8b949e;")

        self.lbl_temp = QLabel("--.-")
        self.lbl_temp.setFont(QFont("Consolas", 38, QFont.Bold))
        self.lbl_temp.setStyleSheet("color: #FF3366;")
        self.lbl_temp.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.lbl_t_unit = QLabel("°C")
        self.lbl_t_unit.setFont(QFont("Consolas", 20, QFont.Bold))
        self.lbl_t_unit.setStyleSheet("color: #FF3366;")
        self.lbl_t_unit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        lbl_h_tag = QLabel("HUM")
        lbl_h_tag.setFont(QFont("Consolas", 16, QFont.Bold))
        lbl_h_tag.setStyleSheet("color: #8b949e;")

        self.lbl_hum = QLabel("--.-")
        self.lbl_hum.setFont(QFont("Consolas", 38, QFont.Bold))
        self.lbl_hum.setStyleSheet("color: #00E5FF;")
        self.lbl_hum.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.lbl_h_unit = QLabel("%")
        self.lbl_h_unit.setFont(QFont("Consolas", 20, QFont.Bold))
        self.lbl_h_unit.setStyleSheet("color: #00E5FF;")
        self.lbl_h_unit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        sensor_grid.addWidget(lbl_t_tag, 0, 0, Qt.AlignLeft | Qt.AlignVCenter)
        sensor_grid.addWidget(self.lbl_temp, 0, 1, Qt.AlignLeft | Qt.AlignVCenter)
        sensor_grid.addWidget(self.lbl_t_unit, 0, 2, Qt.AlignRight | Qt.AlignVCenter)

        sensor_grid.addWidget(lbl_h_tag, 1, 0, Qt.AlignLeft | Qt.AlignVCenter)
        sensor_grid.addWidget(self.lbl_hum, 1, 1, Qt.AlignLeft | Qt.AlignVCenter)
        sensor_grid.addWidget(self.lbl_h_unit, 1, 2, Qt.AlignRight | Qt.AlignVCenter)

        sensor_grid.setColumnStretch(0, 1)
        sensor_grid.setColumnStretch(1, 4)
        sensor_grid.setColumnStretch(2, 1)

        sensor_group.setLayout(sensor_grid)
        dashboard_layout.addWidget(sensor_group, 0, 0, 2, 1)

        # [电机控制]
        motor_group = QGroupBox("DRIVE & SPEED CONTROL")
        motor_vbox = QVBoxLayout()

        status_hbox = QHBoxLayout()
        self.lbl_motor = QLabel("STATUS: [ STOP ]")
        self.lbl_motor.setFont(QFont("Consolas", 14, QFont.Bold))
        self.lbl_motor.setStyleSheet("color: #00FF66;")
        self.lbl_motor.setAlignment(Qt.AlignCenter)

        self.lbl_speed = QLabel("")  # 初始隐藏
        self.lbl_speed.setFont(QFont("Consolas", 14, QFont.Bold))
        self.lbl_speed.setStyleSheet("color: #00E5FF;")
        self.lbl_speed.setAlignment(Qt.AlignCenter)

        status_hbox.addWidget(self.lbl_motor)
        status_hbox.addWidget(self.lbl_speed)

        hbox_m = QHBoxLayout()
        btn_m_fwd = QPushButton("FORWARD")
        btn_m_rev = QPushButton("REVERSE")
        btn_m_stop = QPushButton("STOP")
        btn_m_stop.setProperty("class", "btn_danger")

        btn_m_fwd.clicked.connect(lambda: self.send_protocol_cmd(0x0A, [0x01]))
        btn_m_rev.clicked.connect(lambda: self.send_protocol_cmd(0x0A, [0x02]))
        btn_m_stop.clicked.connect(lambda: self.send_protocol_cmd(0x0A, [0x00]))

        hbox_m.addWidget(btn_m_fwd)
        hbox_m.addWidget(btn_m_stop)
        hbox_m.addWidget(btn_m_rev)

        speed_hbox = QHBoxLayout()
        lbl_spd_tag = QLabel("<b>THROTTLE:</b>")
        lbl_spd_tag.setStyleSheet("color: #a5b4fc;")

        self.slider_speed = QSlider(Qt.Horizontal)
        self.slider_speed.setRange(0, 100)
        self.slider_speed.setSingleStep(10)
        self.slider_speed.setTickInterval(10)
        self.slider_speed.setTickPosition(QSlider.TicksBelow)
        self.slider_speed.setValue(50)
        self.slider_speed.valueChanged.connect(self.on_speed_changed)
        self.slider_speed.sliderReleased.connect(self.send_speed_cmd)

        self.btn_spd_step = QPushButton("+10%")
        self.btn_spd_step.setStyleSheet(
            "background-color: #005cc5; color: white; border: none; padding: 5px; font-weight: bold; border-radius: 3px;")
        self.btn_spd_step.setFixedWidth(50)
        self.btn_spd_step.clicked.connect(self.step_speed)

        speed_hbox.addWidget(lbl_spd_tag)
        speed_hbox.addWidget(self.slider_speed)
        speed_hbox.addWidget(self.btn_spd_step)

        motor_vbox.addLayout(status_hbox)
        motor_vbox.addLayout(hbox_m)
        motor_vbox.addLayout(speed_hbox)
        motor_group.setLayout(motor_vbox)
        dashboard_layout.addWidget(motor_group, 0, 1)

        # [RGB控制]
        rgb_group = QGroupBox("RGB ILLUMINATION")
        rgb_hbox = QHBoxLayout()
        self.combo_rgb = QComboBox()
        self.colors = ["Black", "Red", "Green", "Yellow", "Blue", "Magenta", "Cyan", "White"]
        self.combo_rgb.addItems(self.colors)

        btn_rgb_set = QPushButton("ENGAGE")
        btn_rgb_set.clicked.connect(lambda: self.send_protocol_cmd(0x0B, [self.combo_rgb.currentIndex()]))

        self.lbl_rgb = QLabel("COLOR: [ Black ]")
        self.lbl_rgb.setFont(QFont("Consolas", 12, QFont.Bold))

        rgb_hbox.addWidget(self.combo_rgb)
        rgb_hbox.addWidget(btn_rgb_set)
        rgb_hbox.addWidget(self.lbl_rgb)
        rgb_group.setLayout(rgb_hbox)
        dashboard_layout.addWidget(rgb_group, 1, 1)

        dashboard_layout.setColumnStretch(0, 10)
        dashboard_layout.setColumnStretch(1, 12)
        main_layout.addLayout(dashboard_layout, 1)

        # ====== 3. 底部：通信终端 (QSplitter 实现弹性拉伸) ======
        terminal_splitter = QSplitter(Qt.Horizontal)

        # 3.1 协议解析日志区
        log_group = QGroupBox("PROTOCOL LOG")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setProperty("class", "terminal")
        btn_clear_log = QPushButton("CLEAR LOG")
        btn_clear_log.clicked.connect(self.log_text.clear)
        log_layout.addWidget(self.log_text)
        log_layout.addWidget(btn_clear_log)
        log_group.setLayout(log_layout)
        terminal_splitter.addWidget(log_group)

        # 3.2 原始数据收发区
        raw_group = QGroupBox("RAW TRANSCEIVER (LOOPBACK TEST)")
        raw_layout = QVBoxLayout()

        # 接收区
        rx_ctrl_layout = QHBoxLayout()
        lbl_rx = QLabel("<b>RX DATA:</b>")
        lbl_rx.setStyleSheet("color: #a5b4fc;")
        rx_ctrl_layout.addWidget(lbl_rx)

        self.radio_rx_ascii = QRadioButton("ASCII")
        self.radio_rx_hex = QRadioButton("HEX")
        self.radio_rx_hex.setChecked(True)
        rx_group_btn = QButtonGroup(self)
        rx_group_btn.addButton(self.radio_rx_ascii)
        rx_group_btn.addButton(self.radio_rx_hex)
        btn_clear_rx = QPushButton("CLEAR RX")
        btn_clear_rx.clicked.connect(self.raw_rx_text.clear if hasattr(self, 'raw_rx_text') else lambda: None)
        rx_ctrl_layout.addWidget(self.radio_rx_ascii)
        rx_ctrl_layout.addWidget(self.radio_rx_hex)
        rx_ctrl_layout.addStretch()
        rx_ctrl_layout.addWidget(btn_clear_rx)

        self.raw_rx_text = QTextEdit()
        self.raw_rx_text.setReadOnly(True)
        self.raw_rx_text.setProperty("class", "terminal_raw")

        # 发送区
        tx_ctrl_layout = QHBoxLayout()
        lbl_tx = QLabel("<b>TX DATA:</b>")
        lbl_tx.setStyleSheet("color: #a5b4fc;")
        tx_ctrl_layout.addWidget(lbl_tx)

        self.radio_tx_ascii = QRadioButton("ASCII")
        self.radio_tx_hex = QRadioButton("HEX")
        self.radio_tx_hex.setChecked(True)
        tx_group_btn = QButtonGroup(self)
        tx_group_btn.addButton(self.radio_tx_ascii)
        tx_group_btn.addButton(self.radio_tx_hex)
        tx_ctrl_layout.addWidget(self.radio_tx_ascii)
        tx_ctrl_layout.addWidget(self.radio_tx_hex)
        tx_ctrl_layout.addStretch()

        self.raw_tx_input = QTextEdit()
        self.raw_tx_input.setFixedHeight(60)
        self.raw_tx_input.setProperty("class", "terminal_input")
        self.raw_tx_input.setPlaceholderText("Enter data here...")

        btn_send_raw = QPushButton("TRANSMIT RAW DATA")
        btn_send_raw.setProperty("class", "btn_action")
        btn_send_raw.clicked.connect(self.send_raw_data)

        raw_layout.addLayout(rx_ctrl_layout)
        raw_layout.addWidget(self.raw_rx_text, 2)
        raw_layout.addLayout(tx_ctrl_layout)
        raw_layout.addWidget(self.raw_tx_input, 1)
        raw_layout.addWidget(btn_send_raw)
        raw_group.setLayout(raw_layout)
        terminal_splitter.addWidget(raw_group)

        terminal_splitter.setStretchFactor(0, 10)
        terminal_splitter.setStretchFactor(1, 11)
        main_layout.addWidget(terminal_splitter, 2)

    def apply_cyber_theme(self):
        cyber_qss = """
        QMainWindow { background-color: #0d1117; }
        QLabel { color: #c9d1d9; }

        QGroupBox {
            font-weight: bold; color: #00E5FF;
            border: 1px solid #30363d; border-radius: 6px;
            margin-top: 15px; font-family: "Segoe UI", Arial;
            padding-top: 25px; 
            background-color: #161b22;
        }
        QGroupBox::title { 
            subcontrol-origin: margin; subcontrol-position: top left;
            left: 12px; top: 0px; 
            background-color: #0d1117; padding: 2px 8px;
            border: 1px solid #30363d; border-radius: 4px;
        }

        .panel { background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; }

        QPushButton {
            background-color: #21262d; color: #c9d1d9;
            border: 1px solid #30363d; border-radius: 4px; padding: 6px 12px; font-weight: bold;
        }
        QPushButton:hover { background-color: #30363d; border-color: #8b949e; }
        QPushButton:pressed { background-color: #00E5FF; color: #000000; }

        QPushButton[class="btn_connect"] { background-color: #238636; color: #ffffff; border: none; }
        QPushButton[class="btn_connect"]:hover { background-color: #2ea043; }
        QPushButton[class="btn_danger"] { background-color: #da3633; color: white; border: none; }
        QPushButton[class="btn_danger"]:hover { background-color: #f85149; }
        QPushButton[class="btn_action"] { background-color: #005cc5; color: white; border: none; padding: 10px;}
        QPushButton[class="btn_action"]:hover { background-color: #0366d6; }

        QComboBox {
            background-color: #0d1117; color: #c9d1d9; font-weight: bold;
            border: 1px solid #30363d; border-radius: 4px; padding: 5px;
        }
        QComboBox:drop-down { border: none; }
        QComboBox QAbstractItemView { background-color: #161b22; color: #c9d1d9; selection-background-color: #00E5FF; selection-color: black;}

        QTextEdit { background-color: #010409; color: #00FF66; border: 1px solid #30363d; border-radius: 4px; font-family: Consolas, monospace; }
        QTextEdit[class="terminal"] { font-size: 10pt; padding: 5px; }
        QTextEdit[class="terminal_raw"] { color: #E5E5E5; font-size: 10pt; padding: 5px; }
        QTextEdit[class="terminal_input"] { color: #00E5FF; font-size: 11pt; background-color: #0d1117; padding: 5px; border: 1px solid #005cc5;}

        QRadioButton { color: #a5b4fc; font-weight: bold; }
        QRadioButton::indicator { width: 14px; height: 14px; border-radius: 7px; border: 2px solid #30363d; background-color: #0d1117; }
        QRadioButton::indicator:checked { background-color: #00E5FF; border: 2px solid #00E5FF; }

        QSplitter::handle { background-color: #30363d; margin: 2px; border-radius: 2px; }
        QSplitter::handle:horizontal { width: 4px; }

        QSlider::groove:horizontal {
            border: 1px solid #30363d;
            height: 6px;
            background: #010409;
            border-radius: 3px;
        }
        QSlider::sub-page:horizontal {
            background: #00E5FF;
            border-radius: 3px;
        }
        QSlider::add-page:horizontal {
            background: #161b22;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: #ffffff;
            border: 1px solid #00E5FF;
            width: 14px;
            margin: -5px 0;
            border-radius: 7px;
        }
        QSlider::handle:horizontal:hover {
            background: #00E5FF;
        }
        """
        self.setStyleSheet(cyber_qss)

    def refresh_ports(self):
        self.combo_ports.clear()
        ports = serial.tools.list_ports.comports()
        for p in ports:
            self.combo_ports.addItem(p.device)

    def toggle_connection(self):
        if not self.serial_port.is_open:
            port = self.combo_ports.currentText()
            if port:
                try:
                    self.serial_port.port = port
                    self.serial_port.baudrate = 115200
                    self.serial_port.timeout = 0
                    self.serial_port.open()
                    self.btn_connect.setText("⏹ DISCONNECT")
                    self.btn_connect.setProperty("class", "btn_danger")
                    self.btn_connect.style().unpolish(self.btn_connect)
                    self.btn_connect.style().polish(self.btn_connect)
                    self.combo_ports.setEnabled(False)
                    self.log_sys("SYS", f"Data Link Established: {port} @ 115200 bps")
                except Exception as e:
                    self.log_sys("ERR", str(e))
        else:
            self.serial_port.close()
            self.btn_connect.setText("▶ CONNECT")
            self.btn_connect.setProperty("class", "btn_connect")
            self.btn_connect.style().unpolish(self.btn_connect)
            self.btn_connect.style().polish(self.btn_connect)
            self.combo_ports.setEnabled(True)
            self.log_sys("SYS", "Data Link Terminated.")

    def log_sys(self, tag, message):
        color = "#00FF66"
        if tag == "ERR":
            color = "#FF3366"
        elif tag == "TX":
            color = "#FF9900"
        elif tag == "SYS":
            color = "#00E5FF"

        self.log_text.append(f"<span style='color:{color};'>[{tag}]</span> {message}")
        self.log_text.moveCursor(QTextCursor.End)

    def append_raw_rx(self, data_bytes):
        if self.radio_rx_hex.isChecked():
            text = " ".join([f"{x:02X}" for x in data_bytes]) + " "
        else:
            text = data_bytes.decode('ascii', errors='replace')

        self.raw_rx_text.moveCursor(QTextCursor.End)
        self.raw_rx_text.insertPlainText(text)
        self.raw_rx_text.moveCursor(QTextCursor.End)

    def send_protocol_cmd(self, cmd, data_bytes):
        if not self.serial_port.is_open:
            self.log_sys("ERR", "Port offline!")
            return

        length = 1 + len(data_bytes)
        frame = bytearray([0x5A, 0xA5, length, cmd]) + bytearray(data_bytes)
        xor_cal = length
        for b in frame[3:]: xor_cal ^= b
        frame.append(xor_cal)

        self.serial_port.write(frame)
        self.log_sys("TX", f"Cmd:0x{cmd:02X} Payload:" + " ".join([f"{x:02X}" for x in frame]))

    def on_speed_changed(self, value):
        snapped_val = round(value / 10) * 10
        if snapped_val != value:
            self.slider_speed.blockSignals(True)
            self.slider_speed.setValue(snapped_val)
            self.slider_speed.blockSignals(False)

        # 仅在非STOP状态才显示具体速度
        if "STOP" not in self.lbl_motor.text():
            self.lbl_speed.setText(f"SPEED: [ {snapped_val}% ]")
        else:
            self.lbl_speed.setText("")

    def step_speed(self):
        current_val = self.slider_speed.value()
        next_val = current_val + 10
        if next_val > 100:
            next_val = 0
        self.slider_speed.setValue(next_val)
        self.send_speed_cmd()

    def send_speed_cmd(self):
        val = self.slider_speed.value()
        self.send_protocol_cmd(0x0C, [val])

    def send_raw_data(self):
        if not self.serial_port.is_open:
            self.log_sys("ERR", "Port offline!")
            return

        input_text = self.raw_tx_input.toPlainText()
        if not input_text: return

        try:
            if self.radio_tx_hex.isChecked():
                clean_hex = input_text.replace(" ", "").replace("\n", "")
                data_to_send = bytes.fromhex(clean_hex)
            else:
                data_to_send = input_text.encode('utf-8')

            self.serial_port.write(data_to_send)
            self.log_sys("TX", f"RAW TRANSMIT: {len(data_to_send)} bytes")
        except ValueError:
            self.log_sys("ERR", "Invalid HEX format in TX window!")

    def read_serial(self):
        if not self.serial_port.is_open: return

        waiting = self.serial_port.in_waiting
        if waiting:
            raw_data = self.serial_port.read(waiting)
            self.append_raw_rx(raw_data)
            self.rx_buffer.extend(raw_data)

        while len(self.rx_buffer) >= 4:
            if self.rx_buffer[0] == 0x5A and self.rx_buffer[1] == 0xA5:
                length = self.rx_buffer[2]
                if len(self.rx_buffer) >= 3 + length + 1:
                    calc_xor = length
                    for i in range(length):
                        calc_xor ^= self.rx_buffer[3 + i]

                    if calc_xor == self.rx_buffer[3 + length]:
                        cmd = self.rx_buffer[3]
                        data = self.rx_buffer[4: 3 + length]
                        self.process_protocol(cmd, data)
                        self.rx_buffer = self.rx_buffer[4 + length:]
                        continue
                    else:
                        self.rx_buffer.pop(0)
                else:
                    break
            else:
                self.rx_buffer.pop(0)

    def process_protocol(self, cmd, data):
        if cmd == 0x01 and len(data) == 4:
            temp = int.from_bytes(data[0:2], byteorder='big', signed=True) / 10.0
            hum = int.from_bytes(data[2:4], byteorder='big', signed=True) / 10.0

            if temp <= -90.0:
                self.lbl_temp.setText("ERR")
                self.lbl_hum.setText("ERR")
                self.lbl_t_unit.setText("")
                self.lbl_h_unit.setText("")
                self.lbl_temp.setStyleSheet("color: #FF3366;")
                self.lbl_hum.setStyleSheet("color: #FF3366;")
                self.log_sys("ERR", "HTS221 I2C Comm Failure!")
            else:
                self.lbl_temp.setStyleSheet("color: #FF3366;")
                self.lbl_hum.setStyleSheet("color: #00E5FF;")
                self.lbl_t_unit.setText("°C")
                self.lbl_h_unit.setText("%")
                self.lbl_temp.setText(f"{temp:.1f}")
                self.lbl_hum.setText(f"{hum:.1f}")
                self.log_sys("RX", f"Telemetry: {temp:.1f}C, {hum:.1f}%")

        elif cmd == 0x02:
            m_states = ["STOP", "FORWARD", "REVERSE"]
            m_idx = data[0] if data[0] < 3 else 0
            self.lbl_motor.setText(f"STATUS: [ {m_states[m_idx]} ]")

            if len(data) >= 3:
                spd = data[2]
                if m_idx == 0:
                    self.lbl_speed.setText("")
                else:
                    self.lbl_speed.setText(f"SPEED: [ {spd}% ]")

                self.slider_speed.blockSignals(True)
                self.slider_speed.setValue(spd)
                self.slider_speed.blockSignals(False)

                c_idx = data[1] % 8
                self.log_sys("RX", f"State Sync: Motor={m_states[m_idx]}, Speed={spd}%, RGB={self.colors[c_idx]}")
            else:
                c_idx = data[1] % 8
                self.log_sys("RX", f"State Sync: Motor={m_states[m_idx]}, RGB={self.colors[c_idx]}")

            self.lbl_rgb.setText(f"COLOR: [ {self.colors[c_idx]} ]")
            self.combo_rgb.setCurrentIndex(c_idx)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    ex = STM32MonitorApp()
    ex.show()
    sys.exit(app.exec_())