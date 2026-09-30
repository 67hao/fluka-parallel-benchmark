"""
Sinh tu dong file .inp cho PHITS - MO HINH HINH HOC CHUAN BAI 1 (Paper 10.1 - PNE 2022)
Mo hinh chuan theo Fig. 1 va Section 2.2 cua bai bao:
- Nguon photon diem dang huong tai z = 0 cm
- Ong chuan truc chi (Pb collimator) tu z = 10 cm den z = 50 cm
- Mau thuy tinh (Glass sample S1-S8) dat tai z = 50.0 cm
- Vung do F4 Tally Mesh dat tai z = 70.0 cm (F4 cell flux tally = [ T-Track ])
- Vo chi boc ngoai (Outer Pb Shield) bao quanh vung mau va dau do tu z = 45 den 75 cm

Cach chay:
    python generate_inputs.py thickness_table.xlsx inputs/
"""
import re
import sys
import pandas as pd
from pathlib import Path

# ---------------------------------------------------------------------------
# Thanh phan vat lieu 8 mau thuy tinh (S1 -> S8) trong Paper 1 (PNE 2022)
# Tinh chinh xac tu Table 1 cua bai bao
# ---------------------------------------------------------------------------
COMPOSITION = {
    # S1: 45 B2O3 - 10 SiO2 - 40 Li2O - 5 Al2O3 - 0 Gd2O3 (rho = 2.390 g/cm3)
    "s1": {
        "3000.00c": -0.18583,   # Li
        "5000.00c": -0.13976,   # B
        "8000.00c": -0.60120,   # O
        "13000.00c": -0.02646,  # Al
        "14000.00c": -0.04674,  # Si
    },
    # S2: 40 B2O3 - 10 SiO2 - 40 Li2O - 5 Al2O3 - 5 Gd2O3 (rho = 2.725 g/cm3)
    "s2": {
        "3000.00c": -0.18583,   # Li
        "5000.00c": -0.12423,   # B
        "8000.00c": -0.57335,   # O
        "13000.00c": -0.02646,  # Al
        "14000.00c": -0.04674,  # Si
        "64000.00c": -0.04338,  # Gd
    },
    # S3: 35 B2O3 - 10 SiO2 - 40 Li2O - 5 Al2O3 - 10 Gd2O3 (rho = 2.908 g/cm3)
    "s3": {
        "3000.00c": -0.18583,   # Li
        "5000.00c": -0.10870,   # B
        "8000.00c": -0.54550,   # O
        "13000.00c": -0.02646,  # Al
        "14000.00c": -0.04674,  # Si
        "64000.00c": -0.08676,  # Gd
    },
    # S4: 30 B2O3 - 10 SiO2 - 40 Li2O - 5 Al2O3 - 15 Gd2O3 (rho = 3.103 g/cm3)
    "s4": {
        "3000.00c": -0.18583,   # Li
        "5000.00c": -0.09317,   # B
        "8000.00c": -0.51765,   # O
        "13000.00c": -0.02646,  # Al
        "14000.00c": -0.04674,  # Si
        "64000.00c": -0.13014,  # Gd
    },
    # S5: 60 B2O3 - 10 SiO2 - 10 CaO - 20 Gd2O3 (rho = 3.836 g/cm3)
    "s5": {
        "5000.00c": -0.18635,   # B
        "8000.00c": -0.52192,   # O
        "14000.00c": -0.04674,  # Si
        "20000.00c": -0.07147,  # Ca
        "64000.00c": -0.17352,  # Gd
    },
    # S6: 55 B2O3 - 10 SiO2 - 10 CaO - 25 Gd2O3 (rho = 3.909 g/cm3)
    "s6": {
        "5000.00c": -0.17082,   # B
        "8000.00c": -0.49407,   # O
        "14000.00c": -0.04674,  # Si
        "20000.00c": -0.07147,  # Ca
        "64000.00c": -0.21690,  # Gd
    },
    # S7: 50 B2O3 - 10 SiO2 - 10 CaO - 30 Gd2O3 (rho = 4.181 g/cm3)
    "s7": {
        "5000.00c": -0.15529,   # B
        "8000.00c": -0.46622,   # O
        "14000.00c": -0.04674,  # Si
        "20000.00c": -0.07147,  # Ca
        "64000.00c": -0.26028,  # Gd
    },
    # S8: 45 B2O3 - 10 SiO2 - 10 CaO - 35 Gd2O3 (rho = 4.411 g/cm3)
    "s8": {
        "5000.00c": -0.13976,   # B
        "8000.00c": -0.43837,   # O
        "14000.00c": -0.04674,  # Si
        "20000.00c": -0.07147,  # Ca
        "64000.00c": -0.30366,  # Gd
    },
}

DENSITY = {
    "s1": 2.390,
    "s2": 2.725,
    "s3": 2.908,
    "s4": 3.103,
    "s5": 3.836,
    "s6": 3.909,
    "s7": 4.181,
    "s8": 4.411,
}

