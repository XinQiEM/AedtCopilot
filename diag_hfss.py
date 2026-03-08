"""Diagnostic script for HFSS COM SetActiveEditor."""
import sys
import time
import win32com.client

sys.stdout.reconfigure(encoding='utf-8')

print("=== HFSS COM Diagnostic ===")

try:
    app = win32com.client.Dispatch('AnsoftHfss.HfssScriptInterface')
    print("[OK] COM connected")
except Exception as e:
    print(f"[FAIL] COM connect: {e}")
    sys.exit(1)

try:
    desktop = app.GetAppDesktop()
    print(f"[OK] Desktop version: {desktop.GetVersion()}")
except Exception as e:
    print(f"[FAIL] GetAppDesktop: {e}")
    sys.exit(1)

# List existing projects
try:
    projs = list(desktop.GetProjects())
    print(f"[INFO] Existing projects count: {len(projs)}")
except Exception as e:
    print(f"[WARN] GetProjects failed: {e}")
    projs = []

import os
SAVE_PATH = r"D:\Xin\GitCopilot\AedtCopilot\data\ValidationTest.aedt"

# Create new project and SAVE to disk before using
try:
    oProj = desktop.NewProject()
    print("[OK] NewProject created")
    # Save to disk immediately - this is required in HFSS 19.5 before project is usable
    import os
    save_path = SAVE_PATH
    if os.path.exists(save_path):
        os.remove(save_path)
    oProj.SaveAs(save_path, True)
    if os.path.exists(save_path):
        print(f"[OK] Project saved to {save_path} ({os.path.getsize(save_path)} bytes)")
except Exception as e:
    print(f"[FAIL] NewProject/SaveAs: {e}")
    # Try alternative: use Save instead of SaveAs
    try:
        oProj.Save(save_path)
        print(f"[OK] Project saved via Save()")
    except Exception as e2:
        print(f"[FAIL] Save: {e2}")

# Insert HFSS design
try:
    oProj.InsertDesign('HFSS', 'DiagDesign', 'DrivenModal', '')
    print("[OK] InsertDesign done")
    # In HFSS 19.5, need to explicitly set the active design
    oProj.SetActiveDesign('DiagDesign')
    time.sleep(0.5)
    oDesign = oProj.GetActiveDesign()
    if oDesign is None:
        print("[FAIL] GetActiveDesign returned None even after SetActiveDesign")
        sys.exit(1)
    print(f"[OK] Active design: {oDesign.GetName()}")
except Exception as e:
    print(f"[FAIL] InsertDesign/SetActiveDesign/GetActiveDesign: {e}")
    sys.exit(1)

# Try SetActiveEditor
try:
    editor = oDesign.SetActiveEditor('3D Modeler')
    print(f"[OK] SetActiveEditor: {type(editor).__name__}")
    # Check what we can DO with the editor first
    try:
        objs = list(editor.GetObjectsInGroup("Solids"))
        print(f"[OK] GetObjectsInGroup('Solids'): {objs}")
    except Exception as e:
        print(f"[FAIL] GetObjectsInGroup: {e}")

    # Test material value formats
    for label, attrs in [
        ("pec with quotes",    ["NAME:Attributes","Name:=","Box1","MaterialValue:=",'"pec"']),
        ("pec no quotes",      ["NAME:Attributes","Name:=","Box2","MaterialValue:=","pec"]),
        ("vacuum with quotes", ["NAME:Attributes","Name:=","Box3","MaterialValue:=",'"vacuum"']),
        ("vacuum no quotes",   ["NAME:Attributes","Name:=","Box4","MaterialValue:=","vacuum"]),
        ("no material",        ["NAME:Attributes","Name:=","Box5"]),
    ]:
        try:
            editor.CreateBox(
                ["NAME:BoxParameters","XPosition:=","0mm","YPosition:=","0mm",
                 "ZPosition:=","0mm","XSize:=","1mm","YSize:=","1mm","ZSize:=","1mm"],
                attrs
            )
            print(f"[OK] CreateBox ({label}) succeeded")
        except Exception as e:
            print(f"[FAIL] CreateBox ({label}): {e}")

    # Test AssignMaterial on Box5 (no-material box)
    try:
        editor.AssignMaterial(
            ["NAME:Selections","Selections:=","Box5"],
            ["NAME:Attributes","MaterialValue:=",'"pec"']
        )
        print("[OK] AssignMaterial (pec with quotes) succeeded")
    except Exception as e:
        print(f"[FAIL] AssignMaterial (pec with quotes): {e}")
        try:
            editor.AssignMaterial(
                ["NAME:Selections","Selections:=","Box5"],
                ["NAME:Attributes","MaterialValue:=","pec"]
            )
            print("[OK] AssignMaterial (pec no quotes) succeeded")
        except Exception as e2:
            print(f"[FAIL] AssignMaterial (pec no quotes): {e2}")

except Exception as e:
    print(f"[FAIL] SetActiveEditor('3D Modeler'): {e}")

    # Try alternate editor names
    for ed_name in ['3D Modeler', 'ModelerWindow', 'Modeler3D']:
        try:
            editor2 = oDesign.SetActiveEditor(ed_name)
            print(f"[OK] SetActiveEditor('{ed_name}'): {type(editor2).__name__}")
            break
        except Exception as e2:
            print(f"[FAIL] SetActiveEditor('{ed_name}'): {e2}")

# List available editors
try:
    eds = list(oDesign.GetEditors())
    print(f"[INFO] Available editors: {eds}")
except Exception as e:
    print(f"[WARN] GetEditors: {e}")

# Try GetModeler
try:
    mod = oDesign.GetModule("Modeler")
    print(f"[OK] GetModule('Modeler'): {type(mod).__name__}")
except Exception as e:
    print(f"[INFO] GetModule('Modeler'): {e}")

# Cleanup
try:
    oProj.Close()
    print("[OK] Project closed")
    # Remove temporary file
    import os
    if os.path.exists(SAVE_PATH):
        os.remove(SAVE_PATH)
        print("[OK] Temp file removed")
except Exception as e:
    print(f"[WARN] Close: {e}")

print("=== Diagnostic Complete ===")
