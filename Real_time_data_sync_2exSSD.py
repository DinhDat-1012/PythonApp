#!/usr/bin/env python3
import os
import sys
import shutil
import logging
import tkinter as tk
from pathlib import Path
from datetime import datetime, timedelta
from distutils.dir_util import copy_tree
import time
import threading

# ======================================================================================================
# GLOBAL CONFIG
# ======================================================================================================
TODAY_STRING = datetime.today().strftime("%Y%m%d")
VEHICLE_ID = os.getenv("VEHICLE_ID")
SSD_MOUNT_PATH = '/mnt/dsu0/'
SSD_FREE = 0
LOCK_FILE = '/home/autera-admin/python/sync.lock'
SYNC_TIMEOUT = 3 * 3600  # 3 hours
DEFAULT_SSD_MOUNT_POINT = '/media/autera-admin/'
Syn_TIME_CYCLE = 5

list_syned_raw = []  # danh sách folder đã sync

log_file_name = datetime.now().strftime('sync_data_ssd_%s_%H_%M_%d_%m_%Y.log')
logging.basicConfig(
    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
    datefmt='%y-%m-%d %H:%M:%S',
    level=logging.DEBUG,
    handlers=[
        logging.FileHandler(f"/home/autera-admin/python/logs/{log_file_name}", mode='w+'),
        logging.StreamHandler()
    ]
)

# ======================================================================================================
# HELPER FUNCTIONS
# ======================================================================================================
def get_tag_file_name(raw_folder: str):
    """Tìm file .txt trong folder"""
    for file_name in os.listdir(raw_folder):
        # logging.info("Search_for_txt_log_file:%s", file_name) # Quá nhiều log
        if file_name.endswith('.txt'):
            return file_name
    return None

def is_completed(raw_name: str) -> bool:
    """Kiểm tra folder đã >7 phút thì coi là completed"""
    # Xử lý trường hợp raw_name không chứa '@'
    if '@' not in raw_name:
        logging.warning(f"Raw folder name '{raw_name}' does not contain '@'. Skipping completion check.")
        return False
    
    str_raw_time = raw_name.split('@')[1]
    try:
        raw_time = datetime.strptime(str_raw_time, '%Y%m%d_%H%M%S%f')
        return (datetime.now() - raw_time) > timedelta(minutes=7)
    except ValueError:
        logging.error(f"Could not parse datetime from '{str_raw_time}' in '{raw_name}'. Skipping completion check.")
        return False


def get_list_completed_raw(car_folder: str):
    """Lấy danh sách folder đã hoàn thành"""
    if not os.path.exists(car_folder):
        logging.warning(f"Car folder '{car_folder}' does not exist.")
        return []

    list_raw_names = os.listdir(car_folder)
    list_completed_raw = []
    global TODAY_STRING # Sử dụng TODAY_STRING từ global config

    for raw_name in list_raw_names:
        if '@' in raw_name and is_completed(raw_name) and TODAY_STRING in raw_name:
            list_completed_raw.append(raw_name)
    return list_completed_raw


def other_process_running():
    """Check có process khác đang chạy hay không"""
    if os.path.exists(LOCK_FILE):
        try:
            last_running_time = os.path.getctime(LOCK_FILE)
            if datetime.now().timestamp() - last_running_time < SYNC_TIMEOUT:
                return True
            else:
                add_log("Lock file expired. Deleting...")
                mark_there_is_no_process_running()
        except Exception as e:
            logging.error(f"Error checking lock file: {e}", exc_info=True)
            mark_there_is_no_process_running() # Xóa lock file nếu có lỗi
    return False


def mark_there_is_running_process():
    try:
        with open(LOCK_FILE, 'w') as f:
            f.write(f'i am running - PID: {os.getpid()}')
        add_log("Lock file created.")
    except Exception as e:
        logging.error(f"Error creating lock file: {e}", exc_info=True)


def mark_there_is_no_process_running():
    if os.path.exists(LOCK_FILE):
        try:
            os.remove(LOCK_FILE)
            add_log("Lock file removed.")
        except Exception as e:
            logging.error(f"Error removing lock file: {e}", exc_info=True)


