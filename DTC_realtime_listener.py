"""
dtc_console_vector_full.py
CLI tool để:
 - kết nối Vector CAN (Windows)
 - đọc / xóa DTC theo OBD-II (Mode 01/02/03/04/07/09) (đơn giản)
 - đọc / xóa DTC theo UDS (ISO-TP + 0x19 ReadDTCInformation, 0x14 ClearDiagnosticInformation)
 
Yêu cầu:
  pip install python-can can-isotp udsoncan

Ghi chú kỹ thuật:
 - OBD-II "multi-frame" (ISO-TP) thường cần layer ISO-TP -> dùng UDS stack (udsoncan + can-isotp) để xử lý an toàn.
 - Tool này hỗ trợ 2 luồng: gửi/recv CAN raw cho OBD "single-frame" và UDS via isotp/udsoncan cho multi-frame/UDS.
 - Nếu ECU không trả Mode03 (xe EV đời mới), dùng UDS (uds_setup + uds_* commands).
"""

import sys
import time
import binascii

# CAN / Vector / ISO-TP / UDS libs
try:
    import can
except Exception as e:
    print("Thiếu thư viện 'python-can'. Cài: pip install python-can")
    raise

# optional imports (UDS)
try:
    import isotp
    from udsoncan.connections import PythonIsoTpConnection
    from udsoncan.client import Client
    import udsoncan.configs as uds_configs
    from udsoncan import exceptions as uds_exceptions
    import udsoncan
    HAVE_UDS = True
except Exception:
    HAVE_UDS = False

# VectorBus availability (preferred)
try:
    from can.interfaces.vector import VectorBus
    HAS_VECTORBUS = True
except Exception:
    HAS_VECTORBUS = False

# -------------------------
# HELP / Globals
# -------------------------
PROMPT = ">> "
bus = None                    # python-can Bus (Vector)
notifier = None               # can.Notifier (optional, used by isotp stack)
isotp_stack = None            # isotp stack (NotifierBasedCanStack)
uds_conn = None               # PythonIsoTpConnection
uds_client = None             # udsoncan.Client (entered context)
uds_config = None             # config copy
uds_address = None            # (txid, rxid)
DEFAULT_BITRATE = 500000

def print_help():
    print("""
Lệnh hỗ trợ (gõ help để hiện lại):
  connect <channel> [bitrate] [app_name]   - Kết nối Vector (vd: connect 0 500000 CANalyzer)
  disconnect                               - Ngắt kết nối CAN
  dtc                                      - Đọc DTC (OBD-II Mode 03, gửi 0x7DF)
  pending                                  - Đọc Pending DTCs (OBD Mode 07)
  freeze                                   - Đọc Freeze Frame (OBD Mode 02)
  clear                                    - Xóa DTC (OBD Mode 04)
  info                                     - Lấy VIN (OBD Mode 09 PID 02)  *multi-frame có thể fail*
  sensor <PID_hex>                         - Đọc sensor (OBD Mode 01, PID ví dụ 0C = RPM)
  uds_setup [txid_hex] [rxid_hex]          - Setup UDS ISO-TP stack (mặc định 0x7E0 -> 0x7E8)
  uds_close                                - Đóng UDS client
  uds_supported                            - Đọc DTCs supported (UDS 0x19 subfn = reportSupportedDTCs)
  uds_list_all                             - Đọc tất cả DTC (UDS: reportDTCByStatusMask, mặc định status_mask=0xFF)
  uds_first_confirmed                      - Lấy first confirmed DTC
  uds_clear [group_mask_hex (optional)]    - Xóa DTC bằng UDS (0x14). default = 0xFFFFFF (tất cả)
  exit                                     - Thoát
  help                                     - Xem hướng dẫn
""")

# -------------------------
# Utility helpers
# -------------------------
def hex_or_int(s):
    """Chuyển string hex/dec thành int"""
    try:
        if isinstance(s, int):
            return s
        s = s.strip().lower()
        if s.startswith("0x"):
            return int(s, 16)
        return int(s, 10)
    except Exception:
        raise ValueError(f"Không parse được số: {s}")

def safe_print(msg):
    print(msg, flush=True)

