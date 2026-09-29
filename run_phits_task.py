"""
Script chay tren moi GitHub Runner de thuc thi PHITS song song theo kien truc
Zero Data Loss & Auto-Resume qua Google Drive.
"""
import argparse
import os
import sys
import time
import shutil
import zipfile
import subprocess
from pathlib import Path
import pandas as pd

from generate_inputs import _parse_thickness_list, _fmt_thickness, SAMPLE_TEMPLATE, BLANK_TEMPLATE, COMPOSITION, DENSITY, format_material
import gdrive_helper

def parse_track_flux(filepath: Path) -> tuple:
    """Doc file T-Track (F4 equivalent) trong vung detector (reg 104), tra ve (flux, r_err)."""
    lines = filepath.read_text(encoding="utf-8", errors="ignore").splitlines()
    for line in lines:
        parts = line.strip().split()
        if len(parts) >= 5 and parts[0] == "1" and parts[1] == "104":
            try:
                flux = float(parts[-2])
                err = float(parts[-1])
                return flux, err
            except ValueError:
                pass
    raise ValueError(f"Khong tim thay du lieu flux vung reg 104 trong {filepath}")

def parse_args():
    parser = argparse.ArgumentParser(description="PHITS Parallel Worker")
    parser.add_argument("--runner-id", type=int, required=True, help="ID cua runner (1..20)")
    parser.add_argument("--num-runners", type=int, default=20, help="Tong so runner")
    parser.add_argument("--sample-filter", type=str, default="All", help="Loc theo mau: All, S1, S2, ...")
    parser.add_argument("--maxcas", type=int, default=100000000, help="So hat moi job (10^8)")
    parser.add_argument("--omp", type=int, default=2, help="So luong thread OpenMP cho moi job")
    parser.add_argument("--package-path", type=str, default="phits_pack/phits_package.tar.gz")
    parser.add_argument("--excel-table", type=str, default="thickness_table_all9.xlsx")
    parser.add_argument("--timeout-hours", type=float, default=5.4, help="Thoi gian chay toi da truoc khi chu dong checkpoint va thoat an toan")
    return parser.parse_args()

def setup_phits_environment(tar_path: Path, target_dir: Path) -> tuple:
    target_dir.mkdir(parents=True, exist_ok=True)
    phits_bin = target_dir / "phits"
    if not phits_bin.exists():
        print(f">>> [SETUP] Dang giai nen goi PHITS tu {tar_path}...")
        subprocess.run(["tar", "-zxf", str(tar_path), "-C", str(target_dir)], check=True)
        if not phits_bin.exists():
            matches = list(target_dir.rglob("phits"))
            if matches:
                phits_bin = matches[0]
        subprocess.run(["chmod", "+x", str(phits_bin)], check=True)
    
    print(f">>> [SETUP] PHITS binary san sang tai: {phits_bin}")
    return phits_bin, target_dir

