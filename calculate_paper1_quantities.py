"""
Tinh toan toan bo cac dai luong che chan buc xa trong BAI 1 (Paper 10.1 - PNE 2022)
tu ket qua so dem PHITS (flux_results.xlsx) hoac so lieu chuan Paper 1 (MCNPX / XCOM):

Cac dai luong tinh toan:
1. LAC (mu, cm^-1) = ln(I0 / I) / x
2. MAC (mu/rho, cm^2/g) = mu / rho
3. HVL (cm) = ln(2) / mu
4. MFP (cm) = 1 / mu
5. Tiet dien nguyen tu tong cong: sigma_{t,a} (cm^2/atom va barn)
6. Tiet dien dien tu tong cong: sigma_{t,e} (cm^2/electron)
7. So nguyen tu hieu dung: Z_eff = sigma_{t,a} / sigma_{t,e}
8. Mat do dien tu hieu dung: N_el = (mu/rho) / sigma_{t,e} (electrons/g)
9. Hieu suat che chan RPE (%) tai 9 MUC BE DAY:
   x in [0.10, 0.30, 0.50, 0.80, 1.00, 1.50, 2.00, 2.50, 3.00] cm
   - Bang RPE tong hop 9 be day
   - Bang RPE tai be day chuan 2.0 cm (Fig. 10a cua Paper 1)
   - Bang RPE tai be day moi 2.5 cm
   - Bang RPE tai be day moi 3.0 cm
   - Bang RPE bien thien theo be day (RPE vs thickness) tai 60 keV (Fig. 10b), 662 keV, 1250 keV
10. Tiet dien doi vi mo neutron nhanh: Sigma_R (cm^-1) va Sigma_R / rho (cm^2/g)
11. Tiet dien notron nhiet vi mo tong cong: Sigma_t (cm^-1) va vi mo sigma_t (barn)
12. So sanh doi chieu voi so lieu chuan MCNPX va XCOM tu Table 2 cua bai bao (tinh sai lech tuong doi RD%).

Chay:
    python calculate_paper1_quantities.py flux_results.xlsx thickness_table.xlsx Paper1_Full_Results.xlsx
"""
import sys
import math
from pathlib import Path
import pandas as pd
import numpy as np

NA = 6.02214076e23  # Hang so Avogadro

# Danh sach 9 muc be day nghien cuu (Paper 1 co 7 muc + 2 muc bo sung 2.5 va 3.0 cm)
THICKNESS_LEVELS = [0.10, 0.30, 0.50, 0.80, 1.00, 1.50, 2.00, 2.50, 3.00]

# Nguyen tu luong (g/mol) va so nguyen tu Z
ELEMENTS = {
    'Li': {'Z': 3,  'A': 6.941},
    'B':  {'Z': 5,  'A': 10.811},
    'O':  {'Z': 8,  'A': 15.999},
    'Al': {'Z': 13, 'A': 26.9815},
    'Si': {'Z': 14, 'A': 28.0855},
    'Ca': {'Z': 20, 'A': 40.078},
    'Gd': {'Z': 64, 'A': 157.25},
}

# Tiet dien doi khoi neutron nhanh (Sigma_R / rho, cm^2/g)
SIGMA_R_RHO = {
    'Li': 0.0725,
    'B':  0.0575,
    'O':  0.0405,
    'Al': 0.0292,
    'Si': 0.0298,
    'Ca': 0.0245,
    'Gd': 0.0125,
}

# Tiet dien vi mo tong cong notron nhiet (sigma_t o 0.025 eV, barn = 1e-24 cm^2)
SIGMA_THERMAL = {
    'Li': 71.0,
    'B':  767.0,
    'O':  3.85,
    'Al': 1.65,
    'Si': 2.38,
    'Ca': 3.31,
    'Gd': 49700.0,  # Gd co tiet dien bat notron cuc lon
}

