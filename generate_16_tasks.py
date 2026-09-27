#!/usr/bin/env python3
"""
generate_16_tasks.py - Sinh 16 file FLUKA input cho bai toan Benchmark truyen qua khiên che chan (Deep Shielding Transport).
Moi task mo phong 1 do day khiên chi (Lead Shield) khac nhau tu 1 cm den 16 cm (hoac 16 cycle song song),
so hat lon (250,000 primaries) voi Random Seed khac nhau cho moi task.
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUTS_DIR = os.path.join(BASE_DIR, "inputs")
os.makedirs(INPUTS_DIR, exist_ok=True)

# Mau the FLUKA (Card standard format, 10 cot)
TEMPLATE_INP = """TITLE
FLUKA 16-Core Parallel Benchmark - Task {task_id:02d} (Shield {shield_thick:.1f} cm)
*...+....1....+....2....+....3....+....4....+....5....+....6....+....7....+....8
DEFAULTS                                                              PRECISIO
* Beam: 2.614 MeV Photon (tuong duong Tl-208 gamma line)
BEAM         -0.0026                                                  PHOTON
BEAMPOS          0.0       0.0     -10.0                              POSITIVE
* Random Seed doc lap cho moi may ao
RANDOMIZ         1.0  {seed:.1f}
*
GEOBEGIN                                                              COMBNAME
    0    0          Shielding Benchmark Geometry
* --- Bodies ---
* Nguon / Vung chieu
RPP beamBox    -15.0 15.0 -15.0 15.0 -12.0  -2.0
* Tam khiên chi voi do day thay doi: z tu 0.0 den {shield_thick:.1f} cm
RPP shield     -25.0 25.0 -25.0 25.0   0.0  {shield_thick:.1f}
* Vung dau do (Detector) dat ngay sau khiên: day 5 cm
RPP detBox     -10.0 10.0 -10.0 10.0 {det_z1:.1f} {det_z2:.1f}
* Vung khong khi va blackhole
RPP airBox     -60.0 60.0 -60.0 60.0 -30.0  60.0
RPP blkBox    -100.0 100.0 -100.0 100.0 -100.0 100.0
END
* --- Regions ---
TARGET       5 +beamBox
SHIELD       5 +shield
DETECTOR     5 +detBox
AIR          5 +airBox -beamBox -shield -detBox
BLACKHOLE    5 +blkBox -airBox
END
GEOEND
*
* --- Materials ---
ASSIGNMA      COPPER    TARGET
ASSIGNMA        LEAD    SHIELD
ASSIGNMA    GERMANIU  DETECTOR
ASSIGNMA         AIR       AIR
ASSIGNMA    BLCKHOLE BLACKHOLE
*
* --- Scoring: USRBIN tinh phan bo lieu nang luong (Dose / Edep) ---
* Scorer 1: USRBIN tren vung Detector (Z tu {det_z1:.1f} den {det_z2:.1f})
USRBIN          10.0    ENERGY     -40.0      10.0      10.0 {det_z2:.1f}DetDose
USRBIN         -10.0     -10.0 {det_z1:.1f}      10.0      10.0      10.0 &
*
* Scorer 2: USRTRACK do thong luong photon (Fluence) trong Detector
USRTRACK         1.0    PHOTON     -41.0  DETECTOR       0.0       1.0DetFlux
USRTRACK       0.003       0.0     100.0                                  &
*
* --- So luong hat: 250,000 hat (task nang, chay mat vai phut moi may ao) ---
START       {primaries:.1f}
STOP
"""

def generate_tasks(num_tasks=16, primaries=250000):
    print("=" * 68)
    print(f"  SINH {num_tasks} TASKS MO PHONG FLUKA BENCHMARK")
    print(f"  So hat moi task : {primaries:,} primaries")
    print("=" * 68)

    for i in range(1, num_tasks + 1):
        task_name = f"task_{i:02d}"
        task_dir = os.path.join(INPUTS_DIR, task_name)
        os.makedirs(task_dir, exist_ok=True)

        # Do day khiên tang dan tu 0.5 cm den 8.0 cm (khiên cang day tinh toan cang sau)
        shield_thick = 0.5 + (i - 1) * 0.5
        det_z1 = shield_thick + 1.0
        det_z2 = det_z1 + 5.0

        # Seed ngau nhien doc lap
        seed = 1000000.0 + i * 87654.0

        content = TEMPLATE_INP.format(
            task_id=i,
            shield_thick=shield_thick,
            det_z1=det_z1,
            det_z2=det_z2,
            seed=seed,
            primaries=float(primaries)
        )

        inp_path = os.path.join(task_dir, f"{task_name}.inp")
        with open(inp_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"  [Task {i:02d}] Shield: {shield_thick:4.1f} cm | Seed: {seed:.0f} -> {inp_path}")

    print("\n>>> Da sinh thanh cong 16 tasks trong thu muc inputs/!")

if __name__ == "__main__":
    generate_tasks(16, 250000)
