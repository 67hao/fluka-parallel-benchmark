"""
Script chạy trên mỗi GitHub Runner để thực thi FLUKA v4 song song cho Paper 10.1 (PNE 2022)
theo kiến trúc Zero Data Loss & Auto-Resume qua Google Drive.
"""
import argparse
import os
import sys
import time
import shutil
import zipfile
import subprocess
import re
import struct
import random
from pathlib import Path
from decimal import Decimal
import pandas as pd

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import gdrive_helper
from generate_fluka_inputs import generate_fluka_input, _parse_thickness_list, COMPOSITION

def find_fluka_binaries():
    candidates = [
        "/usr/local/fluka/bin",
        "/usr/local/fluka/flutil",
        "/usr/local/flukagfor/bin",
        "/usr/local/flukagfor/flutil",
        "/usr/local/bin",
        "/usr/bin"
    ]
    rfluka = shutil.which("rfluka")
    ustsuw = shutil.which("ustsuw")
    for c in candidates:
        if not rfluka and os.path.exists(f"{c}/rfluka"):
            rfluka = f"{c}/rfluka"
        if not ustsuw and os.path.exists(f"{c}/ustsuw"):
            ustsuw = f"{c}/ustsuw"

    flupro = os.environ.get("FLUPRO")
    if not flupro:
        for p in ["/usr/local/fluka", "/usr/local/flukagfor"]:
            if os.path.exists(p):
                flupro = p
                break
    if not flupro:
        flupro = "/usr/local/fluka"

    return rfluka, ustsuw, flupro

def parse_usrtrack_ascii(filepath: Path) -> tuple:
    """Đọc file USRTRACK ASCII (do ustsuw sinh ra hoặc FLUKA formatted), trả về (fluence, error_pct)."""
    text = filepath.read_text(encoding="utf-8", errors="ignore")
    
    # 1. Regex chuẩn ustsuw: "Fluence in peak (part/cm^2/pr): 8.127688E-03 +/- 0.125 %"
    m_peak = re.search(r"Fluence\s*(?:in peak)?\s*\(part/cm\^2/pr\):\s*([\d\.\+\-Ee]+)\s*\+/-\s*([\d\.\+\-Ee]+)\s*%", text)
    if m_peak:
        return float(m_peak.group(1)), float(m_peak.group(2))

    # 2. Hoặc "Total fluence:"
    m_tot = re.search(r"(?:Total|Tot\.)\s*fluence.*?:\s*([\d\.\+\-Ee]+)\s*\+/-\s*([\d\.\+\-Ee]+)\s*%", text, re.IGNORECASE)
    if m_tot:
        return float(m_tot.group(1)), float(m_tot.group(2))

    # 3. Vector A(ie) của ustsuw
    lines = text.splitlines()
    bin_width = None
    data_start = False
    error_start = False
    values = []
    errors = []

    for line in lines:
        if "GeV wide" in line:
            m = re.search(r"\(\s*([\d\.\+\-Ee]+)\s*GeV wide\)", line)
            if m:
                bin_width = float(m.group(1))

        if "Data follow in a vector A(ie)" in line:
            data_start = True
            error_start = False
            continue

        if "Percentage errors follow in a vector" in line:
            error_start = True
            data_start = False
            continue

        if data_start:
            for p in line.strip().split():
                try:
                    values.append(float(p))
                except ValueError:
                    pass

        if error_start:
            for p in line.strip().split():
                try:
                    errors.append(float(p))
                except ValueError:
                    pass

    if values:
        fluence = sum(v * bin_width for v in values) if (bin_width and bin_width > 0) else sum(values)
        err = errors[0] if errors else 0.0
        return fluence, err

    raise ValueError(f"Khong tim thay du lieu fluence trong {filepath.name}")

