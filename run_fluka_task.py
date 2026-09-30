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
from pathlib import Path
import pandas as pd

import gdrive_helper
from generate_fluka_inputs import generate_fluka_input, _parse_thickness_list, COMPOSITION

def parse_usrtrack_ascii(filepath: Path) -> tuple:
    """Đọc file USRTRACK ASCII (do ustsuw sinh ra), trả về (fluence, error_pct)."""
    text = filepath.read_text(encoding="utf-8", errors="ignore")
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

    if not values:
        raise ValueError(f"Khong tim thay du lieu A(ie) trong {filepath}")

    if bin_width is not None and bin_width > 0:
        fluence = sum(v * bin_width for v in values)
    else:
        fluence = sum(values)

    err = errors[0] if errors else 0.0
    return fluence, err

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

def process_fort_file(fort_path: Path, flupro: str) -> tuple:
    """Chuyển đổi fort thành ascii qua ustsuw hoặc binary parse."""
    if not fort_path.exists():
        raise FileNotFoundError(f"Khong tim thay {fort_path}")

    lis_path = fort_path.with_suffix(".lis")
    ustsuw_bin = None
    if flupro:
        candidate = Path(flupro) / "flutil" / "ustsuw"
        if candidate.exists():
            ustsuw_bin = str(candidate)

    if not ustsuw_bin:
        ustsuw_bin = shutil.which("ustsuw") or "/usr/local/flukagfor/flutil/ustsuw"

    if os.path.exists(ustsuw_bin):
        try:
            # ustsuw stdin: <fort_file>\n\n<out_lis>\n
            inp_data = f"{fort_path.name}\n\n{lis_path.name}\n"
            subprocess.run([ustsuw_bin], input=inp_data, text=True, cwd=str(fort_path.parent), capture_output=True, timeout=30)
            if lis_path.exists():
                return parse_usrtrack_ascii(lis_path)
        except Exception:
            pass

    # Fallback binary
    return parse_usrtrack_binary(fort_path)

