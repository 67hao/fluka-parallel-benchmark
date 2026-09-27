# Hướng Dẫn Toàn Tập: Setup & Chạy FLUKA Song Song Trên GitHub Actions (16 - 32 vCPU Miễn Phí)

Tài liệu này hướng dẫn chi tiết từ A-Z cách biến **GitHub Actions** thành một cụm siêu máy tính phân tán (Cluster) để chạy mô phỏng hạt nhân **FLUKA v4**, phục vụ nghiên cứu vật lý hạt nhân (như dự án phòng thí nghiệm TEXONO) mà **không tốn 1% tài nguyên máy tính cá nhân**.

---

## Mục Lục
1. [Nguyên Lý Hoạt Động & Lợi Thế](#1-nguyên-lý-hoạt-động--lợi-thế)
2. [Bước 1: Chuẩn Bị Kho Lưu Trữ (GitHub Repository)](#bước-1-chuẩn-bị-kho-lưu-trữ-github-repository)
3. [Bước 2: Xử Lý Bộ Cài Đặt FLUKA (.deb)](#bước-2-xử-lý-bộ-cài-đặt-fluka-deb)
4. [Bước 3: Chuẩn Bị Input Decks & Random Seeds](#bước-3-chuẩn-bị-input-decks--random-seeds)
5. [Bước 4: Cấu Hình Pipeline GitHub Actions (.yml)](#bước-4-cấu-hình-pipeline-github-actions-yml)
6. [Bước 5: Kích Hoạt & Theo Dõi Mô Phỏng](#bước-5-kích-hoạt--theo-dõi-mô-phỏng)
7. [Bước 6: Thu Thập & Phân Tích Dữ Liệu Đầu Ra](#bước-6-thu-thập--phân-tích-dữ-liệu-đầu-ra)
8. [Các Lỗi Thường Gặp & Cách Khắc Phục (Troubleshooting)](#các-lỗi-thường-gặp--cách-khắc-phục-troubleshooting)

---

## 1. Nguyên Lý Hoạt Động & Lợi Thế

* **Bản chất Monte Carlo:** Mô phỏng hạt mang tính ngẫu nhiên độc lập thống kê (Embarrassingly Parallel). 100 triệu hạt chạy trên 1 máy trong 30 tiếng cho kết quả tương đương 100% việc chia cho 16 máy, mỗi máy chạy 6.25 triệu hạt với các hạt giống ngẫu nhiên (`RANDOMIZ`) khác nhau trong ~1.8 tiếng.
* **Cấu hình phần cứng:**
  * Mỗi máy ảo GitHub (Runner) có **2 vCPU, 7 GB RAM, ~25 GB SSD**.
  * Chạy đồng thời tối đa **20 máy ảo cùng lúc** (tương đương **40 vCPU, 140 GB RAM** hoàn toàn miễn phí).
  * Chạy tối đa **6 tiếng / job** và **0 giây cooldown** (hết lượt này bấm chạy tiếp lượt khác ngay).
* **Chi phí:** **0 VNĐ** (Chỉ cần Repo để chế độ **Public**).

---

## 2. Bước 1: Chuẩn Bị Kho Lưu Trữ (GitHub Repository)

1. Đăng nhập vào [GitHub](https://github.com/).
2. Nhấn nút **New repository** (Tạo repo mới):
   * **Repository name:** `fluka-parallel-benchmark` (hoặc tên dự án của bạn).
   * **Visibility:** Chọn **Public** (Bắt buộc chọn Public để hưởng miễn phí không giới hạn số phút GitHub Actions và dung lượng lưu trữ Artifacts).
   * **Initialize with:** Tích chọn `Add a README file`.
3. Bấm **Create repository**.

---

## 3. Bước 2: Xử Lý Bộ Cài Đặt FLUKA (.deb)

GitHub có quy định: **Không cho phép đẩy (push) file đơn lẻ vượt quá 100 MB**. 
Gói cài đặt FLUKA `.deb` chính thức từ CERN (`fluka_4-5.2.x86-Linux-gfor9_amd64.deb`) nặng khoảng **141 MB**. Do đó, chúng ta cần cắt đôi file trước khi đưa lên Git.

### 2.1. Cắt file trên Windows (PowerShell):
Mở PowerShell tại thư mục chứa file `.deb` và chạy:
```powershell
# Tạo thư mục packages
New-Item -ItemType Directory -Force -Path packages

# Đọc và cắt file deb thành 2 phần <= 75MB
$filePath = "fluka_4-5.2.x86-Linux-gfor9_amd64.deb"
$stream = [System.IO.File]::OpenRead($filePath)
$chunkSize = 75MB
$buffer = New-Object byte[] $chunkSize
$partNumber = 1

while ($bytesRead = $stream.Read($buffer, 0, $buffer.Length)) {
    $partName = "packages/fluka_deb.part_{0:D2}" -f $partNumber
    $outStream = [System.IO.File]::Create($partName)
    $outStream.Write($buffer, 0, $bytesRead)
    $outStream.Close()
    Write-Host "Da tao: $partName ($([math]::round($bytesRead/1MB, 2)) MB)"
    $partNumber++
}
$stream.Close()
```
Kết quả sinh ra 2 file:
* `packages/fluka_deb.part_01` (~75 MB)
* `packages/fluka_deb.part_02` (~66 MB)

> Khi lên máy ảo GitHub Actions, hệ thống sẽ dùng lệnh bash `cat packages/fluka_deb.part_* > fluka.deb` để ghép lại nguyên vẹn trong 1 giây.

---

## 4. Bước 3: Chuẩn Bị Input Decks & Random Seeds

Mỗi máy ảo cần chạy một file input riêng biệt để tránh trùng lặp thống kê. Yếu tố quan trọng nhất trong FLUKA là thẻ **`RANDOMIZ`**.

### 4.1. Quy tắc thẻ RANDOMIZ trong FLUKA:
```text
*...+....1....+....2....+....3....+....4....+....5....+....6....+....7....+....8
RANDOMIZ      1.00001087654.00
```
* **WHAT(1):** `1.0` (chọn bộ sinh số ngẫu nhiên mặc định).
* **WHAT(2):** Số nguyên bất kỳ (Ví dụ: `1087654.0`, `2087654.0`,...). **Bắt buộc mỗi task phải có số này khác nhau!**

### 4.2. Thẻ LOW-PWXS (Cực kỳ quan trọng để tối ưu hóa):
Trong FLUKA 4, nếu bạn dùng cấu hình chính xác cao (`DEFAULTS PRECISIO`), FLUKA sẽ tự động tìm kiếm thư viện nơtron điểm (Pointwise data) nặng 2–3 GB. Nếu bài toán của bạn là tương tác tia Gamma/Photon/Electron qua vật liệu che chắn, hãy thêm thẻ:
```text
LOW-PWXS     -1.0000
```
Thẻ này giúp tắt yêu cầu nạp thư viện nơtron 3 GB, giúp máy ảo cài đặt FLUKA siêu tốc chỉ trong 10 giây.

### 4.3. Script Python tự động sinh 16 hoặc 32 tasks (`generate_tasks.py`):
Tạo file `generate_tasks.py` trong thư mục gốc dự án:
```python
import os

NUM_TASKS = 16  # Hoặc đổi thành 32
PRIMARIES = 250000  # Số hạt mỗi task

for i in range(1, NUM_TASKS + 1):
    task_id = f"{i:02d}"
    task_dir = os.path.join("inputs", f"task_{task_id}")
    os.makedirs(task_dir, exist_ok=True)
    
    seed = 1000000 + i * 87654
    # Độ dày thay đổi (ví dụ khảo sát che chắn từ 0.5cm đến 8cm)
    shield_thick = i * 0.5
    
    inp_content = f"""TITLE
FLUKA Benchmark - Task {task_id}
*...+....1....+....2....+....3....+....4....+....5....+....6....+....7....+....8
DEFAULTS                                                              PRECISIO  
LOW-PWXS     -1.0000                                                            
BEAM         -0.0026                                                  PHOTON    
BEAMPOS       0.0000    0.0000  -10.0000                                        
RANDOMIZ      1.0000{seed:9.1f}                                                  
GEOBEGIN                                                              COMBNAME  
    0    0          Geometry
RPP beamBox      -15.0      15.0     -15.0      15.0     -12.0      -2.0
RPP shield       -25.0      25.0     -25.0      25.0       0.0  {shield_thick:8.2f}
RPP detBox       -10.0      10.0     -10.0      10.0      1.50      6.50
RPP airBox       -60.0      60.0     -60.0      60.0     -30.0      60.0
RPP blkBox      -100.0     100.0    -100.0     100.0    -100.0     100.0
END
TARGET   5 +beamBox
SHIELD   5 +shield
DETECTOR 5 +detBox
AIR      5 +airBox -beamBox -shield -detBox
BLKHOLE  5 +blkBox -airBox
END
GEOEND                                                                          
MATERIAL     32.0000              5.3230                              GERMANIU  
ASSIGNMA      COPPER    TARGET                                                  
ASSIGNMA        LEAD    SHIELD                                                  
ASSIGNMA    GERMANIU  DETECTOR                                                  
ASSIGNMA         AIR       AIR                                                  
ASSIGNMA    BLCKHOLE   BLKHOLE                                                  
USRTRACK      1.0000    PHOTON  -41.0000  DETECTOR 2000.0000   50.0000DetFlux   
USRTRACK      0.0030    0.0000                                        &         
START     {PRIMARIES:10.2f}                                                            
STOP
"""
    with open(os.path.join(task_dir, f"task_{task_id}.inp"), "w", encoding="utf-8") as f:
        f.write(inp_content)

print(f"Da sinh thanh cong {NUM_TASKS} task input decks.")
```
Chạy file này: `python generate_tasks.py`. Thư mục `inputs/task_01` đến `inputs/task_16` sẽ được tạo ra.

---

## 5. Bước 4: Cấu Hình Pipeline GitHub Actions (.yml)

Tạo file tại đường dẫn: `.github/workflows/fluka_parallel.yml` với nội dung hoàn chỉnh:

```yaml
name: FLUKA Cloud Parallel Computing

on:
  workflow_dispatch:
    inputs:
      primaries:
        description: 'Số hạt cho mỗi task'
        required: false
        default: '250000'

jobs:
  run-fluka-matrix:
    name: Task ${{ matrix.task_id }}
    runs-on: ubuntu-22.04  # Bắt buộc dùng 22.04 vì tương thích hoàn hảo với gfortran-9
    strategy:
      fail-fast: false
      matrix:
        task_id: [
          "01", "02", "03", "04",
          "05", "06", "07", "08",
          "09", "10", "11", "12",
          "13", "14", "15", "16"
        ]

    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Install FLUKA
        shell: bash
        run: |
          echo ">>> [1/3] Ghép file .deb..."
          cat packages/fluka_deb.part_* > fluka.deb
          
          echo ">>> [2/3] Cài đặt gfortran-9 và thư viện hỗ trợ..."
          sudo apt-get update -qq
          sudo apt-get install -y -qq gfortran-9 libgfortran5
          
          echo ">>> [3/3] Cài đặt gói FLUKA..."
          sudo dpkg -i --force-depends fluka.deb || sudo apt-get install -f -y -qq

      - name: Run FLUKA Simulation
        shell: bash
        run: |
          TASK_DIR="inputs/task_${{ matrix.task_id }}"
          cd "$TASK_DIR"
          
          # Thiết lập môi trường chạy FLUKA
          export PATH="/usr/local/flukagfor/bin:/usr/local/fluka/bin:/usr/local/bin:$PATH"
          export FLUFOR=gfortran
          
          echo ">>> Dang khoi chay rfluka tren may ao..."
          rfluka -N0 -M1 "task_${{ matrix.task_id }}.inp"
          
          echo ">>> Kiem tra danh sach file ket qua:"
          ls -lh

      - name: Upload Results to Cloud Storage
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: task_${{ matrix.task_id }}_results
          path: |
            inputs/task_${{ matrix.task_id }}/*.out
            inputs/task_${{ matrix.task_id }}/*.log
            inputs/task_${{ matrix.task_id }}/*fort*
          retention-days: 7

  merge-results:
    name: Merge Results & Aggregate
    needs: run-fluka-matrix
    if: always()
    runs-on: ubuntu-22.04
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Download All Artifacts
        uses: actions/download-artifact@v4
        with:
          path: downloaded_artifacts

      - name: Organize Data
        shell: bash
        run: |
          for i in $(seq -w 1 16); do
            SRC="downloaded_artifacts/task_${i}_results"
            DST="inputs/task_${i}"
            if [ -d "$SRC" ]; then
              cp -r "$SRC"/* "$DST"/ 2>/dev/null || true
            fi
          done

      - name: Upload Final Package
        uses: actions/upload-artifact@v4
        with:
          name: FLUKA_16_TASKS_FINAL_SUMMARY
          path: inputs/
          retention-days: 14
```

> **Mở rộng lên 32 tasks:** Bạn chỉ cần thêm `"17", "18", ..., "32"` vào mảng `task_id` trong file yaml trên.

---

## 6. Bước 5: Kích Hoạt & Theo Dõi Mô Phỏng

Sau khi đẩy toàn bộ code, file `packages/` và file `.github/` lên GitHub:

### Cách 1: Bấm nút trực tiếp trên Web GitHub
1. Vào trang GitHub Repository của bạn.
2. Click tab **Actions**.
3. Ở cột bên trái, click vào workflow **FLUKA Cloud Parallel Computing**.
4. Nhìn sang bên phải có nút **Run workflow** màu xanh $\rightarrow$ Click vào nút đó và bấm **Run workflow**.
5. Màn hình sẽ hiện ra 16 ô vuông đại diện cho 16 máy ảo đang chạy song song theo thời gian thực. Bạn có thể bấm vào từng task để xem dòng log FLUKA đang tính toán.

### Cách 2: Kích hoạt tự động bằng PowerShell Script (API)
Nếu bạn muốn máy tính tự động ra lệnh cho GitHub chạy từ xa:
```powershell
$token = "ghp_YOUR_TOKEN_HERE"
$headers = @{
    "Authorization" = "Bearer $token"
    "Accept" = "application/vnd.github+json"
}
$body = @{
    ref = "main"
} | ConvertTo-Json

Invoke-RestMethod -Uri "https://api.github.com/repos/<username>/<repo_name>/actions/workflows/fluka_parallel.yml/dispatches" `
    -Method Post -Headers $headers -Body $body
Write-Host "Da gui lenh khoi chay 16 may ao thanh cong!"
```

---

## 7. Bước 6: Thu Thập & Phân Tích Dữ Liệu Đầu Ra

### 7.1. Tải kết quả từ Web:
1. Khi tất cả 16 task và job `merge-results` hoàn thành (hiện dấu tích xanh lá), click vào lần chạy đó.
2. Kéo xuống cuối trang mục **Artifacts**.
3. Click vào **`FLUKA_16_TASKS_FINAL_SUMMARY`** để tải toàn bộ file `.zip` chứa kết quả của 16 máy ảo về máy cá nhân.

### 7.2. Trích xuất phổ năng lượng nhị phân `fort.41` bằng Python:
Các file đầu ra của FLUKA `task_*001_fort.41` lưu theo định dạng Fortran Unformatted Binary. Sử dụng script Python sau để đọc và vẽ đồ thị:

```python
import struct, glob, os
import matplotlib.pyplot as plt

def read_fluka_usrtrack(fort_file):
    with open(fort_file, 'rb') as f:
        data = f.read()
    
    offset = 0
    records = []
    while offset < len(data):
        reclen = struct.unpack('<I', data[offset:offset+4])[0]
        offset += 4
        payload = data[offset:offset+reclen]
        offset += reclen
        offset += 4  # trailing reclen
        records.append(payload)
    
    # Record thứ 3 chứa mảng float các bin năng lượng (50 bins)
    bins = struct.unpack('<50f', records[2])
    return bins

# Đọc thử task 01
flux_bins = read_fluka_usrtrack("inputs/task_01/task_01001_fort.41")
print("Tong thong luong photon:", sum(flux_bins))
```

---

## 8. Các Lỗi Thường Gặp & Cách Khắc Phục (Troubleshooting)

| STT | Lỗi Thường Gặp | Nguyên Nhân | Cách Khắc Phục |
| :--- | :--- | :--- | :--- |
| **1** | `STOP NO/UNKNOWN DEFAULT` | Cột SDUM của thẻ `DEFAULTS` bị sai vị trí. FLUKA đọc thẻ theo chuẩn 80 cột cố định, SDUM nằm từ cột 71–80 và **bắt buộc phải căn lề trái (bắt đầu đúng cột 71)**. | Đảm bảo `PRECISIO` nằm đúng cột 71. Cú pháp: `DEFAULTS                                                              PRECISIO  `. |
| **2** | `gfortran-9 not found` | Chạy trên `ubuntu-latest` (mặc định là Ubuntu 24.04 đã bỏ gói gfortran-9). | Trong file yaml, luôn đặt cứng: `runs-on: ubuntu-22.04`. |
| **3** | File `.deb` push bị GitHub từ chối | Dung lượng file `.deb` > 100 MB. | Cắt file thành 2 phần bằng script PowerShell ở Bước 2. |
| **4** | FLUKA yêu cầu dữ liệu nơtron điểm rồi dừng | FLUKA 4 tự động bật pointwise neutron khi dùng `PRECISIO`. | Thêm thẻ `LOW-PWXS     -1.0000` vào đầu input deck. |
| **5** | Thẻ `BEAMPOS` báo lỗi | Trong FLUKA, `BEAMPOS` không nhận giá trị `POSITIVE` trong SDUM. | Để trống hoàn toàn 10 cột SDUM của `BEAMPOS` (FLUKA tự mặc định chiều tia theo trục $+z$). |

---

> [!TIP]
> Tài liệu này có thể được lưu trữ trực tiếp trong repository của bạn hoặc mở bằng VS Code để tra cứu bất cứ khi nào bạn triển khai mô phỏng hạt nhân quy mô lớn.