def get_car_data_folder():
    """Tìm folder data theo VEHICLE_ID"""
    try:
        if not os.path.exists(SSD_MOUNT_PATH):
            logging.error(f"SSD_MOUNT_PATH '{SSD_MOUNT_PATH}' does not exist.")
            return None
        
        for folder_name in os.listdir(SSD_MOUNT_PATH):
            if VEHICLE_ID in folder_name:
                return folder_name
    except FileNotFoundError:
        logging.error(f"SSD_MOUNT_PATH '{SSD_MOUNT_PATH}' not found.", exc_info=True)
        return None
    except Exception as e:
        logging.error(f"Error getting car data folder: {e}", exc_info=True)
        return None
    return None


def check_external_SSD_space(path, min_free_space=10):
    """Check dung lượng SSD ngoài, nếu < min_free_space GB thì return True"""
    try:
        total, used, free = shutil.disk_usage(path)
        free_GB = free / (1024 ** 3)
        total_GB = total / (1024 ** 3)
        logging.info("Checking Disk at %s : Free %.1f GiB / Total %.1f GiB",
                     path, free_GB, total_GB)
        add_log(f"SSD free space: {free_GB:.1f} GiB (required > {min_free_space} GiB)")
        return free_GB < min_free_space
    except FileNotFoundError:
        logging.info("SSD checking fault: Path not found %s", path, exc_info=True)
        add_log(f"ERROR: SSD path '{path}' not found.")
        return True # Coi như không đủ không gian nếu không tìm thấy
    except Exception as e:
        logging.error(f"Error checking SSD space: {e}", exc_info=True)
        add_log(f"ERROR: Failed to check SSD space. {e}")
        return True # Coi như không đủ không gian nếu có lỗi

# ======================================================================================================
# SYNC FUNCTIONS
# ======================================================================================================
def real_time_synchronize_folder(source_folder, dst_external_ssd_folder_name):
    global list_syned_raw # Đảm bảo cập nhật danh sách toàn cục
    list_completed_raw = get_list_completed_raw(source_folder)
    logging.info("list_completed_raw %s", list_completed_raw)
    add_log(f"Found {len(list_completed_raw)} completed raw folders to sync.")
    destination_critical_path = os.path.join(dst_external_ssd_folder_name,f"Critical@{TODAY_STRING}")
    if not os.path.exists(destination_critical_path):
        os.makedirs(destination_critical_path)
        add_log(f"created folder{destination_critical_path}")
    for raw_folder_name in list_completed_raw:
        if raw_folder_name not in list_syned_raw:
            raw_folder_path = os.path.join(source_folder, raw_folder_name)
            tag_file_name = get_tag_file_name(raw_folder=raw_folder_path)

        if tag_file_name is not None:
            tag_file_path = os.path.join(raw_folder_path, tag_file_name)
            add_log(f"Tag txt file name: {tag_file_path} detechted")
            # Kiểm tra xem thư mục nguồn có tồn tại không trước khi cố gắng sao chép
            if not os.path.exists(raw_folder_path):
                logging.warning(f"Source folder '{raw_folder_path}' does not exist. Skipping.")
                continue

            try:
                with open(tag_file_path, 'r') as file:
                    content = file.read()
                    if "[TAG],manual_annotation.Start.Stop,0,true" in content:
                        logging.info("%s is a critical file, handling...", tag_file_path)
                        add_log(f"CRITICAL: '{raw_folder_name}' is critical. Moving...")
                        try:
                # copy folder kể cả khi đích đã tồn tại
                            copy_tree(raw_folder_path, os.path.join(destination_critical_path,
                                            os.path.basename(raw_folder_path)))
                            list_syned_raw.append(raw_folder_name)
                            logging.info(f"Synced: {raw_folder_name}")
                            add_log(f"Successfully synced: {raw_folder_name} to critical@{TODAY_STRING}")
                        except Exception as e:
                            logging.error(f"Failed to sync '{raw_folder_name}': {e}", exc_info=True)
                            add_log(f"ERROR: Failed to sync '{raw_folder_name}'. {e}")
                                    
            except Exception as e:
                add_log(f"ERRO{e}")

            destination_path = os.path.join(dst_external_ssd_folder_name,
                                            os.path.basename(raw_folder_path))
            add_log(f"Syncing: {raw_folder_name} to {destination_path}")
            try:
                # copy folder kể cả khi đích đã tồn tại
                copy_tree(raw_folder_path, destination_path)
                list_syned_raw.append(raw_folder_name)
                logging.info(f"Synced: {raw_folder_name}")
                add_log(f"Successfully synced: {raw_folder_name}")
            except Exception as e:
                logging.error(f"Failed to sync '{raw_folder_name}': {e}", exc_info=True)
                add_log(f"ERROR: Failed to sync '{raw_folder_name}'. {e}")
        else:
            add_log(f"Skipping already synced: {raw_folder_name}")


