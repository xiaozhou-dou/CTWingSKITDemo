import sys
import serial
import serial.tools.list_ports
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QGridLayout, QLabel, QPushButton,
                             QComboBox, QTextEdit, QFrame, QRadioButton,
                             QButtonGroup, QSplitter, QSlider, QCheckBox)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont, QTextCursor


class STM32MonitorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.serial_port = serial.Serial()
        self.rx_buffer = bytearray()

        # 统计与历史数据
        self.tx_count = 0
        self.rx_count = 0
        self.log_entries = []
        self.min_temp = None
        self.max_temp = None
        self.min_hum = None
        self.max_hum = None

        self.initUI()

        # 轮询定时器 (20ms)
        self.timer = QTimer()
        self.timer.timeout.connect(self.read_serial)
        self.timer.start(20)

    # ==========================================
    # 自定义面板组件生成器
    # ==========================================
    def create_panel(self, title_html, badge_text=None):
        frame = QFrame()
        frame.setProperty("class", "panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 12, 15, 15)
        layout.setSpacing(10)

        header_layout = QHBoxLayout()
        lbl_title = QLabel(title_html)
        lbl_title.setStyleSheet("color: #00E5FF; font-weight: bold; font-size: 10pt; font-family: 'Segoe UI', Arial;")
        header_layout.addWidget(lbl_title)

        lbl_badge = None
        if badge_text:
            lbl_badge = QLabel(badge_text)
            lbl_badge.setProperty("class", "badge")
            header_layout.addWidget(lbl_badge)

        header_layout.addStretch()
        layout.addLayout(header_layout)

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #30363d; max-height: 1px;")
        layout.addWidget(line)

        content_layout = QVBoxLayout()
        content_layout.setSpacing(10)
        layout.addLayout(content_layout)

        return frame, content_layout, header_layout, lbl_badge

    def initUI(self):
        self.setWindowTitle('STM32 Industrial Terminal [Cyber Edition]')
        self.resize(1200, 850)
        self.apply_cyber_theme()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # ==========================================
        # 1. 顶部：串口配置与流量统计区
        # ==========================================
        port_frame = QFrame()
        port_frame.setProperty("class", "panel")
        port_layout = QHBoxLayout(port_frame)
        port_layout.setContentsMargins(15, 10, 15, 10)

        lbl_link = QLabel("<b><span style='color:#00E5FF'>●</span> LINK INTERFACE:</b>")
        lbl_link.setStyleSheet("color: #c9d1d9; font-size: 10pt; font-family: 'Segoe UI';")

        self.combo_ports = QComboBox()
        self.combo_ports.setMinimumWidth(250)
        self.refresh_ports()

        lbl_baud = QLabel("BAUD:")
        lbl_baud.setStyleSheet("color: #8b949e; font-family: Consolas; font-size: 9pt;")

        self.combo_baud = QComboBox()
        self.combo_baud.addItems(["9600", "19200", "38400", "57600", "115200"])
        self.combo_baud.setCurrentText("115200")
        self.combo_baud.setStyleSheet("color: #a5b4fc; font-weight: bold;")

        self.btn_refresh = QPushButton("⟳ SCAN PORTS")
        self.btn_refresh.clicked.connect(self.refresh_ports)

        self.btn_connect = QPushButton("▶ CONNECT")
        self.btn_connect.setProperty("class", "btn_connect")
        self.btn_connect.clicked.connect(self.toggle_connection)

        self.lbl_stats = QLabel(
            "<span style='color:#FF9900'>● TX: 0B</span> <span style='color:#30363d'>|</span> <span style='color:#00FF66'>● RX: 0B</span>")
        self.lbl_stats.setFont(QFont("Consolas", 10, QFont.Bold))
        self.lbl_stats.setStyleSheet(
            "background-color: #0d1117; padding: 6px 12px; border: 1px solid #30363d; border-radius: 4px;")

        btn_sim = QPushButton("⚙ STM32 BOARD SIMULATOR")
        btn_sim.setProperty("class", "btn_outline_cyan")

        port_layout.addWidget(lbl_link)
        port_layout.addWidget(self.combo_ports)
        port_layout.addWidget(lbl_baud)
        port_layout.addWidget(self.combo_baud)
        port_layout.addWidget(self.btn_refresh)
        port_layout.addWidget(self.btn_connect)
        port_layout.addStretch()
        port_layout.addWidget(self.lbl_stats)
        port_layout.addSpacing(10)
        port_layout.addWidget(btn_sim)
        main_layout.addWidget(port_frame)

        # ==========================================
        # 2. 中部：数据与控制大屏区
        # ==========================================
        dashboard_layout = QHBoxLayout()
        dashboard_layout.setSpacing(15)

        # ----- 2.1 [传感器大屏面板] -----
        sensor_frame, sensor_vbox, sensor_header, _ = self.create_panel("📈 CORE SENSORS (HTS221)")
        lbl_i2c = QLabel("I2C: 0xBE")
        lbl_i2c.setProperty("class", "badge_right")
        sensor_header.addWidget(lbl_i2c)

        sensor_vbox.addStretch(1)

        # 温度模块
        temp_block = QFrame()
        temp_block.setProperty("class", "sensor_block")
        temp_layout = QHBoxLayout(temp_block)

        lbl_t_icon = QLabel("🌡️")
        lbl_t_icon.setProperty("class", "icon_box_red")
        lbl_t_text = QLabel("<b>TEMP</b><br><span style='font-size:8pt; font-weight:normal;'>Ambient Thermal</span>")
        lbl_t_text.setStyleSheet("color: #8b949e; font-family: 'Segoe UI';")

        self.lbl_temp = QLabel("--.-")
        self.lbl_temp.setFont(QFont("Consolas", 42, QFont.Bold))
        self.lbl_temp.setStyleSheet("color: #FF3366;")
        self.lbl_temp.setMinimumWidth(150)
        self.lbl_temp.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.lbl_t_unit = QLabel("°C")
        self.lbl_t_unit.setFont(QFont("Consolas", 20, QFont.Bold))
        self.lbl_t_unit.setStyleSheet("color: #FF3366;")
        self.lbl_t_unit.setFixedWidth(40)
        self.lbl_t_unit.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        temp_layout.addWidget(lbl_t_icon)
        temp_layout.addWidget(lbl_t_text)
        temp_layout.addStretch()
        temp_layout.addWidget(self.lbl_temp)
        temp_layout.addWidget(self.lbl_t_unit)
        temp_layout.addSpacing(40)

        sensor_vbox.addWidget(temp_block)
        sensor_vbox.addSpacing(20)

        # 湿度模块
        hum_block = QFrame()
        hum_block.setProperty("class", "sensor_block")
        hum_layout = QHBoxLayout(hum_block)

        lbl_h_icon = QLabel("💧")
        lbl_h_icon.setProperty("class", "icon_box_cyan")
        lbl_h_text = QLabel("<b>HUM</b><br><span style='font-size:8pt; font-weight:normal;'>Relative Humidity</span>")
        lbl_h_text.setStyleSheet("color: #8b949e; font-family: 'Segoe UI';")

        self.lbl_hum = QLabel("--.-")
        self.lbl_hum.setFont(QFont("Consolas", 42, QFont.Bold))
        self.lbl_hum.setStyleSheet("color: #00E5FF;")
        self.lbl_hum.setMinimumWidth(150)
        self.lbl_hum.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.lbl_h_unit = QLabel("%")
        self.lbl_h_unit.setFont(QFont("Consolas", 20, QFont.Bold))
        self.lbl_h_unit.setStyleSheet("color: #00E5FF;")
        self.lbl_h_unit.setFixedWidth(40)
        self.lbl_h_unit.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        hum_layout.addWidget(lbl_h_icon)
        hum_layout.addWidget(lbl_h_text)
        hum_layout.addStretch()
        hum_layout.addWidget(self.lbl_hum)
        hum_layout.addWidget(self.lbl_h_unit)
        hum_layout.addSpacing(40)

        sensor_vbox.addWidget(hum_block)
        sensor_vbox.addStretch(1)

        # 极值统计模块
        stats_layout = QHBoxLayout()
        self.lbl_temp_range = QLabel("TEMP RANGE: -- ~ -- °C")
        self.lbl_hum_range = QLabel("HUM RANGE: -- ~ -- %")
        stats_style = "color: #8b949e; font-family: Consolas; font-size: 8pt; font-weight: bold;"
        self.lbl_temp_range.setStyleSheet(stats_style)
        self.lbl_hum_range.setStyleSheet(stats_style)
        stats_layout.addWidget(self.lbl_temp_range)
        stats_layout.addStretch()
        stats_layout.addWidget(self.lbl_hum_range)

        sensor_vbox.addLayout(stats_layout)

        # ----- 2.2 [右侧控制面板] -----
        controls_layout = QVBoxLayout()
        controls_layout.setSpacing(15)
        controls_layout.setContentsMargins(0, 0, 0, 0)

        # 2.2.1 [电机与调速控制]
        motor_frame, motor_vbox, motor_header, _ = self.create_panel("⏱ DRIVE & SPEED CONTROL")
        lbl_pwm = QLabel("TIM3 PWM (PA7)")
        lbl_pwm.setProperty("class", "badge_right")
        motor_header.addWidget(lbl_pwm)

        status_frame = QFrame()
        status_frame.setStyleSheet("background-color: #0d1117; border: 1px solid #30363d; border-radius: 4px;")
        status_hbox = QHBoxLayout(status_frame)
        status_hbox.setContentsMargins(10, 5, 10, 5)

        self.lbl_motor = QLabel("STATUS: [ STOP ]")
        self.lbl_motor.setFont(QFont("Consolas", 11, QFont.Bold))
        self.lbl_motor.setStyleSheet("color: #8b949e;")

        status_hbox.addWidget(self.lbl_motor)
        status_hbox.addStretch()

        hbox_m = QHBoxLayout()
        btn_m_fwd = QPushButton("⟲ FORWARD")
        btn_m_stop = QPushButton("🛑 STOP")
        btn_m_rev = QPushButton("⟳ REVERSE")
        btn_m_fwd.setProperty("class", "btn_outline_gray")
        btn_m_rev.setProperty("class", "btn_outline_gray")
        btn_m_stop.setProperty("class", "btn_danger_solid")

        btn_m_fwd.clicked.connect(lambda: self.send_protocol_cmd(0x0A, [0x01]))
        btn_m_rev.clicked.connect(lambda: self.send_protocol_cmd(0x0A, [0x02]))
        btn_m_stop.clicked.connect(lambda: self.send_protocol_cmd(0x0A, [0x00]))

        hbox_m.addWidget(btn_m_fwd)
        hbox_m.addWidget(btn_m_stop)
        hbox_m.addWidget(btn_m_rev)

        speed_frame = QFrame()
        speed_frame.setStyleSheet("background-color: #0d1117; border: 1px solid #30363d; border-radius: 4px;")
        speed_vbox = QVBoxLayout(speed_frame)
        speed_vbox.setContentsMargins(15, 10, 15, 10)

        speed_top = QHBoxLayout()
        lbl_spd_tag = QLabel("⚡ THROTTLE :")
        lbl_spd_tag.setStyleSheet("color: #a5b4fc; font-weight: bold; font-family: Consolas; font-size: 9pt;")
        self.lbl_speed = QLabel("50%")
        self.lbl_speed.setStyleSheet("color: #00E5FF; font-weight: bold; font-family: Consolas; font-size: 9pt;")
        speed_top.addWidget(lbl_spd_tag)
        speed_top.addStretch()
        speed_top.addWidget(self.lbl_speed)

        speed_mid = QHBoxLayout()
        self.slider_speed = QSlider(Qt.Horizontal)
        self.slider_speed.setRange(0, 100)
        self.slider_speed.setSingleStep(10)
        self.slider_speed.setValue(50)
        self.slider_speed.valueChanged.connect(self.on_speed_changed)
        self.slider_speed.sliderReleased.connect(self.send_speed_cmd)

        self.btn_spd_step = QPushButton("+10%")
        self.btn_spd_step.setProperty("class", "btn_action_small")
        self.btn_spd_step.setFixedWidth(60)
        self.btn_spd_step.clicked.connect(self.step_speed)

        speed_mid.addWidget(self.slider_speed)
        speed_mid.addWidget(self.btn_spd_step)

        tick_layout = QHBoxLayout()
        for tick in ["0%", "25%", "50%", "75%", "100%"]:
            l = QLabel(tick)
            l.setStyleSheet("color: #8b949e; font-size: 8pt; font-family: Consolas;")
            tick_layout.addWidget(l)
            if tick != "100%": tick_layout.addStretch()

        speed_vbox.addLayout(speed_top)
        speed_vbox.addLayout(speed_mid)
        speed_vbox.addLayout(tick_layout)

        motor_vbox.addWidget(status_frame)
        motor_vbox.addLayout(hbox_m)
        motor_vbox.addWidget(speed_frame)

        # 2.2.2 [RGB控制]
        rgb_frame, rgb_vbox, rgb_header, _ = self.create_panel("💡 RGB ILLUMINATION")
        lbl_gpio = QLabel("GPIO: PB2(R) PB10(G) PB11(B)")
        lbl_gpio.setProperty("class", "badge_right")
        rgb_header.addWidget(lbl_gpio)

        rgb_hbox = QHBoxLayout()
        self.combo_rgb = QComboBox()
        self.colors = [
            ("Black", "#161b22", "R:1 G:1 B:1"), ("Red", "#FF3366", "R:0 G:1 B:1"),
            ("Green", "#00FF66", "R:1 G:0 B:1"), ("Yellow", "#FFDD00", "R:0 G:0 B:1"),
            ("Blue", "#3498DB", "R:1 G:1 B:0"), ("Magenta", "#9B59B6", "R:0 G:1 B:0"),
            ("Cyan", "#00E5FF", "R:1 G:0 B:0"), ("White", "#FFFFFF", "R:0 G:0 B:0")
        ]
        self.combo_rgb.addItems([c[0] for c in self.colors])

        btn_rgb_set = QPushButton("ENGAGE")
        btn_rgb_set.setProperty("class", "btn_action")
        btn_rgb_set.clicked.connect(lambda: self.send_protocol_cmd(0x0B, [self.combo_rgb.currentIndex()]))

        self.lbl_rgb = QLabel("COLOR: [ Black ]")
        self.lbl_rgb.setStyleSheet(
            "background-color: #0d1117; padding: 4px 8px; border: 1px solid #30363d; border-radius: 3px; color: #8b949e; font-family: Consolas; font-weight: bold;")

        rgb_hbox.addWidget(self.combo_rgb)
        rgb_hbox.addWidget(btn_rgb_set)
        rgb_hbox.addStretch()
        rgb_hbox.addWidget(self.lbl_rgb)

        # RGB 快速拾色器与引脚状态 (彻底修复高低不平现象)
        swatch_frame = QFrame()
        swatch_frame.setStyleSheet("background-color: #0d1117; border: 1px solid #30363d; border-radius: 4px;")
        swatch_hbox = QHBoxLayout(swatch_frame)
        swatch_hbox.setContentsMargins(10, 8, 10, 8)
        swatch_hbox.setSpacing(8)
        swatch_hbox.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        for idx, (name, hex_code, pins) in enumerate(self.colors):
            btn = QPushButton()
            btn.setFixedSize(24, 24)
            # 通过 QSS 直接剥离默认按钮导致的高低差
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {hex_code};
                    border: 2px solid #30363d;
                    border-radius: 12px;
                }}
                QPushButton:hover {{
                    border: 2px solid #00E5FF;
                }}
            """)
            btn.setToolTip(name)
            btn.clicked.connect(lambda checked, i=idx: self.apply_rgb_preset(i))
            swatch_hbox.addWidget(btn)

        swatch_hbox.addStretch()

        self.lbl_rgb_pins = QLabel("R:1  G:1  B:1")
        self.lbl_rgb_pins.setStyleSheet(
            "color: #8b949e; font-family: Consolas; font-size: 9pt; background-color: #21262d; padding: 3px 6px; border-radius: 3px;")
        swatch_hbox.addWidget(self.lbl_rgb_pins)

        rgb_vbox.addLayout(rgb_hbox)
        rgb_vbox.addWidget(swatch_frame)

        controls_layout.addWidget(motor_frame)
        controls_layout.addWidget(rgb_frame)

        # 组合大屏 (左:右 = 45:55)
        dashboard_layout.addWidget(sensor_frame, 45)
        dashboard_layout.addLayout(controls_layout, 55)
        main_layout.addLayout(dashboard_layout, 1)

        # ==========================================
        # 3. 底部：通信终端 (QSplitter 实现弹性拉伸)
        # ==========================================
        terminal_splitter = QSplitter(Qt.Horizontal)

        # ----- 3.1 协议解析日志区 -----
        log_frame, log_layout, log_header, self.lbl_log_count = self.create_panel(">_ PROTOCOL LOG", "(0)")

        filter_hbox = QHBoxLayout()
        filter_hbox.addWidget(QLabel("Filter:"))
        self.combo_filter = QComboBox()
        self.combo_filter.addItems(["▽ ALL", "▽ SYS", "▽ RX", "▽ TX", "▽ ERR"])
        self.combo_filter.setProperty("class", "combo_filter")
        self.combo_filter.currentTextChanged.connect(self.render_logs)

        self.btn_copy_log = QPushButton("⎘")
        self.btn_copy_log.setProperty("class", "btn_icon_gray")
        self.btn_copy_log.setToolTip("Copy Logs")
        self.btn_copy_log.setFixedSize(30, 26)
        self.btn_copy_log.clicked.connect(self.copy_logs)

        btn_clear_log = QPushButton("🗑 CLEAR LOG")
        btn_clear_log.setProperty("class", "btn_outline_gray_small")
        btn_clear_log.clicked.connect(self.clear_logs)

        log_header.addWidget(self.combo_filter)
        log_header.addWidget(self.btn_copy_log)
        log_header.addWidget(btn_clear_log)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setProperty("class", "terminal")

        log_bottom = QHBoxLayout()
        self.chk_autoscroll = QCheckBox("Auto-scroll to bottom")
        self.chk_autoscroll.setChecked(True)
        self.chk_autoscroll.setStyleSheet("color: #8b949e; font-size: 9pt;")
        lbl_proto = QLabel("Protocol: 0x5A 0xA5 Frame")
        lbl_proto.setStyleSheet("color: #8b949e; font-size: 9pt; font-family: Consolas;")
        log_bottom.addWidget(self.chk_autoscroll)
        log_bottom.addStretch()
        log_bottom.addWidget(lbl_proto)

        log_layout.addWidget(self.log_text)
        log_layout.addLayout(log_bottom)
        terminal_splitter.addWidget(log_frame)

        # ----- 3.2 原始数据收发区 -----
        raw_frame, raw_layout, raw_header, _ = self.create_panel("01/10 RAW TRANSCEIVER (LOOPBACK TEST)")

        rx_ctrl_layout = QHBoxLayout()
        lbl_rx = QLabel("<b>RX DATA:</b>")
        lbl_rx.setStyleSheet("color: #a5b4fc; font-family: Consolas; font-size: 9pt;")

        self.radio_rx_ascii = QRadioButton("ASCII")
        self.radio_rx_hex = QRadioButton("HEX")
        self.radio_rx_hex.setChecked(True)
        rx_group_btn = QButtonGroup(self)
        rx_group_btn.addButton(self.radio_rx_ascii)
        rx_group_btn.addButton(self.radio_rx_hex)

        btn_clear_rx = QPushButton("🗑 CLEAR RX")
        btn_clear_rx.setProperty("class", "btn_outline_gray_small")
        btn_clear_rx.clicked.connect(self.raw_rx_text.clear if hasattr(self, 'raw_rx_text') else lambda: None)

        rx_ctrl_layout.addWidget(lbl_rx)
        rx_ctrl_layout.addSpacing(10)
        rx_ctrl_layout.addWidget(self.radio_rx_ascii)
        rx_ctrl_layout.addWidget(self.radio_rx_hex)
        rx_ctrl_layout.addStretch()
        rx_ctrl_layout.addWidget(btn_clear_rx)

        self.raw_rx_text = QTextEdit()
        self.raw_rx_text.setReadOnly(True)
        self.raw_rx_text.setProperty("class", "terminal_raw")

        tx_ctrl_layout = QHBoxLayout()
        lbl_tx = QLabel("<b>TX DATA:</b>")
        lbl_tx.setStyleSheet("color: #a5b4fc; font-family: Consolas; font-size: 9pt;")

        self.radio_tx_ascii = QRadioButton("ASCII")
        self.radio_tx_hex = QRadioButton("HEX")
        self.radio_tx_hex.setChecked(True)
        tx_group_btn = QButtonGroup(self)
        tx_group_btn.addButton(self.radio_tx_ascii)
        tx_group_btn.addButton(self.radio_tx_hex)

        # 快捷预设指令
        btn_pre_fwd = QPushButton("FWD")
        btn_pre_fwd.setProperty("class", "btn_preset_green")
        btn_pre_fwd.setFixedHeight(24)  # 强制固定高度，确保整体处于同一水平线
        btn_pre_fwd.clicked.connect(lambda: self.apply_raw_preset("5A A5 02 0A 01 09"))

        btn_pre_stop = QPushButton("STOP")
        btn_pre_stop.setProperty("class", "btn_preset_red")
        btn_pre_stop.setFixedHeight(24)
        btn_pre_stop.clicked.connect(lambda: self.apply_raw_preset("5A A5 02 0A 00 08"))

        btn_pre_cyan = QPushButton("RGB:CYAN")
        btn_pre_cyan.setProperty("class", "btn_preset_cyan")
        btn_pre_cyan.setFixedHeight(24)
        btn_pre_cyan.clicked.connect(lambda: self.apply_raw_preset("5A A5 02 0B 06 0F"))

        btn_pre_spd = QPushButton("SPD:80%")
        btn_pre_spd.setProperty("class", "btn_preset_yellow")
        btn_pre_spd.setFixedHeight(24)
        btn_pre_spd.clicked.connect(lambda: self.apply_raw_preset("5A A5 02 0C 50 5E"))

        tx_ctrl_layout.addWidget(lbl_tx)
        tx_ctrl_layout.addSpacing(10)
        tx_ctrl_layout.addWidget(self.radio_tx_ascii)
        tx_ctrl_layout.addWidget(self.radio_tx_hex)
        tx_ctrl_layout.addStretch()
        tx_ctrl_layout.addWidget(btn_pre_fwd)
        tx_ctrl_layout.addWidget(btn_pre_stop)
        tx_ctrl_layout.addWidget(btn_pre_cyan)
        tx_ctrl_layout.addWidget(btn_pre_spd)

        self.raw_tx_input = QTextEdit()
        self.raw_tx_input.setFixedHeight(50)
        self.raw_tx_input.setProperty("class", "terminal_input")
        self.raw_tx_input.setPlaceholderText("Enter hex bytes (e.g. 5A A5 02 0A 01 09)...")

        btn_send_raw = QPushButton("➤ TRANSMIT RAW DATA")
        btn_send_raw.setProperty("class", "btn_action_full")
        btn_send_raw.clicked.connect(self.send_raw_data)

        raw_layout.addLayout(rx_ctrl_layout)
        raw_layout.addWidget(self.raw_rx_text, 1)
        raw_layout.addLayout(tx_ctrl_layout)
        raw_layout.addWidget(self.raw_tx_input)
        raw_layout.addWidget(btn_send_raw)
        terminal_splitter.addWidget(raw_frame)

        # 终端切分布局比例拓宽 (左:右 = 1:1)
        terminal_splitter.setStretchFactor(0, 1)
        terminal_splitter.setStretchFactor(1, 1)
        main_layout.addWidget(terminal_splitter, 2)

    def apply_cyber_theme(self):
        cyber_qss = """
        QMainWindow { background-color: #0d1117; }
        QLabel { color: #c9d1d9; font-family: "Segoe UI", Arial, sans-serif; }

        .panel { 
            background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; 
        }

        .badge {
            color: #8b949e; font-family: Consolas; font-size: 10pt;
        }

        .badge_right {
            background-color: #0d1117; color: #8b949e; border: 1px solid #30363d; 
            border-radius: 3px; padding: 2px 6px; font-family: Consolas; font-size: 8pt;
        }

        /* 修复方框粗细不匀的问题：改为纯色 2px 边框 */
        .sensor_block { 
            background-color: #0d1117; 
            border: 2px solid #005C66; 
            border-radius: 6px;
        }
        .sensor_block:hover {
            border: 2px solid #00E5FF;
            background-color: #161b22;
        }

        .icon_box_red { background-color: rgba(255, 51, 102, 0.1); border: 1px solid rgba(255, 51, 102, 0.3); border-radius: 4px; padding: 8px; font-size: 16pt;}
        .icon_box_cyan { background-color: rgba(0, 229, 255, 0.1); border: 1px solid rgba(0, 229, 255, 0.3); border-radius: 4px; padding: 8px; font-size: 16pt;}

        QPushButton {
            background-color: #21262d; color: #c9d1d9;
            border: 1px solid #30363d; border-radius: 4px; padding: 6px 12px; font-weight: bold; font-family: 'Segoe UI';
        }
        QPushButton:hover { background-color: #30363d; border-color: #8b949e; }
        QPushButton:pressed { background-color: #00E5FF; color: #000000; }

        QPushButton[class="btn_connect"] { background-color: #238636; color: #ffffff; border: none; }
        QPushButton[class="btn_connect"]:hover { background-color: #2ea043; }

        QPushButton[class="btn_danger"] { background-color: #da3633; color: white; border: none; }
        QPushButton[class="btn_danger"]:hover { background-color: #f85149; }

        QPushButton[class="btn_danger_solid"] { background-color: #da3633; color: white; border: none; padding: 12px;}
        QPushButton[class="btn_danger_solid"]:hover { background-color: #f85149; }

        QPushButton[class="btn_outline_cyan"] { background-color: transparent; color: #00E5FF; border: 1px solid #00E5FF; }
        QPushButton[class="btn_outline_cyan"]:hover { background-color: rgba(0, 229, 255, 0.1); }

        QPushButton[class="btn_outline_gray"] { background-color: #21262d; color: #c9d1d9; border: 1px solid #30363d; padding: 12px;}
        QPushButton[class="btn_outline_gray"]:hover { background-color: #30363d; }

        QPushButton[class="btn_outline_gray_small"] { background-color: transparent; color: #c9d1d9; border: 1px solid #30363d; border-radius: 4px; padding: 4px 10px; font-size: 8pt; font-family: Consolas;}
        QPushButton[class="btn_outline_gray_small"]:hover { background-color: #21262d; border-color: #8b949e; }

        QPushButton[class="btn_icon_gray"] { background-color: transparent; color: #8b949e; border: 1px solid #30363d; border-radius: 4px; font-size: 11pt; padding: 2px 4px; }
        QPushButton[class="btn_icon_gray"]:hover { background-color: #21262d; color: #c9d1d9; border-color: #8b949e; }

        QPushButton[class="btn_action"] { background-color: #005cc5; color: white; border: none; padding: 6px 15px;}
        QPushButton[class="btn_action"]:hover { background-color: #0366d6; }

        QPushButton[class="btn_action_small"] { background-color: #005cc5; color: white; border: none; padding: 4px;}
        QPushButton[class="btn_action_small"]:hover { background-color: #0366d6; }

        QPushButton[class="btn_action_full"] { background-color: #005cc5; color: white; border: none; padding: 10px;}
        QPushButton[class="btn_action_full"]:hover { background-color: #0366d6; }

        QPushButton[class="btn_preset_green"] { background-color: #21262d; color: #00FF66; font-size: 8pt; padding: 3px 6px; font-family: Consolas;}
        QPushButton[class="btn_preset_red"] { background-color: #21262d; color: #FF3366; font-size: 8pt; padding: 3px 6px; font-family: Consolas;}
        QPushButton[class="btn_preset_cyan"] { background-color: #21262d; color: #00E5FF; font-size: 8pt; padding: 3px 6px; font-family: Consolas;}
        QPushButton[class="btn_preset_yellow"] { background-color: #21262d; color: #FFDD00; font-size: 8pt; padding: 3px 6px; font-family: Consolas;}

        QComboBox {
            background-color: #0d1117; color: #c9d1d9; font-weight: bold; font-family: 'Segoe UI';
            border: 1px solid #30363d; border-radius: 4px; padding: 5px;
        }
        QComboBox:drop-down { border: none; }
        QComboBox QAbstractItemView { background-color: #161b22; color: #c9d1d9; selection-background-color: #00E5FF; selection-color: black;}

        QComboBox[class="combo_filter"] {
            background-color: transparent; color: #8b949e; border: 1px solid #30363d; 
            border-radius: 4px; padding: 3px 8px; font-weight: bold; font-size: 9pt; font-family: Consolas;
        }
        QComboBox[class="combo_filter"]:hover { background-color: #21262d; color: #c9d1d9; }
        QComboBox[class="combo_filter"]::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 15px; border-left: none; }

        QTextEdit { background-color: #010409; color: #00FF66; border: 1px solid #30363d; border-radius: 4px; font-family: Consolas, monospace; }
        QTextEdit[class="terminal"] { font-size: 9pt; padding: 8px; line-height: 1.5;}
        QTextEdit[class="terminal_raw"] { color: #E5E5E5; font-size: 9pt; padding: 8px; }
        QTextEdit[class="terminal_input"] { color: #00E5FF; font-size: 10pt; background-color: #0d1117; padding: 5px; border: 1px solid #005cc5;}

        QRadioButton { color: #a5b4fc; font-weight: bold; font-family: Consolas; font-size: 9pt;}
        QRadioButton::indicator { width: 12px; height: 12px; border-radius: 6px; border: 2px solid #30363d; background-color: #0d1117; }
        QRadioButton::indicator:checked { background-color: #00E5FF; border: 2px solid #00E5FF; }

        QSplitter::handle { background-color: transparent; margin: 0px; }

        QSlider::groove:horizontal { border: 1px solid #30363d; height: 6px; background: #010409; border-radius: 3px; }
        QSlider::sub-page:horizontal { background: #00E5FF; border-radius: 3px; }
        QSlider::add-page:horizontal { background: #161b22; border-radius: 3px; }
        QSlider::handle:horizontal { background: #ffffff; border: 2px solid #00E5FF; width: 14px; margin: -5px 0; border-radius: 7px; }
        QSlider::handle:horizontal:hover { background: #00E5FF; }

        QCheckBox { color: #8b949e; font-size: 9pt; }
        QCheckBox::indicator { width: 14px; height: 14px; border-radius: 3px; border: 1px solid #30363d; background-color: #0d1117; }
        QCheckBox::indicator:checked { background-color: #00E5FF; border: 1px solid #00E5FF; }
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
            baud = int(self.combo_baud.currentText())
            if port:
                try:
                    self.serial_port.port = port
                    self.serial_port.baudrate = baud
                    self.serial_port.timeout = 0
                    self.serial_port.open()
                    self.btn_connect.setText("⏹ DISCONNECT")
                    self.btn_connect.setProperty("class", "btn_danger")
                    self.btn_connect.style().unpolish(self.btn_connect)
                    self.btn_connect.style().polish(self.btn_connect)
                    self.combo_ports.setEnabled(False)
                    self.combo_baud.setEnabled(False)
                    self.log_sys("SYS", f"Data Link Established: {port} @ {baud} bps")
                except Exception as e:
                    self.log_sys("ERR", str(e))
        else:
            self.serial_port.close()
            self.btn_connect.setText("▶ CONNECT")
            self.btn_connect.setProperty("class", "btn_connect")
            self.btn_connect.style().unpolish(self.btn_connect)
            self.btn_connect.style().polish(self.btn_connect)
            self.combo_ports.setEnabled(True)
            self.combo_baud.setEnabled(True)
            self.log_sys("SYS", "Data Link Terminated.")

    def update_stats(self):
        self.lbl_stats.setText(
            f"<span style='color:#FF9900'>● TX: {self.tx_count}B</span> <span style='color:#30363d'>|</span> <span style='color:#00FF66'>● RX: {self.rx_count}B</span>")

    def update_log_count(self):
        self.lbl_log_count.setText(f"({len(self.log_entries)})")

    def log_sys(self, tag, message, raw_hex=None):
        self.log_entries.append({"tag": tag, "msg": message, "hex": raw_hex})
        if len(self.log_entries) > 500:
            self.log_entries.pop(0)

        self.update_log_count()

        filter_tag = self.combo_filter.currentText().replace("▽ ", "").strip()
        if filter_tag == "ALL" or filter_tag == tag:
            self.append_single_log(tag, message, raw_hex)

    def get_tag_color(self, tag):
        if tag == "ERR":
            return "#FF3366"
        elif tag == "TX":
            return "#FF9900"
        elif tag == "SYS":
            return "#00E5FF"
        return "#00FF66"

    def append_single_log(self, tag, message, raw_hex):
        color = self.get_tag_color(tag)
        hex_str = f" <span style='color:#8b949e;'>({raw_hex})</span>" if raw_hex else ""
        self.log_text.append(
            f"<span style='color:{color}; font-weight:bold;'>[{tag}]</span> <span style='color:#c9d1d9;'>{message}</span>{hex_str}")
        if self.chk_autoscroll.isChecked():
            self.log_text.moveCursor(QTextCursor.End)

    def render_logs(self):
        self.log_text.clear()
        filter_tag = self.combo_filter.currentText().replace("▽ ", "").strip()
        html = ""
        for entry in self.log_entries:
            if filter_tag == "ALL" or filter_tag == entry["tag"]:
                color = self.get_tag_color(entry["tag"])
                hex_str = f" <span style='color:#8b949e;'>({entry['hex']})</span>" if entry['hex'] else ""
                html += f"<span style='color:{color}; font-weight:bold;'>[{entry['tag']}]</span> <span style='color:#c9d1d9;'>{entry['msg']}</span>{hex_str}<br>"
        self.log_text.setHtml(html)
        if self.chk_autoscroll.isChecked():
            self.log_text.moveCursor(QTextCursor.End)

    def copy_logs(self):
        text = self.log_text.toPlainText()
        QApplication.clipboard().setText(text)
        self.btn_copy_log.setText("✓")
        self.btn_copy_log.setStyleSheet("color: #00FF66;")
        QTimer.singleShot(1500, self.reset_copy_btn)

    def reset_copy_btn(self):
        self.btn_copy_log.setText("⎘")
        self.btn_copy_log.setStyleSheet("")

    def clear_logs(self):
        self.log_entries.clear()
        self.log_text.clear()
        self.update_log_count()

    def append_raw_rx(self, data_bytes):
        if self.radio_rx_hex.isChecked():
            text = " ".join([f"{x:02X}" for x in data_bytes]) + " "
        else:
            text = data_bytes.decode('ascii', errors='replace')

        self.raw_rx_text.moveCursor(QTextCursor.End)
        self.raw_rx_text.insertPlainText(text)
        self.raw_rx_text.moveCursor(QTextCursor.End)

    def apply_rgb_preset(self, idx):
        self.combo_rgb.setCurrentIndex(idx)
        self.send_protocol_cmd(0x0B, [idx])

    def apply_raw_preset(self, hex_str):
        self.radio_tx_hex.setChecked(True)
        self.raw_tx_input.setText(hex_str)

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
        self.tx_count += len(frame)
        self.update_stats()

        hex_str = " ".join([f"{x:02X}" for x in frame])
        self.log_sys("TX", f"Cmd:0x{cmd:02X} Payload Sent", hex_str)

    def on_speed_changed(self, value):
        snapped_val = round(value / 10) * 10
        if snapped_val != value:
            self.slider_speed.blockSignals(True)
            self.slider_speed.setValue(snapped_val)
            self.slider_speed.blockSignals(False)

        if "STOP" not in self.lbl_motor.text():
            self.lbl_speed.setText(f"{snapped_val}%")
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
            self.tx_count += len(data_to_send)
            self.update_stats()
            self.log_sys("TX", f"RAW TRANSMIT: {len(data_to_send)} bytes")
        except ValueError:
            self.log_sys("ERR", "Invalid HEX format in TX window!")

    def read_serial(self):
        if not self.serial_port.is_open: return

        waiting = self.serial_port.in_waiting
        if waiting:
            raw_data = self.serial_port.read(waiting)
            self.rx_count += len(raw_data)
            self.update_stats()
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
                        raw_frame_hex = " ".join([f"{x:02X}" for x in self.rx_buffer[:4 + length]])

                        self.process_protocol(cmd, data, raw_frame_hex)
                        self.rx_buffer = self.rx_buffer[4 + length:]
                        continue
                    else:
                        self.rx_buffer.pop(0)
                else:
                    break
            else:
                self.rx_buffer.pop(0)

    def process_protocol(self, cmd, data, raw_frame_hex):
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
                self.log_sys("ERR", "HTS221 I2C Comm Failure!", raw_frame_hex)
            else:
                if self.min_temp is None or temp < self.min_temp: self.min_temp = temp
                if self.max_temp is None or temp > self.max_temp: self.max_temp = temp
                if self.min_hum is None or hum < self.min_hum: self.min_hum = hum
                if self.max_hum is None or hum > self.max_hum: self.max_hum = hum

                self.lbl_temp_range.setText(f"TEMP RANGE: {self.min_temp:.1f}° ~ {self.max_temp:.1f}°C")
                self.lbl_hum_range.setText(f"HUM RANGE: {self.min_hum:.1f}% ~ {self.max_hum:.1f}%")

                self.lbl_temp.setStyleSheet("color: #FF3366;")
                self.lbl_hum.setStyleSheet("color: #00E5FF;")
                self.lbl_t_unit.setText("°C")
                self.lbl_h_unit.setText("%")
                self.lbl_temp.setText(f"{temp:.1f}")
                self.lbl_hum.setText(f"{hum:.1f}")
                self.log_sys("RX", f"Telemetry: {temp:.1f}C, {hum:.1f}%", raw_frame_hex)

        elif cmd == 0x02:
            m_states = ["STOP", "FORWARD", "REVERSE"]
            m_idx = data[0] if data[0] < 3 else 0

            if m_idx == 0:
                self.lbl_motor.setStyleSheet("color: #8b949e;")
            elif m_idx == 1:
                self.lbl_motor.setStyleSheet("color: #00FF66;")
            else:
                self.lbl_motor.setStyleSheet("color: #FFDD00;")

            self.lbl_motor.setText(f"STATUS: [ {m_states[m_idx]} ]")

            if len(data) >= 3:
                spd = data[2]
                if m_idx == 0:
                    self.lbl_speed.setText("")
                else:
                    self.lbl_speed.setText(f"{spd}%")

                self.slider_speed.blockSignals(True)
                self.slider_speed.setValue(spd)
                self.slider_speed.blockSignals(False)

                c_idx = data[1] % 8
                self.log_sys("RX", f"State Sync: Motor={m_states[m_idx]}, Speed={spd}%, RGB={self.colors[c_idx][0]}",
                             raw_frame_hex)
            else:
                c_idx = data[1] % 8
                self.log_sys("RX", f"State Sync: Motor={m_states[m_idx]}, RGB={self.colors[c_idx][0]}", raw_frame_hex)

            self.lbl_rgb.setText(f"COLOR: [ {self.colors[c_idx][0]} ]")
            self.lbl_rgb_pins.setText(self.colors[c_idx][2])
            self.combo_rgb.setCurrentIndex(c_idx)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    ex = STM32MonitorApp()
    ex.show()
    sys.exit(app.exec_())