# -------------------------
# CAN / OBD functions (raw, đơn giản)
# -------------------------
def connect_vector(channel=0, bitrate=DEFAULT_BITRATE, app_name="CANalyzer"):
    global bus, notifier
    if bus is not None:
        safe_print("⚠️ Bus đã kết nối trước đó. Gõ 'disconnect' trước khi connect mới.")
        return

    try:
        # ưu tiên VectorBus nếu có (được udsoncan docs dùng trong ví dụ)
        if HAS_VECTORBUS:
            safe_print(f"Đang tạo VectorBus(channel={channel}, bitrate={bitrate}) ...")
            bus = VectorBus(channel=int(channel), bitrate=int(bitrate), app_name=app_name)
        else:
            # fallback: python-can interface
            safe_print(f"Đang tạo can.interface.Bus(bustype='vector', channel={channel}, bitrate={bitrate}) ...")
            bus = can.interface.Bus(bustype='vector', channel=int(channel), bitrate=int(bitrate), app_name=app_name)

        # tạo notifier rỗng + printer để debug — isotp stack có thể đăng ký listener vào notifier này
        notifier = can.Notifier(bus, [can.Printer()], timeout=1.0)
        safe_print(f"✅ Kết nối Vector channel {channel} thành công (bitrate={bitrate}).")
    except Exception as e:
        bus = None
        notifier = None
        safe_print("❌ Kết nối thất bại: " + str(e))

def disconnect_vector():
    global bus, notifier, isotp_stack, uds_conn, uds_client
    if uds_client:
        try:
            uds_client.__exit__(None, None, None)
        except Exception:
            pass
        uds_client = None
    if uds_conn:
        try:
            uds_conn.close()
        except Exception:
            pass
        uds_conn = None
    if isotp_stack:
        try:
            isotp_stack.close()
        except Exception:
            pass
    if notifier:
        try:
            notifier.stop()
        except Exception:
            pass
    if bus:
        try:
            bus.shutdown()
        except Exception:
            pass
    bus = None
    notifier = None
    isotp_stack = None
    safe_print("Đã ngắt kết nối CAN (Vector).")

def send_obd_request(service, pid=None, expect_resp=True, timeout=2.0):
    """
    Gửi OBD-II request theo cách 'raw' tới functional ID 0x7DF.
    Lưu ý: phương pháp này phù hợp với single-frame replies. Multi-frame (ISO-TP) cần isotp/UDS.
    Trả về data payload của frame phản hồi (mảng byte) hoặc None.
    """
    global bus
    if not bus:
        safe_print("⚠️ Chưa kết nối bus. Gõ connect trước.")
        return None

    # xây payload 8 bytes (simple)
    if pid is None:
        data = [0x02, service, 0x00] + [0x00]*5
    else:
        data = [0x02, service, pid & 0xFF] + [0x00]*5

    msg = can.Message(arbitration_id=0x7DF, data=bytearray(data), is_extended_id=False)
    try:
        bus.send(msg)
    except Exception as e:
        safe_print("❌ Lỗi gửi OBD request: " + str(e))
        return None

    start = time.time()
    expected_service = service + 0x40
    while time.time() - start < timeout:
        rx = bus.recv(timeout=0.5)
        if rx is None:
            continue
        # phản hồi thường ở 0x7E8..0x7EF
        if 0x7E8 <= rx.arbitration_id <= 0x7EF:
            data = list(rx.data)
            # trong nhiều trace, data[1] = positive service (ví dụ 0x43 cho Mode03)
            # nhưng có thể có PCI byte (trong ISO-TP). Ở đây ta cố gắng dò:
            # nếu data[1] == expected_service -> ok
            if len(data) >= 2 and data[1] == expected_service:
                return data
            # đôi khi single-frame không có leading PCI, thử dò data[0] == expected_service
            if data[0] == expected_service:
                return data
            # else: tiếp tục dò (có thể không phải khung mong đợi)
    # timeout
    return None

def decode_obd_mode03_from_data(data):
    """
    Giải DTC theo SAE J2012 khi payload đã ở dạng bytes chứa ngay sau byte service.
    Input data là list/int bytes bắt đầu tại vị trí payload (nếu data[0]==pci, data[1]==0x43, v.v.)
    Cách đơn giản: tìm hai byte liên tiếp (A,B) sau service byte -> convert theo quy tắc cũ (của bạn).
    Lưu ý: đây chỉ simple decode; UDS/udsoncan có decode mạnh hơn.
    """
    # find index of 0x43 positive response
    idx = None
    for i, b in enumerate(data):
        if b == 0x43:
            idx = i
            break
    if idx is None:
        # có thể data[0] == 0x43
        if data and data[0] == 0x43:
            idx = 0
        else:
            return []
    # bytes after idx+1 are DTC bytes (pair)
    dtc_bytes = data[idx+1:]
    dtcs = []
    for i in range(0, len(dtc_bytes), 2):
        if i+1 >= len(dtc_bytes):
            break
        a, b = dtc_bytes[i], dtc_bytes[i+1]
        if a == 0 and b == 0:
            continue
        first = (a & 0xC0) >> 6
        ch_map = {0:'P',1:'C',2:'B',3:'U'}
        code_chr = ch_map[first]
        digit1 = (a & 0x30) >> 4
        digit2 = (a & 0x0F)
        code = f"{code_chr}{digit1}{digit2}{b:02X}"
        dtcs.append(code)
    return dtcs

