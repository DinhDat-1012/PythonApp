import numpy as np
import matplotlib.pyplot as plt
import socket
import struct

# Thông số của LiDAR Pandar128
# LƯU Ý: HOST ở đây là địa chỉ IP của MÁY TÍNH CỦA BẠN, nơi lắng nghe dữ liệu
HOST = '0.0.0.0' # Lắng nghe trên tất cả các giao diện mạng
PORT = 2368
UDP_PACKET_SIZE = 1248 # Kích thước gói tin UDP Pandar128

# Mở socket để nhận dữ liệu UDP
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Lắng nghe dữ liệu trên cổng 2368 từ BẤT KỲ địa chỉ IP nào
    sock.bind((HOST, PORT))
    sock.settimeout(0.1)
    print(f"Đã mở socket thành công và lắng nghe trên cổng {PORT}")
except socket.error as e:
    print(f"Lỗi khi mở socket: {e}")
    exit()

# ... (các phần còn lại của code tương tự như ví dụ ban đầu)
# Cấu hình Matplotlib
plt.ion()
fig, ax = plt.subplots(figsize=(8, 8))
ax.set_facecolor('black')
ax.set_aspect('equal', adjustable='box')
ax.set_xlim(-20, 20)
ax.set_ylim(-20, 20)
ax.set_title("Pandar128 2D Top-Down View")
ax.grid(True, linestyle='--', alpha=0.5)
sc = ax.scatter([], [], s=1, color='cyan')

# Vòng lặp chính để cập nhật dữ liệu
try:
    while True:
        try:
            # Nhận gói tin từ LiDAR
            # Vẫn cần kiểm tra địa chỉ IP gửi đến để đảm bảo đúng nguồn
            data, addr = sock.recvfrom(UDP_PACKET_SIZE)
            
            # Giả định dữ liệu đã được giải mã
            num_random_points = 500
            distances = np.random.uniform(0, 15, num_random_points)
            angles = np.random.uniform(0, 2 * np.pi, num_random_points)
            
            x_points = distances * np.cos(angles)
            y_points = distances * np.sin(angles)
            
            sc.set_offsets(np.c_[x_points, y_points])
            fig.canvas.draw()
            fig.canvas.flush_events()
            
        except socket.timeout:
            continue
            
except KeyboardInterrupt:
    print("Dừng chương trình.")
    sock.close()
    plt.close('all')