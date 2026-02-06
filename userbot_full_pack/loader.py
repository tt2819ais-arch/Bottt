import os, importlib, traceback

MODULES_PATH="modules"

def load_all_modules(client):
    for f in os.listdir(MODULES_PATH):
        if f.endswith(".py") and not f.startswith("_"):
            name=f[:-3]
            try:
                m=importlib.import_module(f"{MODULES_PATH}.{name}")
                if hasattr(m,"on_load"):
                    client.loop.create_task(m.on_load(client))
                print("[MODULE] Loaded",name)
            except:
                print("[ERROR]",f)
                traceback.print_exc()
