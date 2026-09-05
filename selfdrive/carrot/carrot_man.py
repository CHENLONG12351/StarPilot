# StarPilot port of CarrotPilot's carrot_man (m2 branch), trimmed to the
# CPlink phone-app bridge: UDP 7706 navi JSON + 12345 kisa + 20 Hz publish
# loop. CP's own CarrotNavi HTTP server, zmq debug console and FTP telemetry
# are intentionally not ported.
import fcntl
import json
import math
import os
import socket
import struct
import threading
import time
import traceback
from typing import Any, Dict, List, Optional

import numpy as np

import cereal.messaging as messaging
from openpilot.common.realtime import Ratekeeper
from openpilot.common.params import Params
from openpilot.common.gps import get_gps_location_service
from openpilot.system.hardware import PC

from openpilot.selfdrive.carrot.carrot_serv import CarrotServ

try:
  from shapely.geometry import LineString
  SHAPELY_AVAILABLE = True
except ImportError:
  SHAPELY_AVAILABLE = False

NAVI_ROUTE_MAX_POINTS = 4096

# 국가법령정보센터: 도로설계기준
V_CURVE_LOOKUP_BP = [0., 1./800., 1./670., 1./560., 1./440., 1./360., 1./265., 1./190., 1./135., 1./85., 1./55., 1./30., 1./25.]
V_CRUVE_LOOKUP_VALS = [300, 150, 120, 110, 100, 90, 80, 70, 60, 50, 40, 15, 5]


def limit_route_points(points, max_points=NAVI_ROUTE_MAX_POINTS):
  if max_points <= 0:
    return []
  count = len(points)
  if count <= max_points:
    return list(points)

  limited = []
  last_index = count - 1
  previous_index = -1
  for i in range(max_points):
    source_index = round(i * last_index / max(1, max_points - 1))
    if source_index == previous_index:
      continue
    limited.append(points[source_index])
    previous_index = source_index
  return limited


def haversine(lon1, lat1, lon2, lat2):
  R = 6371000  # Radius of Earth in meters
  phi1, phi2 = math.radians(lat1), math.radians(lat2)
  dphi = math.radians(lat2 - lat1)
  dlambda = math.radians(lon2 - lon1)

  a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
  distance = 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))
  return distance


def closest_point_on_segment(p1, p2, current_position):
  x1, y1 = p1
  x2, y2 = p2
  px, py = current_position

  dx = x2 - x1
  dy = y2 - y1
  if dx == 0 and dy == 0:
    return p1

  t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
  t = max(0, min(1, t))

  closest_x = x1 + t * dx
  closest_y = y1 + t * dy

  return (closest_x, closest_y)


def get_path_after_distance(start_index, coordinates, current_position, distance_m):
  total_distance = 0
  path_after_distance = []
  closest_index = -1
  closest_point = None
  min_distance = float('inf')

  start_index = max(0, start_index - 2)

  for i in range(start_index, len(coordinates) - 1):
    p1 = coordinates[i]
    p2 = coordinates[i + 1]
    candidate_point = closest_point_on_segment(p1, p2, current_position)
    distance = haversine(current_position[0], current_position[1], candidate_point[0], candidate_point[1])

    if distance < min_distance:
      min_distance = distance
      closest_point = candidate_point
      closest_index = i
    elif distance > min_distance and min_distance < 10:
      break

  start_index = closest_index
  if closest_index != -1:
    path_after_distance.append(closest_point)

    path_after_distance.append(coordinates[closest_index + 1])
    total_distance = haversine(closest_point[0], closest_point[1], coordinates[closest_index + 1][0],
                               coordinates[closest_index + 1][1])

    for i in range(closest_index + 1, len(coordinates) - 1):
      coord1 = coordinates[i]
      coord2 = coordinates[i + 1]
      segment_distance = haversine(coord1[0], coord1[1], coord2[0], coord2[1])

      if total_distance + segment_distance >= distance_m and segment_distance > 0:
        remaining_distance = distance_m - total_distance
        ratio = remaining_distance / segment_distance
        interpolated_lon = coord1[0] + ratio * (coord2[0] - coord1[0])
        interpolated_lat = coord1[1] + ratio * (coord2[1] - coord1[1])
        path_after_distance.append((interpolated_lon, interpolated_lat))
        break

      total_distance += segment_distance
      path_after_distance.append(coord2)

  return path_after_distance, start_index, closest_point


def calculate_angle(point1, point2):
  delta_lon = point2[0] - point1[0]
  delta_lat = point2[1] - point1[1]
  return math.degrees(math.atan2(delta_lat, delta_lon))