def move_parent_folder_of_txt_to_critical(source_folder, critical_folder_on_ssd_autera, dst_external_ssd_folder_name):
    """Xử lý critical folder và đồng bộ ra SSD ngoài"""
    if not os.path.exists(critical_folder_on_ssd_autera):
        os.makedirs(critical_folder_on_ssd_autera)
        add_log(f'Created folder "{critical_folder_on_ssd_autera}"')
    else:
        add_log(f'Folder "{critical_folder_on_ssd_autera}" already exists.')

    list_completed_raw = get_list_completed_raw(source_folder)
    logging.info("list_completed_raw %s", list_completed_raw)
    add_log(f"Found {len(list_completed_raw)} completed raw folders for critical check.")

    critical_folders_moved = []

    # Lọc critical
    for raw_folder_name in list_completed_raw:
        raw_folder_path = os.path.join(source_folder, raw_folder_name)
        
        if not os.path.exists(raw_folder_path):
            logging.warning(f"Source folder '{raw_folder_path}' does not exist. Skipping critical check.")
            continue

        tag_file_name = get_tag_file_name(raw_folder=raw_folder_path)

        if tag_file_name is not None:
            tag_file_path = os.path.join(raw_folder_path, tag_file_name)
            try:
                with open(tag_file_path, 'r') as file:
                    content = file.read()
                    if "[TAG],manual_annotation.Start.Stop,0,true" in content:
                        logging.info("%s is a critical file, handling...", tag_file_path)
                        add_log(f"CRITICAL: '{raw_folder_name}' is critical. Moving...")
                        destination_path = os.path.join(critical_folder_on_ssd_autera,
                                                        os.path.basename(raw_folder_path))
                        shutil.move(raw_folder_path, destination_path)
                        add_log(f"Moved '{raw_folder_name}' to 'criticalData'")
                        critical_folders_moved.append(raw_folder_name)
                    else:
                        add_log(f"Folder is not critical: {raw_folder_name}")
            except Exception as e:
                logging.error(f"Error reading tag file '{tag_file_path}': {e}", exc_info=True)
                add_log(f"ERROR: Could not read tag file for '{raw_folder_name}'. {e}")
        else:
            add_log(f"No tag file found in: {raw_folder_name}")
        # print("------") # Xóa dòng này để không in ra quá nhiều

    # Đồng bộ criticalData ra SSD ngoài
    folders_to_sync_with_rsync = [os.path.join(critical_folder_on_ssd_autera)] + [os.path.join(source_folder, f) for f in list_completed_raw if f not in critical_folders_moved]
    
    add_log(f"Starting rsync for critical data and remaining completed folders...")
    for source_sync_path in folders_to_sync_with_rsync:
        if not os.path.exists(source_sync_path):
            logging.warning(f"Source path for rsync '{source_sync_path}' does not exist. Skipping.")
            continue

        logging.info("sync data from %s to %s", source_sync_path, dst_external_ssd_folder_name)
        add_log(f"rsyncing: {os.path.basename(source_sync_path)}")
        try:
            # Sử dụng os.system hoặc subprocess.run
            # subprocess.run sẽ an toàn hơn và cung cấp nhiều kiểm soát hơn
            # Ví dụ:
            # result = subprocess.run(['rsync', '-azvh', '--no-o', '--no-g', '--no-compress', '--no-perms', '--progress', source_sync_path, dst_external_ssd_folder_name], capture_output=True, text=True)
            # if result.returncode == 0:
            #     add_log(f"rsync success for {os.path.basename(source_sync_path)}")
            # else:
            #     add_log(f"rsync failed for {os.path.basename(source_sync_path)}: {result.stderr}")
            os.system(f'rsync -azvh --no-o --no-g --no-compress --no-perms --progress '
                      f'{source_sync_path} {dst_external_ssd_folder_name}')
            add_log(f"rsync successful for {os.path.basename(source_sync_path)}")
        except Exception as e:
            logging.error(f"Error during rsync for '{source_sync_path}': {e}", exc_info=True)
            add_log(f"ERROR: rsync failed for '{os.path.basename(source_sync_path)}'. {e}")


    # Xóa folder gốc sau khi sync (chỉ những folder đã được xử lý)
    for raw_folder_name in list_completed_raw:
        raw_folder_path = os.path.join(source_folder, raw_folder_name)
        if os.path.exists(raw_folder_path) and raw_folder_name not in critical_folders_moved:
            try:
                shutil.rmtree(raw_folder_path)
                logging.info("Deleted source folder: %s", raw_folder_path)
                add_log(f"Deleted source folder: {raw_folder_name}")
            except Exception as e:
                logging.error(f"Error deleting source folder '{raw_folder_path}': {e}", exc_info=True)
                add_log(f"ERROR: Could not delete source folder '{raw_folder_path}'. {e}")

