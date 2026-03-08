"""Fix ensure_project() body to use _get_desktop()."""

with open('backend/hfss/com_client.py', 'r', encoding='utf-8') as f:
    src = f.read()

# Find and replace the old ensure_project body
import re

old_body = '''        # Check if there's already an active project with a design
        try:
            proj = self.oDesktop.GetActiveProject()
            if proj is not None:
                design = proj.GetActiveDesign()
                if design is not None:
                    return  # Already have a project with active design
        except Exception:
            pass

        # Create new project
        oProj = self.oDesktop.NewProject()

        # Save to disk first (HFSS 19.5 requires this before design operations)
        if save_path is None:
            data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
            os.makedirs(data_dir, exist_ok=True)
            save_path = os.path.join(data_dir, "HfssSession.aedt")
        # Remove old file if exists
        if os.path.exists(save_path):
            try:
                os.remove(save_path)
            except Exception:
                pass
        oProj.SaveAs(save_path, True)

        # Insert HFSS DrivenModal design
        oProj.InsertDesign("HFSS", design_name, "DrivenModal", "")

        # Explicitly set the new design as active
        oProj.SetActiveDesign(design_name)'''

new_body = '''        desktop = self._get_desktop()
        self._ensure_project_with(desktop, save_path=save_path, design_name=design_name)'''

if old_body in src:
    src = src.replace(old_body, new_body)
    print('Replaced ensure_project body OK')
else:
    print('ERROR: pattern not found, checking line by line...')
    for i, line in enumerate(old_body.splitlines()):
        if line not in src:
            print(f'  Missing line {i}: {repr(line)}')

import ast
try:
    ast.parse(src)
    print('Syntax OK')
except SyntaxError as e:
    print('Syntax ERROR:', e)

n_odesktop = src.count('self.oDesktop.')
print(f'Remaining self.oDesktop. references (excluding assignment): {n_odesktop}')

with open('backend/hfss/com_client.py', 'w', encoding='utf-8') as f:
    f.write(src)
print('Saved.')