# -------------------------
# UDS functions (udsoncan + isotp)
# -------------------------
def uds_setup(txid=0x7E0, rxid=0x7E8, isotp_params=None, uds_req_timeout=5):
    """
    Thiết lập ISO-TP + UDS client (persistent).
    txid/rxid: tester->ECU (txid) và ECU->tester (rxid) theo Normal 11-bit addressing (ví dụ 0x7E0/0x7E8).
    """
    global bus, notifier, isotp_stack, uds_conn, uds_client, uds_config, uds_address

    if not HAVE_UDS:
        safe_print("❌ Thiếu thư viện UDS/ISOTP (udsoncan/isotp). Cài: pip install can-isotp udsoncan")
        return

    if not bus:
        safe_print("⚠️ Chưa kết nối CAN. Gõ connect trước.")
        return

    try:
        # params cơ bản theo ví dụ docs (tùy chỉnh nếu cần)
        isotp_params = isotp_params or {
            'stmin': 10,
            'blocksize': 8,
            'wftmax': 0,
            'tx_data_length': 8,
            'tx_data_min_length': None,
            'tx_padding': 0,
            'rx_flowcontrol_timeout': 1000,
            'rx_consecutive_frame_timeout': 1000,
            'override_receiver_stmin': None,
            'max_frame_size': 4095,
            'can_fd': False,
            'bitrate_switch': False,
            'rate_limit_enable': False,
            'rate_limit_max_bitrate': 1000000,
            'rate_limit_window_size': 0.2,
            'listen_mode': False,
        }

        # copy default client config and tweak timeout
        uds_config = dict(uds_configs.default_client_config)
        # optional: raise exceptions on negative responses? leave default
        # uds_config['exception_on_negative_response'] = False

        # build Addr and stack
        tp_addr = isotp.Address(isotp.AddressingMode.Normal_11bits, txid=txid, rxid=rxid)
        # reuse existing notifier so that printing/logging vẫn hiện
        if notifier is None:
            notifier = can.Notifier(bus, [can.Printer()])

        # NotifierBasedCanStack sẽ thêm listener vào notifier
        isotp_stack = isotp.NotifierBasedCanStack(bus=bus, notifier=notifier, address=tp_addr, params=isotp_params)

        uds_conn = PythonIsoTpConnection(isotp_stack)
        uds_client = Client(uds_conn, config=uds_config, request_timeout=uds_req_timeout)

        # mở kết nối (client context enter)
        uds_client.__enter__()   # tương đương with Client(...):
        uds_address = (txid, rxid)
        safe_print(f"✅ UDS client opened (txid=0x{txid:X}, rxid=0x{rxid:X}).")
    except Exception as e:
        safe_print("❌ Lỗi khi setup UDS: " + str(e))
        # cleanup partial
        try:
            if uds_client:
                uds_client.__exit__(None, None, None)
        except Exception:
            pass

def uds_close():
    global uds_client, uds_conn, isotp_stack
    if uds_client:
        try:
            uds_client.__exit__(None, None, None)
        except Exception:
            pass
        uds_client = None
    if uds_conn:
        try:
            uds_conn.close()
        except Exception:
            pass
        uds_conn = None
    if isotp_stack:
        try:
            isotp_stack.close()
        except Exception:
            pass
        isotp_stack = None
    safe_print("UDS client đóng.")

def print_udsoncan_dtcs(dtcs):
    """
    dtcs: list of udsoncan.common.dtc.Dtc
    In ra dạng readable: ID hex + status byte + status flags.
    """
    for d in dtcs:
        id_hex = f"0x{d.id:06X}"
        status_byte = d.status.get_byte_as_int()
        flags = []
        st = d.status
        if st.test_failed: flags.append("test_failed")
        if st.test_failed_this_operation_cycle: flags.append("test_failed_this_cycle")
        if st.pending: flags.append("pending")
        if st.confirmed: flags.append("confirmed")
        if st.test_not_completed_since_last_clear: flags.append("not_completed_since_last_clear")
        if st.test_failed_since_last_clear: flags.append("failed_since_last_clear")
        if st.test_not_completed_this_operation_cycle: flags.append("not_completed_this_cycle")
        if st.warning_indicator_requested: flags.append("warning_ind_req")
        print(f"  DTC {id_hex}  status=0x{status_byte:02X}  flags={','.join(flags)}")

