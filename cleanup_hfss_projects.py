"""Close all HFSS projects that were created by test/validation runs."""
import sys
import win32com.client

sys.stdout.reconfigure(encoding='utf-8')

print("=== Closing test HFSS projects ===")

try:
    app = win32com.client.Dispatch('AnsoftHfss.HfssScriptInterface')
    desktop = app.GetAppDesktop()
    print(f"Connected: HFSS {desktop.GetVersion()}")
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)

try:
    projs = list(desktop.GetProjects())
    print(f"Found {len(projs)} open projects")
except Exception as e:
    print(f"GetProjects failed: {e}")
    sys.exit(0)

for p in projs:
    try:
        name = p.GetName()
        print(f"  Closing: {name}")
        try:
            p.CloseNoSave()
        except Exception:
            p.Close()
        print(f"  Closed OK")
    except Exception as e:
        print(f"  Close error: {e}")

print("Cleanup done")
