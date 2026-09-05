from __future__ import annotations
import re

from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr, tr_noop
from openpilot.system.ui.widgets import DialogResult
from openpilot.system.ui.widgets.option_dialog import MultiOptionDialog

from openpilot.selfdrive.ui.lib.starpilot_state import starpilot_state
from openpilot.selfdrive.ui.layouts.settings.starpilot.panel import _SettingsPage
from openpilot.selfdrive.ui.layouts.settings.starpilot.aethergrid import (
    AetherSliderDialog,
    DEFAULT_PANEL_STYLE,
    ParentToggle,
    SettingRow,
    SettingSection,
    AetherSettingsView,
    CardHubManagerView,
)
from openpilot.selfdrive.ui.layouts.settings.starpilot.simple_download_manager import SimpleDownloadManager
from openpilot.starpilot.common.starpilot_variables import THEME_SAVE_PATH

PANEL_STYLE = DEFAULT_PANEL_STYLE

THEME_KEY_CONFIG = {
    "BootLogo": {
        "default": "starpilot",
        "extra": [],
    },
}

COLOR_PRESETS = ["Stock", "#FFFFFF", "#178644", "#3B82F6", "#E63956", "#8B5CF6", "#F59E0B"]
CAMERA_VIEWS = ["Auto", "Driver", "Standard", "Wide"]

# Keys are the int values stored in DeveloperSidebarMetric{1..7}; values are the
# human-readable labels shown in both the row value and the picker dialog.
DEVELOPER_SIDEBAR_METRIC_OPTIONS: dict[int, str] = {
  0:  "None",
  1:  "Acceleration: Current",
  2:  "Acceleration: Max",
  3:  "Auto Tune: Actuator Delay",
  4:  "Auto Tune: Friction",
  5:  "Auto Tune: Lateral Acceleration",
  6:  "Auto Tune: Steer Ratio",
  7:  "Auto Tune: Stiffness Factor",
  8:  "Engagement %: Lateral",
  9:  "Engagement %: Longitudinal",
  10: "Lateral Control: Steering Angle",
  11: "Lateral Control: Torque % Used",
  12: "Longitudinal Control: Actuator Acceleration Output",
  13: "Longitudinal MPC: Danger Factor",
  14: "Longitudinal MPC Jerk: Acceleration",
  15: "Longitudinal MPC Jerk: Danger Zone",
  16: "Longitudinal MPC Jerk: Speed Control",
  17: "Model Name",
}

def _theme_display_name(value: str) -> str:
    if not value:
        return "Stock"
    if value.lower() == "stock":
        return "Stock"
    if value.lower() == "none":
        return "None"
    base, creator = (value.split("~", 1) + [""])[:2] if "~" in value else (value, "")
    user_created_suffixes = ("-user_created", "_user_created", "-user-created", "_user-created")
    user_created = False
    for suffix in user_created_suffixes:
        if base.endswith(suffix):
            base = base[:-len(suffix)]
            user_created = True
            break
    parts = [part for part in re.split(r"[-_]+", base) if part]
    display = " ".join(part[:1].upper() + part[1:] for part in parts) if parts else value
    if user_created:
        display += " (User Created)"
    if creator:
        display += f" - by: {creator}"
    return display

# ═══════════════════════════════════════════════════════════════
# AppearanceManagerView — 6-card category hub
# ═══════════════════════════════════════════════════════════════

class AppearanceManagerView(CardHubManagerView):
    def __init__(self, controller, sections, **kwargs):
        super().__init__(controller, sections, **kwargs)

    def _build_cards(self):
        return [
            {
                "title": tr("模型与路径可视化"),
                "desc": tr("自定义动态车道路径、道路边缘和颜色。"),
                "icon": "steering",
                "on_click": lambda: self._controller._navigate_to("model"),
            },
            {
                "title": tr("驾驶组件与 HUD"),
                "desc": tr("配置指南针、动态踏板、信号和屏幕边框。"),
                "icon": "display",
                "on_click": lambda: self._controller._navigate_to("hud"),
            },
            {
                "title": tr("屏幕简洁与可见性"),
                "desc": tr("切换限速、提醒横幅和驾驶员监测图标。"),
                "icon": "system",
                "on_click": lambda: self._controller._navigate_to("declutter"),
            },
            {
                "title": tr("导航与地图"),
                "desc": tr("配置道路名称、维也纳标志和离车路线。"),
                "icon": "navigate",
                "on_click": lambda: self._controller._navigate_to("nav"),
            },
            {
                "title": tr("摄像头与系统启动"),
                "desc": tr("管理驾驶员监测摄像头、开机标志和启动声音。"),
                "icon": "vehicle",
                "on_click": lambda: self._controller._navigate_to("system"),
            },
            {
                "title": tr("高级指标"),
                "desc": tr("调整雷达图、前车信息和停车标志指标。"),
                "icon": "sound",
                "on_click": lambda: self._controller._navigate_to("dev"),
            },
        ]


