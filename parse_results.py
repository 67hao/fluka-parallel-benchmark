"""
Doc ket qua thong luong photon (T-Track F4 equivalent) tu file .out cua PHITS,
trich xuat thong luong cua mau (Phi) va blank (Phi_0) ca thong luong tong va thong luong dinh (uncollided),
gom lai va xuat ra file Excel flux_results.xlsx.

Chay:
    python parse_results.py thickness_table.xlsx outputs/ flux_results.xlsx
"""
import re
import sys
from pathlib import Path
import pandas as pd


def _fmt_thickness(th: float) -> str:
    s = f"{th:.4f}".rstrip("0").rstrip(".")
    return s if s else "0"


def _parse_thickness_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, float) and pd.isna(value):
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    s = str(value).strip()
    if not s:
        return []
    parts = [p for p in re.split(r"[,;\s]+", s) if p]
    return [float(p) for p in parts]


def parse_track_flux(filepath: Path) -> tuple[float, float]:
    """
    Doc file T-Track (F4 equivalent) trong vung detector (reg 104),
    tra ve (flux, r_err).
    """
    lines = filepath.read_text(encoding="utf-8", errors="ignore").splitlines()
    for line in lines:
        parts = line.strip().split()
        # Tim dong chua '1   104   volume   photon   r.err'
        if len(parts) >= 5 and parts[0] == "1" and parts[1] == "104":
            try:
                flux = float(parts[-2])
                err = float(parts[-1])
                return flux, err
            except ValueError:
                pass
    raise ValueError(f"Khong tim thay du lieu flux vung reg 104 trong {filepath}")


def main(excel_path: str = "thickness_table.xlsx", outputs_dir: str = "outputs", result_path: str = "flux_results.xlsx"):
    df = pd.read_excel(excel_path)
    materials = [c for c in df.columns if c.lower() != "energy"]
    outputs_path = Path(outputs_dir)

    result_data_peak = {"Energy": df["Energy"].tolist()}
    result_data_peak["blank"] = [None] * len(df)
    for mat in materials:
        result_data_peak[mat] = [None] * len(df)

    result_data_tot = {"Energy": df["Energy"].tolist()}
    result_data_tot["blank"] = [None] * len(df)
    for mat in materials:
        result_data_tot[mat] = [None] * len(df)

    missing = []
    errors = []

    for idx, row in df.iterrows():
        energy_kev = int(round(row["Energy"]))

        # 1. Doc blank
        blank_job = f"blank_{energy_kev}keV"
        possible_blank_dirs = [
            outputs_path / blank_job,
            outputs_path,
        ]

        found_blank_peak = None
        found_blank_tot = None
        for d in possible_blank_dirs:
            p_peak = d / f"peak_{blank_job}.out"
            p_tot = d / f"track_{blank_job}.out"
            if p_peak.exists():
                found_blank_peak = p_peak
            if p_tot.exists():
                found_blank_tot = p_tot

        if found_blank_peak:
            try:
                val, _ = parse_track_flux(found_blank_peak)
                result_data_peak["blank"][idx] = val
            except Exception as e:
                errors.append(f"{blank_job} peak: {e}")
        if found_blank_tot:
            try:
                val, _ = parse_track_flux(found_blank_tot)
                result_data_tot["blank"][idx] = val
            except Exception as e:
                errors.append(f"{blank_job} tot: {e}")
        if not found_blank_peak and not found_blank_tot:
            missing.append(blank_job)

        # 2. Doc cac sample
        for mat in materials:
            th_list = _parse_thickness_list(row[mat])
            if not th_list:
                continue
            th_str = _fmt_thickness(th_list[0])
            job_name = f"{mat.lower()}_{energy_kev}keV_th{th_str}cm"
            possible_sample_dirs = [
                outputs_path / job_name,
                outputs_path,
            ]
            found_sample_peak = None
            found_sample_tot = None
            for d in possible_sample_dirs:
                p_peak = d / f"peak_{job_name}.out"
                p_tot = d / f"track_{job_name}.out"
                if p_peak.exists():
                    found_sample_peak = p_peak
                if p_tot.exists():
                    found_sample_tot = p_tot

            if found_sample_peak:
                try:
                    val, _ = parse_track_flux(found_sample_peak)
                    result_data_peak[mat][idx] = val
                except Exception as e:
                    errors.append(f"{job_name} peak: {e}")
            if found_sample_tot:
                try:
                    val, _ = parse_track_flux(found_sample_tot)
                    result_data_tot[mat][idx] = val
                except Exception as e:
                    errors.append(f"{job_name} tot: {e}")
            if not found_sample_peak and not found_sample_tot:
                missing.append(job_name)

    # Xuat ra Excel voi 2 sheet: Peak_Flux va Total_Flux
    with pd.ExcelWriter(result_path, engine="openpyxl") as writer:
        pd.DataFrame(result_data_peak).to_excel(writer, sheet_name="Peak_Flux_Uncollided", index=False)
        pd.DataFrame(result_data_tot).to_excel(writer, sheet_name="Total_Flux", index=False)

    print(f"Da xuat ket qua thong luong vao: {result_path}")
    if missing:
        print(f"Canh bao: {len(missing)} job chua tim thay file output.")
    if errors:
        print(f"Canh bao: {len(errors)} loi khi parse du lieu.")


if __name__ == "__main__":
    ex_path = sys.argv[1] if len(sys.argv) > 1 else "thickness_table.xlsx"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "outputs"
    res_path = sys.argv[3] if len(sys.argv) > 3 else "flux_results.xlsx"
    main(ex_path, out_dir, res_path)