# ---------------------------------------------------------------------------
# Template SAMPLE - Hinh hoc chuan Paper 1 (Fig. 1)
# ---------------------------------------------------------------------------
SAMPLE_TEMPLATE = """Paper 1 MCNPX Benchmark Geometry - Material {mat_upper} @ {energy_kev} keV, thickness {thickness_str} cm
Setup: Point Source @ 0 cm, Sample Position @ 50 cm, F4 Tally Mesh @ 70 cm

$OMP={omp} 

[ Parameters ]
icntl    = 0
nucdata  = 0
maxcas   = {maxcas}
maxbch   = 1
file(6)  = phits_{job_name}.out

[ Source ]
totfact  = 1.0
s-type   = 1
x0       = 0.0
y0       = 0.0
z0       = 0.0
z1       = 0.0
proj     = photon
e0       = {e0_mev:.6f}
dir      = 1.0
r0       = 0.0

[ Material ]
m1    82000.00c  1.0     $ Pb (Lead)

m2    {mat_comp}

[ Surface ]
10  pz   0.0          $ Source position (z = 0 cm)
11  pz  10.0          $ Collimator front face (z = 10 cm)
12  pz  50.0          $ Collimator back face / Sample front face (z = 50 cm)
13  pz  {z_sample_back:.4f}       $ Sample back face (thickness {thickness_str} cm)
14  pz  45.0          $ Outer Pb shield front face (z = 45 cm)
15  pz  70.0          $ F4 Tally detection field front face (z = 70 cm)
16  pz  72.0          $ F4 Tally detection field back face (z = 72 cm)
17  pz  75.0          $ Outer Pb shield back face (z = 75 cm)

20  cz   0.5          $ Collimator hole radius (r = 0.5 cm)
21  cz   3.0          $ Collimator outer radius (r = 3.0 cm)
22  cz   5.0          $ Glass sample & Detection field radius (r = 5.0 cm)
23  cz   8.0          $ Outer Pb shield inner radius (r = 8.0 cm)
24  cz  10.0          $ Outer Pb shield outer radius (r = 10.0 cm)
99  so 100.0          $ World boundary

[ Cell ]
$ Collimator bore (hole along z-axis)
101   0          11 -12 -20
$ Collimator Pb body
102   1 -11.34   11 -12 20 -21
$ Glass sample slot - {mat_upper} (rho = {density:.4f} g/cm3)
103   2 -{density:.4f}   12 -13 -22
$ F4 Tally Mesh detection field (z = 70 to 72 cm, r <= 5 cm)
104   0          15 -16 -22
$ Outer Pb shield (z = 45 to 75 cm, 8 <= r <= 10 cm)
105   1 -11.34   14 -17 23 -24
$ Free chamber inside Pb shield (excluding collimator, sample, detector)
106   0          14 -17 -23  #101 #102 #103 #104
$ Space between source and collimator / shield
107   0          10 -14 -99  #101 #102
$ Surrounding space outside shield and collimator inside world
108   0          -99  #101 #102 #103 #104 #105 #106 #107
$ Graveyard (outside world)
110  -1          99

[ Volume ]
reg   vol
104   157.0796

[ T-Track ]
title = Average Photon Flux in Detection Field (F4 equivalent) - {mat_upper} @ {energy_kev} keV
mesh  = reg
reg   = 104
part  = photon
unit  = 1
e-type = 2
ne    = 1
emin  = 0.0
emax  = {emax_mev:.6f}
axis  = reg
file  = track_{job_name}.out

[ T-Track ]
title = Uncollided Peak Photon Flux in Detection Field - {mat_upper} @ {energy_kev} keV
mesh  = reg
reg   = 104
part  = photon
unit  = 1
e-type = 2
ne    = 1
emin  = {emin_peak:.6f}
emax  = {emax_peak:.6f}
axis  = reg
file  = peak_{job_name}.out
"""

