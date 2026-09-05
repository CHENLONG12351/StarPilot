from __future__ import annotations

from openpilot.system.hardware import HARDWARE
from openpilot.selfdrive.ui.lib.starpilot_state import starpilot_state
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.lib.multilang import tr, tr_noop
from openpilot.system.ui.widgets import DialogResult
from openpilot.system.ui.widgets.option_dialog import MultiOptionDialog

from openpilot.selfdrive.ui.layouts.settings.starpilot.panel import _SettingsPage
from openpilot.selfdrive.ui.layouts.settings.starpilot.aethergrid import (
  DEFAULT_PANEL_STYLE,
  AetherSettingsView,
  CardHubManagerView,
  ParentToggle,
  SettingRow,
  SettingSection,
  AetherSliderDialog,
)


def _confirm_reboot_toggle(params, key, state):
  params.put_bool(key, state)
  from openpilot.selfdrive.ui.ui_state import ui_state
  if ui_state.started:
    from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog
    gui_app.push_widget(ConfirmDialog(
      tr("需要重启。现在重启吗？"), tr("重启"), tr("取消"),
      callback=lambda res: HARDWARE.reboot() if res == DialogResult.CONFIRM else None,
    ))


PANEL_STYLE = DEFAULT_PANEL_STYLE
_LATERAL_TUNE_KEYS = ["TurnDesires", "NNFF", "NNFFLite", "ForceTorqueController"]
_ADVANCED_LATERAL_KEYS = ["ForceAutoTune", "ForceAutoTuneOff"]


def _sync_parent(params, parent_key, child_keys):
  if any(params.get_bool(k) for k in child_keys):
    if not params.get_bool(parent_key):
      params.put_bool(parent_key, True)
  else:
    if params.get_bool(parent_key):
      params.put_bool(parent_key, False)


# ═══════════════════════════════════════════════════════════════
# SteeringManagerView — 3-card category hub
# ═══════════════════════════════════════════════════════════════

class SteeringManagerView(CardHubManagerView):
  def __init__(self, controller, **kwargs):
    super().__init__(controller, [], **kwargs)

  def _build_cards(self):
    cards = [
      {
        "title": tr("转向行为"),
        "desc": tr("配置常开转向(AOL)、暂停速度阈值和转向灯行为。"),
        "icon": "steering",
        "on_click": lambda: self._controller._navigate_to("behavior"),
      },
      {
        "title": tr("车道变更"),
        "desc": tr("配置自动变道、速度/宽度阈值和平滑参数。"),
        "icon": "road",
        "on_click": lambda: self._controller._navigate_to("lane_changes"),
      },
      {
        "title": tr("高级转向调校"),
        "desc": tr("调整执行器延迟、转向比、Kp、摩擦力和神经网络前馈控制器。"),
        "icon": "system",
        "on_click": lambda: self._controller._navigate_to("advanced"),
      },
    ]
    if starpilot_state.car_state.isFord:
      cards.append({
        "title": tr("福特转向调校"),
        "desc": tr("选择福特转向策略，调节预测、变道和速度响应。"),
        "icon": "steering",
        "on_click": lambda: self._controller._navigate_to("ford"),
      })
    return cards


# ═══════════════════════════════════════════════════════════════
# StarPilotLateralLayout — controller
# ═══════════════════════════════════════════════════════════════

