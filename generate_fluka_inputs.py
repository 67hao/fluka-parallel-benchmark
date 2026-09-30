"""
Sinh tu dong file .inp cho FLUKA - MO HINH HINH HOC CHUAN BAI 1 (Paper 10.1 - PNE 2022)
Mo hinh chuan theo Fig. 1 va Section 2.2 cua bai bao:
- Nguon photon diem tai z = 0 cm (chieu doc theo truc +z)
- Ong chuan truc chi (Pb collimator) tu z = 10 cm den z = 50 cm (lo r = 0.5 cm, vo r = 3.0 cm)
- Mau thuy tinh (Glass sample S1-S8) dat tai z = 50.0 cm (be day x cm, ban kinh r = 5.0 cm)
- Vung do F4 Tally equivalent (USRTRACK) tai z = 70.0 den 72.0 cm (ban kinh r = 5.0 cm, V = 157.0796 cm3)
- Vo chi boc ngoai (Outer Pb Shield) tu z = 45 den 75 cm (ban kinh trong r = 8 cm, ngoai r = 10 cm)
- Tally USRTRACK: Unit 21 cho tong thong luong (0 -> E0) va Unit 22 cho thong luong dinh (E0 +- 1%)

Cach chay:
    python generate_fluka_inputs.py thickness_table.xlsx inputs/ 1000000
"""
import re
import sys
from pathlib import Path
import pandas as pd

# ---------------------------------------------------------------------------
# Thanh phan vat lieu 8 mau thuy tinh (S1 -> S8) trong Paper 1 (PNE 2022)
# Tinh chinh xac tu Table 1 cua bai bao
# ---------------------------------------------------------------------------
COMPOSITION = {
    "s1": {
        "density": 2.390,
        "comp": [(-0.18583, "LITHIUM"), (-0.13976, "BORON"), (-0.60120, "OXYGEN"),
                 (-0.02646, "ALUMINUM"), (-0.04674, "SILICON")]
    },
    "s2": {
        "density": 2.725,
        "comp": [(-0.18583, "LITHIUM"), (-0.12423, "BORON"), (-0.57335, "OXYGEN"),
                 (-0.02646, "ALUMINUM"), (-0.04674, "SILICON"), (-0.04338, "GADOLINI")]
    },
    "s3": {
        "density": 2.908,
        "comp": [(-0.18583, "LITHIUM"), (-0.10870, "BORON"), (-0.54550, "OXYGEN"),
                 (-0.02646, "ALUMINUM"), (-0.04674, "SILICON"), (-0.08676, "GADOLINI")]
    },
    "s4": {
        "density": 3.103,
        "comp": [(-0.18583, "LITHIUM"), (-0.09317, "BORON"), (-0.51765, "OXYGEN"),
                 (-0.02646, "ALUMINUM"), (-0.04674, "SILICON"), (-0.13014, "GADOLINI")]
    },
    "s5": {
        "density": 3.836,
        "comp": [(-0.18635, "BORON"), (-0.52192, "OXYGEN"), (-0.04674, "SILICON"),
                 (-0.07147, "CALCIUM"), (-0.17352, "GADOLINI")]
    },
    "s6": {
        "density": 3.909,
        "comp": [(-0.17082, "BORON"), (-0.49407, "OXYGEN"), (-0.04674, "SILICON"),
                 (-0.07147, "CALCIUM"), (-0.21690, "GADOLINI")]
    },
    "s7": {
        "density": 4.181,
        "comp": [(-0.15529, "BORON"), (-0.46622, "OXYGEN"), (-0.04674, "SILICON"),
                 (-0.07147, "CALCIUM"), (-0.26028, "GADOLINI")]
    },
    "s8": {
        "density": 4.411,
        "comp": [(-0.13976, "BORON"), (-0.43837, "OXYGEN"), (-0.04674, "SILICON"),
                 (-0.07147, "CALCIUM"), (-0.30366, "GADOLINI")]
    },
}


def fmt10(val) -> str:
    """Dinh dang so hoac chuoi ve dung 10 ky tu chuan cot co dinh FLUKA."""
    if val == "" or val is None:
        return " " * 10
    if isinstance(val, (int, float)):
        if val == 0 or val == 0.0:
            return "       0.0"
        val_f = float(val)
        if abs(val_f) < 0.01 or abs(val_f) >= 100000:
            s = f"{val_f:10.3E}"
            return f"{s:>10}"[:10]
        if val_f == int(val_f):
            s = f"{val_f:10.1f}"
            return f"{s:>10}"[:10]
        for f_s in [f"{val_f:10.5f}", f"{val_f:10.4f}", f"{val_f:10.3f}", f"{val_f:10.2f}", f"{val_f:10.1f}"]:
            if len(f_s) == 10:
                return f_s
        s = f"{val_f:10.3E}"
        return f"{s:>10}"[:10]
    return f"{str(val):>10}"[:10]


