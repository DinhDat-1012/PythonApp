def main():
    try:
        number = float(input("Nhập một số: "))

        print(f"Số bạn đã nhập: {number}")
        print(f"Giá trị bình phương: {number ** 2}")
        print(f"Giá trị căn bậc hai: {number ** 0.5}")
    except ValueError:
        print("Vui lòng nhập một số hợp lệ!")

if __name__ == "__main__":
    main()
