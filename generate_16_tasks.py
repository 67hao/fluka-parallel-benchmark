#!/usr/bin/env python3
"""
generate_16_tasks.py - Sinh 16 file FLUKA input cho bai toan Benchmark theo chuẩn Fixed Format 80-cot của CERN FLUKA.
Moi the deu duoc kiem tra (assert len == 81 voi newline) de dam bao do dai 80 cot tuyet doi.
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUTS_DIR = os.path.join(BASE_DIR, "inputs")
os.makedirs(INPUTS_DIR, exist_ok=True)

def fmt_val(v):
    if v is None or v == "":
        return " " * 10
    if isinstance(v, (int, float)):
        s = f"{v:.4f}"
        if len(s) > 10:
            s = f"{v:.2f}"
        if len(s) > 10:
            s = f"{v:.1f}"
        if len(s) > 10:
            s = f"{v:.0f}."
        if len(s) > 10:
            s = f"{v:10.2e}"
        return f"{s:>10}"
    return f"{str(v):>10}"[:10]

def fluka_card(name, w1="", w2="", w3="", w4="", w5="", w6="", sdum=""):
    """Tao mot the FLUKA chuan 80 cot (10 cot x 8 truong)"""
    line = f"{name:<10}{fmt_val(w1)}{fmt_val(w2)}{fmt_val(w3)}{fmt_val(w4)}{fmt_val(w5)}{fmt_val(w6)}{fmt_val(sdum)}\n"
    assert len(line) == 81, f"Card length error: len={len(line)} for line: {repr(line)}"
    return line

def generate_tasks(num_tasks=16, primaries=250000):
    print("=" * 68)
    print(f"  SINH {num_tasks} TASKS FLUKA CHUAN FIXED FORMAT (EXACT 80-COLS)")
    print(f"  So hat moi task : {primaries:,} primaries")
    print("=" * 68)

    for i in range(1, num_tasks + 1):
        task_name = f"task_{i:02d}"
        task_dir = os.path.join(INPUTS_DIR, task_name)
        os.makedirs(task_dir, exist_ok=True)

        shield_thick = 0.5 + (i - 1) * 0.5
        det_z1 = shield_thick + 1.0
        det_z2 = det_z1 + 5.0
        seed = 1000000.0 + i * 87654.0

        lines = []
        lines.append("TITLE\n")
        lines.append(f"FLUKA 16-Task Benchmark - Task {i:02d} (Lead Shield {shield_thick:.1f} cm)\n")
        lines.append("*...+....1....+....2....+....3....+....4....+....5....+....6....+....7....+....8\n")
        lines.append(fluka_card("DEFAULTS", sdum="PRECISIO"))
        lines.append(fluka_card("BEAM", -0.0026, sdum="PHOTON"))
        lines.append(fluka_card("BEAMPOS", 0.0, 0.0, -10.0, sdum="POSITIVE"))
        lines.append(fluka_card("RANDOMIZ", 1.0, seed))
        
        # Geometry
        lines.append(fluka_card("GEOBEGIN", sdum="COMBNAME"))
        lines.append("    0    0          Shielding Benchmark Geometry\n")
        lines.append(f"RPP {'beamBox':<8}{'-15.0':>10}{'15.0':>10}{'-15.0':>10}{'15.0':>10}{'-12.0':>10}{'-2.0':>10}\n")
        lines.append(f"RPP {'shield':<8}{'-25.0':>10}{'25.0':>10}{'-25.0':>10}{'25.0':>10}{'0.0':>10}{shield_thick:>10.2f}\n")
        lines.append(f"RPP {'detBox':<8}{'-10.0':>10}{'10.0':>10}{'-10.0':>10}{'10.0':>10}{det_z1:>10.2f}{det_z2:>10.2f}\n")
        lines.append(f"RPP {'airBox':<8}{'-60.0':>10}{'60.0':>10}{'-60.0':>10}{'60.0':>10}{'-30.0':>10}{'60.0':>10}\n")
        lines.append(f"RPP {'blkBox':<8}{'-100.0':>10}{'100.0':>10}{'-100.0':>10}{'100.0':>10}{'-100.0':>10}{'100.0':>10}\n")
        lines.append("END\n")
        lines.append("TARGET   5 +beamBox\n")
        lines.append("SHIELD   5 +shield\n")
        lines.append("DETECTOR 5 +detBox\n")
        lines.append("AIR      5 +airBox -beamBox -shield -detBox\n")
        lines.append("BLKHOLE  5 +blkBox -airBox\n")
        lines.append("END\n")
        lines.append(fluka_card("GEOEND"))
        
        # Materials
        lines.append(fluka_card("ASSIGNMA", "COPPER", "TARGET"))
        lines.append(fluka_card("ASSIGNMA", "LEAD", "SHIELD"))
        lines.append(fluka_card("ASSIGNMA", "GERMANIU", "DETECTOR"))
        lines.append(fluka_card("ASSIGNMA", "AIR", "AIR"))
        lines.append(fluka_card("ASSIGNMA", "BLCKHOLE", "BLKHOLE"))
        
        # Scorer
        lines.append(fluka_card("USRTRACK", 1.0, "PHOTON", -41.0, "DETECTOR", 2000.0, 50.0, sdum="DetFlux"))
        lines.append(fluka_card("USRTRACK", 0.003, 0.0, sdum="&"))
        
        # Primaries
        lines.append(fluka_card("START", primaries))
        lines.append(fluka_card("STOP"))

        inp_path = os.path.join(task_dir, f"{task_name}.inp")
        with open(inp_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        print(f"  [Task {i:02d}] Shield: {shield_thick:4.1f} cm -> {inp_path}")

    print("\n>>> Da sinh xong 16 file FLUKA chuan fixed-format 80-cot!")

if __name__ == "__main__":
    generate_tasks(16, 250000)