def card(name: str, w1="", w2="", w3="", w4="", w5="", w6="", sdum="") -> str:
    """Tao 1 dong the FLUKA chuan 80 cot co dinh."""
    return f"{name:<10}{fmt10(w1)}{fmt10(w2)}{fmt10(w3)}{fmt10(w4)}{fmt10(w5)}{fmt10(w6)}{str(sdum):<10}"[:80] + "\n"


def generate_fluka_input(job_name: str, mat_key: str, energy_kev: float, thickness_cm: float, n_primaries: int = 100000000) -> str:
    """Sinh noi dung file .inp hoan chinh cho FLUKA."""
    is_blank = (mat_key.lower() == "blank")
    mat_upper = "BLANK" if is_blank else mat_key.upper()
    e_gev = energy_kev / 1.0e6  # FLUKA dung don vi GeV
    emax_gev = e_gev * 1.05
    emin_peak = e_gev * 0.990
    emax_peak = e_gev * 1.010

    lines = []
    lines.append("* ..+....1....+....2....+....3....+....4....+....5....+....6....+....7....+....8\n")
    lines.append("TITLE\n")
    th_title_str = f"{thickness_cm:.4f}".rstrip("0").rstrip(".")
    lines.append(f"Paper 1 Benchmark FLUKA - {mat_upper} @ {energy_kev} keV, th={th_title_str} cm\n")
    lines.append("*\n")
    lines.append(card("DEFAULTS", sdum="EM-CASCA"))
    lines.append(card("EMFRAY", 1.0))
    lines.append(card("EMFFLUO", 1.0))
    lines.append(card("DISCARD", "NEUTRON"))
    lines.append("*\n")
    lines.append(f"* Nguon photon {energy_kev} keV ({e_gev:.6E} GeV) huong doc truc +z\n")
    lines.append(card("BEAM", -e_gev, sdum="PHOTON"))
    lines.append(card("BEAMPOS", 0.0, 0.0, 0.0))
    lines.append("*\n")
    lines.append(card("GEOBEGIN", sdum="COMBNAME"))
    lines.append("    0    0          Geometry for Paper 1 (MCNPX Benchmark equivalent)\n")
    lines.append("SPH BLK        0.0 0.0 40.0 120.0\n")
    lines.append("SPH WORLD      0.0 0.0 40.0 100.0\n")
    lines.append("RCC COLLOUT    0.0 0.0 10.0 0.0 0.0 40.0 3.0\n")
    lines.append("RCC COLLIN     0.0 0.0 10.0 0.0 0.0 40.0 0.5\n")
    lines.append(f"RCC SAMPLE     0.0 0.0 50.0 0.0 0.0 {thickness_cm:.4f} 5.0\n")
    lines.append("RCC DETECT     0.0 0.0 70.0 0.0 0.0 2.0 5.0\n")
    lines.append("RCC SHIELDO    0.0 0.0 45.0 0.0 0.0 30.0 10.0\n")
    lines.append("RCC SHIELDI    0.0 0.0 45.0 0.0 0.0 30.0 8.0\n")
    lines.append("END\n")
    lines.append("* Regions\n")
    lines.append("BLKHOLE      5 +BLK -WORLD\n")
    lines.append("COLLBODY     5 +COLLOUT -COLLIN\n")
    lines.append("COLLBORE     5 +COLLIN\n")
    lines.append("SAMPLE       5 +SAMPLE\n")
    lines.append("DETECT       5 +DETECT\n")
    lines.append("SHIELD       5 +SHIELDO -SHIELDI\n")
    lines.append("CHAMBER      5 +SHIELDI -COLLOUT -SAMPLE -DETECT\n")
    lines.append("AIRVOID      5 +WORLD -SHIELDO -COLLOUT\n")
    lines.append("END\n")
    lines.append("GEOEND\n")
    lines.append("*\n")

    # Dinh nghia cac nguyen to can thiet cho mau thuy tinh S1-S8 trong FLUKA 4
    # FLUKA 4 yeu cau WHAT(2) (nguyen tu luong) de trong de dung database tu nhien
    lines.append("* Dinh nghia nguyen to vat lieu\n")
    lines.append(card("MATERIAL", 3.0, "", 0.534, sdum="LITHIUM"))
    lines.append(card("MATERIAL", 5.0, "", 2.340, sdum="BORON"))
    lines.append(card("MATERIAL", 20.0, "", 1.550, sdum="CALCIUM"))
    lines.append(card("MATERIAL", 64.0, "", 7.900, sdum="GADOLINI"))
    lines.append("*\n")

    # Dinh nghia mau thuy tinh
    if not is_blank:
        prop = COMPOSITION[mat_key.lower()]
        mat_fluka_name = f"GL_{mat_key.upper()}"
        lines.append(f"* Glass sample {mat_key.upper()} (rho = {prop['density']:.4f} g/cm3)\n")
        lines.append(card("MATERIAL", "", "", prop["density"], sdum=mat_fluka_name))
        comp_pairs = prop["comp"]
        for i in range(0, len(comp_pairs), 3):
            chunk = comp_pairs[i:i+3]
            w1 = chunk[0][0] if len(chunk) > 0 else ""
            w2 = chunk[0][1] if len(chunk) > 0 else ""
            w3 = chunk[1][0] if len(chunk) > 1 else ""
            w4 = chunk[1][1] if len(chunk) > 1 else ""
            w5 = chunk[2][0] if len(chunk) > 2 else ""
            w6 = chunk[2][1] if len(chunk) > 2 else ""
            lines.append(card("COMPOUND", w1, w2, w3, w4, w5, w6, sdum=mat_fluka_name))
        sample_mat = mat_fluka_name
    else:
        sample_mat = "VACUUM"

    lines.append("*\n")
    lines.append("* Gan vat lieu cho cac vung hinh hoc\n")
    lines.append(card("ASSIGNMA", "BLCKHOLE", "BLKHOLE"))
    lines.append(card("ASSIGNMA", "LEAD", "COLLBODY"))
    lines.append(card("ASSIGNMA", "VACUUM", "COLLBORE"))
    lines.append(card("ASSIGNMA", sample_mat, "SAMPLE"))
    lines.append(card("ASSIGNMA", "VACUUM", "DETECT"))
    lines.append(card("ASSIGNMA", "LEAD", "SHIELD"))
    lines.append(card("ASSIGNMA", "VACUUM", "CHAMBER"))
    lines.append(card("ASSIGNMA", "VACUUM", "AIRVOID"))
    lines.append("*\n")

    # EMF thresholds: ha nguong van chuyen photon/electron xuong 1 keV (1.0E-6 GeV)
    lines.append("* Ha nguong van chuyen xuong 1 keV\n")
    lines.append(card("EMFCUT", -1.0e-6, 1.0e-6, 1.0e-5, "VACUUM", "@LASTMAT", sdum="PROD-CUT"))
    lines.append(card("EMFCUT", -1.0e-6, 1.0e-6, "", "BLKHOLE", "@LASTREG"))
    lines.append("*\n")

    # Scoring: USRTRACK
    lines.append("* Scoring: USRTRACK (F4 equivalent track-length fluence)\n")
    lines.append(card("USRTRACK", 1.0, "PHOTON", 21.0, "DETECT", 157.0796, 1.0, sdum="TotFlux"))
    lines.append(card("USRTRACK", emax_gev, 0.0, sdum="&"))
    lines.append(card("USRTRACK", 1.0, "PHOTON", 22.0, "DETECT", 157.0796, 1.0, sdum="PeakFlux"))
    lines.append(card("USRTRACK", emax_peak, emin_peak, sdum="&"))
    lines.append("*\n")

    # Random seed va so hat phat
    lines.append(card("RANDOMIZ", 1.0))
    lines.append(card("START", float(n_primaries)))
    lines.append(card("STOP"))

    return "".join(lines)


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


