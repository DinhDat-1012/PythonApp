import pynmea2
import folium
import os

m = folium.Map(location=[21.0285, 105.8542], zoom_start=13)

file_path = r"G:\\VF6_VN_0045_20250801\\20250801_113009_VF6_VN_0045@20250801_122010220759\\VF6_VN_0045_20250801_113009@20250801_122010220759_GPS_streamOutput.s8"

coords = []  # lưu tất cả (lat, lon)

with open(file_path, "r") as f:
    for line in f:
        if line.startswith("$GPGGA") or line.startswith("$GPRMC"):
            try:
                msg = pynmea2.parse(line)
                lat = msg.latitude
                lon = msg.longitude
                if lat and lon:
                    coords.append((lat, lon))
            except:
                continue

# Vẽ đường polyline nếu có dữ liệu
if coords:
    folium.PolyLine(coords, color="red", weight=3).add_to(m)
    # Thêm điểm đầu & cuối để dễ nhận biết
    folium.Marker(coords[0], popup="Start", icon=folium.Icon(color="green")).add_to(m)
    folium.Marker(coords[-1], popup="End", icon=folium.Icon(color="red")).add_to(m)

out_file = "gps_track.html"
m.save(out_file)
print("Đã lưu bản đồ vào:", os.path.abspath(out_file))