class StarPilotAppearanceLayout(_SettingsPage):
    def __init__(self):
        super().__init__()
        self._build_view()

    def _make_parent(self, key: str, label: str, subtitle: str = "") -> ParentToggle:
        return ParentToggle(
            label=label,
            subtitle=subtitle,
            get_state=lambda k=key: self._params.get_bool(k),
            set_state=lambda s, k=key: self._params.put_bool(k, s),
        )

    def _show_lead_detection_threshold_selector(self):
        def on_close(res, val):
            if res == DialogResult.CONFIRM:
                self._params.put_int("LeadDetectionThreshold", int(val))
        gui_app.push_widget(
            AetherSliderDialog(
                tr("前车检测阈值"),
                25.0, 100.0, 1.0,
                float(self._params.get_int("LeadDetectionThreshold", return_default=True, default=35)),
                on_close,
                presets=[25.0, 50.0, 75.0, 100.0],
                unit="%",
                color=PANEL_STYLE.accent,
            )
        )

    def _set_developer_sidebar(self, enabled):
        self._params.put_bool("DeveloperSidebar", enabled)
        if enabled:
            self._params.put_bool("DeveloperUI", True)

    def _set_developer_metrics(self, enabled):
        self._params.put_bool("DeveloperMetrics", enabled)
        if enabled:
            self._params.put_bool("DeveloperUI", True)

    def _build_view(self):
        po = lambda: self._params.get_bool("PedalsOnUI")
        ol = lambda: starpilot_state.car_state.hasOpenpilotLongitudinal
        bsm = lambda: starpilot_state.car_state.hasBSM
        model_on = lambda: self._params.get_bool("ModelUI")
        hud_on = lambda: self._params.get_bool("CustomUI")
        dev_metrics_on = lambda: self._params.get_bool("DeveloperMetrics")
        dev_sidebar_on = lambda: self._params.get_bool("DeveloperSidebar")

        # ═══ 1. Model & Path Visualization ═══
        self._model_rows = [
            SettingRow("DynamicPathWidth", "toggle", tr_noop("动态路径"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("DynamicPathWidth"),
                       set_state=lambda s: self._params.put_bool("DynamicPathWidth", s),
                       visible=model_on),
            SettingRow("LaneLinesWidth", "value", tr_noop("车道线宽度"),
                       subtitle="",
                       get_value=self._get_lane_lines_display,
                       on_click=lambda: self._show_int_selector("LaneLinesWidth", 0, 24, self._get_lane_lines_unit()),
                       visible=model_on),
            SettingRow("LaneLinesColor", "value", tr_noop("车道线颜色"),
                       subtitle="",
                       get_value=lambda: self._get_color_display("LaneLinesColor"),
                       on_click=lambda: self._show_color_selector("LaneLinesColor"),
                       visible=model_on),
            SettingRow("PathWidth", "value", tr_noop("路径宽度"),
                       subtitle="",
                       get_value=self._get_path_width_display,
                       on_click=self._show_path_width_selector,
                       visible=model_on),
            SettingRow("PathEdgeWidth", "value", tr_noop("路径边缘宽度"),
                       subtitle="",
                       get_value=lambda: f"{self._params.get_int('PathEdgeWidth')}%",
                       on_click=lambda: self._show_int_selector("PathEdgeWidth", 0, 100, "%"),
                       visible=model_on),
            SettingRow("PathEdgesColor", "value", tr_noop("路径边缘颜色"),
                       subtitle="",
                       get_value=lambda: self._get_color_display("PathEdgesColor"),
                       on_click=lambda: self._show_color_selector("PathEdgesColor"),
                       visible=model_on),
            SettingRow("PathColor", "value", tr_noop("路径颜色"),
                       subtitle="",
                       get_value=lambda: self._get_color_display("PathColor"),
                       on_click=lambda: self._show_color_selector("PathColor"),
                       visible=model_on),
            SettingRow("RoadEdgesWidth", "value", tr_noop("道路边缘宽度"),
                       subtitle="",
                       get_value=self._get_road_edges_display,
                       on_click=lambda: self._show_int_selector("RoadEdgesWidth", 0, 24, self._get_road_edges_unit()),
                       visible=model_on),
            SettingRow("RainbowPath", "toggle", tr_noop("彩虹路径"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("RainbowPath"),
                       set_state=lambda s: self._params.put_bool("RainbowPath", s),
                       visible=model_on),
            SettingRow("AccelerationPath", "toggle", tr_noop("加速路径"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("AccelerationPath"),
                       set_state=lambda s: self._params.put_bool("AccelerationPath", s),
                       enabled=ol,
                       visible=model_on),
            SettingRow("AdjacentPath", "toggle", tr_noop("相邻车道"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("AdjacentPath"),
                       set_state=lambda s: self._params.put_bool("AdjacentPath", s),
                       visible=model_on),
            SettingRow("AdjacentPathMetrics", "toggle", tr_noop("相邻车道指标"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("AdjacentPathMetrics"),
                       set_state=lambda s: self._params.put_bool("AdjacentPathMetrics", s),
                       visible=model_on),
            SettingRow("BlindSpotPath", "toggle", tr_noop("盲区路径"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("BlindSpotPath"),
                       set_state=lambda s: self._params.put_bool("BlindSpotPath", s),
                       enabled=bsm,
                       visible=model_on),
        ]

        # ═══ 2. Driving Widgets & HUD ═══
        self._hud_rows = [
            SettingRow("Compass", "toggle", tr_noop("指南针"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("Compass"),
                       set_state=lambda s: self._params.put_bool("Compass", s),
                       visible=hud_on),
            SettingRow("OnroadDistanceButton", "toggle", tr_noop("风格按钮"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("OnroadDistanceButton"),
                       set_state=lambda s: self._params.put_bool("OnroadDistanceButton", s),
                       visible=hud_on),
            SettingRow("RotatingWheel", "toggle", tr_noop("旋转方向盘"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("RotatingWheel"),
                       set_state=lambda s: self._params.put_bool("RotatingWheel", s),
                       visible=hud_on),
            SettingRow("ShowSteering", "toggle", tr_noop("转向扭矩指示器"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("ShowSteering"),
                       set_state=lambda s: self._params.put_bool("ShowSteering", s),
                       visible=hud_on),
            SettingRow("EnableTorqueBarWidget", "toggle", tr_noop("扭矩条"),
                       subtitle=tr_noop("在驾驶界面底部显示曲线扭矩利用率指示器。"),
                       get_state=lambda: self._params.get_bool("EnableTorqueBarWidget"),
                       set_state=lambda s: self._params.put_bool("EnableTorqueBarWidget", s),
                       visible=hud_on),
            SettingRow("SignalMetrics", "toggle", tr_noop("转向灯边框"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("SignalMetrics"),
                       set_state=lambda s: self._params.put_bool("SignalMetrics", s),
                       visible=hud_on),
            SettingRow("BlindSpotMetrics", "toggle", tr_noop("盲区边框"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("BlindSpotMetrics"),
                       set_state=lambda s: self._params.put_bool("BlindSpotMetrics", s),
                       enabled=bsm,
                       visible=hud_on),
            SettingRow("WheelSpeed", "toggle", tr_noop("车轮速度"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("WheelSpeed"),
                       set_state=lambda s: self._params.put_bool("WheelSpeed", s),
                       visible=hud_on),
            SettingRow("BorderWidth", "value", tr_noop("边框宽度"),
                       subtitle="",
                       get_value=lambda: f"{int(round(self._params.get_float('BorderWidth')))}%",
                       on_click=lambda: self._show_float_selector("BorderWidth", 25, 250, 5, "%"),
                       visible=hud_on),
            SettingRow("PedalsOnUI", "toggle", tr_noop("踏板指示器"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("PedalsOnUI"),
                       set_state=lambda s: self._params.put_bool("PedalsOnUI", s),
                       enabled=ol,
                       visible=hud_on),
            SettingRow("DynamicPedalsOnUI", "toggle", tr_noop("动态踏板"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("DynamicPedalsOnUI"),
                       set_state=lambda s: self._set_exclusive_pedal("DynamicPedalsOnUI", "StaticPedalsOnUI", s),
                       enabled=lambda: po() and ol(),
                       visible=hud_on),
            SettingRow("StaticPedalsOnUI", "toggle", tr_noop("静态踏板"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("StaticPedalsOnUI"),
                       set_state=lambda s: self._set_exclusive_pedal("StaticPedalsOnUI", "DynamicPedalsOnUI", s),
                       enabled=lambda: po() and ol(),
                       visible=hud_on),
            SettingRow("StoppedTimer", "toggle", tr_noop("停车计时器"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("StoppedTimer"),
                       set_state=lambda s: self._params.put_bool("StoppedTimer", s)),
            SettingRow("ShowCSCStatus", "toggle", tr_noop("弯道速度控制状态组件"),
                       subtitle=tr_noop("显示弯道速度控制器目标速度和环境边框光晕。"),
                       get_state=lambda: self._params.get_bool("ShowCSCStatus"),
                       set_state=lambda s: self._params.put_bool("ShowCSCStatus", s),
                       visible=hud_on),
        ]

        # ═══ 3. Screen Declutter & Visibility ═══
        self._declutter_rows = [
            SettingRow("HideSpeed", "toggle", tr_noop("隐藏速度"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("HideSpeed"),
                       set_state=lambda s: self._params.put_bool("HideSpeed", s)),
            SettingRow("HideMaxSpeed", "toggle", tr_noop("隐藏最高速度"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("HideMaxSpeed"),
                       set_state=lambda s: self._params.put_bool("HideMaxSpeed", s)),
            SettingRow("HideAlerts", "toggle", tr_noop("隐藏提醒"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("HideAlerts"),
                       set_state=lambda s: self._params.put_bool("HideAlerts", s)),
            SettingRow("HideSteeringWheel", "toggle", tr_noop("隐藏方向盘"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("HideSteeringWheel"),
                       set_state=lambda s: self._params.put_bool("HideSteeringWheel", s)),
            SettingRow("HideDMIcon", "toggle", tr_noop("隐藏驾驶员监测图标"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("HideDMIcon"),
                       set_state=lambda s: self._params.put_bool("HideDMIcon", s)),
            SettingRow("HideLeadMarker", "toggle", tr_noop("隐藏前车标记"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("HideLeadMarker"),
                       set_state=lambda s: self._params.put_bool("HideLeadMarker", s),
                       visible=ol),
            SettingRow("HideChangingLanesBanner", "toggle", tr_noop("隐藏变道横幅"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("HideChangingLanesBanner"),
                       set_state=lambda s: self._params.put_bool("HideChangingLanesBanner", s)),
            SettingRow("HideDistanceProfileBanner", "toggle", tr_noop("隐藏距离曲线横幅"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("HideDistanceProfileBanner"),
                       set_state=lambda s: self._params.put_bool("HideDistanceProfileBanner", s)),
            SettingRow("HideTurningBanner", "toggle", tr_noop("隐藏转向横幅"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("HideTurningBanner"),
                       set_state=lambda s: self._params.put_bool("HideTurningBanner", s)),
        ]

        # ═══ 4. Navigation & Mapping ═══
        self._nav_rows = [
            SettingRow("NavigationUI", "toggle", tr_noop("导航组件"),
                       subtitle=tr_noop("在驾驶界面显示导航信息。"),
                       get_state=lambda: self._params.get_bool("NavigationUI"),
                       set_state=lambda s: self._params.put_bool("NavigationUI", s)),
            SettingRow("CarrotNavUI", "toggle", tr_noop("CP导航卡"),
                       subtitle=tr_noop("在驾驶屏左侧显示CP手机导航数据（转向、限速、倒计时）。"),
                       get_state=lambda: self._params.get_bool("CarrotNavUI"),
                       set_state=lambda s: self._params.put_bool("CarrotNavUI", s)),
            SettingRow("ClearNavOnOffroad", "toggle", tr_noop("离车时清除路线"),
                       subtitle=tr_noop("设备离车时清除活动导航目的地。"),
                       get_state=lambda: self._params.get_bool("ClearNavOnOffroad"),
                       set_state=lambda s: self._params.put_bool("ClearNavOnOffroad", s)),
            SettingRow("RoadNameUI", "toggle", tr_noop("道路名称"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("RoadNameUI"),
                       set_state=lambda s: self._params.put_bool("RoadNameUI", s)),
            SettingRow("ShowSpeedLimits", "toggle", tr_noop("显示限速"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("ShowSpeedLimits"),
                       set_state=lambda s: self._params.put_bool("ShowSpeedLimits", s)),
            SettingRow("UseVienna", "toggle", tr_noop("维也纳标志"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("UseVienna"),
                       set_state=lambda s: self._params.put_bool("UseVienna", s),
                       visible=lambda: self._params.get_bool("ShowSpeedLimits")),
            SettingRow("QOLVisuals", "toggle", tr_noop("舒适便利"),
                       subtitle=tr_noop("日常驾驶的便利功能。"),
                       get_state=lambda: self._params.get_bool("QOLVisuals"),
                       set_state=lambda s: self._params.put_bool("QOLVisuals", s)),
        ]

        # ═══ 5. Camera & System Startup ═══
        self._system_rows = [
            SettingRow("CameraView", "value", tr_noop("摄像头视图"),
                       subtitle="",
                       get_value=lambda: tr(CAMERA_VIEWS[self._params.get_int("CameraView", return_default=True, default=2)]),
                       on_click=self._show_camera_view_selector),
            SettingRow("DriverCamera", "toggle", tr_noop("驾驶员摄像头"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("DriverCamera"),
                       set_state=lambda s: self._params.put_bool("DriverCamera", s)),
            SettingRow("BootLogo", "value", tr_noop("开机标志"),
                       subtitle="",
                       get_value=lambda: self._get_theme_value("BootLogo"),
                       on_click=self._show_boot_logo_manager),
            SettingRow("StartupAlert", "value", tr_noop("启动提醒"),
                       subtitle="",
                       get_value=self._get_startup_alert_display,
                       on_click=self._show_startup_alert_selector),
        ]

        # ═══ 6. Advanced Metrics ═══
        self._dev_rows = [
            SettingRow("DeveloperSidebar", "toggle", tr_noop("开发者侧栏"),
                       subtitle=tr_noop("右侧驾驶指标面板"),
                       get_state=lambda: self._params.get_bool("DeveloperSidebar"),
                       set_state=lambda s: self._set_developer_sidebar(s)),
            SettingRow("LeadDetectionThreshold", "value", tr_noop("前车检测阈值"),
                       subtitle="",
                       get_value=lambda: f"{self._params.get_int('LeadDetectionThreshold', return_default=True, default=35)}%",
                       on_click=self._show_lead_detection_threshold_selector,
                       enabled=ol),
            SettingRow("LeadInfo", "toggle", tr_noop("前车指标"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("LeadInfo"),
                       set_state=lambda s: self._params.put_bool("LeadInfo", s),
                       enabled=ol),
            SettingRow("RadarTracksUI", "toggle", tr_noop("雷达点显示"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("RadarTracksUI"),
                       set_state=lambda s: self._params.put_bool("RadarTracksUI", s),
                       enabled=lambda: starpilot_state.car_state.hasRadar),
            SettingRow("ShowStoppingPoint", "toggle", tr_noop("显示停车标志"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("ShowStoppingPoint"),
                       set_state=lambda s: self._params.put_bool("ShowStoppingPoint", s),
                       enabled=ol),
            SettingRow("ShowStoppingPointMetrics", "toggle", tr_noop("停车距离"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("ShowStoppingPointMetrics"),
                       set_state=lambda s: self._params.put_bool("ShowStoppingPointMetrics", s),
                       enabled=lambda: self._params.get_bool("ShowStoppingPoint") and ol()),
            SettingRow("DeveloperMetrics", "toggle", tr_noop("开发者指标"),
                       subtitle=tr_noop("性能数据、传感器读数和系统指标。"),
                       get_state=lambda: self._params.get_bool("DeveloperMetrics"),
                       set_state=lambda s: self._set_developer_metrics(s)),
            SettingRow("FPSCounter", "toggle", tr_noop("FPS 显示"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("FPSCounter"),
                       set_state=lambda s: self._params.put_bool("FPSCounter", s),
                       visible=dev_metrics_on),
            SettingRow("ShowCPU", "toggle", tr_noop("CPU 指标"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("ShowCPU"),
                       set_state=lambda s: self._params.put_bool("ShowCPU", s),
                       visible=dev_metrics_on),
            SettingRow("ShowGPU", "toggle", tr_noop("GPU 指标"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("ShowGPU"),
                       set_state=lambda s: self._params.put_bool("ShowGPU", s),
                       visible=dev_metrics_on),
            SettingRow("NumericalTemp", "toggle", tr_noop("温度指标"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("NumericalTemp"),
                       set_state=lambda s: self._params.put_bool("NumericalTemp", s),
                       visible=dev_metrics_on),
            SettingRow("ShowMemoryUsage", "toggle", tr_noop("内存指标"),
                       subtitle="",
                       get_state=lambda: self._params.get_bool("ShowMemoryUsage"),
                       set_state=lambda s: self._params.put_bool("ShowMemoryUsage", s),
                       visible=dev_metrics_on),
            SettingRow("DeveloperSidebarMetrics", "value", tr_noop("开发者侧栏指标"),
                       subtitle=tr_noop("选择驾驶界面开发者侧栏显示的指标。"),
                       get_value=lambda: tr("管理"),
                       on_click=lambda: self._navigate_to("dev_sidebar"),
                       visible=dev_sidebar_on),
        ]

        self._dev_sidebar_rows = [
            SettingRow(
                f"DeveloperSidebarMetric{i}",
                "value",
                tr_noop(f"Metric #{i}"),
                subtitle="",
                get_value=lambda i=i: self._get_developer_sidebar_metric_display(i),
                on_click=lambda i=i: self._show_developer_sidebar_metric_selector(i),
                visible=dev_sidebar_on,
            )
            for i in range(1, 8)
        ]

        self._manager_view = AppearanceManagerView(
            self, [],
            header_title=tr_noop("外观"),
            header_subtitle=tr_noop("自定义你的显示、驾驶组件、模型可视化和主题。"),
            tab_defs=None,
            panel_style=PANEL_STYLE,
        )

        pt_model = self._make_parent("ModelUI", "Model UI",
            "Display the driving model path, lanes, and road edges.")
        pt_hud = self._make_parent("CustomUI", "Driving Screen Widgets",
            "Show interactive indicators on the driving screen.")
        pt_declutter = self._make_parent("AdvancedCustomUI", "Advanced UI Controls",
            "Fine-tune which elements appear on screen.")

        # Register subpanels for Level 2 slide transitions
        self._sub_panels["model"] = AetherSettingsView(
            self,
            [SettingSection(title="", rows=self._model_rows)],
            header_title=tr_noop("模型与路径可视化"),
            header_subtitle=tr_noop("自定义动态车道路径、道路边缘和颜色。"),
            parent_toggle=pt_model,
            panel_style=PANEL_STYLE,
        )
        self._sub_panels["hud"] = AetherSettingsView(
            self,
            [SettingSection(title="", rows=self._hud_rows)],
            header_title=tr_noop("驾驶组件与 HUD"),
            header_subtitle=tr_noop("配置指南针、动态踏板、信号和屏幕边框。"),
            parent_toggle=pt_hud,
            panel_style=PANEL_STYLE,
        )
        self._sub_panels["declutter"] = AetherSettingsView(
            self,
            [SettingSection(title="", rows=self._declutter_rows)],
            header_title=tr_noop("屏幕简洁与可见性"),
            header_subtitle=tr_noop("切换限速、提醒横幅和驾驶员监测图标。"),
            parent_toggle=pt_declutter,
            panel_style=PANEL_STYLE,
        )
        self._sub_panels["nav"] = AetherSettingsView(
            self,
            [SettingSection(title="", rows=self._nav_rows)],
            header_title=tr_noop("导航与地图"),
            header_subtitle=tr_noop("配置道路名称、维也纳标志和离车路线。"),
            panel_style=PANEL_STYLE,
        )
        self._sub_panels["system"] = AetherSettingsView(
            self,
            [SettingSection(title="", rows=self._system_rows)],
            header_title=tr_noop("摄像头与系统启动"),
            header_subtitle=tr_noop("管理驾驶员监测摄像头、开机标志和启动声音。"),
            panel_style=PANEL_STYLE,
        )
        self._sub_panels["dev"] = AetherSettingsView(
            self,
            [SettingSection(title="", rows=self._dev_rows)],
            header_title=tr_noop("高级指标"),
            header_subtitle=tr_noop("调整雷达图、前车信息和停车标志指标。"),
            panel_style=PANEL_STYLE,
        )
        self._sub_panels["dev_sidebar"] = AetherSettingsView(
            self,
            [SettingSection(title="", rows=self._dev_sidebar_rows)],
            header_title=tr_noop("开发者侧栏指标"),
            header_subtitle=tr_noop("选择驾驶界面开发者侧栏显示的指标。"),
            panel_style=PANEL_STYLE,
        )
        self._wire_sub_panels()

    # ── Theme helpers ──

    def _build_theme_options(self, key: str) -> tuple[list[str], dict[str, str], str]:
        config = THEME_KEY_CONFIG[key]
        options_map = {display: slug for slug, display in config["extra"]}
        current_slug = self._params.get(key, encoding='utf-8') or config["default"]
        current_display = _theme_display_name(current_slug)
        if current_display not in options_map:
            options_map[current_display] = current_slug
        options = sorted(options_map.keys(), key=str.casefold)
        return options, options_map, current_display

    def _get_theme_value(self, key: str) -> str:
        default = THEME_KEY_CONFIG[key]["default"]
        return _theme_display_name(self._params.get(key, encoding='utf-8') or default)

    def _show_theme_selector(self, key):
        themes, option_map, current = self._build_theme_options(key)
        if not themes:
            return

        def on_select(res):
            if res == DialogResult.CONFIRM and dialog.selection:
                selected_slug = option_map.get(dialog.selection)
                if selected_slug is None:
                    return
                self._params.put(key, selected_slug)

        dialog = MultiOptionDialog(tr(key), themes, current, callback=on_select)
        gui_app.push_widget(dialog)

    # ── Widget helpers ──

    def _set_exclusive_pedal(self, key, other_key, state):
        self._params.put_bool(key, state)
        if state:
            self._params.put_bool(other_key, False)

    # ── Camera view ──

    def _show_camera_view_selector(self):
        current = self._params.get_int("CameraView", return_default=True, default=2)

        def on_select(res):
            if res == DialogResult.CONFIRM and dialog.selection:
                idx = CAMERA_VIEWS.index(dialog.selection)
                self._params.put_int("CameraView", idx)

        dialog = MultiOptionDialog(tr("摄像头视图"), CAMERA_VIEWS, CAMERA_VIEWS[current], callback=on_select)
        gui_app.push_widget(dialog)

    # ── Color selectors ──

    def _get_color_display(self, key):
        val = self._params.get(key, encoding='utf-8') or ""
        if not val:
            return "Stock"
        return val.upper()

    def _show_color_selector(self, key):
        current = self._params.get(key, encoding='utf-8') or "Stock"

        def on_select(res):
            if res == DialogResult.CONFIRM and dialog.selection:
                if dialog.selection == "Stock":
                    self._params.remove(key)
                else:
                    self._params.put(key, dialog.selection)

        dialog = MultiOptionDialog(tr(key), COLOR_PRESETS, current, callback=on_select)
        gui_app.push_widget(dialog)

    # ── Numeric sliders (int / float) ──

    def _show_int_selector(self, key, min_v, max_v, unit=""):
        def on_close(res, val):
            if res == DialogResult.CONFIRM:
                self._params.put_int(key, int(val))
        gui_app.push_widget(AetherSliderDialog(tr(key), min_v, max_v, 1, self._params.get_int(key), on_close,
                                                 unit=unit, color=PANEL_STYLE.accent))

    def _show_float_selector(self, key, min_v, max_v, step, unit="", convert=None, unconvert=None):
        current = self._params.get_float(key)
        if convert:
            current = convert(current)

        def on_close(res, val):
            if res == DialogResult.CONFIRM:
                v = float(val)
                if unconvert:
                    v = unconvert(v)
                self._params.put_float(key, v)

        gui_app.push_widget(AetherSliderDialog(tr(key), min_v, max_v, step, current, on_close,
                                                 unit=unit, color=PANEL_STYLE.accent))

    # ── Unit-aware display helpers ──

    def _is_metric(self):
        return self._params.get_bool("IsMetric")

    def _get_lane_lines_unit(self):
        return "cm" if self._is_metric() else "in"

    def _get_lane_lines_display(self):
        val = self._params.get_int("LaneLinesWidth")
        if self._is_metric():
            return f"{int(val * 2.54)}cm"
        return f"{val}in"

    def _get_road_edges_unit(self):
        return "cm" if self._is_metric() else "in"

    def _get_road_edges_display(self):
        val = self._params.get_int("RoadEdgesWidth")
        if self._is_metric():
            return f"{int(val * 2.54)}cm"
        return f"{val}in"

    def _get_path_width_display(self):
        val = self._params.get_float("PathWidth")
        if self._is_metric():
            return f"{val / 3.28084:.1f}m"
        return f"{val:.1f}ft"

    def _show_path_width_selector(self):
        if self._is_metric():
            self._show_float_selector("PathWidth", 0, 10, 0.1, "m", convert=lambda v: v / 3.28084, unconvert=lambda v: v * 3.28084)
        else:
            self._show_float_selector("PathWidth", 0, 10, 0.1, "ft")

    # ── Startup alert ──

    def _get_startup_alert_display(self):
        current_top = self._params.get("StartupMessageTop", encoding='utf-8') or ""
        if current_top == "Be ready to take over at any time":
            return "Stock"
        if current_top == "Hop in and buckle up!":
            return "StarPilot"
        return "Clear"

    def _show_startup_alert_selector(self):
        options = ["Stock", "StarPilot", "Clear"]
        current = self._get_startup_alert_display()

        def on_select(res):
            if res == DialogResult.CONFIRM and dialog.selection:
                if dialog.selection == "Stock":
                    self._params.put("StartupMessageTop", "Be ready to take over at any time")
                    self._params.put("StartupMessageBottom", "Always keep hands on wheel and eyes on road")
                elif dialog.selection == "StarPilot":
                    self._params.put("StartupMessageTop", "Hop in and buckle up!")
                    self._params.put("StartupMessageBottom", "Human-tested, frog-approved")
                else:
                    self._params.remove("StartupMessageTop")
                    self._params.remove("StartupMessageBottom")

        dialog = MultiOptionDialog(tr("启动提醒"), options, current, callback=on_select)
        gui_app.push_widget(dialog)

    # ── Developer sidebar metric selectors ──

    def _show_developer_sidebar_metric_selector(self, idx: int):
        key = f"DeveloperSidebarMetric{idx}"
        current_int = self._params.get_int(key)
        options = list(DEVELOPER_SIDEBAR_METRIC_OPTIONS.values())
        current_display = DEVELOPER_SIDEBAR_METRIC_OPTIONS.get(current_int, tr("无"))

        def on_select(res):
            if res == DialogResult.CONFIRM and dialog.selection:
                selected_int = next(
                    (k for k, v in DEVELOPER_SIDEBAR_METRIC_OPTIONS.items() if v == dialog.selection),
                    0,
                )
                self._params.put_int(key, selected_int)

        dialog = MultiOptionDialog(tr(f"Metric #{idx}"), options, current_display, callback=on_select)
        gui_app.push_widget(dialog)

    def _get_developer_sidebar_metric_display(self, idx: int) -> str:
        val = self._params.get_int(f"DeveloperSidebarMetric{idx}")
        return tr(DEVELOPER_SIDEBAR_METRIC_OPTIONS.get(val, "None"))

    # ── Boot logo manager ──

    def _show_boot_logo_manager(self):
        def on_close(res, val):
            pass

        gui_app.push_widget(SimpleDownloadManager(
            title=tr("开机标志"),
            asset_type="boot logo",
            directory=THEME_SAVE_PATH / "bootlogos",
            asset_param="BootLogo",
            download_param="BootLogoToDownload",
            downloadable_list_param="DownloadableBootLogos",
            params=self._params,
            params_memory=self._params_memory,
            on_close=on_close,
        ))
