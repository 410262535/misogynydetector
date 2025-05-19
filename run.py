print("✅ 啟動 run.py")
import os
from app import create_app

application = create_app()
print("✅ create_app() 完成")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    print(f"✅ Flask app 啟動中，PORT={port}")
    application.run(host="0.0.0.0", port=port)