def parse_args():
    parser = argparse.ArgumentParser(description="FLUKA Parallel Worker for Paper 10.1")
    parser.add_argument("--runner-id", type=int, required=True, help="ID cua runner (1..20)")
    parser.add_argument("--num-runners", type=int, default=20, help="Tong so runner")
    parser.add_argument("--sample-filter", type=str, default="All", help="Loc theo mau: All, S1, S2, ...")
    parser.add_argument("--primaries", type=int, default=100000000, help="So hat moi job (10^8)")
    parser.add_argument("--gdrive-folder", type=str, default="1YRth9_SQka7Mpg07GkggANXb9-ed_CkU")
    parser.add_argument("--excel-table", type=str, default="thickness_table_all9.xlsx")
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

        # 1. Job Blank
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

        # 2. Job Sample
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
    print(f"🚀 STARTING FLUKA PARALLEL RUNNER #{args.runner_id} / {args.num_runners}")
    print(f"Filter: {args.sample_filter} | Primaries: {args.primaries:,}")
    print(f"Target Drive Folder: {args.gdrive_folder}")
    print("=" * 80)

    flupro = os.environ.get("FLUPRO", "/usr/local/flukagfor")
    rfluka_bin = shutil.which("rfluka") or f"{flupro}/flutil/rfluka"
    print(f">>> [FLUKA] rfluka path: {rfluka_bin} (FLUPRO={flupro})")

    work_dir = Path("/tmp/fluka_work")
    work_dir.mkdir(parents=True, exist_ok=True)

    # Ket noi Google Drive
    drive_service = None
    folder_ids = {}
    try:
        os.environ["GDRIVE_FOLDER_ID"] = args.gdrive_folder
        drive_service = gdrive_helper.get_drive_service()
        folder_ids = gdrive_helper.get_or_create_subfolders(drive_service, parent_id=args.gdrive_folder)
        print(">>> [DRIVE] Ket noi Google Drive FLUKA thanh cong!")
    except Exception as e:
        print(f">>> [CANH BAO] Khong the ket noi Google Drive: {e}. Luu local.")

    # Check resume
    completed_jobs = set()
    if drive_service and "02_Flux_Data" in folder_ids:
        print(">>> [RESUME] Dang kiem tra cac job FLUKA da hoan thanh tren Drive...")
        completed_jobs = gdrive_helper.get_completed_jobs_from_drive(drive_service, folder_ids["02_Flux_Data"])
        print(f">>> [RESUME] Tim thay {len(completed_jobs)} job FLUKA da hoan thanh tren Drive.")

    # Sinh jobs
    inputs_base = work_dir / "inputs"
    all_jobs = build_fluka_job_list(args.excel_table, inputs_base, args.sample_filter, args.primaries)
    print(f">>> [PLAN] Tong so job FLUKA cua toan bo nghien cuu: {len(all_jobs)}")

    # Phan bo runner
    my_jobs = [j for i, j in enumerate(all_jobs) if i % args.num_runners == (args.runner_id - 1)]
    todo_jobs = [j for j in my_jobs if j["name"] not in completed_jobs]
    print(f">>> [RUNNER #{args.runner_id}] Phan bo: {len(my_jobs)} jobs | Da xong: {len(my_jobs) - len(todo_jobs)} | Con lai: {len(todo_jobs)} jobs")

    if not todo_jobs:
        print(f">>> [HOAN THANH] Toan bo {len(my_jobs)} job cua Runner #{args.runner_id} da xong tren Drive! Thoat.")
        return

    sample_tag = f"{args.sample_filter.upper()}_" if args.sample_filter.lower() != "all" else ""
    csv_file = work_dir / f"flux_runner_{sample_tag}{args.runner_id:02d}.csv"
    if not csv_file.exists():
        csv_file.write_text("job_name,energy_mev,sample,thickness_cm,peak_flux,peak_err,total_flux,total_err,elapsed_s\n", encoding="utf-8")

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

        print(f"\n--- [{idx}/{len(todo_jobs)}] Runner #{args.runner_id} đang chạy FLUKA: {jname} ({job['sample']} @ {job['energy_kev']} keV, th={job['thickness']} cm) ---")
        t0 = time.time()

        env = os.environ.copy()
        env["FLUPRO"] = str(flupro)
        env["FLUFOR"] = "gfortran"
        env["PATH"] = f"{flupro}/flutil:{flupro}/bin:{env.get('PATH', '')}"

        cmd = [rfluka_bin, "-N0", "-M1", jinp.name]
        res = subprocess.run(cmd, cwd=str(jdir), env=env, capture_output=True, text=True)
        job_time = time.time() - t0

        # Tim fort.21 va fort.22
        fort21 = list(jdir.glob("*_fort.21")) or list(jdir.glob("*fort.21"))
        fort22 = list(jdir.glob("*_fort.22")) or list(jdir.glob("*fort.22"))

        if fort21 and fort22:
            try:
                tot_val, tot_err = process_fort_file(fort21[0], flupro)
                peak_val, peak_err = process_fort_file(fort22[0], flupro)
                print(f"    -> OK ({job_time:.1f}s) | Peak: {peak_val:.6e} (err: {peak_err:.2f}%) | Tot: {tot_val:.6e}")

                with open(csv_file, "a", encoding="utf-8") as f:
                    f.write(f"{jname},{e_mev:.6f},{job['sample']},{job['thickness']},{peak_val:.8e},{peak_err:.4f},{tot_val:.8e},{tot_err:.4f},{job_time:.1f}\n")

                batch_outs.extend([fort21[0], fort22[0]])
                lis_files = list(jdir.glob("*.lis"))
                batch_outs.extend(lis_files)
            except Exception as e:
                print(f"    -> LOI PARSE: {e}")
        else:
            print(f"    -> LOI THIEU FILE FORT! Returncode: {res.returncode}. Stderr: {res.stderr[:200]}")

        # Dong bo len Drive sau moi 2 job
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
                    print(f">>> [SYNC] Đã đồng bộ FLUKA Batch #{batch_idx} lên Drive!")
                    batch_outs = []
                    batch_idx += 1
                except Exception as e:
                    print(f">>> [CANH BAO SYNC] {e}")

    # Dong bo cuoi cung
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
