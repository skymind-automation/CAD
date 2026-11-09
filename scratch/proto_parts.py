
import sys
import time
from types import SimpleNamespace as NS

sys.path.insert(0, r"C:\Users\ICT\Untitled project\backend")
from delta3d import engine_parts as ep
from delta3d.cad import precise_mass_properties


def spec(**kwargs):
    return NS(parameters=NS(**kwargs))


crank = spec(
    cylinder_count=6, firing_order="153624", cylinder_spacing=150, stroke=130,
    main_journal_diameter=100, main_journal_length=44, pin_diameter=82, pin_length=46,
    web_thickness=30, web_pin_radius=60, web_main_radius=70, counterweight_radius=115,
    counterweight_angle=140, nose_diameter=70, nose_length=130, rear_seal_diameter=120,
    rear_seal_length=88, flange_diameter=160, flange_thickness=25,
)
piston = spec(
    diameter=125.8, compression_height=80, skirt_length=60, bowl_diameter=80, bowl_depth=18,
    top_land=16, ring_count=3, ring_pitch=7, ring_groove_width=3.5, ring_groove_depth=5,
    recess_1_x=-27, recess_1_y=-14, recess_1_diameter=56, recess_2_x=27, recess_2_y=-14,
    recess_2_diameter=50, recess_depth=1.5, pin_diameter=52, pin_clearance=0.05,
    slot_width=44, boss_wall=14, skirt_inner_diameter=112,
)
rod = spec(
    length=219, big_end_bore=87.1, small_end_bore=52.1, big_end_outer_radius=62,
    small_end_outer_radius=34, big_end_width=44, small_end_width=38, shank_width_big=56,
    shank_width_small=36, web_thickness=12, flange_thickness=8,
)
liner = spec(bore=126, outer_diameter=132, length=210, flange_diameter=144, flange_height=8)
cap = spec(width=36, half_width=110, height=75, bore=105, bolt_spacing=150, bolt_hole_diameter=18.5)
shell = spec(length_1=34, diameter_1=104.9, length_2=0, diameter_2=0, length_3=0, diameter_3=0, bore_diameter=100.1)
bolt = spec(diameter=18, length=185, head_across_flats=27, head_height=12)

densities = {"crank": 7850, "piston": 2700, "rod": 7850, "liner": 7200, "cap": 7200, "shell": 7850, "bolt": 7850}
for name, builder, item, check in (
    ("crank", ep._crankshaft, crank, None),
    ("piston", ep._piston, piston, None),
    ("rod", ep._connecting_rod, rod, None),
    ("liner", ep._cylinder_liner, liner, ep.liner_volume),
    ("cap", ep._bearing_cap, cap, ep.bearing_cap_volume),
    ("shell", ep._shaft, shell, ep.shaft_volume),
    ("bolt", ep._fastener, bolt, ep.fastener_volume),
):
    started = time.time()
    solid, features = builder(item)
    volume, centre = precise_mass_properties(solid)
    box = solid.BoundingBox()
    line = f"{name:7s} vol={volume:12.1f} mass={volume * 1e-9 * densities[name]:8.3f} kg  bbox=({box.xlen:.1f},{box.ylen:.1f},{box.zlen:.1f}) faces={len(solid.Faces())} t={time.time() - started:.1f}s"
    if check:
        expected = check(item.parameters)
        line += f"  closed-form rel.err={abs(volume - expected) / expected:.2e}"
    print(line)
print("sweep radius", ep.crankshaft_sweep_radius(crank.parameters))
print("phases", ep.throw_phases(6, "153624"))
bowl = ep.revolved_polygon_volume(ep.bowl_profile(piston.parameters), z_cap=80)
print("bowl volume (below crown)", bowl)