# ======================================================================================================
# GUI
# ======================================================================================================
def open_guide_window():
    child = tk.Toplevel(root)
    child.title("Guide")
    child.geometry("500x400")

    tk.Label(child, text="This program transfers data from Autera to external SSD").pack(pady=0)
    tk.Label(child, text="Article 1: Do not close the software while transferring.").pack(pady=10)
    tk.Label(child, text="Article 2: If crashed, contact Coordinator or email v.datdd9@vinfast.vn").pack(pady=20)
    tk.Label(child, text="Article 3: Check available disk space before transferring.").pack(pady=30)

    tk.Button(child, text="Close", command=child.destroy).pack(pady=50)


def add_log(msg):
    now = datetime.now().strftime("%H:%M:%S")
    log_box.insert(tk.END, f"[{now}] {msg}\n")
    log_box.see(tk.END) # Cuộn xuống cuối


def submit_date():
    global TODAY_STRING
    value = date_input_entry.get()
    # Kiểm tra định dạng ngày (YYYYMMDD)
    if len(value) == 8 and value.isdigit():
        TODAY_STRING = value
        DATE_var.set(f"{TODAY_STRING}")
        add_log(f"Date set to: {value}")
        logging.info(f"Date input: {value}")
    else:
        add_log(f"Invalid date format: {value}. Please use YYYYMMDD.")


def submit_vehicle_id():
    global VEHICLE_ID
    value = VEHICLE_ID_input_entry.get()
    if value: # Kiểm tra không rỗng
        VEHICLE_ID = value
        VEHICLE_ID_var.set(f"VEID: {VEHICLE_ID}")
        add_log(f"VEHICLE_ID set to: {value}")
        logging.info("VEHICLE_ID:%s", value)
    else:
        add_log(f"VEHICLE_ID cannot be empty.")

# ======================================================================================================
# MAIN LOGIC AND THREAD MANAGEMENT
# ======================================================================================================
sync_thread = None
stop_event = threading.Event()
pause_event = threading.Event()