def gps_to_relative_xy(gps_path, reference_point, heading_deg):
  ref_lon, ref_lat = reference_point
  relative_coordinates = []

  heading_rad = math.radians(heading_deg)

  for lon, lat in gps_path:
    x = (lon - ref_lon) * 40008000 * math.cos(math.radians(ref_lat)) / 360
    y = (lat - ref_lat) * 40008000 / 360

    x_rot = x * math.cos(heading_rad) - y * math.sin(heading_rad)
    y_rot = x * math.sin(heading_rad) + y * math.cos(heading_rad)

    relative_coordinates.append((y_rot, x_rot))

  return relative_coordinates


def calculate_curvature(p1, p2, p3):
  v1 = (p2[0] - p1[0], p2[1] - p1[1])
  v2 = (p3[0] - p2[0], p3[1] - p2[1])

  cross_product = v1[0] * v2[1] - v1[1] * v2[0]
  len_v1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
  len_v2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)

  if len_v1 * len_v2 == 0:
    curvature = 0
  else:
    curvature = cross_product / (len_v1 * len_v2 * len_v1)

  return curvature


class CarrotMan:
  def __init__(self):
    print("************************************************CarrotMan init************************************************")
    self.params = Params()
    self.params_memory = Params(memory=True)
    self.gps_location_service = get_gps_location_service(self.params)
    self.sm = messaging.SubMaster(['deviceState', 'carState', 'controlsState', 'radarState', 'longitudinalPlan',
                                   'modelV2', 'selfdriveState', 'carControl', self.gps_location_service, 'navInstruction'])
    self.pm = messaging.PubMaster(['carrotMan', 'navInstructionCarrot'])

    self.carrot_serv = CarrotServ()

    self.broadcast_ip = self.get_broadcast_address()
    self.broadcast_port = 7705
    self.carrot_man_port = 7706
    self.connection = None

    self.ip_address = "0.0.0.0"
    self.remote_addr = None

    self.navi_points = []
    self.navi_points_start_index = 0
    self.navi_points_active = False
    self.navd_active = False

    self.active_carrot_last = False

    self.is_running = True
    thread = threading.Thread(target=self.broadcast_version_info)
    thread.daemon = True
    thread.start()

    self.is_metric = self.params.get_bool("IsMetric")

  def get_broadcast_address(self):
    if PC:
      iface = b'br0'
    else:
      iface = b'wlan0'
    try:
      with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        ip = fcntl.ioctl(
          s.fileno(),
          0x8919,
          struct.pack('256s', iface)
        )[20:24]
        return socket.inet_ntoa(ip)
    except (OSError, Exception):
      return None

  def get_local_ip(self):
    try:
      with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception as e:
      return f"Error: {e}"

  def broadcast_version_info(self):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    frame = 0

    rk = Ratekeeper(20, print_delay_threshold=None)

    while self.is_running:
      try:
        self.sm.update(0)
        remote_addr = self.remote_addr
        remote_ip = remote_addr[0] if remote_addr is not None else ""
        vturn_speed = self.carrot_curve_speed(self.sm)
        coords, distances, route_speed = self.carrot_navi_route()

        self.carrot_serv.update_navi(remote_ip, self.sm, self.pm, vturn_speed, coords, distances, route_speed, self.gps_location_service)

        if frame % 20 == 0 or remote_addr is not None:
          try:
            self.broadcast_ip = self.get_broadcast_address() if remote_addr is None else remote_addr[0]
            if not PC:
              ip_address = socket.gethostbyname(socket.gethostname())
            else:
              ip_address = self.get_local_ip()
            if ip_address != self.ip_address:
              self.ip_address = ip_address
              self.remote_addr = None

            msg = self.make_send_message()
            if self.broadcast_ip is not None:
              dat = msg.encode('utf-8')
              sock.sendto(dat, (self.broadcast_ip, self.broadcast_port))

            if remote_addr is None and not self.navd_active:
              self.navi_points = []
              self.navi_points_active = False

          except Exception as e:
            if self.connection:
              self.connection.close()
            self.connection = None
            print(f"##### broadcast_error...: {e}")
            traceback.print_exc()

        rk.keep_time()
        frame += 1
      except Exception as e:
        print(f"broadcast_version_info error...: {e}")
        traceback.print_exc()
        time.sleep(1)

  def carrot_navi_route(self):
    if self.carrot_serv.active_carrot > 1:
      if False and self.navd_active:  # mabox always active
        self.navd_active = False
        self.params.remove("NavDestination")
    is_onroad = self.params.get_bool("IsOnroad")
    if not is_onroad or not self.navi_points_active or not SHAPELY_AVAILABLE or (self.carrot_serv.active_carrot <= 1 and not self.navd_active):
      if self.navi_points_active:
        print("navi_points_active: ", self.navi_points_active, "active_carrot: ", self.carrot_serv.active_carrot, "navd_active: ", self.navd_active)
        self.navi_points = []
        self.navi_points_active = False
      self.active_carrot_last = self.carrot_serv.active_carrot
      return [], [], 300

    current_position = (self.carrot_serv.vpPosPointLon, self.carrot_serv.vpPosPointLat)
    heading_deg = self.carrot_serv.bearing

    distance_interval = 10.0
    out_speed = 300
    path, self.navi_points_start_index, start_point = get_path_after_distance(self.navi_points_start_index, self.navi_points, current_position, 300)
    relative_coords = []
    if path:
      relative_coords = gps_to_relative_xy(path, start_point, heading_deg)
      # Resample relative_coords at 5m intervals using LineString
      line = LineString(relative_coords)
      resampled_points = []
      resampled_distances = []
      current_distance = 0
      while current_distance <= line.length:
        point = line.interpolate(current_distance)
        resampled_points.append((point.x, point.y))
        resampled_distances.append(current_distance)
        current_distance += distance_interval

      curvatures = []
      distances = []
      distance = 10.0
      sample = 4
      if len(resampled_points) >= sample * 2 + 1:
        speeds = []
        for i in range(len(resampled_points) - sample * 2):
          distance += distance_interval
          p1, p2, p3 = resampled_points[i], resampled_points[i + sample], resampled_points[i + sample * 2]
          curvature = calculate_curvature(p1, p2, p3)
          curvatures.append(curvature)
          speed = np.interp(abs(curvature), V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS)
          if abs(curvature) < 0.02:
            speed = max(speed, self.carrot_serv.nRoadLimitSpeed)
          speeds.append(speed)
          distances.append(distance)
        # Apply acceleration limits in reverse to adjust speeds
        accel_limit = self.carrot_serv.autoNaviSpeedDecelRate  # m/s^2
        accel_limit_kmh = accel_limit * 3.6
        out_speeds = [0] * len(speeds)
        out_speeds[-1] = speeds[-1]
        v_ego_kph = self.sm['carState'].vEgo * 3.6

        time_delay = self.carrot_serv.autoNaviSpeedCtrlEnd
        time_wait = 0
        for i in range(len(speeds) - 2, -1, -1):
          target_speed = speeds[i]
          next_out_speed = out_speeds[i + 1]

          if target_speed < next_out_speed:
            time_delay = max(0, ((v_ego_kph - target_speed) / accel_limit_kmh))
            time_wait = -time_delay

          time_interval = distance_interval / (next_out_speed / 3.6) if next_out_speed > 0 else 0

          time_apply = min(time_interval, max(0, time_interval + time_wait))

          max_allowed_speed = next_out_speed + (accel_limit_kmh * time_apply)
          adjusted_speed = min(target_speed, max_allowed_speed)

          time_wait += min(2.0, time_interval)

          out_speeds[i] = adjusted_speed

        out_speed = out_speeds[0]
    else:
      resampled_points = []
      resampled_distances = []

    return resampled_points, resampled_distances, out_speed

  def make_send_message(self):
    msg = {}
    msg['Carrot2'] = self.params.get("Version")
    isOnroad = self.params.get_bool("IsOnroad")
    msg['IsOnroad'] = isOnroad
    msg['CarrotRouteActive'] = self.navi_points_active
    msg['ip'] = self.ip_address
    msg['port'] = self.carrot_man_port
    msg['navi_debug'] = 0
    self.controls_active = False
    self.xState = 0
    self.trafficState = 0
    v_ego_kph = 0
    log_carrot = ""
    v_cruise_kph = 0
    carcruiseSpeed = 0
    if not isOnroad:
      self.xState = 0
      self.trafficState = 0
    else:
      if self.sm.alive['carState']:
        carState = self.sm['carState']
        v_ego_kph = int(carState.vEgoCluster * 3.6 + 0.5)
        log_carrot = getattr(carState, 'logCarrot', "")
        v_cruise_kph = carState.vCruise
        carcruiseSpeed = carState.cruiseState.speed * 3.6
      if self.sm.alive['selfdriveState']:
        selfdrive = self.sm['selfdriveState']
        self.controls_active = selfdrive.active
      if self.sm.alive['longitudinalPlan']:
        lp = self.sm['longitudinalPlan']
        self.xState = getattr(lp, 'xState', 0)
        self.trafficState = getattr(lp, 'trafficState', 0)

    msg['log_carrot'] = log_carrot
    msg['v_cruise_kph'] = v_cruise_kph
    msg['carcruiseSpeed'] = carcruiseSpeed
    msg['v_ego_kph'] = v_ego_kph
    msg['tbt_dist'] = self.carrot_serv.xDistToTurn
    msg['sdi_dist'] = self.carrot_serv.xSpdDist
    msg['active'] = self.controls_active
    msg['xState'] = self.xState
    msg['trafficState'] = self.trafficState
    return json.dumps(msg)

  def carrot_man_thread(self):
    while True:
      try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
          sock.settimeout(10)
          sock.bind(('0.0.0.0', self.carrot_man_port))
          print("#########carrot_man_thread: UDP thread started...")

          while True:
            try:
              try:
                data, remote_addr = sock.recvfrom(4096)
                if not data:
                  raise ConnectionError("No data received")

                if self.remote_addr is None:
                  print("Connected to: ", remote_addr)
                self.remote_addr = remote_addr
                try:
                  json_obj = json.loads(data.decode())
                  self.carrot_serv.update(json_obj)
                except Exception as e:
                  print(f"carrot_man_thread: json error...: {e}")
                  print(data)

              except TimeoutError:
                self.remote_addr = None
                time.sleep(1)

              except Exception as e:
                print(f"carrot_man_thread: error...: {e}")
                self.remote_addr = None
                break

            except Exception as e:
              print(f"carrot_man_thread: recv error...: {e}")
              self.remote_addr = None
              break

          time.sleep(1)
      except Exception as e:
        self.remote_addr = None
        print(f"Network error, retrying...: {e}")
        time.sleep(2)

  def parse_kisa_data(self, data: bytes):
    result = {}

    try:
      decoded = data.decode('utf-8')
    except UnicodeDecodeError:
      print("Decoding error:", data)
      return result

    parts = decoded.split('/')
    for part in parts:
      if ':' in part:
        key, value = part.split(':', 1)
        try:
          result[key] = int(value)
        except ValueError:
          result[key] = value
    return result

  def kisa_app_thread(self):
    while True:
      try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
          sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
          sock.settimeout(10)
          sock.bind(('', 12345))
          print("#########kisa_app_thread: UDP thread started...")

          while True:
            try:
              try:
                data, remote_addr = sock.recvfrom(4096)
                if not data:
                  raise ConnectionError("No data received")

                try:
                  kisa_data = self.parse_kisa_data(data)
                  self.carrot_serv.update_kisa(kisa_data)
                except Exception as e:
                  traceback.print_exc()
                  print(f"kisa_app_thread: json error...: {e}")
                  print(data)

              except TimeoutError:
                time.sleep(1)

              except Exception as e:
                print(f"kisa_app_thread: error...: {e}")
                break

            except Exception as e:
              print(f"kisa_app_thread: recv error...: {e}")
              break

          time.sleep(1)
      except Exception as e:
        print(f"Network error, retrying...: {e}")
        time.sleep(2)

  def carrot_curve_speed_params(self):
    self.autoCurveSpeedFactor = self.params.get_int("AutoCurveSpeedFactor", default=100) * 0.01

  def carrot_curve_speed(self, sm):
    self.carrot_curve_speed_params()
    if not sm.alive['carState'] and not sm.alive['modelV2']:
      return 250
    if len(sm['modelV2'].orientationRate.z) == 0:
      return 250

    return self.vturn_speed(sm['carState'], sm)

  def vturn_speed(self, CS, sm):
    TARGET_LAT_A = 1.9  # m/s^2

    modelData = sm['modelV2']
    v_ego = max(CS.vEgo, 0.1)
    orientation_rate = np.array(modelData.orientationRate.z) * self.autoCurveSpeedFactor
    velocity = np.array(modelData.velocity.x)

    max_index = np.argmax(np.abs(orientation_rate))
    curv_direction = np.sign(orientation_rate[max_index])
    max_pred_lat_acc = np.amax(np.abs(orientation_rate) * velocity)

    max_curve = max_pred_lat_acc / (v_ego**2)

    adjusted_target_lat_a = TARGET_LAT_A

    turnSpeed = max(abs(adjusted_target_lat_a / max_curve)**0.5 * 3.6, 5)
    turnSpeed = min(turnSpeed, 250)
    return turnSpeed * curv_direction
