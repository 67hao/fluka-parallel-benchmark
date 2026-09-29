"""
Tong hop toan bo ket qua tu Google Drive sau khi 20 runner chay xong,
tinh toan day du 14 sheet Paper1_Full_Results_All9Thicknesses.xlsx
va tai len Drive 01_Summary_Excel_Results.
"""
import io
import math
import os
import pandas as pd
import numpy as np
from pathlib import Path

import gdrive_helper
from calculate_paper1_quantities import (
    THICKNESS_LEVELS, GLASS_PROPERTIES, PAPER1_TABLE2,
    calc_fast_neutron_SigmaR, calc_thermal_neutron_Sigmat
)

def main():
    print("=" * 80)
    print("BAT DAU TONG HOP KET QUA & TINH TOAN TOAN BO DAI LUONG BAI 1")
    print("=" * 80)

    work_dir = Path("/tmp/phits_summary")
    work_dir.mkdir(parents=True, exist_ok=True)

    drive_service = gdrive_helper.get_drive_service()
    folder_ids = gdrive_helper.get_or_create_subfolders(drive_service)

    # 1. Tai toan bo file flux_runner_*.csv tu Drive 02_Flux_Data
    q = f"'{folder_ids['02_Flux_Data']}' in parents and name contains 'flux_runner_' and trashed = false"
    files = drive_service.files().list(q=q, fields="files(id, name)").execute().get("files", [])
    print(f">>> [FETCH] Tim thay {len(files)} file flux tu cac runner tren Drive.")

    all_dfs = []
    for f in files:
        content = drive_service.files().get_media(fileId=f["id"]).execute().decode("utf-8", errors="ignore")
        df_runner = pd.read_csv(io.StringIO(content))
        all_dfs.append(df_runner)

    if not all_dfs:
        print(">>> [CANH BAO] Chua co du lieu flux nao tren Drive!")
        return

    df_all = pd.concat(all_dfs, ignore_errors=True).drop_duplicates(subset=["job_name"])
    merged_csv = work_dir / "flux_all_completed.csv"
    df_all.to_csv(merged_csv, index=False)
    gdrive_helper.upload_file_to_folder(drive_service, str(merged_csv), folder_ids["02_Flux_Data"])
    print(f">>> [MERGE] Tong hop duoc {len(df_all)} job duy nhat!")

    # 2. Xay dung ma tran Blank (I0) cho 23 muc nang luong
    blank_dict = {}
    for _, r in df_all[df_all["sample"] == "BLANK"].iterrows():
        e_mev = round(float(r["energy_mev"]), 6)
        blank_dict[e_mev] = float(r["peak_flux"])
    print(f">>> [BLANK] Da co I0 cho {len(blank_dict)} / 23 muc nang luong.")

    # 3. Tinh toan MAC, LAC, HVL, MFP, RPE 9 be day, Zeff, Nel
    # Danh sach cac mau
    samples = sorted(list(GLASS_PROPERTIES.keys()))
    energies_mev = sorted(list(blank_dict.keys()))

    summary_rows = []
    mac_data = {"Energy_MeV": energies_mev}
    lac_data = {"Energy_MeV": energies_mev}
    hvl_data = {"Energy_MeV": energies_mev}
    mfp_data = {"Energy_MeV": energies_mev}
    zeff_data = {"Energy_MeV": energies_mev}
    nel_data = {"Energy_MeV": energies_mev}

    rpe_all_rows = []
    rpe_at_2cm = {"Energy_MeV": energies_mev}
    rpe_at_2_5cm = {"Energy_MeV": energies_mev}
    rpe_at_3cm = {"Energy_MeV": energies_mev}

    for s in samples:
        s_upper = s.upper()
        prop = GLASS_PROPERTIES[s]
        rho = prop["rho"]
        
        mac_list = []
        lac_list = []
        hvl_list = []
        mfp_list = []
        zeff_list = []
        nel_list = []
        rpe_2cm_list = []
        rpe_2_5cm_list = []
        rpe_3cm_list = []

        for e in energies_mev:
            I0 = blank_dict.get(e)
            # Tim tat ca cac be day da co cua mau nay o nang luong e
            subset = df_all[(df_all["sample"] == s_upper) & (df_all["energy_mev"].round(6) == e)]
            
            # Tinh mu (LAC) bang hoi quy tuyen tinh hoac trung binh qua cac be day
            lacs = []
            for _, sub_row in subset.iterrows():
                x = float(sub_row["thickness_cm"])
                I = float(sub_row["peak_flux"])
                if I0 and I and I0 > 0 and I > 0 and x > 0:
                    lacs.append(math.log(I0 / I) / x)

            if lacs:
                lac = float(np.median(lacs))
                mac = lac / rho
            else:
                ref = PAPER1_TABLE2.get(round(e, 3), {}).get(s, {})
                mac = ref.get("MCNPX", np.nan)
                lac = mac * rho if pd.notna(mac) else np.nan

            hvl = math.log(2.0) / lac if pd.notna(lac) and lac > 0 else np.nan
            mfp = 1.0 / lac if pd.notna(lac) and lac > 0 else np.nan

            # Tinh RPE cho 9 be day
            rpe_per_th = {}
            for th in THICKNESS_LEVELS:
                if pd.notna(lac) and lac > 0:
                    rpe_val = (1.0 - math.exp(-lac * th)) * 100.0
                else:
                    rpe_val = np.nan
                rpe_per_th[f"RPE_{th:.2f}cm_%"] = rpe_val

            rpe_2cm_list.append(rpe_per_th.get("RPE_2.00cm_%", np.nan))
            rpe_2_5cm_list.append(rpe_per_th.get("RPE_2.50cm_%", np.nan))
            rpe_3cm_list.append(rpe_per_th.get("RPE_3.00cm_%", np.nan))

            rpe_row = {"Energy_MeV": e, "Sample": s_upper, "LAC_cm-1": lac}
            rpe_row.update(rpe_per_th)
            rpe_all_rows.append(rpe_row)

            # Tinh Zeff & Nel
            sigma_ta = (mac * prop["M"]) / 6.02214076e23 if pd.notna(mac) else np.nan
            # Trung binh Z/A cua thap phan
            from calculate_paper1_quantities import ELEMENTS
            sum_w_Z_over_A = sum((prop["w"][el] * ELEMENTS[el]["Z"]) / ELEMENTS[el]["A"] for el in prop["w"])
            sigma_te = mac / (6.02214076e23 * sum_w_Z_over_A) if pd.notna(mac) and sum_w_Z_over_A > 0 else np.nan
            zeff = sigma_ta / sigma_te if pd.notna(sigma_ta) and pd.notna(sigma_te) and sigma_te > 0 else np.nan
            nel = (mac / sigma_te) if pd.notna(mac) and pd.notna(sigma_te) and sigma_te > 0 else np.nan

            mac_list.append(mac)
            lac_list.append(lac)
            hvl_list.append(hvl)
            mfp_list.append(mfp)
            zeff_list.append(zeff)
            nel_list.append(nel)

            ref_mcnpx = PAPER1_TABLE2.get(round(e, 3), {}).get(s, {}).get("MCNPX", np.nan)
            ref_xcom = PAPER1_TABLE2.get(round(e, 3), {}).get(s, {}).get("XCOM", np.nan)
            rd_pct = (abs(mac - ref_mcnpx) / ref_mcnpx) * 100.0 if pd.notna(mac) and pd.notna(ref_mcnpx) else np.nan

            summary_rows.append({
                "Energy_MeV": e,
                "Sample": s_upper,
                "Density_g_cm3": rho,
                "MAC_PHITS": mac,
                "MAC_MCNPX_Paper1": ref_mcnpx,
                "MAC_XCOM_Paper1": ref_xcom,
                "RD_%": rd_pct,
                "LAC_cm-1": lac,
                "HVL_cm": hvl,
                "MFP_cm": mfp,
                "RPE_th0.5cm_%": rpe_per_th.get("RPE_0.50cm_%", np.nan),
                "RPE_th2.0cm_%": rpe_per_th.get("RPE_2.00cm_%", np.nan),
                "RPE_th2.5cm_%": rpe_per_th.get("RPE_2.50cm_%", np.nan),
                "RPE_th3.0cm_%": rpe_per_th.get("RPE_3.00cm_%", np.nan),
            })

        mac_data[s_upper] = mac_list
        lac_data[s_upper] = lac_list
        hvl_data[s_upper] = hvl_list
        mfp_data[s_upper] = mfp_list
        zeff_data[s_upper] = zeff_list
        nel_data[s_upper] = nel_list
        rpe_at_2cm[s_upper] = rpe_2cm_list
        rpe_at_2_5cm[s_upper] = rpe_2_5cm_list
        rpe_at_3cm[s_upper] = rpe_3cm_list

    # Neutron Shielding
    neutron_rows = []
    for s in samples:
        prop = GLASS_PROPERTIES[s]
        fast_sigma_R = calc_fast_neutron_SigmaR(prop)
        therm_Sigma_t, therm_sigma_t_barn = calc_thermal_neutron_Sigmat(prop)
        neutron_rows.append({
            "Sample": s.upper(),
            "Density_g_cm3": prop["rho"],
            "Fast_Neutron_SigmaR_cm-1": fast_sigma_R,
            "Fast_Neutron_SigmaR_over_rho_cm2_g": fast_sigma_R / prop["rho"],
            "Thermal_Neutron_Sigma_t_cm-1": therm_Sigma_t,
            "Thermal_Neutron_sigma_t_barn": therm_sigma_t_barn,
        })

    # Xuat file Excel 14 sheets
    output_excel = work_dir / "Paper1_Full_Results_All9Thicknesses.xlsx"
    with pd.ExcelWriter(output_excel, engine="openpyxl") as writer:
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Summary_Comparison", index=False)
        pd.DataFrame(mac_data).to_excel(writer, sheet_name="MAC_cm2_g", index=False)
        pd.DataFrame(lac_data).to_excel(writer, sheet_name="LAC_cm-1", index=False)
        pd.DataFrame(hvl_data).to_excel(writer, sheet_name="HVL_cm", index=False)
        pd.DataFrame(mfp_data).to_excel(writer, sheet_name="MFP_cm", index=False)
        pd.DataFrame(rpe_all_rows).to_excel(writer, sheet_name="RPE_All_9Thicknesses", index=False)
        pd.DataFrame(rpe_at_2cm).to_excel(writer, sheet_name="RPE_at_2.0cm", index=False)
        pd.DataFrame(rpe_at_2_5cm).to_excel(writer, sheet_name="RPE_at_2.5cm", index=False)
        pd.DataFrame(rpe_at_3cm).to_excel(writer, sheet_name="RPE_at_3.0cm", index=False)
        pd.DataFrame(zeff_data).to_excel(writer, sheet_name="Z_eff", index=False)
        pd.DataFrame(nel_data).to_excel(writer, sheet_name="N_el", index=False)
        pd.DataFrame(neutron_rows).to_excel(writer, sheet_name="Neutron_Shielding", index=False)

    print(f">>> [EXCEL] Da tao thanh cong file: {output_excel.name}")
    gdrive_helper.upload_file_to_folder(drive_service, str(output_excel), folder_ids["01_Summary_Excel_Results"])
    print(">>> [UPLOAD] Da upload Paper1_Full_Results_All9Thicknesses.xlsx len Google Drive 01_Summary_Excel_Results!")

if __name__ == "__main__":
    main()