def parse_usrtrack_binary(filepath: Path) -> tuple:
    """Parse trực tiếp binary fort file nếu không có ustsuw."""
    with open(filepath, "rb") as f:
        data = f.read()

    offset = 0
    recs = []
    while offset < len(data):
        if offset + 4 > len(data):
            break
        reclen = struct.unpack("<I", data[offset:offset+4])[0]
        offset += 4
        if offset + reclen > len(data):
            break
        recs.append(data[offset:offset+reclen])
        offset += reclen
        offset += 4

    if len(recs) < 3:
        raise ValueError(f"Binary file {filepath} khong du records ({len(recs)})")

    rec2 = recs[1]
    e_min = struct.unpack("<f", rec2[46:50])[0] if len(rec2) >= 50 else 0.0
    e_max = struct.unpack("<f", rec2[50:54])[0] if len(rec2) >= 54 else 1.0
    dE = max(1e-12, e_max - e_min)
    val = struct.unpack("<f", recs[2][:4])[0]
    fluence = val * dE
    return fluence, 0.0

def process_fort_file(fort_path: Path, ustsuw_bin: str) -> tuple:
    """Chuyển đổi fort thành ascii qua ustsuw hoặc binary parse."""
    if not fort_path.exists():
        raise FileNotFoundError(f"Khong tim thay {fort_path}")
    if fort_path.stat().st_size == 0:
        raise ValueError(f"File {fort_path.name} co kich thuoc 0 bytes (FLUKA loi khoi tao hoac khong ghi duoc)")

    # 1. Thử kiểm tra định dạng text ASCII trực tiếp
    try:
        raw_head = fort_path.read_bytes()[:128]
        if b"Differential fluence" in raw_head or b"Total number of primary" in raw_head or b"FLUKA" in raw_head:
            return parse_usrtrack_ascii(fort_path)
    except Exception:
        pass

    # 2. Thử dùng ustsuw nếu có
    if ustsuw_bin and os.path.exists(ustsuw_bin):
        try:
            inp_data = f"{fort_path.name}\n\nres_{fort_path.stem}\n"
            subprocess.run([ustsuw_bin], input=inp_data, text=True, cwd=str(fort_path.parent), capture_output=True, timeout=30)
            
            # ustsuw sinh ra file res_<stem>_sum.lis
            candidates = list(fort_path.parent.glob(f"res_{fort_path.stem}*_sum.lis")) or list(fort_path.parent.glob("*_sum.lis"))
            if candidates:
                return parse_usrtrack_ascii(candidates[0])
        except Exception:
            pass

    # 3. Parse binary trực tiếp
    return parse_usrtrack_binary(fort_path)

def parse_args():
    parser = argparse.ArgumentParser(description="FLUKA Parallel Worker for Paper 10.1")
    parser.add_argument("--runner-id", type=int, required=True, help="ID cua runner (1..20)")
    parser.add_argument("--num-runners", type=int, default=20, help="Tong so runner")
    parser.add_argument("--sample-filter", type=str, default="All", help="Loc theo mau: All, S1, S2, ...")
    parser.add_argument("--primaries", type=int, default=100000000, help="So hat moi job (mac dinh 10^8)")
    parser.add_argument("--gdrive-folder", type=str, default="1YRth9_SQka7Mpg07GkggANXb9-ed_CkU")
    parser.add_argument("--excel-table", type=str, default="thickness_table_all9.xlsx")
    parser.add_argument("--plan-file", type=str, default=None, help="File JSON chua phan bo jobs sweep (neu co)")
    parser.add_argument("--github-user", type=str, default=None, help="Ten GitHub account hien tai de tra cuu plan")
    parser.add_argument("--timeout-hours", type=float, default=5.4)
    return parser.parse_args()