def main_sync_process():
    """Hàm chính chạy trong luồng"""
    global list_syned_raw # Đảm bảo reset khi bắt đầu chu kỳ mới nếu cần

    while not stop_event.is_set():
        pause_event.wait() # Chờ nếu luồng bị tạm dừng

        add_log("Starting sync cycle...")
        logging.info('start sync data cycle')

        if other_process_running():
            add_log('Another sync process is already running or lock file expired. Waiting...')
            logging.info('exit this cycle because other process is running')
            time.sleep(30) # Chờ một lúc trước khi kiểm tra lại
            continue

        try:
            mark_there_is_running_process()

            car_data_folder = get_car_data_folder()
            if car_data_folder is None:
                add_log("ERROR: No car data folder found in SSD mount path. Check SSD_MOUNT_PATH or VEHICLE_ID.")
                logging.error("No car data folder found in SSD mount path.")
                time.sleep(60) # Chờ lâu hơn nếu không tìm thấy folder
                continue

            source_folder = os.path.join(SSD_MOUNT_PATH, car_data_folder)
            add_log(f"Source data folder: {source_folder}")
            logging.info("source data folder: %s", source_folder)

            critical_folder_on_ssd_autera = os.path.join(source_folder, 'criticalData')
            add_log(f"Critical data folder: {critical_folder_on_ssd_autera}")
            logging.info("critical_folder_on_ssd_autera: %s", critical_folder_on_ssd_autera)

            # Đảm bảo DEFAULT_SSD_MOUNT_POINT tồn tại và có nội dung
            if not os.path.exists(DEFAULT_SSD_MOUNT_POINT) or not os.listdir(DEFAULT_SSD_MOUNT_POINT):
                add_log(f"ERROR: External SSD mount point '{DEFAULT_SSD_MOUNT_POINT}' not found or empty.")
                logging.error(f"External SSD mount point '{DEFAULT_SSD_MOUNT_POINT}' not found or empty.")
                time.sleep(60)
                continue

            dst_external_ssd_name = os.listdir(DEFAULT_SSD_MOUNT_POINT)[0]
            dst_external_ssd_folder_name = os.path.join(DEFAULT_SSD_MOUNT_POINT,
                                                        dst_external_ssd_name,
                                                        'BlockBlob')
            Path(dst_external_ssd_folder_name).mkdir(exist_ok=True, parents=True)
            add_log(f"Destination SSD folder: {dst_external_ssd_folder_name}")

            if check_external_SSD_space(dst_external_ssd_folder_name, 100): # Kiểm tra 100GB
                add_log('ERROR: No more space remaining on external SSD (less than 100 GiB). Halting sync.')
                logging.info('no more space remaining....')
                # Thay vì sys.exit(), chỉ thoát chu kỳ hiện tại và chờ
                mark_there_is_no_process_running()
                time.sleep(60) # Chờ 5 phút trước khi kiểm tra lại
                continue

            # Chọn hàm sync bạn muốn chạy:
            # uncomment dòng này để chạy hàm move_parent_folder_of_txt_to_critical
            # add_log("Running critical data processing and rsync...")
            # move_parent_folder_of_txt_to_critical(source_folder, critical_folder_on_ssd_autera, dst_external_ssd_folder_name)
            
            add_log("Running real-time folder synchronization...")
            real_time_synchronize_folder(source_folder, dst_external_ssd_folder_name)
            # list_syned_raw = [] # Reset danh sách đã sync sau mỗi chu kỳ chính

        except Exception as ex:
            add_log(f"ERROR: Sync process failed: {ex}")
            logging.error("error sync data", exc_info=True)

        finally:
            add_log("Sync cycle finished. Deleting lock file.")
            logging.info("delete LOCK_FILE")
            mark_there_is_no_process_running()
        
        # Kiểm tra sự kiện dừng hoặc tạm dừng trước khi ngủ
        if stop_event.is_set():
            break
        if pause_event.is_set():
            add_log("Sync paused. Waiting for resume.")
            pause_event.wait() # Chờ cho đến khi được resume
        
        # Ngủ 5 phút trước chu kỳ tiếp theo
        add_log("Waiting 1 minutes for next sync cycle...")
        time.sleep(60) # 5 phút