def main(excel_path: str = "thickness_table_all9.xlsx", output_dir: str = "inputs", n_primaries: int = 100000000):
    df = pd.read_excel(excel_path)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    materials = [col for col in df.columns if col.lower() != "energy"]
    count_jobs = 0
    blank_generated = set()

    for _, row in df.iterrows():
        energy_kev = int(round(row["Energy"]))

        # 1. Tao file Blank cho muc nang luong nay
        if energy_kev not in blank_generated:
            th_blank = 0.5
            blank_job_name = f"blank_{energy_kev}keV"
            blank_content = generate_fluka_input(blank_job_name, "blank", energy_kev, th_blank, n_primaries)
            (output_path / f"{blank_job_name}.inp").write_text(blank_content, encoding="utf-8")
            blank_generated.add(energy_kev)
            count_jobs += 1

        # 2. Tao file cho tung mau thuy tinh
        for mat in materials:
            mat_key = mat.lower()
            if mat_key not in COMPOSITION:
                continue

            th_list = _parse_thickness_list(row[mat])
            for th in th_list:
                th_str = f"{th:.4f}".rstrip("0").rstrip(".")
                job_name = f"{mat_key}_{energy_kev}keV_th{th_str}cm"
                content = generate_fluka_input(job_name, mat_key, energy_kev, th, n_primaries)
                (output_path / f"{job_name}.inp").write_text(content, encoding="utf-8")
                count_jobs += 1

    print(f"\n=======================================================")
    print(f"DA SINH THANH CONG {count_jobs} FILE .INP FLUKA VAO: {output_path}")
    print(f"So hat phat moi job: {n_primaries} primaries")
    print(f"=======================================================")


if __name__ == "__main__":
    ex_p = sys.argv[1] if len(sys.argv) > 1 else "thickness_table_all9.xlsx"
    out_d = sys.argv[2] if len(sys.argv) > 2 else "inputs"
    n_prim = int(sys.argv[3]) if len(sys.argv) > 3 else 100000000
    main(ex_p, out_d, n_prim)