def build_fluka_job_list(excel_path: str, output_base: Path, sample_filter: str, n_primaries: int):
    df = pd.read_excel(excel_path)
    output_base.mkdir(parents=True, exist_ok=True)

    all_materials = [col for col in df.columns if col.lower() != "energy"]
    if sample_filter.lower() != "all":
        target_mats = [m for m in all_materials if m.lower() == sample_filter.lower()]
    else:
        target_mats = all_materials

    all_jobs = []
    blank_generated = set()

    for _, row in df.iterrows():
        energy_kev = int(round(row["Energy"]))

        if energy_kev not in blank_generated:
            th_blank = 0.5
            blank_name = f"blank_{energy_kev}keV"
            blank_dir = output_base / blank_name
            blank_dir.mkdir(parents=True, exist_ok=True)
            blank_inp = blank_dir / f"{blank_name}.inp"
            blank_content = generate_fluka_input(blank_name, "blank", energy_kev, th_blank, n_primaries)
            blank_inp.write_text(blank_content, encoding="utf-8")
            blank_generated.add(energy_kev)

            all_jobs.append({
                "name": blank_name,
                "dir": blank_dir,
                "inp": blank_inp,
                "is_blank": True,
                "energy_kev": energy_kev,
                "sample": "BLANK",
                "thickness": th_blank
            })

        for mat in target_mats:
            mat_key = mat.lower()
            if mat_key not in COMPOSITION:
                continue

            th_list = _parse_thickness_list(row[mat])
            for th in th_list:
                th_str = f"{th:.4f}".rstrip("0").rstrip(".")
                job_name = f"{mat_key}_{energy_kev}keV_th{th_str}cm"
                job_dir = output_base / job_name
                job_dir.mkdir(parents=True, exist_ok=True)
                job_inp = job_dir / f"{job_name}.inp"

                content = generate_fluka_input(job_name, mat_key, energy_kev, th, n_primaries)
                job_inp.write_text(content, encoding="utf-8")

                all_jobs.append({
                    "name": job_name,
                    "dir": job_dir,
                    "inp": job_inp,
                    "is_blank": False,
                    "energy_kev": energy_kev,
                    "sample": mat_key.upper(),
                    "thickness": th
                })

    return all_jobs