def start_sync_thread():
    global sync_thread
    if sync_thread is None or not sync_thread.is_alive():
        stop_event.clear() # Đảm bảo không có lệnh dừng trước đó
        pause_event.set()  # Đảm bảo bắt đầu trong trạng thái chạy
        sync_thread = threading.Thread(target=main_sync_process, daemon=True)
        sync_thread.start()
        add_log("Sync process STARTED.")
        start_sync_process_btn.config(state=tk.DISABLED)
        pause_sync_process_btn.config(state=tk.NORMAL)
        end_sync_process_btn.config(state=tk.NORMAL)
    else:
        add_log("Sync process is already running.")

def pause_sync_thread():
    if sync_thread and sync_thread.is_alive():
        pause_event.clear() # Đặt sự kiện tạm dừng
        add_log("Sync process PAUSED.")
        pause_sync_process_btn.config(state=tk.DISABLED)
        start_sync_process_btn.config(state=tk.NORMAL) # Cho phép nhấn Start để Resume
    else:
        add_log("No active sync process to pause.")

def resume_sync_thread():
    if sync_thread and sync_thread.is_alive():
        pause_event.set() # Tiếp tục sự kiện
        add_log("Sync process RESUMED.")
        pause_sync_process_btn.config(state=tk.NORMAL)
        start_sync_process_btn.config(state=tk.DISABLED)
    else:
        add_log("No active sync process to resume.")

def end_sync_thread():
    global sync_thread
    if sync_thread and sync_thread.is_alive():
        stop_event.set() # Đặt sự kiện dừng
        pause_event.set() # Đảm bảo thoát khỏi trạng thái tạm dừng nếu có
        sync_thread.join(timeout=10) # Chờ luồng kết thúc (có timeout)
        if sync_thread.is_alive():
            add_log("WARNING: Sync thread did not terminate gracefully.")
        sync_thread = None
        add_log("Sync process ENDED.")
        start_sync_process_btn.config(state=tk.NORMAL)
        pause_sync_process_btn.config(state=tk.DISABLED)
        end_sync_process_btn.config(state=tk.DISABLED)
        mark_there_is_no_process_running() # Đảm bảo xóa lock file khi kết thúc
    else:
        add_log("No active sync process to end.")

# ======================================================================================================
# INIT GUI
# ======================================================================================================
root = tk.Tk()
root.title("Real-time transfer data from Autera to external SSD")
root.geometry("700x450") # Tăng chiều cao để có thêm không gian cho log

VEHICLE_ID_var = tk.StringVar(master=root,value=VEHICLE_ID)
DATE_var = tk.StringVar(master=root,value=TODAY_STRING)
btn_guiline = tk.Button(root, text="Help/?", command=open_guide_window)
btn_guiline.place(x=0, y=0)

tk.Label(root, text="Date (format YYYYMMDD, ex: 20250722):").place(x=0, y=40)
date_input_entry = tk.Entry(root)
date_input_entry.place(x=10, y=60)

date_input_submit_btn = tk.Button(root, height=1, width=4, text="submit",command=submit_date)
date_input_submit_btn.place(x=300, y=55)

tk.Label(root, text="VEHIVLE_ID (format VFX, ex: VF8FL2_VN_LS1551):").place(x=0, y=90)
VEHICLE_ID_input_entry = tk.Entry(root)
VEHICLE_ID_input_entry.place(x=10, y=110)

tk.Label(root,textvariable=VEHICLE_ID_var,font=("Arial", 8)).place(x=200, y=120)
tk.Label(root,textvariable=DATE_var,font=("Arial", 8)).place(x=200, y=65)

VEHICLE_ID_input_submit_btn = tk.Button(root, height=1, width=4, text="submit",command=submit_vehicle_id)
VEHICLE_ID_input_submit_btn.place(x=300, y=105)

