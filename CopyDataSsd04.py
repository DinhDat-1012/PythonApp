#huongnm13@vingroup.net
# v 4.0

# Yêu cầu: 
# -đã cài python3 (môi trường)
# -cài các thư viện PyQt5 shutil os

# Tóm tắ: 
# -Tool dùng để copy file, dành cho các định dạng video
# -có bộ lọc linh hoạt (bản cũ dùng danh sách, bản này dùng textbox cho nhập điều kiện thoải mái :v)
# -đảm bảo không copy file trùng
# -chấp nhận cả chữ hoa và chữ thường

# Cách dùng: 
# -chọn thư mục nguồn (ssd trong) chứa các video cần sao chép, chọn thư mục đích (ssd ngoài)


import os
import shutil
import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QFileDialog, QVBoxLayout, QWidget, QLabel, QLineEdit
)

class FileCopyApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Filtered Video Copy Tool")
        self.setGeometry(200, 200, 600, 300)

        # Widgets
        self.selected_folder_label = QLabel("Source Folder: Not Selected")
        self.dest_label = QLabel("Destination Folder: Not Selected")
        self.status_label = QLabel("")

        self.filter_label = QLabel("Enter Filter Criteria (leave blank for no filter):")
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("E.g., VF8, VN, 01/12/2025")

        self.select_folder_btn = QPushButton("Select Source Folder")
        self.select_dest_btn = QPushButton("Select Destination Folder")
        self.copy_btn = QPushButton("Start Copying")

        self.select_folder_btn.clicked.connect(self.select_source_folder)
        self.select_dest_btn.clicked.connect(self.select_dest)
        self.copy_btn.clicked.connect(self.start_copying)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.selected_folder_label)
        layout.addWidget(self.select_folder_btn)
        layout.addWidget(self.dest_label)
        layout.addWidget(self.select_dest_btn)
        layout.addWidget(self.filter_label)
        layout.addWidget(self.filter_input)
        layout.addWidget(self.copy_btn)
        layout.addWidget(self.status_label)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.source_folder = None
        self.dest_folder = None

    def select_source_folder(self):
        self.source_folder = QFileDialog.getExistingDirectory(self, "Select Source Folder")
        self.selected_folder_label.setText(f"Source Folder: {self.source_folder}")

    def select_dest(self):
        self.dest_folder = QFileDialog.getExistingDirectory(self, "Select Destination Folder")
        self.dest_label.setText(f"Destination Folder: {self.dest_folder}")

    def start_copying(self):
        if not self.source_folder or not self.dest_folder:
            self.status_label.setText("Please select both source and destination folders!")
            return

        filter_criteria = self.filter_input.text().strip()
        filters = [filter.strip().lower() for filter in filter_criteria.split(",")] if filter_criteria else []

        try:
            copied_files = 0
            skipped_files = 0

            for file_name in os.listdir(self.source_folder):
                file_path = os.path.join(self.source_folder, file_name)

                # Check if it's a video file and matches the filter
                if os.path.isfile(file_path) and file_name.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.flv')):
                    if not filters or any(filter in file_name.lower() for filter in filters):
                        dest_file_path = os.path.join(self.dest_folder, file_name)

                        # Skip copying if file already exists in destination folder
                        if os.path.exists(dest_file_path):
                            skipped_files += 1
                            continue

                        shutil.copy(file_path, self.dest_folder)
                        copied_files += 1

            self.status_label.setText(f"Copied {copied_files} video file(s), skipped {skipped_files} duplicate(s).")
        except Exception as e:
            self.status_label.setText(f"Error: {str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FileCopyApp()
    window.show()
    sys.exit(app.exec_())