# UDS actions:
def uds_supported_dtc():
    global uds_client
    if not uds_client:
        safe_print("⚠️ UDS client chưa setup. Gõ uds_setup trước.")
        return
    try:
        resp = uds_client.get_supported_dtc()
        # resp.service_data.dtcs là list of Dtc
        dtcs = resp.service_data.dtcs
        if not dtcs:
            safe_print("✅ Không có DTC 'supported' trả về (empty).")
            return
        safe_print("✅ DTC supported:")
        print_udsoncan_dtcs(dtcs)
    except uds_exceptions.NegativeResponseException as e:
        safe_print(f"UDS negative response: {e}")
    except Exception as e:
        safe_print("Lỗi khi đọc supported DTC: " + str(e))

def uds_list_all_dtc(status_mask=0xFF):
    global uds_client
    if not uds_client:
        safe_print("⚠️ UDS client chưa setup. Gõ uds_setup trước.")
        return
    try:
        # subfunction reportDTCByStatusMask
        resp = uds_client.get_dtc_with_permanent_status() if False else uds_client.get_supported_dtc()  # placeholder
        # Better: use ReadDTCInformation.make_request but client helper funcs exist.
        # Let's attempt reportDTCByStatusMask via client.read_all_dtc_by_status_mask (not public), so use helper:
        resp = uds_client.read_dtc(status_mask=status_mask) if hasattr(uds_client, 'read_dtc') else None
        # Fallback: use generic ReadDTCInformation subfunction call
        if resp is None:
            # use low-level: ReadDTCInformation.make_request then client.connection
            from udsoncan.services import ReadDTCInformation
            req = ReadDTCInformation.make_request(ReadDTCInformation.Subfunction.reportDTCByStatusMask, status_mask=status_mask)
            response = uds_client.connection.send(req.get_payload(), decode=False)
            # interpret response
            interpreted = ReadDTCInformation.interpret_response(response, ReadDTCInformation.Subfunction.reportDTCByStatusMask)
            dtcs = interpreted.service_data.dtcs
        else:
            # if resp present and has service_data
            dtcs = resp.service_data.dtcs if hasattr(resp, 'service_data') else []
        if not dtcs:
            safe_print("✅ Không có DTC trả về (UDS).")
            return
        safe_print("✅ DTC list (UDS):")
        print_udsoncan_dtcs(dtcs)
    except uds_exceptions.NegativeResponseException as e:
        safe_print(f"UDS negative response: {e}")
    except Exception as e:
        safe_print("Lỗi khi đọc DTC (UDS): " + str(e))

def uds_first_confirmed():
    global uds_client
    if not uds_client:
        safe_print("⚠️ UDS client chưa setup. Gõ uds_setup trước.")
        return
    try:
        resp = uds_client.get_first_confirmed_dtc()
        if resp is None or not hasattr(resp, 'service_data') or not resp.service_data.dtcs:
            safe_print("Không có first confirmed DTC.")
            return
        print_udsoncan_dtcs(resp.service_data.dtcs)
    except Exception as e:
        safe_print("Lỗi: " + str(e))

def uds_clear(group_mask=0xFFFFFF):
    global uds_client
    if not uds_client:
        safe_print("⚠️ UDS client chưa setup. Gõ uds_setup trước.")
        return
    try:
        # client.clear_dtc exists (wrapper cho ClearDiagnosticInformation)
        if hasattr(uds_client, 'clear_dtc'):
            rsp = uds_client.clear_dtc(group=int(group_mask))
            safe_print("✅ Yêu cầu xóa DTC (UDS) đã gửi. Kiểm tra response:")
            safe_print(str(rsp))
        else:
            # fallback: craft service request
            from udsoncan.services import ClearDiagnosticInformation
            req = ClearDiagnosticInformation.make_request(group=int(group_mask))
            response = uds_client.connection.send(req.get_payload(), decode=False)
            safe_print("✅ gửi ClearDiagnosticInformation (raw). Response: " + str(response))
    except uds_exceptions.NegativeResponseException as e:
        safe_print("UDS negative response khi clear DTC: " + str(e))
    except Exception as e:
        safe_print("Lỗi khi clear DTC (UDS): " + str(e))

