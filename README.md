# FLUKA 16-Core Parallel Benchmark Project

Dự án mẫu độc lập (Standalone Benchmark) mô phỏng bài toán **Truyền bức xạ qua khiên che chắn (Deep Shielding Attenuation)** bằng phần mềm **FLUKA**, được tối ưu để chạy song song trên **16 máy ảo GitHub Actions đồng thời**.

---

## 1. Cấu trúc bài toán Benchmark (16 Tasks)

* **Loại hạt & năng lượng:** Chùm tia Photon 2.614 MeV (tương đương đỉnh gamma của $^{208}\text{Tl}$).
* **Hình học:** Khiên chì (Lead Shield) với độ dày tăng dần từ **0.5 cm đến 8.0 cm** qua 16 bài toán:
  * `task_01`: Khiên chì 0.5 cm
  * `task_02`: Khiên chì 1.0 cm
  * ...
  * `task_16`: Khiên chì 8.0 cm
* **Khối lượng tính toán (Task nặng):** Mỗi task chạy **250,000 hạt** (`START 250000.0`), với Random Seed độc lập hoàn toàn.
* **Đại lượng đo đạc:** Liều năng lượng lắng đọng (`USRBIN`) và thông lượng photon (`USRTRACK`) sau khiên che chắn.

---

## 2. Cách chạy trên GitHub Actions (16 máy ảo song song)

1. Tạo một kho mã nguồn mới trên GitHub (khuyên dùng chế độ **Public** để chạy không giới hạn giờ).
2. Đẩy toàn bộ thư mục này lên GitHub:
   ```bash
   git remote add origin https://github.com/<your-username>/fluka-parallel-benchmark.git
   git push -u origin master
   ```
3. Mở tab **Actions** trên GitHub, chọn workflow **"FLUKA 16-Core Parallel Benchmark"**, chọn số lượng hạt (mặc định 250,000) và bấm **Run workflow**.
4. GitHub sẽ:
   * Bật cùng lúc **16 máy ảo Ubuntu** (tổng cộng 32 vCPU + 112 GB RAM).
   * Mỗi máy ảo tự động cài đặt FLUKA từ thư mục `packages/` và chạy 1 task độc lập.
   * Job cuối cùng tự động tải toàn bộ 16 kết quả về, chạy `merge_and_plot.py` và xuất file `summary_results.csv`.

---

## 3. Chạy thử nghiệm trên máy cục bộ (WSL2 / Linux)

* Sinh lại 16 bài toán (nếu muốn thay đổi số hạt):
  ```bash
  python3 generate_16_tasks.py
  ```
* Chạy 1 task cụ thể:
  ```bash
  cd inputs/task_01
  rfluka -N0 -M1 task_01.inp
  ```
* Tổng hợp kết quả:
  ```bash
  python3 merge_and_plot.py
  ```
