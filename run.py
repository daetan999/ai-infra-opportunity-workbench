import app as myapp

print("✅ Imported app from:", myapp.__file__)
print("✅ Routes in this app:")
for r in myapp.app.routes:
    print(" -", getattr(r, "path", r))

import uvicorn
uvicorn.run(myapp.app, host="127.0.0.1", port=8000, log_level="debug")