# -------------------------
# Console / main loop
# -------------------------
def main():
    print("=== DTC Console Tool (Vector) - Full (OBD + UDS) ===")
    print_help()
    while True:
        try:
            cmdline = input(PROMPT)
            if not cmdline:
                continue
            parts = cmdline.strip().split()
            cmd = parts[0].lower()

            if cmd == "exit":
                safe_print("Thoát. Đang cleanup...")
                disconnect_vector()
                break

            elif cmd == "help":
                print_help()

            elif cmd == "connect":
                if len(parts) < 2:
                    safe_print("Thiếu channel. Ví dụ: connect 0")
                    continue
                ch = parts[1]
                bitrate = int(parts[2]) if len(parts) >= 3 else DEFAULT_BITRATE
                app_name = parts[3] if len(parts) >= 4 else "CANalyzer"
                connect_vector(channel=ch, bitrate=bitrate, app_name=app_name)

            elif cmd == "disconnect":
                disconnect_vector()

            elif cmd == "dtc":
                data = send_obd_request(0x03)
                if data is None:
                    safe_print("⚠️ Không nhận được phản hồi OBD Mode03 (Mode 03).")
                else:
                    dtcs = decode_obd_mode03_from_data(data)
                    if not dtcs:
                        safe_print("✅ Không có DTC (OBD Mode03) hoặc không thể decode.")
                    else:
                        safe_print("DTC (OBD Mode03):")
                        for d in dtcs:
                            print("  ", d)

            elif cmd == "pending":
                data = send_obd_request(0x07)
                if not data:
                    safe_print("Không nhận được phản hồi Mode07.")
                else:
                    safe_print("Raw reply: " + str(data))

            elif cmd == "freeze":
                data = send_obd_request(0x02)
                if not data:
                    safe_print("Không nhận được Freeze Frame.")
                else:
                    safe_print("Raw freeze frame reply: " + str(data))

            elif cmd == "clear":
                data = send_obd_request(0x04)
                if data:
                    safe_print("Gửi Mode04 (Clear). Kiểm tra ECU/cluster. Response raw: " + str(data))
                else:
                    safe_print("Không nhận được phản hồi khi gửi Mode04 (có thể ECU không trả single-frame).")

            elif cmd == "info":
                data = send_obd_request(0x09, pid=0x02)
                if not data:
                    safe_print("Không đọc được VIN bằng Mode09 (có thể multi-frame -> dùng UDS).")
                else:
                    # kiểu 'raw' — extract printable chars after service byte if present
                    s = bytes(data)
                    # naive try: tìm service byte 0x49 (09 + 0x40 = 0x49) rồi printf bytes sau đó as ascii
                    try:
                        idx = s.index(0x49)
                        vin_bytes = s[idx+1:]
                        vin = bytes([b for b in vin_bytes if b != 0]).decode(errors='ignore')
                        safe_print("VIN (OBD raw): " + vin)
                    except Exception:
                        safe_print("Không parse VIN từ raw data: " + str(s))

            elif cmd == "sensor":
                if len(parts) < 2:
                    safe_print("Ví dụ: sensor 0C  (0C = engine RPM)")
                    continue
                try:
                    pid = hex_or_int(parts[1])
                except ValueError as ex:
                    safe_print(str(ex)); continue
                data = send_obd_request(0x01, pid=pid)
                if not data:
                    safe_print("Không đọc được PID.")
                else:
                    safe_print("Raw sensor reply: " + str(data))

            elif cmd == "uds_setup":
                if len(parts) >= 3:
                    try:
                        txid = hex_or_int(parts[1])
                        rxid = hex_or_int(parts[2])
                    except Exception as e:
                        safe_print("Không parse txid/rxid: " + str(e)); continue
                else:
                    txid, rxid = 0x7E0, 0x7E8
                uds_setup(txid=txid, rxid=rxid)

            elif cmd == "uds_close":
                uds_close()

            elif cmd == "uds_supported":
                uds_supported_dtc()

            elif cmd == "uds_list_all":
                # default status mask 0xFF (tùy ECU)
                uds_list_all_dtc(status_mask=0xFF)

            elif cmd == "uds_first_confirmed":
                uds_first_confirmed()

            elif cmd == "uds_clear":
                mask = 0xFFFFFF
                if len(parts) >= 2:
                    try:
                        mask = hex_or_int(parts[1])
                    except Exception as e:
                        safe_print("Không parse group mask: " + str(e)); continue
                uds_clear(group_mask=mask)

            else:
                safe_print("⚠️ Lệnh không hợp lệ. Gõ 'help' để xem danh sách.")
        except KeyboardInterrupt:
            safe_print("\nNgắt chương trình (Ctrl-C).")
            disconnect_vector()
            break
        except Exception as e:
            safe_print("❌ Lỗi trong loop: " + str(e))

if __name__ == "__main__":
    main()