# Tăng chiều cao của log_box
log_box = tk.Text(root, height=8, width=100, state=tk.NORMAL, wrap=tk.WORD) # wrap=tk.WORD để ngắt dòng
log_box.place(x=0, y=310)
add_log("==> Process start. Please configure Date/VEHICLE_ID and click START SYNC.")


start_sync_process_btn = tk.Button(
    root,
    height=2, width=14,
    text="▶START SYNC",
    bg="#28a745",        # xanh lá
    fg="white",          # chữ trắng
    activebackground="#218838",
    activeforeground="white",
    font=("Arial", 10, "bold"),
    relief="groove",     # viền nhẹ
    bd=3,
    command=start_sync_thread # Gắn vào hàm bắt đầu luồng
)
start_sync_process_btn.place(x=550, y=20)

pause_sync_process_btn = tk.Button(
    root,
    height=2, width=14,
    text="PAUSE SYNC",
    bg="#ffc107",        # vàng cam
    fg="black",
    activebackground="#e0a800",
    activeforeground="black",
    font=("Arial", 10, "bold"),
    relief="groove",
    bd=3,
    command=pause_sync_thread, # Gắn vào hàm tạm dừng luồng
    state=tk.DISABLED # Bắt đầu ở trạng thái bị vô hiệu hóa
)
pause_sync_process_btn.place(x=550, y=80)

end_sync_process_btn = tk.Button(
    root,
    height=2, width=14,
    text="END SYNC",
    bg="#dc3545",
    fg="white",
    activebackground="#c82333",
    activeforeground="white",
    font=("Arial", 10, "bold"),
    relief="groove",
    bd=3,
    command=end_sync_thread, # Gắn vào hàm kết thúc luồng
    state=tk.DISABLED # Bắt đầu ở trạng thái bị vô hiệu hóa
)
end_sync_process_btn.place(x=550, y=140)

ssd_space_label = tk.Label(root, text="SSD space remaining: ...", font=("Arial", 8))
ssd_space_label.place(y=297, x=485)

def up2date_external_SSD_space():
    try:
        # Kiểm tra xem DEFAULT_SSD_MOUNT_POINT có nội dung không
        if not os.path.exists(DEFAULT_SSD_MOUNT_POINT) or not os.listdir(DEFAULT_SSD_MOUNT_POINT):
            ssd_space_label.config(text="SSD space remaining: SSD not detected")
            root.after(5000, up2date_external_SSD_space)
            return

        dst_external_ssd_name = os.listdir(DEFAULT_SSD_MOUNT_POINT)[0]
        ssd_path = os.path.join(DEFAULT_SSD_MOUNT_POINT, dst_external_ssd_name)
        
        if not os.path.exists(ssd_path):
            ssd_space_label.config(text="SSD space remaining: Path ERROR")
            root.after(5000, up2date_external_SSD_space)
            return


        total, used, free = shutil.disk_usage(ssd_path)

        free_GB = free / (1024 ** 3)
        total_GB = total / (1024 ** 3)

        # cập nhật label
        ssd_space_label.config(
            text=f"SSD space remaining: {free_GB:.1f} / {total_GB:.1f} GiB"
        )

    except Exception as e:
        ssd_space_label.config(text=f"SSD space remaining: ERROR ({e})")
        logging.error(f"Error updating SSD space: {e}", exc_info=True)


    # gọi lại sau 5 giây
    root.after(5000, up2date_external_SSD_space)

# gọi lần đầu
up2date_external_SSD_space()


root.mainloop()

# Đảm bảo luồng kết thúc khi GUI đóng
# Nếu người dùng đóng cửa sổ Tkinter mà không nhấn END SYNC
# Cần xử lý để luồng daemon cũng kết thúc
stop_event.set()
pause_event.set() # Đảm bảo luồng thoát khỏi wait nếu bị tạm dừng
if sync_thread and sync_thread.is_alive():
    sync_thread.join(timeout=5)
    if sync_thread.is_alive():
        logging.warning("Sync thread did not terminate after GUI closed.")
mark_there_is_no_process_running() # Đảm bảo lock file được xóa khi chương trình kết thúc
logging.info("Application closed.")