def build_job_list(excel_path: str, output_base: Path, sample_filter: str, omp: int, maxcas: int):
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
        e0_mev = energy_kev / 1000.0
        emax_mev = e0_mev * 1.05
        emin_peak = e0_mev * 0.990
        emax_peak = e0_mev * 1.010

        # Tao Blank job
        if energy_kev not in blank_generated:
            th_blank = 0.5
            z_sample_back = 50.0 + th_blank
            blank_name = f"blank_{energy_kev}keV"
            blank_dir = output_base / blank_name
            blank_dir.mkdir(parents=True, exist_ok=True)
            blank_inp = blank_dir / f"{blank_name}.inp"
            
            content = BLANK_TEMPLATE.format(
                energy_kev=energy_kev,
                e0_mev=e0_mev,
                emax_mev=emax_mev,
                emin_peak=emin_peak,
                emax_peak=emax_peak,
                omp=omp,
                maxcas=maxcas,
                thickness_str=_fmt_thickness(th_blank),
                z_sample_back=z_sample_back,
            )
            blank_inp.write_text(content, encoding="utf-8")
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

        # Tao Sample jobs
        for mat in target_mats:
            mat_key = mat.lower()
            if mat_key not in COMPOSITION:
                continue

            th_list = _parse_thickness_list(row[mat])
            for th in th_list:
                th_str = _fmt_thickness(th)
                job_name = f"{mat_key}_{energy_kev}keV_th{th_str}cm"
                job_dir = output_base / job_name
                job_dir.mkdir(parents=True, exist_ok=True)
                job_inp = job_dir / f"{job_name}.inp"

                z_sample_back = 50.0 + th
                sample_content = SAMPLE_TEMPLATE.format(
                    job_name=job_name,
                    mat_upper=mat_key.upper(),
                    energy_kev=energy_kev,
                    thickness_str=th_str,
                    e0_mev=e0_mev,
                    emax_mev=emax_mev,
                    emin_peak=emin_peak,
                    emax_peak=emax_peak,
                    omp=omp,
                    maxcas=maxcas,
                    mat_comp=format_material(COMPOSITION[mat_key]),
                    density=DENSITY[mat_key],
                    z_sample_back=z_sample_back,
                )
                job_inp.write_text(sample_content, encoding="utf-8")

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
    print(f"STARTING PHITS PARALLEL RUNNER #{args.runner_id} / {args.num_runners}")
    print(f"Filter: {args.sample_filter} | Maxcas: {args.maxcas:,} | OMP: {args.omp}")
    print("=" * 80)

    work_dir = Path("/tmp/phits_work")
    work_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Setup PHITS bin
    phits_bin, phits_root = setup_phits_environment(Path(args.package_path), work_dir / "bin")

    # 2. Ket noi Google Drive
    drive_service = None
    folder_ids = {}
    try:
        drive_service = gdrive_helper.get_drive_service()
        folder_ids = gdrive_helper.get_or_create_subfolders(drive_service)
        print(">>> [DRIVE] Ket noi Google Drive thanh cong!")
    except Exception as e:
        print(f">>> [CANH BAO] Khong the ket noi Google Drive: {e}. Tien trinh se tiep tuc luu local.")

    # 3. Kiem tra tien do da co tren Drive (Auto-Resume)
    completed_jobs = set()
    if drive_service and "02_Flux_Data" in folder_ids:
        print(">>> [RESUME] Dang kiem tra cac job da hoan thanh tren Google Drive...")
        completed_jobs = gdrive_helper.get_completed_jobs_from_drive(drive_service, folder_ids["02_Flux_Data"])
        print(f">>> [RESUME] Tim thay {len(completed_jobs)} job da hoan thanh tren Drive.")

    # 4. Sinh toan bo input
    inputs_base = work_dir / "inputs"
    all_jobs = build_job_list(args.excel_table, inputs_base, args.sample_filter, args.omp, args.maxcas)
    print(f">>> [PLAN] Tong so job cua toan bo nghien cuu: {len(all_jobs)}")

    # 5. Phan bo job cho runner nay
    my_jobs = [j for i, j in enumerate(all_jobs) if i % args.num_runners == (args.runner_id - 1)]
    todo_jobs = [j for j in my_jobs if j["name"] not in completed_jobs]
    print(f">>> [RUNNER #{args.runner_id}] Phan bo: {len(my_jobs)} jobs | Da xong: {len(my_jobs) - len(todo_jobs)} | Con lai: {len(todo_jobs)} jobs")

    if not todo_jobs:
        print(f">>> [HOAN THANH] Toan bo {len(my_jobs)} job cua Runner #{args.runner_id} da hoan tat tren Drive! Thoat.")
        return

    # 6. Thuc thi tung job
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
            print(f">>> [CHECKPOINT] Sap dat nguong timeout an toan ({args.timeout_hours}h). Dong bo va thoat an toan.")
            break

        jname = job["name"]
        jdir = job["dir"]
        jinp = job["inp"]
        e_mev = job["energy_kev"] / 1000.0

        print(f"\n--- [{idx}/{len(todo_jobs)}] Runner #{args.runner_id} dang chay: {jname} ({job['sample']} @ {job['energy_kev']} keV, th={job['thickness']} cm) ---")
        t0 = time.time()
        
        env = os.environ.copy()
        env["PHITSPATH"] = str(phits_root)
        env["OMP_NUM_THREADS"] = str(args.omp)
        
        cmd = f'"{phits_bin}" < "{jinp.name}"'
        res = subprocess.run(cmd, shell=True, cwd=str(jdir), env=env, capture_output=True, text=True)
        job_time = time.time() - t0

        peak_out = jdir / f"peak_{jname}.out"
        track_out = jdir / f"track_{jname}.out"

        if peak_out.exists() and track_out.exists():
            try:
                p_val, p_err = parse_track_flux(peak_out)
                t_val, t_err = parse_track_flux(track_out)
                print(f"    -> OK ({job_time:.1f}s) | Peak: {p_val:.6e} (err: {p_err:.4f}) | Tot: {t_val:.6e}")
                
                # Ghi vao CSV
                with open(csv_file, "a", encoding="utf-8") as f:
                    f.write(f"{jname},{e_mev:.6f},{job['sample']},{job['thickness']},{p_val:.8e},{p_err:.6f},{t_val:.8e},{t_err:.6f},{job_time:.1f}\n")
                
                batch_outs.extend([peak_out, track_out])
            except Exception as e:
                print(f"    -> LOI PARSE: {e}")
        else:
            print(f"    -> LOI THIEU FILE OUT! Tail log: {(res.stderr or res.stdout)[-300:]}")

        # Dong bo len Drive sau moi 2 job
        if len(batch_outs) >= 4:
            if drive_service and "03_Simulation_Outputs" in folder_ids:
                try:
                    zip_path = work_dir / f"outputs_runner_{sample_tag}{args.runner_id:02d}_batch_{batch_idx:03d}.zip"
                    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
                        for out_file in batch_outs:
                            z.write(out_file, arcname=out_file.name)
                    gdrive_helper.upload_file_to_folder(drive_service, str(zip_path), folder_ids["03_Simulation_Outputs"])
                    gdrive_helper.upload_file_to_folder(drive_service, str(csv_file), folder_ids["02_Flux_Data"])
                    print(f">>> [SYNC] Da dong bo Batch #{batch_idx} len Google Drive!")
                    batch_outs = []
                    batch_idx += 1
                except Exception as e:
                    print(f">>> [CANH BAO SYNC] Loi dong bo Drive: {e}, bo qua va tiep tuc chay.")

    # Dong bo phan con lai cuoi cung
    if batch_outs and drive_service and "03_Simulation_Outputs" in folder_ids:
        try:
            zip_path = work_dir / f"outputs_runner_{sample_tag}{args.runner_id:02d}_batch_{batch_idx:03d}.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
                for out_file in batch_outs:
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
RUNNER #{args.runner_id} HOAN THANH DOT CHAY
Tong thoi gian: {total_time:.1f} giay ({total_time/60:.1f} phut)
So job da xu ly dot nay: {len(todo_jobs)}
File ket qua flux: {csv_file.name}
=======================================================
"""
    timing_log.write_text(summary_text, encoding="utf-8")
    if drive_service and "05_Execution_Logs_and_Benchmarks" in folder_ids:
        try:
            gdrive_helper.upload_file_to_folder(drive_service, str(timing_log), folder_ids["05_Execution_Logs_and_Benchmarks"])
        except Exception as e:
            pass

    print(summary_text)

if __name__ == "__main__":
    main()