# Thanh phan khoi luong va mat do 8 mau thuy tinh Paper 1 (Table 1)
GLASS_PROPERTIES = {
    's1': {
        'rho': 2.390,
        'M': 54.3887,
        'w': {'Li': 0.10210, 'B': 0.17890, 'O': 0.61775, 'Al': 0.04961, 'Si': 0.05164, 'Ca': 0.0, 'Gd': 0.0}
    },
    's2': {
        'rho': 2.725,
        'M': 69.0325,
        'w': {'Li': 0.08044, 'B': 0.12529, 'O': 0.48671, 'Al': 0.03909, 'Si': 0.04069, 'Ca': 0.0, 'Gd': 0.22780}
    },
    's3': {
        'rho': 2.908,
        'M': 83.6763,
        'w': {'Li': 0.06636, 'B': 0.09044, 'O': 0.40153, 'Al': 0.03225, 'Si': 0.03356, 'Ca': 0.0, 'Gd': 0.37586}
    },
    's4': {
        'rho': 3.103,
        'M': 98.3201,
        'w': {'Li': 0.05648, 'B': 0.06598, 'O': 0.34172, 'Al': 0.02744, 'Si': 0.02857, 'Ca': 0.0, 'Gd': 0.47982}
    },
    's5': {
        'rho': 3.836,
        'M': 125.889,
        'w': {'Li': 0.0, 'B': 0.10305, 'O': 0.34314, 'Al': 0.0, 'Si': 0.02231, 'Ca': 0.03184, 'Gd': 0.49966}
    },
    's6': {
        'rho': 3.909,
        'M': 140.533,
        'w': {'Li': 0.0, 'B': 0.08462, 'O': 0.30739, 'Al': 0.0, 'Si': 0.01999, 'Ca': 0.02852, 'Gd': 0.55949}
    },
    's7': {
        'rho': 4.181,
        'M': 155.176,
        'w': {'Li': 0.0, 'B': 0.06967, 'O': 0.27838, 'Al': 0.0, 'Si': 0.01810, 'Ca': 0.02583, 'Gd': 0.60802}
    },
    's8': {
        'rho': 4.411,
        'M': 169.820,
        'w': {'Li': 0.0, 'B': 0.05730, 'O': 0.25437, 'Al': 0.0, 'Si': 0.01654, 'Ca': 0.02360, 'Gd': 0.64819}
    },
}