def main():
    args = parse_args()
    print("=" * 80)
    print(f"STARTING FLUKA PARALLEL RUNNER #{args.runner_id} / {args.num_runners}")
    print(f"Filter: {args.sample_filter} | Primaries: {args.primaries:,}")
    print(f"Target Drive Folder: {args.gdrive_folder}")
    print("=" * 80)

    rfluka_bin, ustsuw_bin, flupro = find_fluka_binaries()
    print(f">>> [FLUKA] rfluka: {rfluka_bin} | ustsuw: {ustsuw_bin} | FLUPRO: {flupro}")
    if not rfluka_bin or not os.path.exists(rfluka_bin):
        raise FileNotFoundError(f"Khong tim thay rfluka tren runner! Candidates searched: /usr/local/fluka/bin, /usr/local/flukagfor/bin")

    work_dir = Path("/tmp/fluka_work")
    work_dir.mkdir(parents=True, exist_ok=True)

    # Startup jitter de tranh 180 runner tan cong Drive cung luc
    startup_delay = random.uniform(1.0, 15.0)
    print(f">>> [STARTUP] Cho ngau nhien {startup_delay:.1f}s truoc khi ket noi...")
    time.sleep(startup_delay)

    drive_service = None
    folder_ids = {}
    try:
        os.environ["GDRIVE_FOLDER_ID"] = args.gdrive_folder
        drive_service = gdrive_helper.get_drive_service()
        folder_ids = gdrive_helper.get_or_create_subfolders(drive_service, parent_id=args.gdrive_folder)
        print(">>> [DRIVE] Ket noi Google Drive FLUKA thanh cong!")
    except Exception as e:
        print(f">>> [CANH BAO] Khong the ket noi Google Drive: {e}. Luu local.")

    sample_tag = f"{args.sample_filter.upper()}_" if args.sample_filter.lower() != "all" else ""
    csv_filename = f"flux_runner_{sample_tag}{args.runner_id:02d}.csv"
    csv_file = work_dir / csv_filename

    completed_jobs = set()
    if drive_service and "02_Flux_Data" in folder_ids:
        print(f">>> [RESUME] Dang kiem tra cac job da xong cua runner nay tren Drive ({csv_filename})...")
        completed_jobs = gdrive_helper.get_completed_jobs_from_drive(drive_service, folder_ids["02_Flux_Data"], target_filename=csv_filename)
        print(f">>> [RESUME] Tim thay {len(completed_jobs)} job FLUKA da hoan thanh tren Drive.")

    if csv_file.exists():
        try:
            df_local = pd.read_csv(csv_file)
            if "job_name" in df_local.columns:
                local_done = set(df_local["job_name"].dropna().astype(str).tolist())
                completed_jobs.update(local_done)
                print(f">>> [RESUME LOCAL] Doc duoc them {len(local_done)} job tu local CSV.")
        except Exception:
            pass
    else:
        csv_file.write_text("job_name,energy_mev,sample,thickness_cm,peak_flux,peak_err,total_flux,total_err,elapsed_s\n", encoding="utf-8")

    inputs_base = work_dir / "inputs"
    inputs_base.mkdir(parents=True, exist_ok=True)

    if args.plan_file and os.path.exists(args.plan_file):
        import json
        print(f">>> [PLAN-SWEEP] Su dung Sweep Plan File: {args.plan_file}")
        with open(args.plan_file, "r", encoding="utf-8") as pf:
            full_plan = json.load(pf)
        
        user_key = args.github_user or os.environ.get("GITHUB_REPOSITORY_OWNER") or ""
        # Match user_key or find in accounts
        matched_acc = None
        for acc in full_plan:
            if acc.lower() == user_key.lower():
                matched_acc = acc
                break
        if not matched_acc and full_plan:
            # fallback to first key if not found
            matched_acc = list(full_plan.keys())[0]

        print(f">>> [PLAN-SWEEP] Account: {matched_acc} | Runner ID: {args.runner_id}")
        raw_my_jobs = full_plan.get(matched_acc, {}).get(str(args.runner_id), [])

        my_jobs = []
        for rj in raw_my_jobs:
            jname = rj["job_name"]
            jdir = inputs_base / jname
            jdir.mkdir(parents=True, exist_ok=True)
            jinp = jdir / f"{jname}.inp"
            mat_key = rj["sample"].lower()
            e_kev = rj["energy_kev"]
            th = rj["thickness_cm"]
            content = generate_fluka_input(jname, mat_key, e_kev, th, args.primaries)
            jinp.write_text(content, encoding="utf-8")
            my_jobs.append({
                "name": jname,
                "dir": jdir,
                "inp": jinp,
                "is_blank": False,
                "energy_kev": e_kev,
                "sample": rj["sample"],
                "thickness": th
            })
    else:
        all_jobs = build_fluka_job_list(args.excel_table, inputs_base, args.sample_filter, args.primaries)
        print(f">>> [PLAN] Tong so job FLUKA cua toan bo nghien cuu: {len(all_jobs)}")
        my_jobs = [j for i, j in enumerate(all_jobs) if i % args.num_runners == (args.runner_id - 1)]

    todo_jobs = [j for j in my_jobs if j["name"] not in completed_jobs]
    print(f">>> [RUNNER #{args.runner_id}] Phan bo: {len(my_jobs)} jobs | Da xong: {len(my_jobs) - len(todo_jobs)} | Con lai: {len(todo_jobs)} jobs")

    if not todo_jobs:
        print(f">>> [HOAN THANH] Toan bo {len(my_jobs)} job cua Runner #{args.runner_id} da xong tren Drive! Thoat.")
        return

    timing_log = work_dir / f"benchmark_timing_runner_{sample_tag}{args.runner_id:02d}.txt"
    start_all = time.time()
    batch_outs = []
    batch_idx = 1

    for idx, job in enumerate(todo_jobs, 1):
        elapsed_total = time.time() - start_all
        if elapsed_total > (args.timeout_hours * 3600 - 900):
            print(f">>> [CHECKPOINT] Sap dat nguong timeout an toan ({args.timeout_hours}h). Thoat an toan.")
            break

        jname = job["name"]
        jdir = job["dir"]
        jinp = job["inp"]
        e_mev = job["energy_kev"] / 1000.0

        print(f"\n--- [{idx}/{len(todo_jobs)}] Runner #{args.runner_id} dang chay FLUKA: {jname} ({job['sample']} @ {job['energy_kev']} keV, th={job['thickness']} cm) ---")
        t0 = time.time()

        env = os.environ.copy()
        env["FLUPRO"] = str(flupro)
        env["FLUFOR"] = "gfortran"
        env["PATH"] = f"{flupro}/bin:{flupro}/flutil:{env.get('PATH', '')}"

        cmd = [rfluka_bin, "-N0", "-M1", jinp.name]
        res = subprocess.run(cmd, cwd=str(jdir), env=env, capture_output=True, text=True)
        job_time = time.time() - t0

        fort21 = list(jdir.glob("*_fort.21")) or list(jdir.glob("*fort.21"))
        fort22 = list(jdir.glob("*_fort.22")) or list(jdir.glob("*fort.22"))

        fort_valid = False
        if fort21 and fort22 and fort21[0].stat().st_size > 0 and fort22[0].stat().st_size > 0:
            try:
                tot_val, tot_err = process_fort_file(fort21[0], ustsuw_bin)
                peak_val, peak_err = process_fort_file(fort22[0], ustsuw_bin)
                print(f"    -> OK ({job_time:.1f}s) | Peak: {peak_val:.6e} (err: {peak_err:.2f}%) | Tot: {tot_val:.6e}", flush=True)

                with open(csv_file, "a", encoding="utf-8") as f:
                    f.write(f"{jname},{e_mev:.6f},{job['sample']},{job['thickness']},{peak_val:.8e},{peak_err:.4f},{tot_val:.8e},{tot_err:.4f},{job_time:.1f}\n")

                batch_outs.extend([fort21[0], fort22[0]])
                lis_files = list(jdir.glob("*.lis"))
                batch_outs.extend(lis_files)
                fort_valid = True
            except Exception as e:
                print(f"    -> LOI PARSE: {e}", flush=True)

        if not fort_valid:
            print(f"    -> LOI THIEU FILE FORT HOAC FILE 0 BYTES! Returncode: {res.returncode}. Stderr: {res.stderr[:200]}", flush=True)
            for log_f in list(jdir.glob("*.log")) + list(jdir.glob("*.out")) + list(jdir.glob("*.err")) + list(jdir.glob("fluka_*/*")):
                if log_f.is_file() and log_f.stat().st_size > 0:
                    print(f"=== CONTENT OF {log_f.name} ({log_f.stat().st_size} bytes) ===", flush=True)
                    try:
                        print(log_f.read_text(errors='ignore')[-1500:], flush=True)
                    except Exception:
                        pass

        if len(batch_outs) >= 4:
            if drive_service and "03_Simulation_Outputs" in folder_ids:
                try:
                    zip_path = work_dir / f"outputs_runner_{sample_tag}{args.runner_id:02d}_batch_{batch_idx:03d}.zip"
                    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
                        for out_file in set(batch_outs):
                            if out_file.exists():
                                z.write(out_file, arcname=out_file.name)
                    gdrive_helper.upload_file_to_folder(drive_service, str(zip_path), folder_ids["03_Simulation_Outputs"])
                    gdrive_helper.upload_file_to_folder(drive_service, str(csv_file), folder_ids["02_Flux_Data"])
                    print(f">>> [SYNC] Da dong bo FLUKA Batch #{batch_idx} len Drive!")
                    batch_outs = []
                    batch_idx += 1
                except Exception as e:
                    print(f">>> [CANH BAO SYNC] {e}")

    if batch_outs and drive_service and "03_Simulation_Outputs" in folder_ids:
        try:
            zip_path = work_dir / f"outputs_runner_{sample_tag}{args.runner_id:02d}_batch_{batch_idx:03d}.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
                for out_file in set(batch_outs):
                    if out_file.exists():
                        z.write(out_file, arcname=out_file.name)
            gdrive_helper.upload_file_to_folder(drive_service, str(zip_path), folder_ids["03_Simulation_Outputs"])
        except Exception as e:
            print(f">>> [CANH BAO FINAL SYNC]: {e}")

    if drive_service and "02_Flux_Data" in folder_ids and csv_file.exists():
        try:
            gdrive_helper.upload_file_to_folder(drive_service, str(csv_file), folder_ids["02_Flux_Data"])
        except Exception as e:
            print(f">>> [CANH BAO FINAL CSV]: {e}")

    total_time = time.time() - start_all
    summary_text = f"""=======================================================
FLUKA RUNNER #{args.runner_id} HOAN THANH DOT CHAY
Tong thoi gian: {total_time:.1f}s ({total_time/60:.1f} phut)
So job da xu ly dot nay: {len(todo_jobs)}
File ket qua flux: {csv_file.name}
=======================================================
"""
    timing_log.write_text(summary_text, encoding="utf-8")
    if drive_service and "05_Execution_Logs_and_Benchmarks" in folder_ids:
        try:
            gdrive_helper.upload_file_to_folder(drive_service, str(timing_log), folder_ids["05_Execution_Logs_and_Benchmarks"])
        except Exception:
            pass

    print(summary_text)

if __name__ == "__main__":
    main()
