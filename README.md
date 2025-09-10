# 🚀 Real_time_data_sync_2exSSD

## Giới thiệu
**Real_time_data_sync_2exSSD** là công cụ đồng bộ dữ liệu thu thập từ thiết bị **Autera** sang **SSD ngoài** hoặc thư mục lưu trữ khác.  
Mục tiêu:
- Giữ an toàn dữ liệu gốc từ Autera.
- Đồng bộ thông minh (chỉ copy file mới/thay đổi).
- Hỗ trợ tự động hóa bằng cron job hoặc script trực tiếp.

---

## Tính năng
- ✅ Đồng bộ toàn bộ dữ liệu hoặc incremental bằng `rsync`.  
- ✅ Kiểm tra dung lượng SSD trước khi copy.  
- ✅ Giao diện dòng lệnh đơn giản (CLI).  
- ✅ Có thể chạy **tự động định kỳ** bằng cron.  

---

## Yêu cầu hệ thống
- **Hệ điều hành**: Linux (Ubuntu/Autera OS)  
- **Ngôn ngữ**: Python >= 3.8  
- **Công cụ hỗ trợ**:  
  - `rsync` (dùng cho incremental sync)  
  - `cron` (nếu muốn chạy định kỳ)  

Cài đặt gói cần thiết:  
```bash
sudo apt-get update
sudo apt-get install -y rsync python3 python3-pip
Clone và Cài đặt
Clone repo về máy:
```

bash
### pull code
```bash
git clone https://github.com/DinhDat-1012/Real_time_data_sync_2exSSD.git
```

cd Real_time_data_sync_2exSSD
### Cài đặt các dependency Python:
``` bash
pip3 install -r requirements.txt
```
File requirements.txt bao gồm:

txt
---
### Sao chép mã
argparse
shutilwhich
Cấu trúc dự án
bash

Sao chép mã
Real_time_data_sync_2exSSD/
│── sync.py          # Script Python để copy dữ liệu
│── run_rsync.sh     # Script shell dùng rsync để đồng bộ
│── requirements.txt # Danh sách dependency Python
│── README.md        # Tài liệu dự án
Cách sử dụng
1. Dùng Python Script
Chạy lệnh:

bash
Sao chép mã
python3 sync.py --source /mnt/autera/data --dest /media/ssd/backup
Các tham số:

--source: Thư mục dữ liệu Autera

--dest: Thư mục đích (SSD hoặc ổ ngoài)

Ví dụ:
```

bash
Sao chép mã
python3 sync.py --source /mnt/data/logs --dest /media/autera-ssd