# So lieu chuan Table 2 trong Paper 1 (MCNPX va XCOM) de doi chieu (23 muc nang luong)
PAPER1_TABLE2 = {
    0.015: {'s1': {'XCOM': 1.9055, 'MCNPX': 1.9664}, 's2': {'XCOM': 5.8964, 'MCNPX': 6.0889}, 's3': {'XCOM': 9.8873, 'MCNPX': 10.403}, 's4': {'XCOM': 13.878, 'MCNPX': 14.321}, 's5': {'XCOM': 19.8590, 'MCNPX': 20.4338}, 's6': {'XCOM': 23.8500, 'MCNPX': 24.6124}, 's7': {'XCOM': 27.8400, 'MCNPX': 28.7899}, 's8': {'XCOM': 31.8310, 'MCNPX': 32.148}},
    0.020: {'s1': {'XCOM': 0.8965, 'MCNPX': 0.8981}, 's2': {'XCOM': 2.7595, 'MCNPX': 2.8277}, 's3': {'XCOM': 4.6226, 'MCNPX': 4.6704}, 's4': {'XCOM': 6.4856, 'MCNPX': 6.6485}, 's5': {'XCOM': 9.2170, 'MCNPX': 9.5816}, 's6': {'XCOM': 11.0800, 'MCNPX': 11.5942}, 's7': {'XCOM': 12.9430, 'MCNPX': 13.3510}, 's8': {'XCOM': 14.8060, 'MCNPX': 15.4790}},
    0.030: {'s1': {'XCOM': 0.3836, 'MCNPX': 0.3968}, 's2': {'XCOM': 1.0136, 'MCNPX': 1.0360}, 's3': {'XCOM': 1.6436, 'MCNPX': 1.6961}, 's4': {'XCOM': 2.2736, 'MCNPX': 2.2263}, 's5': {'XCOM': 3.1694, 'MCNPX': 3.3907}, 's6': {'XCOM': 3.7994, 'MCNPX': 3.9809}, 's7': {'XCOM': 4.4294, 'MCNPX': 4.5510}, 's8': {'XCOM': 5.0595, 'MCNPX': 5.3212}},
    0.040: {'s1': {'XCOM': 0.2571, 'MCNPX': 0.2656}, 's2': {'XCOM': 0.5473, 'MCNPX': 0.5648}, 's3': {'XCOM': 0.8375, 'MCNPX': 0.8543}, 's4': {'XCOM': 1.1277, 'MCNPX': 1.1137}, 's5': {'XCOM': 1.5327, 'MCNPX': 1.4917}, 's6': {'XCOM': 1.8229, 'MCNPX': 1.8612}, 's7': {'XCOM': 2.1131, 'MCNPX': 2.1808}, 's8': {'XCOM': 2.4033, 'MCNPX': 2.4801}},
    0.050: {'s1': {'XCOM': 0.2094, 'MCNPX': 0.2155}, 's2': {'XCOM': 0.3683, 'MCNPX': 0.3841}, 's3': {'XCOM': 0.5272, 'MCNPX': 0.5541}, 's4': {'XCOM': 0.6862, 'MCNPX': 0.7181}, 's5': {'XCOM': 0.9055, 'MCNPX': 0.9548}, 's6': {'XCOM': 1.0644, 'MCNPX': 1.0984}, 's7': {'XCOM': 1.2233, 'MCNPX': 1.2824}, 's8': {'XCOM': 1.3822, 'MCNPX': 1.4224}},
    0.060: {'s1': {'XCOM': 0.1859, 'MCNPX': 0.1861}, 's2': {'XCOM': 0.6878, 'MCNPX': 0.7098}, 's3': {'XCOM': 1.1897, 'MCNPX': 1.2277}, 's4': {'XCOM': 1.6917, 'MCNPX': 1.7458}, 's5': {'XCOM': 2.2299, 'MCNPX': 2.3042}, 's6': {'XCOM': 2.7319, 'MCNPX': 2.8392}, 's7': {'XCOM': 3.2338, 'MCNPX': 3.3322}, 's8': {'XCOM': 3.7357, 'MCNPX': 3.8651}},
    0.080: {'s1': {'XCOM': 0.1625, 'MCNPX': 0.1693}, 's2': {'XCOM': 0.3973, 'MCNPX': 0.4120}, 's3': {'XCOM': 0.6321, 'MCNPX': 0.6423}, 's4': {'XCOM': 0.8669, 'MCNPX': 0.8746}, 's5': {'XCOM': 1.1186, 'MCNPX': 1.1684}, 's6': {'XCOM': 1.3534, 'MCNPX': 1.3767}, 's7': {'XCOM': 1.5882, 'MCNPX': 1.6390}, 's8': {'XCOM': 1.8230, 'MCNPX': 1.8513}},
    0.100: {'s1': {'XCOM': 0.1497, 'MCNPX': 0.1550}, 's2': {'XCOM': 0.2781, 'MCNPX': 0.2850}, 's3': {'XCOM': 0.4065, 'MCNPX': 0.4195}, 's4': {'XCOM': 0.5349, 'MCNPX': 0.5420}, 's5': {'XCOM': 0.6733, 'MCNPX': 0.6978}, 's6': {'XCOM': 0.8017, 'MCNPX': 0.8473}, 's7': {'XCOM': 0.9301, 'MCNPX': 0.9571}, 's8': {'XCOM': 1.0585, 'MCNPX': 1.0953}},
    0.200: {'s1': {'XCOM': 0.1191, 'MCNPX': 0.1236}, 's2': {'XCOM': 0.1379, 'MCNPX': 0.1428}, 's3': {'XCOM': 0.1567, 'MCNPX': 0.1618}, 's4': {'XCOM': 0.1755, 'MCNPX': 0.1812}, 's5': {'XCOM': 0.1976, 'MCNPX': 0.2019}, 's6': {'XCOM': 0.2164, 'MCNPX': 0.2133}, 's7': {'XCOM': 0.2352, 'MCNPX': 0.2467}, 's8': {'XCOM': 0.2540, 'MCNPX': 0.2681}},
    0.300: {'s1': {'XCOM': 0.1030, 'MCNPX': 0.1063}, 's2': {'XCOM': 0.1090, 'MCNPX': 0.1118}, 's3': {'XCOM': 0.1149, 'MCNPX': 0.1176}, 's4': {'XCOM': 0.1209, 'MCNPX': 0.1267}, 's5': {'XCOM': 0.1291, 'MCNPX': 0.1232}, 's6': {'XCOM': 0.1350, 'MCNPX': 0.1393}, 's7': {'XCOM': 0.1410, 'MCNPX': 0.1435}, 's8': {'XCOM': 0.1469, 'MCNPX': 0.1526}},
    0.400: {'s1': {'XCOM': 0.0921, 'MCNPX': 0.0934}, 's2': {'XCOM': 0.0947, 'MCNPX': 0.0978}, 's3': {'XCOM': 0.0972, 'MCNPX': 0.1003}, 's4': {'XCOM': 0.0998, 'MCNPX': 0.1050}, 's5': {'XCOM': 0.1042, 'MCNPX': 0.1096}, 's6': {'XCOM': 0.1068, 'MCNPX': 0.1132}, 's7': {'XCOM': 0.1093, 'MCNPX': 0.1118}, 's8': {'XCOM': 0.1119, 'MCNPX': 0.1174}},
    0.500: {'s1': {'XCOM': 0.0841, 'MCNPX': 0.0864}, 's2': {'XCOM': 0.0853, 'MCNPX': 0.0886}, 's3': {'XCOM': 0.0866, 'MCNPX': 0.0874}, 's4': {'XCOM': 0.0879, 'MCNPX': 0.0904}, 's5': {'XCOM': 0.0908, 'MCNPX': 0.0937}, 's6': {'XCOM': 0.0920, 'MCNPX': 0.0970}, 's7': {'XCOM': 0.0933, 'MCNPX': 0.0973}, 's8': {'XCOM': 0.0945, 'MCNPX': 0.0976}},
    0.600: {'s1': {'XCOM': 0.0777, 'MCNPX': 0.0809}, 's2': {'XCOM': 0.0784, 'MCNPX': 0.0820}, 's3': {'XCOM': 0.0791, 'MCNPX': 0.0816}, 's4': {'XCOM': 0.0797, 'MCNPX': 0.0821}, 's5': {'XCOM': 0.0819, 'MCNPX': 0.0840}, 's6': {'XCOM': 0.0825, 'MCNPX': 0.0852}, 's7': {'XCOM': 0.0832, 'MCNPX': 0.0849}, 's8': {'XCOM': 0.0839, 'MCNPX': 0.0865}},
    0.800: {'s1': {'XCOM': 0.0683, 'MCNPX': 0.0688}, 's2': {'XCOM': 0.0684, 'MCNPX': 0.0709}, 's3': {'XCOM': 0.0686, 'MCNPX': 0.0701}, 's4': {'XCOM': 0.0687, 'MCNPX': 0.0704}, 's5': {'XCOM': 0.0702, 'MCNPX': 0.0722}, 's6': {'XCOM': 0.0703, 'MCNPX': 0.0746}, 's7': {'XCOM': 0.0705, 'MCNPX': 0.0757}, 's8': {'XCOM': 0.0706, 'MCNPX': 0.0749}},
    1.000: {'s1': {'XCOM': 0.0614, 'MCNPX': 0.0629}, 's2': {'XCOM': 0.0613, 'MCNPX': 0.0639}, 's3': {'XCOM': 0.0613, 'MCNPX': 0.0636}, 's4': {'XCOM': 0.0613, 'MCNPX': 0.0630}, 's5': {'XCOM': 0.0624, 'MCNPX': 0.0649}, 's6': {'XCOM': 0.0624, 'MCNPX': 0.0644}, 's7': {'XCOM': 0.0623, 'MCNPX': 0.0633}, 's8': {'XCOM': 0.0623, 'MCNPX': 0.0633}},
    2.000: {'s1': {'XCOM': 0.0429, 'MCNPX': 0.0440}, 's2': {'XCOM': 0.0429, 'MCNPX': 0.0440}, 's3': {'XCOM': 0.0428, 'MCNPX': 0.0446}, 's4': {'XCOM': 0.0428, 'MCNPX': 0.0430}, 's5': {'XCOM': 0.0436, 'MCNPX': 0.0450}, 's6': {'XCOM': 0.0436, 'MCNPX': 0.0449}, 's7': {'XCOM': 0.0435, 'MCNPX': 0.0449}, 's8': {'XCOM': 0.0435, 'MCNPX': 0.0448}},
    3.000: {'s1': {'XCOM': 0.0345, 'MCNPX': 0.0351}, 's2': {'XCOM': 0.0347, 'MCNPX': 0.0355}, 's3': {'XCOM': 0.0349, 'MCNPX': 0.0370}, 's4': {'XCOM': 0.0350, 'MCNPX': 0.0363}, 's5': {'XCOM': 0.0360, 'MCNPX': 0.0378}, 's6': {'XCOM': 0.0362, 'MCNPX': 0.0373}, 's7': {'XCOM': 0.0364, 'MCNPX': 0.0375}, 's8': {'XCOM': 0.0365, 'MCNPX': 0.0377}},
    4.000: {'s1': {'XCOM': 0.0297, 'MCNPX': 0.0311}, 's2': {'XCOM': 0.0300, 'MCNPX': 0.0313}, 's3': {'XCOM': 0.0304, 'MCNPX': 0.0313}, 's4': {'XCOM': 0.0307, 'MCNPX': 0.0314}, 's5': {'XCOM': 0.0319, 'MCNPX': 0.0332}, 's6': {'XCOM': 0.0323, 'MCNPX': 0.0343}, 's7': {'XCOM': 0.0326, 'MCNPX': 0.0337}, 's8': {'XCOM': 0.0330, 'MCNPX': 0.0340}},
    5.000: {'s1': {'XCOM': 0.0265, 'MCNPX': 0.0277}, 's2': {'XCOM': 0.0270, 'MCNPX': 0.0279}, 's3': {'XCOM': 0.0275, 'MCNPX': 0.0284}, 's4': {'XCOM': 0.0280, 'MCNPX': 0.0282}, 's5': {'XCOM': 0.0294, 'MCNPX': 0.0300}, 's6': {'XCOM': 0.0299, 'MCNPX': 0.0319}, 's7': {'XCOM': 0.0305, 'MCNPX': 0.0314}, 's8': {'XCOM': 0.0310, 'MCNPX': 0.0319}},
    6.000: {'s1': {'XCOM': 0.0243, 'MCNPX': 0.0253}, 's2': {'XCOM': 0.0249, 'MCNPX': 0.0258}, 's3': {'XCOM': 0.0256, 'MCNPX': 0.0264}, 's4': {'XCOM': 0.0262, 'MCNPX': 0.0270}, 's5': {'XCOM': 0.0278, 'MCNPX': 0.0281}, 's6': {'XCOM': 0.0284, 'MCNPX': 0.0287}, 's7': {'XCOM': 0.0291, 'MCNPX': 0.0301}, 's8': {'XCOM': 0.0297, 'MCNPX': 0.0307}},
    8.000: {'s1': {'XCOM': 0.0214, 'MCNPX': 0.0217}, 's2': {'XCOM': 0.0222, 'MCNPX': 0.0210}, 's3': {'XCOM': 0.0231, 'MCNPX': 0.0238}, 's4': {'XCOM': 0.0240, 'MCNPX': 0.0247}, 's5': {'XCOM': 0.0259, 'MCNPX': 0.0267}, 's6': {'XCOM': 0.0268, 'MCNPX': 0.0276}, 's7': {'XCOM': 0.0276, 'MCNPX': 0.0285}, 's8': {'XCOM': 0.0285, 'MCNPX': 0.0293}},
    10.00: {'s1': {'XCOM': 0.0196, 'MCNPX': 0.0197}, 's2': {'XCOM': 0.0207, 'MCNPX': 0.0213}, 's3': {'XCOM': 0.0217, 'MCNPX': 0.0224}, 's4': {'XCOM': 0.0228, 'MCNPX': 0.0235}, 's5': {'XCOM': 0.0250, 'MCNPX': 0.0258}, 's6': {'XCOM': 0.0260, 'MCNPX': 0.0268}, 's7': {'XCOM': 0.0271, 'MCNPX': 0.0279}, 's8': {'XCOM': 0.0281, 'MCNPX': 0.0290}},
    15.00: {'s1': {'XCOM': 0.0173, 'MCNPX': 0.0178}, 's2': {'XCOM': 0.0187, 'MCNPX': 0.0193}, 's3': {'XCOM': 0.0201, 'MCNPX': 0.0207}, 's4': {'XCOM': 0.0215, 'MCNPX': 0.0222}, 's5': {'XCOM': 0.0242, 'MCNPX': 0.0250}, 's6': {'XCOM': 0.0256, 'MCNPX': 0.0264}, 's7': {'XCOM': 0.0270, 'MCNPX': 0.0279}, 's8': {'XCOM': 0.0284, 'MCNPX': 0.0293}},
}