# ---------------------------------------------------------------------------
# Template BLANK - Hinh hoc chuan Paper 1 (Cell 103 la chan khong)
# ---------------------------------------------------------------------------
BLANK_TEMPLATE = """Paper 1 MCNPX Benchmark Geometry - BLANK (no sample) @ {energy_kev} keV
Setup: Point Source @ 0 cm, Sample Position @ 50 cm, F4 Tally Mesh @ 70 cm

$OMP={omp} 

[ Parameters ]
icntl    = 0
nucdata  = 0
maxcas   = {maxcas}
maxbch   = 1
file(6)  = phits_blank_{energy_kev}keV.out

[ Source ]
totfact  = 1.0
s-type   = 1
x0       = 0.0
y0       = 0.0
z0       = 0.0
z1       = 0.0
proj     = photon
e0       = {e0_mev:.6f}
dir      = 1.0
r0       = 0.0

[ Material ]
m1    82000.00c  1.0     $ Pb (Lead)

[ Surface ]
10  pz   0.0          $ Source position (z = 0 cm)
11  pz  10.0          $ Collimator front face (z = 10 cm)
12  pz  50.0          $ Collimator back face / Sample front face (z = 50 cm)
13  pz  {z_sample_back:.4f}       $ Sample back face (thickness {thickness_str} cm)
14  pz  45.0          $ Outer Pb shield front face (z = 45 cm)
15  pz  70.0          $ F4 Tally detection field front face (z = 70 cm)
16  pz  72.0          $ F4 Tally detection field back face (z = 72 cm)
17  pz  75.0          $ Outer Pb shield back face (z = 75 cm)

20  cz   0.5          $ Collimator hole radius (r = 0.5 cm)
21  cz   3.0          $ Collimator outer radius (r = 3.0 cm)
22  cz   5.0          $ Glass sample & Detection field radius (r = 5.0 cm)
23  cz   8.0          $ Outer Pb shield inner radius (r = 8.0 cm)
24  cz  10.0          $ Outer Pb shield outer radius (r = 10.0 cm)
99  so 100.0          $ World boundary

[ Cell ]
$ Collimator bore (hole along z-axis)
101   0          11 -12 -20
$ Collimator Pb body
102   1 -11.34   11 -12 20 -21
$ Glass sample slot - BLANK has vacuum (material 0)
103   0          12 -13 -22
$ F4 Tally Mesh detection field (z = 70 to 72 cm, r <= 5 cm)
104   0          15 -16 -22
$ Outer Pb shield (z = 45 to 75 cm, 8 <= r <= 10 cm)
105   1 -11.34   14 -17 23 -24
$ Free chamber inside Pb shield (excluding collimator, sample, detector)
106   0          14 -17 -23  #101 #102 #103 #104
$ Space between source and collimator / shield
107   0          10 -14 -99  #101 #102
$ Surrounding space outside shield and collimator inside world
108   0          -99  #101 #102 #103 #104 #105 #106 #107
$ Graveyard (outside world)
110  -1          99

[ Volume ]
reg   vol
104   157.0796

[ T-Track ]
title = Average Photon Flux in Detection Field (F4 equivalent) - Blank @ {energy_kev} keV
mesh  = reg
reg   = 104
part  = photon
unit  = 1
e-type = 2
ne    = 1
emin  = 0.0
emax  = {emax_mev:.6f}
axis  = reg
file  = track_blank_{energy_kev}keV.out

[ T-Track ]
title = Uncollided Peak Photon Flux in Detection Field - Blank @ {energy_kev} keV
mesh  = reg
reg   = 104
part  = photon
unit  = 1
e-type = 2
ne    = 1
emin  = {emin_peak:.6f}
emax  = {emax_peak:.6f}
axis  = reg
file  = peak_blank_{energy_kev}keV.out
"""


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


def format_material(comp_dict: dict) -> str:
    lines = []
    for zaid, frac in comp_dict.items():
        lines.append(f"      {zaid:10s}  {frac:.5f}")
    first_line = lines[0].strip()
    remaining = "\n".join(lines[1:])
    return first_line + ("\n" + remaining if remaining else "")


def main(excel_path: str = "thickness_table.xlsx", output_dir: str = "inputs", omp: int = 2, maxcas: int = 100000000):
    df = pd.read_excel(excel_path)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    materials = [col for col in df.columns if col.lower() != "energy"]
    count_jobs = 0
    blank_generated = set()

    for _, row in df.iterrows():
        energy_kev = int(round(row["Energy"]))
        e0_mev = energy_kev / 1000.0
        emax_mev = e0_mev * 1.05

        # Cua so nang luong gan dinh uncollided (+/- 1%)
        emin_peak = e0_mev * 0.990
        emax_peak = e0_mev * 1.010

        # Tao Blank job cho energy nay
        if energy_kev not in blank_generated:
            th_blank = 0.5
            z_sample_back = 50.0 + th_blank
            blank_job_name = f"blank_{energy_kev}keV"
            blank_job_dir = output_path / blank_job_name
            blank_job_dir.mkdir(parents=True, exist_ok=True)
            blank_content = BLANK_TEMPLATE.format(
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
            (blank_job_dir / f"{blank_job_name}.inp").write_text(blank_content, encoding="utf-8")
            blank_generated.add(energy_kev)
            count_jobs += 1

        # Tao Sample jobs
        for mat in materials:
            mat_key = mat.lower()
            if mat_key not in COMPOSITION:
                continue

            th_list = _parse_thickness_list(row[mat])
            for th in th_list:
                th_str = _fmt_thickness(th)
                job_name = f"{mat_key}_{energy_kev}keV_th{th_str}cm"
                job_dir = output_path / job_name
                job_dir.mkdir(parents=True, exist_ok=True)

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
                (job_dir / f"{job_name}.inp").write_text(sample_content, encoding="utf-8")
                count_jobs += 1

    print(f"Da sinh thanh cong tong cong {count_jobs} file .inp (Hinh hoc Paper 1) vao '{output_path}'")


if __name__ == "__main__":
    excel_file = sys.argv[1] if len(sys.argv) > 1 else "thickness_table.xlsx"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "inputs"
    main(excel_file, out_dir)
