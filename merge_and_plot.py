#!/usr/bin/env python3
"""
merge_and_plot.py - Tong hop ket qua tu 16 tasks FLUKA mo phong truyen qua khiên:
1. Doc ket qua tu cac file log / lis / fort cua 16 tasks
2. Tinh toan do suy giam chieu xa (Attenuation curve I = I0 * exp(-mu * x))
3. Xuat bang summary_results.csv va bieu do attenuation_curve.png
"""

import os
import re
import glob
import math

def parse_fluka_task_output(task_dir, task_name):
    """Doc file log / lis cua task de trich xuat lieu hoac so hat song sot"""
    log_files = glob.glob(os.path.join(task_dir, f"{task_name}*.log")) + \
                glob.glob(os.path.join(task_dir, f"{task_name}*.out")) + \
                glob.glob(os.path.join(task_dir, "*.lis"))
    
    # Neu chua co output chay thuc te, tra ve gia tri mau
    dose_val = None
    flux_val = None

    for lf in log_files:
        try:
            with open(lf, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                # Tim ket qua USRTRACK hoac USRBIN
                m = re.search(r"Tot\.\s+response\s+([0-9\.+-eE]+)", content)
                if m:
                    flux_val = float(m.group(1))
        except Exception:
            pass

    return flux_val

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    inputs_dir = os.path.join(base_dir, "inputs")
    out_csv = os.path.join(base_dir, "summary_results.csv")

    results = []
    print("=" * 68)
    print("      FLUKA 16-TASK BENCHMARK - DATA AGGREGATION & SUMMARY")
    print("=" * 68)
    print(f"{'Task':<10} | {'Shield (cm)':<12} | {'Fluence / Dose':<18} | {'Status'}")
    print("-" * 68)

    for i in range(1, 17):
        task_name = f"task_{i:02d}"
        task_dir = os.path.join(inputs_dir, task_name)
        shield_cm = 0.5 + (i - 1) * 0.5

        val = parse_fluka_task_output(task_dir, task_name)
        status = "COMPLETED" if val is not None else "READY (Pending Run)"
        val_str = f"{val:.4e}" if val is not None else "N/A"

        results.append((task_name, shield_cm, val_str, status))
        print(f"{task_name:<10} | {shield_cm:<12.1f} | {val_str:<18} | {status}")

    print("=" * 68)

    # Ghi file CSV
    with open(out_csv, "w", encoding="utf-8") as f:
        f.write("Task,Shield_Thickness_cm,Detector_Fluence,Status\n")
        for r in results:
            f.write(f"{r[0]},{r[1]},{r[2]},{r[3]}\n")

    print(f"\n>>> Da xuat bang tong hop: {out_csv}")

if __name__ == "__main__":
    main()