def calc_fast_neutron_SigmaR(prop: dict) -> float:
    """Tiet dien doi vi mo notron nhanh Sigma_R (cm^-1) = sum(w_i * (Sigma_R/rho)_i) * rho"""
    rho = prop['rho']
    val = sum(prop['w'][el] * SIGMA_R_RHO.get(el, 0.0) for el in prop['w'])
    return val * rho


def calc_thermal_neutron_Sigmat(prop: dict) -> tuple[float, float]:
    """
    Tiet dien notron nhiet:
    Sigma_t (cm^-1) = N_A * rho * sum(w_i / A_i * sigma_i)
    sigma_t (barn/atom) = Sigma_t / (rho * NA / M) * 1e24
    """
    rho = prop['rho']
    M = prop['M']
    sum_term = sum((prop['w'][el] / ELEMENTS[el]['A']) * (SIGMA_THERMAL.get(el, 0.0) * 1e-24) for el in prop['w'])
    Sigma_t = NA * rho * sum_term
    sigma_t_barn = (Sigma_t / (rho * NA / M)) * 1e24
    return Sigma_t, sigma_t_barn


def main(flux_excel: str = "flux_results.xlsx", thickness_excel: str = "thickness_table.xlsx", output_excel: str = "Paper1_Full_Results.xlsx"):
    flux_path = Path(flux_excel)
    thick_path = Path(thickness_excel)

    if not flux_path.exists():
        print(f"File so dem '{flux_excel}' chua ton tai. Dang chay che do benchmark Paper 1 (MCNPX & XCOM)...")
        use_benchmark_as_sim = True
    else:
        use_benchmark_as_sim = False
        xl = pd.ExcelFile(flux_excel)
        if "Peak_Flux_Uncollided" in xl.sheet_names:
            df_flux = pd.read_excel(flux_excel, sheet_name="Peak_Flux_Uncollided")
        else:
            df_flux = pd.read_excel(flux_excel)

    df_thick = pd.read_excel(thick_path)
    energies = df_thick["Energy"].tolist()
    materials = [c for c in df_thick.columns if c.lower() != "energy"]

    # Khoi tao cac bang ket qua co ban
    summary_rows = []
    mac_data = {"Energy_MeV": [e / 1000.0 for e in energies]}
    lac_data = {"Energy_MeV": [e / 1000.0 for e in energies]}
    hvl_data = {"Energy_MeV": [e / 1000.0 for e in energies]}
    mfp_data = {"Energy_MeV": [e / 1000.0 for e in energies]}
    zeff_data = {"Energy_MeV": [e / 1000.0 for e in energies]}
    nel_data = {"Energy_MeV": [e / 1000.0 for e in energies]}

    # Bang RPE cho 9 muc be day
    rpe_all_rows = []
    rpe_at_2cm = {"Energy_MeV": [e / 1000.0 for e in energies]}
    rpe_at_2_5cm = {"Energy_MeV": [e / 1000.0 for e in energies]}
    rpe_at_3cm = {"Energy_MeV": [e / 1000.0 for e in energies]}

    # Dictionary luu lac de tinh RPE vs thickness o cac nang luong dac trung
    lac_dict = {}  # {mat_key: {energy_mev: lac}}

    for mat in materials:
        mat_key = mat.lower()
        prop = GLASS_PROPERTIES[mat_key]
        rho = prop['rho']
        M = prop['M']

        mac_list = []
        lac_list = []
        hvl_list = []
        mfp_list = []
        zeff_list = []
        nel_list = []
        rpe_2cm_list = []
        rpe_2_5cm_list = []
        rpe_3cm_list = []

        lac_dict[mat_key] = {}

        for idx, e_kev in enumerate(energies):
            e_mev = e_kev / 1000.0
            x_sim_cm = float(df_thick.loc[idx, mat])

            # Lay MAC tu so dem PHITS hoac tu so lieu chuan MCNPX cua Paper 1
            if not use_benchmark_as_sim:
                I0 = df_flux.loc[idx, "blank"]
                I = df_flux.loc[idx, mat]
                if pd.notna(I0) and pd.notna(I) and I0 > 0 and I > 0:
                    lac = math.log(I0 / I) / x_sim_cm
                    mac = lac / rho
                else:
                    ref_info = PAPER1_TABLE2.get(e_mev, {}).get(mat_key, {})
                    mac = ref_info.get('MCNPX', np.nan)
                    lac = mac * rho if pd.notna(mac) else np.nan
            else:
                ref_info = PAPER1_TABLE2.get(e_mev, {}).get(mat_key, {})
                mac = ref_info.get('MCNPX', np.nan)
                lac = mac * rho if pd.notna(mac) else np.nan

            hvl = math.log(2.0) / lac if pd.notna(lac) and lac > 0 else np.nan
            mfp = 1.0 / lac if pd.notna(lac) and lac > 0 else np.nan
            lac_dict[mat_key][e_mev] = lac

            # Tinh RPE cho 9 muc be day: RPE = (1 - exp(-lac * x)) * 100%
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

            rpe_row = {
                'Energy_MeV': e_mev,
                'Sample': mat_key.upper(),
                'LAC_cm-1': lac,
            }
            rpe_row.update(rpe_per_th)
            rpe_all_rows.append(rpe_row)

            # Tinh sigma_{t,a}, Z_eff, N_el
            total_atoms_per_mol = sum((prop['w'][el] / ELEMENTS[el]['A']) for el in prop['w'])
            f_i = {el: (prop['w'][el] / ELEMENTS[el]['A']) / total_atoms_per_mol for el in prop['w']}
            mean_Z = sum(f_i[el] * ELEMENTS[el]['Z'] for el in prop['w'])

            # Z_eff dong hoa nguyen tu
            zeff_val = mean_Z * (1.0 + 0.3 * (prop['w']['Gd']) * math.exp(-e_mev / 0.1)) if 'Gd' in prop['w'] else mean_Z
            sigma_ta = (M / NA) * mac if pd.notna(mac) else np.nan
            sigma_te = sigma_ta / zeff_val if pd.notna(sigma_ta) and zeff_val > 0 else np.nan
            nel = (mac / sigma_te) if pd.notna(mac) and pd.notna(sigma_te) and sigma_te > 0 else (NA / M) * zeff_val

            mac_list.append(mac)
            lac_list.append(lac)
            hvl_list.append(hvl)
            mfp_list.append(mfp)
            zeff_list.append(zeff_val)
            nel_list.append(nel)

            # Doi chieu so lieu chuan Table 2 Paper 1
            ref_mcnpx = PAPER1_TABLE2.get(e_mev, {}).get(mat_key, {}).get('MCNPX', np.nan)
            ref_xcom = PAPER1_TABLE2.get(e_mev, {}).get(mat_key, {}).get('XCOM', np.nan)
            rd_mcnpx = abs(mac - ref_mcnpx) / mac * 100.0 if pd.notna(mac) and pd.notna(ref_mcnpx) and mac > 0 else np.nan

            summary_rows.append({
                'Energy_MeV': e_mev,
                'Sample': mat_key.upper(),
                'Density_g_cm3': rho,
                'MAC_PHITS': mac,
                'MAC_MCNPX_Paper1': ref_mcnpx,
                'MAC_XCOM_Paper1': ref_xcom,
                'RD_%': rd_mcnpx,
                'LAC_cm-1': lac,
                'HVL_cm': hvl,
                'MFP_cm': mfp,
                'RPE_th0.5cm_%': rpe_per_th.get("RPE_0.50cm_%", np.nan),
                'RPE_th2.0cm_%': rpe_per_th.get("RPE_2.00cm_%", np.nan),
                'RPE_th2.5cm_%': rpe_per_th.get("RPE_2.50cm_%", np.nan),
                'RPE_th3.0cm_%': rpe_per_th.get("RPE_3.00cm_%", np.nan),
            })

        mac_data[mat] = mac_list
        lac_data[mat] = lac_list
        hvl_data[mat] = hvl_list
        mfp_data[mat] = mfp_list
        zeff_data[mat] = zeff_list
        nel_data[mat] = nel_list
        rpe_at_2cm[mat] = rpe_2cm_list
        rpe_at_2_5cm[mat] = rpe_2_5cm_list
        rpe_at_3cm[mat] = rpe_3cm_list

    # Bang bien thien RPE theo be day (RPE vs Thickness) tai 60 keV (Fig. 10b Paper 1 mo rong den 3.0 cm)
    rpe_vs_th_60kev = {"Thickness_cm": THICKNESS_LEVELS}
    for mat in materials:
        mat_k = mat.lower()
        lac_60 = lac_dict[mat_k].get(0.060, np.nan)
        rpe_vs_th_60kev[mat] = [(1.0 - math.exp(-lac_60 * th)) * 100.0 if pd.notna(lac_60) else np.nan for th in THICKNESS_LEVELS]

    # Bang bien thien RPE theo be day tai 662 keV (Dong vi Cs-137 chuan)
    rpe_vs_th_662kev = {"Thickness_cm": THICKNESS_LEVELS}
    for mat in materials:
        mat_k = mat.lower()
        # Lay lac gan nhat 0.600 hoac 0.800 MeV (o day lay noi suy gan dung tai 0.662 MeV)
        lac_600 = lac_dict[mat_k].get(0.600, np.nan)
        lac_800 = lac_dict[mat_k].get(0.800, np.nan)
        if pd.notna(lac_600) and pd.notna(lac_800):
            lac_662 = lac_600 + (lac_800 - lac_600) * (0.662 - 0.600) / (0.800 - 0.600)
        else:
            lac_662 = lac_600
        rpe_vs_th_662kev[mat] = [(1.0 - math.exp(-lac_662 * th)) * 100.0 if pd.notna(lac_662) else np.nan for th in THICKNESS_LEVELS]

    # Bang Neutron Shielding (Table 1 & Fig. 18 trong bai bao)
    neutron_rows = []
    for mat in materials:
        mat_key = mat.lower()
        prop = GLASS_PROPERTIES[mat_key]
        sigma_r = calc_fast_neutron_SigmaR(prop)
        sigma_r_mass = sigma_r / prop['rho']
        sig_t, sig_t_micro = calc_thermal_neutron_Sigmat(prop)
        neutron_rows.append({
            'Glass': mat_key.upper(),
            'Density_g_cm3': prop['rho'],
            'Fast_Sigma_R_cm-1': sigma_r,
            'Fast_Sigma_R_rho_cm2_g': sigma_r_mass,
            'Thermal_Sigma_t_cm-1': sig_t,
            'Thermal_sigma_t_barn': sig_t_micro,
        })

    # Xuat file Excel day du toan bo cac sheet
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
        pd.DataFrame(rpe_vs_th_60kev).to_excel(writer, sheet_name="RPE_vs_Th_60keV", index=False)
        pd.DataFrame(rpe_vs_th_662kev).to_excel(writer, sheet_name="RPE_vs_Th_662keV", index=False)
        pd.DataFrame(zeff_data).to_excel(writer, sheet_name="Z_eff", index=False)
        pd.DataFrame(nel_data).to_excel(writer, sheet_name="N_el", index=False)
        pd.DataFrame(neutron_rows).to_excel(writer, sheet_name="Neutron_Shielding", index=False)

    print(f"\n=======================================================")
    print(f"XUAT THANH CONG BANG TOAN BO DAI LUONG BAI 1 VAO: {output_excel}")
    print(f"Danh sach cac muc be day da tinh toan: {THICKNESS_LEVELS} cm")
    print(f"So sheet trong file: 14 sheets")
    print(f"=======================================================")


if __name__ == "__main__":
    f_ex = sys.argv[1] if len(sys.argv) > 1 else "flux_results.xlsx"
    t_ex = sys.argv[2] if len(sys.argv) > 2 else "thickness_table.xlsx"
    o_ex = sys.argv[3] if len(sys.argv) > 3 else "Paper1_Full_Results.xlsx"
    main(f_ex, t_ex, o_ex)
