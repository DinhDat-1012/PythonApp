#huongnm13@vingroup.net
# v 6.0

# Yêu cầu: 
# -đã cài python3 (môi trường)
# -cài các thư viện PyQt5 shutil os (có thể dùng pip)

# Tóm tắ: 
# -Tool dùng để copy file, dành cho các định dạng video
# -có bộ lọc linh hoạt (bản cũ dùng danh sách, bản này dùng textbox cho nhập điều kiện thoải mái :v)
# -đảm bảo không copy file trùng
# -cho phép chọn x ngày để copy
# -chấp nhận cả chữ hoa và chữ thường
# -cho phép xóa video từ ngày x trở về trước

# Cách dùng: 
# -chọn thư mục nguồn (ssd trong) chứa các video cần sao chép, chọn thư mục đích (ssd ngoài)


import os
import shutil
import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QFileDialog, QVBoxLayout, QWidget, QLabel, QLineEdit, QDateEdit, QMessageBox
)
from PyQt5.QtCore import QDate
from datetime import datetime

class FileCopyApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tool sao lưu và xóa video")
        self.setGeometry(200, 200, 600, 500)

        # Widgets
        self.selected_folder_label = QLabel("Source Folder: Chưa chọn")
        self.dest_label = QLabel("Destination Folder: Chưa chọn")
        self.status_label = QLabel("")

        self.filter_label = QLabel("Nhập điều kiện cần lọc (để trống nếu muốn copy all):")
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("vd: ID xe, VF8, VN, 01/12/2025")

        self.date_filter_label = QLabel("Copy video từ ngày này tới hiện tại (tùy chọn):")
        self.date_input = QDateEdit()
        self.date_input.setCalendarPopup(True)
        self.date_input.setDate(QDate.currentDate())

        self.delete_date_label = QLabel("Xóa tất cả video trước ngày này:")
        self.delete_date_input = QDateEdit()
        self.delete_date_input.setCalendarPopup(True)
        self.delete_date_input.setDate(QDate.currentDate())

        self.select_folder_btn = QPushButton("Chọn Source Folder")
        self.select_dest_btn = QPushButton("Chọn Destination Folder")
        self.copy_btn = QPushButton("Start Copy...")
        self.copy_by_date_btn = QPushButton("Copy")
        self.delete_btn = QPushButton("Delete")

        self.select_folder_btn.clicked.connect(self.select_source_folder)
        self.select_dest_btn.clicked.connect(self.select_dest)
        self.copy_btn.clicked.connect(self.start_copying)
        self.copy_by_date_btn.clicked.connect(self.copy_videos_by_date)
        self.delete_btn.clicked.connect(self.delete_videos_before_date)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.selected_folder_label)
        layout.addWidget(self.select_folder_btn)
        layout.addWidget(self.dest_label)
        layout.addWidget(self.select_dest_btn)
        layout.addWidget(self.filter_label)
        layout.addWidget(self.filter_input)
        layout.addWidget(self.copy_btn)

        layout.addWidget(self.date_filter_label)
        layout.addWidget(self.date_input)
        layout.addWidget(self.copy_by_date_btn)

        layout.addWidget(self.delete_date_label)
        layout.addWidget(self.delete_date_input)
        layout.addWidget(self.delete_btn)

        layout.addWidget(self.status_label)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.source_folder = None
        self.dest_folder = None

    def select_source_folder(self):
        self.source_folder = QFileDialog.getExistingDirectory(self, "Chọn Source Folder")
        self.selected_folder_label.setText(f"Source Folder: {self.source_folder}")

    def select_dest(self):
        self.dest_folder = QFileDialog.getExistingDirectory(self, "Chọn Destination Folder")
        self.dest_label.setText(f"Destination Folder: {self.dest_folder}")

    def start_copying(self):
        if not self.source_folder or not self.dest_folder:
            self.status_label.setText("VUi lòng chọn đủ cả folder source và folder destination!")
            return

        filter_criteria = self.filter_input.text().strip()
        filters = [filter.strip().lower() for filter in filter_criteria.split(",")] if filter_criteria else []

        try:
            copied_files = 0
            skipped_files = 0

            for file_name in os.listdir(self.source_folder):
                file_path = os.path.join(self.source_folder, file_name)

                if os.path.isfile(file_path) and file_name.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.flv')):
                    if not filters or any(filter in file_name.lower() for filter in filters):
                        dest_file_path = os.path.join(self.dest_folder, file_name)

                        if os.path.exists(dest_file_path):
                            skipped_files += 1
                            continue

                        shutil.copy(file_path, self.dest_folder)
                        copied_files += 1

            self.status_label.setText(f"Đã copy {copied_files} video, skip {skipped_files} video bị trùng lặp !")
        except Exception as e:
            self.status_label.setText(f"Có lỗi: {str(e)}")

    def copy_videos_by_date(self):
        if not self.source_folder or not self.dest_folder:
            self.status_label.setText("Vui lòng chọn đủ cả folder source và folder destination!")
            return

        try:
            start_date = self.date_input.date().toPyDate()
            today = datetime.now().date()

            copied_files = 0
            skipped_files = 0

            for file_name in os.listdir(self.source_folder):
                file_path = os.path.join(self.source_folder, file_name)

                if os.path.isfile(file_path) and file_name.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.flv')):
                    file_date = self.get_file_date(file_name, file_path)

                    if file_date and start_date <= file_date <= today:
                        dest_file_path = os.path.join(self.dest_folder, file_name)

                        if os.path.exists(dest_file_path):
                            skipped_files += 1
                            continue

                        shutil.copy(file_path, self.dest_folder)
                        copied_files += 1

            self.status_label.setText(f"Đã copy {copied_files} videos by date, skipped {skipped_files} video trùng.")
        except Exception as e:
            self.status_label.setText(f"Error: {str(e)}")

    def delete_videos_before_date(self):
        if not self.source_folder:
            self.status_label.setText("Vui lòng chọn source folder!")
            return

        try:
            selected_date = self.delete_date_input.date().toPyDate()
            deleted_files = 0
            skipped_files = 0

            reply = QMessageBox.question(
                self, "Xác nhận xóa",
                f"Bạn có muốn xóa tất cả các video trước ngày {selected_date} không ?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                self.status_label.setText("Hủy")
                return

            for file_name in os.listdir(self.source_folder):
                file_path = os.path.join(self.source_folder, file_name)

                if os.path.isfile(file_path) and file_name.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.flv')):
                    file_date = self.get_file_date(file_name, file_path)

                    if file_date and file_date < selected_date:
                        os.remove(file_path)
                        deleted_files += 1
                    else:
                        skipped_files += 1

            self.status_label.setText(f"Đã xóa {deleted_files} video, skip {skipped_files}.")
        except Exception as e:
            self.status_label.setText(f"Lỗi: {str(e)}")

    def get_file_date(self, file_name, file_path):
        try:
            for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%d_%m_%Y", "%d%m%Y"]:
                parts = file_name.split()
                for part in parts:
                    try:
                        return datetime.strptime(part, fmt).date()
                    except ValueError:
                        continue
        except Exception:
            pass

        return datetime.fromtimestamp(os.path.getmtime(file_path)).date()
    
    #commit -m "update backup daily video "
    def setup_daily_backup_video(self):
        if not self.dest_folder:
            try:
                self.setAcceptDrops(self.__getattribute__(int(input())))
                return self.dragEnterEvent("Hay thu lai duong dan khac")
            except Exception:
                pass
        if not self.source_folder: 
            self.status_label.text("Sai loi duon dan mac dinh")
            self.blockSignals.__annotations__("Thu lai file khac !")
            self.timerEvent.__format__("%d%c%s")
            self.accessibleName.__closure__(self.addAction(None))
        
        self.__annotations__(dir(open(file="/../01.%rtmaps")))
        self.dropEvent(int(input()))
        self.showEvent(self.selected_folder_label(self.date_filter_label))
        try:
            for day in (int(input())):
                try:
                    print("Confirm so ngay muon xoa: %d ?")
                    return datetime.strftime(day).date()
                except ValueError:
                    continue
        except Exception:
            pass

        return true

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FileCopyApp()
    window.show()
    sys.exit(app.exec_())