class StarPilotLateralLayout(_SettingsPage):

  def __init__(self):
    super().__init__()
    self._build_panels()

  def _make_parent(self, key: str, label: str, subtitle: str = "") -> ParentToggle:
    return ParentToggle(
      label=label,
      subtitle=subtitle,
      get_state=lambda k=key: self._params.get_bool(k),
      set_state=lambda s, k=key: self._params.put_bool(k, s),
    )

  def _build_panels(self):
    p = self._params
    cs = starpilot_state.car_state

    def alt_on():
      return p.get_bool("AdvancedLateralTune")

    def aol_on():
      return p.get_bool("AlwaysOnLateral")

    def lc_on():
      return p.get_bool("LaneChanges")

    def nlc_on():
      return lc_on() and p.get_bool("NudgelessLaneChange")

    def close_gap_on():
      return lc_on() and p.get_bool("LaneChangeCloseGap")

    def pos_on():
      return p.get_bool("PauseLateralOnSignal")

    # ── 1. Steering Behavior ──
    self._behavior_rows = [
      SettingRow(
        "PauseAOLOnBrake", "value", tr_noop("刹车时暂停 AOL"),
        subtitle=tr_noop("踩刹车时在此速度以下暂停 AOL。"),
        get_value=lambda: f"{p.get_int('PauseAOLOnBrake')} mph",
        on_click=lambda: self._show_slider("PauseAOLOnBrake", 0, 100, unit=" mph"),
        visible=aol_on,
      ),
      SettingRow(
        "PauseLateralSpeed", "value", tr_noop("低于此速度暂停转向"),
        subtitle=tr_noop("低于设定速度时暂停转向。"),
        get_value=lambda: f"{p.get_int('PauseLateralSpeed')} mph",
        on_click=self._on_pause_lateral_speed_clicked,
      ),
      SettingRow(
        "PauseLateralOnSignal", "toggle", tr_noop("仅转向灯时暂停"),
        subtitle=tr_noop("仅当转向灯开启时暂停转向。"),
        get_state=lambda: p.get_bool("PauseLateralOnSignal"),
        set_state=lambda s: p.put_bool("PauseLateralOnSignal", s),
      ),
      SettingRow(
        "LateralResumeDelay", "value", tr_noop("恢复延迟"),
        subtitle=tr_noop("转向灯关闭后恢复转向前的延迟。0 = 关闭。"),
        get_value=self._get_resume_delay_display,
        on_click=lambda: self._show_slider("LateralResumeDelay", 0.0, 5.0, step=0.1, unit="s", value_type="float"),
        visible=pos_on,
      ),
      SettingRow(
        "NavDesiresAllowed", "toggle", tr_noop("使用路线意图"),
        subtitle=tr_noop("允许导航请求车道保持和转弯。"),
        get_state=lambda: p.get_bool("NavDesiresAllowed"),
        set_state=lambda s: p.put_bool("NavDesiresAllowed", s),
      ),
    ]

    # ── 2. Lane Changes ──
    self._lane_change_rows = [
      SettingRow(
        "NudgelessLaneChange", "toggle", tr_noop("自动变道"),
        subtitle=tr_noop("打转向灯触发自动变道。"),
        get_state=lambda: p.get_bool("NudgelessLaneChange"),
        set_state=lambda s: p.put_bool("NudgelessLaneChange", s),
        visible=lc_on,
      ),
      SettingRow(
        "OneLaneChange", "toggle", tr_noop("每次信号一次"),
        subtitle=tr_noop("每次打转向灯只变一次道。"),
        get_state=lambda: p.get_bool("OneLaneChange"),
        set_state=lambda s: p.put_bool("OneLaneChange", s),
        visible=nlc_on,
      ),
      SettingRow(
        "MinimumLaneChangeSpeed", "value", tr_noop("最低变道速度"),
        subtitle=tr_noop("openpilot 变道的最低速度。"),
        get_value=lambda: f"{p.get_int('MinimumLaneChangeSpeed')} mph",
        on_click=lambda: self._show_slider("MinimumLaneChangeSpeed", 0, 100, unit=" mph"),
        visible=lc_on,
      ),
      SettingRow(
        "LaneChangeTime", "value", tr_noop("变道延迟"),
        subtitle=tr_noop("自动变道开始前的延迟。0 = 立即。"),
        get_value=self._get_lane_change_delay_display,
        on_click=lambda: self._show_slider("LaneChangeTime", 0.0, 5.0, step=0.1, unit="s", value_type="float"),
        visible=nlc_on,
      ),
      SettingRow(
        "LaneDetectionWidth", "value", tr_noop("最小车道宽度"),
        subtitle=tr_noop("防止变入更窄的车道。"),
        get_value=lambda: f"{p.get_float('LaneDetectionWidth'):.1f} ft",
        on_click=lambda: self._show_slider("LaneDetectionWidth", 0.0, 15.0, step=0.1, unit=" ft", value_type="float"),
        visible=nlc_on,
      ),
      SettingRow(
        "LaneChangeSmoothing", "value", tr_noop("变道平滑度"),
        subtitle=tr_noop("变道执行平滑度。10 = 默认，1 = 最平滑。"),
        get_value=self._get_lane_change_smoothing_display,
        on_click=self._show_lane_smoothing,
        visible=lc_on,
      ),
      SettingRow(
        "LaneChangeCloseGap", "toggle", tr_noop("变道时缩小跟车距离"),
        subtitle=tr_noop("允许变道时临时缩短跟车距离，让 openpilot 平滑并入，变道时可加速。"),
        get_state=lambda: p.get_bool("LaneChangeCloseGap"),
        set_state=lambda s: p.put_bool("LaneChangeCloseGap", s),
        visible=lc_on,
      ),
      SettingRow(
        "LaneChangeCloseGapSeconds", "value", tr_noop("临时跟车距离"),
        subtitle=tr_noop("变道时保持的跟车距离。仅在比正常车距短时生效。"),
        get_value=self._get_lane_change_close_gap_display,
        on_click=lambda: self._show_slider("LaneChangeCloseGapSeconds", 0.25, 1.0, step=0.05, unit="s", value_type="float"),
        visible=close_gap_on,
      ),
    ]

    # ── 3. Advanced Lateral Tuning ──
    self._advanced_rows = [
      SettingRow(
        "NNFF", "toggle", tr_noop("NNFF"),
        subtitle=tr_noop("神经网络前馈转向控制器。"),
        get_state=lambda: p.get_bool("NNFF"),
        set_state=lambda s: (p.put_bool("NNFF", s),
                             s and p.put_bool("NNFFLite", False),
                             _sync_parent(p, "LateralTune", _LATERAL_TUNE_KEYS)),
        enabled=lambda: cs.hasNNFFLog and not cs.isAngleCar,
        disabled_label=tr_noop("不可用"),
        visible=alt_on,
      ),
      SettingRow(
        "NNFFLite", "toggle", tr_noop("NNFF Lite"),
        subtitle=tr_noop("完整模型关闭时的轻量 NNFF。"),
        get_state=lambda: p.get_bool("NNFFLite"),
        set_state=lambda s: (p.put_bool("NNFFLite", s),
                             _sync_parent(p, "LateralTune", _LATERAL_TUNE_KEYS)),
        enabled=lambda: not cs.isAngleCar,
        disabled_label=tr_noop("不可用"),
        visible=alt_on,
      ),
      SettingRow(
        "ForceTorqueController", "toggle", tr_noop("强制扭矩控制"),
        subtitle=tr_noop("基于扭矩的转向，车道保持更顺滑。"),
        get_state=lambda: p.get_bool("ForceTorqueController"),
        set_state=lambda s: (p.put_bool("ForceTorqueController", s),
                             _sync_parent(p, "LateralTune", _LATERAL_TUNE_KEYS)),
        enabled=lambda: not cs.isTorqueCar and not cs.isAngleCar,
        disabled_label=tr_noop("不可用"),
        visible=alt_on,
      ),
      SettingRow(
        "TurnDesires", "toggle", tr_noop("强制转向意图"),
        subtitle=tr_noop("低于最低变道速度时跟随转向意图。"),
        get_state=lambda: p.get_bool("TurnDesires"),
        set_state=lambda s: (p.put_bool("TurnDesires", s),
                             _sync_parent(p, "LateralTune", _LATERAL_TUNE_KEYS)),
        visible=alt_on,
      ),
      SettingRow(
        "ForceAutoTune", "toggle", tr_noop("强制开启自动调校"),
        subtitle=tr_noop("强制开启摩擦力和横向加速度的实时自动调校。"),
        get_state=lambda: p.get_bool("ForceAutoTune"),
        set_state=lambda s: (p.put_bool("ForceAutoTune", s),
                             s and p.put_bool("ForceAutoTuneOff", False),
                             _sync_parent(p, "AdvancedLateralTune", _ADVANCED_LATERAL_KEYS)),
        enabled=lambda: not cs.hasAutoTune and cs.isTorqueCar and not cs.isAngleCar,
        disabled_label=tr_noop("不可用"),
        visible=alt_on,
      ),
      SettingRow(
        "ForceAutoTuneOff", "toggle", tr_noop("强制关闭自动调校"),
        subtitle=tr_noop("强制关闭学习到的横向参数，使用你设定的值。"),
        get_state=lambda: p.get_bool("ForceAutoTuneOff"),
        set_state=lambda s: (p.put_bool("ForceAutoTuneOff", s),
                             s and p.put_bool("ForceAutoTune", False),
                             _sync_parent(p, "AdvancedLateralTune", _ADVANCED_LATERAL_KEYS)),
        enabled=lambda: cs.isTorqueCar and not cs.isAngleCar,
        disabled_label=tr_noop("不可用"),
        visible=alt_on,
      ),
      SettingRow(
        "UseAutoSteerDelay", "toggle", tr_noop("使用自动学习的延迟"),
        subtitle=tr_noop("自动学习完整转向延迟。开启时下方手动值被忽略。"),
        get_state=lambda: p.get_bool("UseAutoSteerDelay"),
        set_state=lambda s: p.put_bool("UseAutoSteerDelay", s),
        visible=lambda: alt_on() and cs.steerActuatorDelay != 0,
      ),
      SettingRow(
        "SteerDelay", "value", tr_noop("执行器延迟"),
        subtitle=tr_noop("转向指令与车辆响应之间的完整延迟。"),
        get_value=lambda: f"{p.get_float('SteerDelay'):.2f}s",
        on_click=lambda: self._show_slider("SteerDelay", 0.01, 1.0, step=0.01, unit="s", value_type="float"),
        enabled=lambda: not p.get_bool("UseAutoSteerDelay"),
        disabled_label=tr_noop("自动学习延迟开启时禁用。"),
        visible=lambda: alt_on() and cs.steerActuatorDelay != 0,
      ),
      SettingRow(
        "SteerFriction", "value", tr_noop("摩擦力"),
        subtitle=tr_noop("补偿方向盘中心附近的转向摩擦。"),
        get_value=lambda: f"{p.get_float('SteerFriction'):.2f}",
        on_click=lambda: self._show_slider("SteerFriction", 0.0, max(1.0, cs.friction * 1.5), step=0.01, value_type="float"),
        visible=lambda: alt_on() and cs.friction != 0 and cs.isTorqueCar and not cs.isAngleCar,
      ),
      SettingRow(
        "SteerKP", "value", tr_noop("Kp 系数"),
        subtitle=tr_noop("openpilot 纠正横向位置的强度。"),
        get_value=lambda: f"{p.get_float('SteerKP'):.2f}",
        on_click=lambda: self._show_slider("SteerKP", max(0.01, cs.steerKp) * 0.5, max(0.01, cs.steerKp) * 1.5, step=0.01, value_type="float"),
        visible=lambda: alt_on() and cs.steerKp != 0 and cs.isTorqueCar and not cs.isAngleCar,
      ),
      SettingRow(
        "SteerLatAccel", "value", tr_noop("横向加速度"),
        subtitle=tr_noop("将转向扭矩映射到转向响应。"),
        get_value=lambda: f"{p.get_float('SteerLatAccel'):.2f}",
        on_click=lambda: self._show_slider("SteerLatAccel", max(0.01, cs.latAccelFactor) * 0.5, max(0.01, cs.latAccelFactor) * 1.5, step=0.01, value_type="float"),
        visible=lambda: alt_on() and cs.latAccelFactor != 0 and cs.isTorqueCar and not cs.isAngleCar,
      ),
      SettingRow(
        "SteerRatio", "value", tr_noop("转向比"),
        subtitle=tr_noop("方向盘角度与车轮角度之间的关系。"),
        get_value=lambda: f"{p.get_float('SteerRatio'):.1f}",
        on_click=lambda: self._show_slider("SteerRatio", max(0.01, cs.steerRatio) * 0.5, max(0.01, cs.steerRatio) * 1.5, step=0.01, value_type="float"),
        visible=lambda: alt_on() and cs.steerRatio != 0,
      ),
    ]

    # ── 4. Ford Lateral Tuning ──
    def ford_curvature_mode():
      return p.get_int("FordLateralMode") == 1

    def ford_angle_mode():
      return p.get_int("FordLateralMode") == 2

    def ford_enhanced_mode():
      return p.get_int("FordLateralMode") != 0

    self._ford_rows = [
      SettingRow(
        "FordLateralMode", "value", tr_noop("转向策略"),
        subtitle=tr_noop("曲率是调校默认。角度模式供对比；原生保留原厂控制。"),
        get_value=self._get_ford_lateral_mode,
        on_click=self._show_ford_lateral_mode,
      ),
      SettingRow(
        "FordHumanTurnDetection", "toggle", tr_noop("手动转向释放"),
        subtitle=tr_noop("持续手打方向时释放横向控制，随后平滑恢复。"),
        get_state=lambda: p.get_bool("FordHumanTurnDetection"),
        set_state=lambda s: p.put_bool("FordHumanTurnDetection", s),
        visible=ford_enhanced_mode,
      ),
      SettingRow(
        "FordCurvatureBlendLow", "value", tr_noop("小弯道预测"),
        subtitle=tr_noop("将模型预测曲率融入缓弯。"),
        get_value=lambda: f"{p.get_float('FordCurvatureBlendLow') * 100:.0f}%",
        on_click=lambda: self._show_slider("FordCurvatureBlendLow", 0.0, 1.0, step=0.05, unit="", value_type="float"),
        visible=ford_curvature_mode,
      ),
      SettingRow(
        "FordCurvatureBlendHigh", "value", tr_noop("大弯道预测"),
        subtitle=tr_noop("将模型预测曲率融入急弯。"),
        get_value=lambda: f"{p.get_float('FordCurvatureBlendHigh') * 100:.0f}%",
        on_click=lambda: self._show_slider("FordCurvatureBlendHigh", 0.0, 1.0, step=0.05, unit="", value_type="float"),
        visible=ford_curvature_mode,
      ),
      SettingRow(
        "FordCurvatureLaneChangeFactor", "value", tr_noop("曲率变道系数"),
        subtitle=tr_noop("曲率模式下高速变道时的转向缩放。"),
        get_value=lambda: f"{p.get_float('FordCurvatureLaneChangeFactor'):.2f}x",
        on_click=lambda: self._show_slider("FordCurvatureLaneChangeFactor", 0.5, 1.25, step=0.05, unit="x", value_type="float"),
        visible=ford_curvature_mode,
      ),
      SettingRow(
        "FordAngleBlend", "value", tr_noop("角度预测混合"),
        subtitle=tr_noop("将模型预测融入路径角度指令。"),
        get_value=lambda: f"{p.get_float('FordAngleBlend') * 100:.0f}%",
        on_click=lambda: self._show_slider("FordAngleBlend", 0.0, 1.0, step=0.05, unit="", value_type="float"),
        visible=ford_angle_mode,
      ),
      SettingRow(
        "FordAngleLowSpeedFactor", "value", tr_noop("低速角度响应"),
        subtitle=tr_noop("调节低速、大曲率时的路径角度强度。"),
        get_value=lambda: f"{p.get_float('FordAngleLowSpeedFactor'):.2f}x",
        on_click=lambda: self._show_slider("FordAngleLowSpeedFactor", 0.5, 1.5, step=0.05, unit="x", value_type="float"),
        visible=ford_angle_mode,
      ),
      SettingRow(
        "FordAngleHighSpeedFactor", "value", tr_noop("高速角度响应"),
        subtitle=tr_noop("调节高速大弯时的路径角度强度。"),
        get_value=lambda: f"{p.get_float('FordAngleHighSpeedFactor'):.2f}x",
        on_click=lambda: self._show_slider("FordAngleHighSpeedFactor", 0.5, 1.5, step=0.05, unit="x", value_type="float"),
        visible=ford_angle_mode,
      ),
      SettingRow(
        "FordAngleHighSpeedDamping", "value", tr_noop("高速阻尼"),
        subtitle=tr_noop("高速时抑制小幅转向修正。"),
        get_value=lambda: f"{p.get_float('FordAngleHighSpeedDamping'):.2f}x",
        on_click=lambda: self._show_slider("FordAngleHighSpeedDamping", 0.25, 1.25, step=0.05, unit="x", value_type="float"),
        visible=ford_angle_mode,
      ),
      SettingRow(
        "FordAngleLaneChangeFactor", "value", tr_noop("角度变道系数"),
        subtitle=tr_noop("角度模式下高速变道时的转向缩放。"),
        get_value=lambda: f"{p.get_float('FordAngleLaneChangeFactor'):.2f}x",
        on_click=lambda: self._show_slider("FordAngleLaneChangeFactor", 0.5, 1.5, step=0.05, unit="x", value_type="float"),
        visible=ford_angle_mode,
      ),
    ]

    self._manager_view = SteeringManagerView(
      self,
      header_title=tr_noop("转向"),
      header_subtitle=tr_noop("配置转向行为和车道变更。"),
    )

    p = self._params
    pt_behavior = ParentToggle(
      label="常开转向 (AOL)",
      subtitle="ACC 关闭时转向保持激活。",
      get_state=lambda: p.get_bool("AlwaysOnLateral"),
      set_state=lambda s: _confirm_reboot_toggle(p, "AlwaysOnLateral", s) if s else p.put_bool("AlwaysOnLateral", False),
    )
    pt_lane_changes = self._make_parent("LaneChanges", "Lane Changes",
      "Allow openpilot to change lanes.")
    pt_advanced = self._make_parent("AdvancedLateralTune", "Advanced Lateral Tuning",
      "Fine-tune steering response and auto-tuning.")

    # Register subpanels for Level 2 slide transitions
    self._sub_panels["behavior"] = AetherSettingsView(
      self,
      [SettingSection(title="", rows=self._behavior_rows)],
      header_title=tr_noop("转向行为"),
      header_subtitle=tr_noop("配置常开转向(AOL)、暂停速度阈值和转向灯行为。"),
      parent_toggle=pt_behavior,
      panel_style=PANEL_STYLE,
    )
    self._sub_panels["lane_changes"] = AetherSettingsView(
      self,
      [SettingSection(title="", rows=self._lane_change_rows)],
      header_title=tr_noop("车道变更"),
      header_subtitle=tr_noop("配置自动变道、速度/宽度阈值和平滑参数。"),
      parent_toggle=pt_lane_changes,
      panel_style=PANEL_STYLE,
    )
    self._sub_panels["advanced"] = AetherSettingsView(
      self,
      [SettingSection(title="", rows=self._advanced_rows)],
      header_title=tr_noop("高级转向调校"),
      header_subtitle=tr_noop("调整执行器延迟、转向比、Kp、摩擦力和神经网络前馈控制器。"),
      parent_toggle=pt_advanced,
      panel_style=PANEL_STYLE,
    )
    self._sub_panels["ford"] = AetherSettingsView(
      self,
      [SettingSection(title="", rows=self._ford_rows)],
      header_title=tr_noop("福特转向调校"),
      header_subtitle=tr_noop("调校福特专属多项式转向，保留原生策略作为回退。"),
      panel_style=PANEL_STYLE,
    )
    self._wire_sub_panels()

  def _on_pause_lateral_speed_clicked(self):
    def on_speed_close(res, val):
      if res == DialogResult.CONFIRM:
        self._params.put_int("PauseLateralSpeed", int(val))
        self._params.put_bool("QOLLateral", int(val) > 0)
    current = self._params.get_int("PauseLateralSpeed")
    gui_app.push_widget(AetherSliderDialog(
      tr("低于此速度暂停转向"), 0, 100, 1, current, on_speed_close,
      unit=" mph", color=self.SLIDER_COLOR))

  def _get_resume_delay_display(self) -> str:
    val = self._params.get_float("LateralResumeDelay")
    if val == 0.0:
      return tr("关闭")
    return f"{val:.1f}s"

  def _get_lane_change_delay_display(self) -> str:
    val = self._params.get_float("LaneChangeTime")
    if val == 0.0:
      return tr("立即")
    return f"{val:.1f}s"

  def _get_lane_change_smoothing_display(self) -> str:
    val = self._params.get_int("LaneChangeSmoothing")
    if val == 0 or val == 10:
      return tr("默认")
    return str(val)

  def _get_lane_change_close_gap_display(self) -> str:
    return f"{self._params.get_float('LaneChangeCloseGapSeconds'):.2f}s"

  def _show_lane_smoothing(self):
    def on_close(res, val):
      if res == DialogResult.CONFIRM:
        self._params.put_int("LaneChangeSmoothing", int(val))
    current = self._params.get_int("LaneChangeSmoothing") if self._params.get_int("LaneChangeSmoothing") > 0 else 5
    gui_app.push_widget(AetherSliderDialog(tr("变道平滑度"), 1, 10, 1, current, on_close,
                                            color=self.SLIDER_COLOR))

  def _get_ford_lateral_mode(self) -> str:
    return tr(("Native", "Curvature", "Angle")[max(0, min(2, self._params.get_int("FordLateralMode")))])

  def _show_ford_lateral_mode(self):
    options = [tr("原生"), tr("曲率"), tr("角度")]
    current = options[max(0, min(2, self._params.get_int("FordLateralMode")))]

    def on_select(res):
      if res == DialogResult.CONFIRM and dialog.selection in options:
        self._params.put_int("FordLateralMode", options.index(dialog.selection))

    dialog = MultiOptionDialog(tr("福特转向策略"), options, current, callback=on_select)
    gui_app.push_widget(dialog)
